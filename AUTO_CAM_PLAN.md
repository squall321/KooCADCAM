# AutoCAM 고도화 계획서

## 현황 진단: 지금 AutoCAM이 못 하는 것

현재 `auto_cam.py`는 **바운딩 박스 기반 근사**로 동작한다.
실제 형상의 BREP 면/엣지를 추종하지 않아 아래 형상에서 실패한다:

| 형상 유형 | 현재 결과 | 원인 |
|-----------|-----------|------|
| 자유곡면 (dome, loft) | 스캔라인이 형상과 무관한 평면 격자 | 드롭커터(drop-cutter) 없음 |
| 복잡한 포켓 (아일랜드 포함) | 아일랜드 무시, 과삭 | BREP 면 분석 없음 |
| 언더컷 | 미삭 (아무 경고 없음) | 언더컷 감지 없음 |
| 다중 깊이 포켓 | 단일 깊이로 처리 | 계층 분석 없음 |
| 좁은 슬롯/리브 | 공구가 맞지 않는 공구로 시도 | 최소 통과 폭 계산 없음 |
| 필렛 정삭 | 볼엔드밀이 형상과 무관한 경로 이동 | 오프셋 곡면 계산 없음 |

---

## 목표: "형상 추종" AutoCAM

```
입력: 임의의 CadQuery 솔리드
출력: 해당 형상을 실제로 가공할 수 있는 G-code

핵심 원칙:
  공구 경로 = f(BREP 형상, 공구 지오메트리, 소재 조건)
```

---

## 개선 단계

### Step 1. BREP 피처 인식 강화 (즉시 구현 가능)

**목표**: 현재 `_recognize_features()`가 바운딩 박스만 보는 것을 BREP 면/엣지 분석으로 교체

**구현 내용** (`src/cam/feature_recognition.py` 신규):

```
BrepAnalyzer
├── analyze_faces()
│   ├── 평면 (PLANE): 수직/수평 구분 → 페이싱 vs 프로파일
│   ├── 원통면 (CYLINDER): 반경 추출 → 드릴/보링/포켓
│   ├── 구면 (SPHERE): 반경 추출 → 3D 스캔라인
│   ├── 원환면 (TORUS): 필렛 반경 → 볼엔드밀 경로
│   └── B-Spline/NURBS: 자유곡면 표시 → OCL drop-cutter
│
├── analyze_edges()
│   ├── 원호 엣지: 필렛/챔퍼 반경 측정
│   ├── 직선 엣지: 방향 분석 (수직/수평/경사)
│   └── 엣지 연결성: 포켓 루프 구성 여부
│
├── detect_pockets()
│   ├── 면 법선이 +Z 방향이 아닌 평면 → 포켓 바닥
│   ├── 연결된 수직 면들 → 포켓 벽
│   ├── 포켓 깊이/폭/형상 분류 (직사각/원형/자유형)
│   └── 아일랜드 감지 (포켓 안의 돌출부)
│
├── detect_undercuts()
│   └── 면 법선의 Z 성분이 음수인 면 → 언더컷 경고
│
└── classify_accessibility()
    └── 각 면에 대해 공구 접근 방향 가능 여부 판단
```

**구현 주안점**:
- CadQuery의 `face.geomType()`, `face.normalAt()`, `face.Center()` 활용
- 언더컷 면은 `WARNING` 리포트로 사용자에게 알림 (5축 필요)
- 포켓은 루프 방향(CW/CCW)으로 내부/외부 구분

---

### Step 2. OpenCAMLib(OCL) 통합 (자유곡면의 핵심)

**왜 필요한가**: 자유곡면(돔, 임펠러 등)의 3D 피니싱 경로를 생성하려면  
공구가 형상 표면 위를 정확히 따라가는 **드롭커터(drop-cutter)** 알고리즘이 필요하다.  
OCL은 이를 구현한 오픈소스 C++ 라이브러리로 Python 바인딩이 있다.

**OCL 설치**:
```bash
pip install opencamlib  # 또는 소스 빌드
```

**통합 위치** (`src/cam/ocl_bridge.py` 신규):

```python
class OclSurfaceFinisher:
    """OCL drop-cutter 기반 자유곡면 피니싱."""

    def __init__(self, tool: CuttingTool, stl_mesh_path: str):
        # STL → OCL STLSurf 로드
        ...

    def waterline(self, z_levels, stepover) -> list[ToolpathSegment]:
        """등고선(waterline) 황삭 경로 생성."""
        # ocl.WaterlineOperation
        ...

    def drop_cutter_scanline(self, stepover) -> list[ToolpathSegment]:
        """드롭커터 스캔라인 피니싱 경로 생성."""
        # ocl.ParallelDropCutter
        ...

    def drop_cutter_zigzag(self, stepover, angle=0) -> list[ToolpathSegment]:
        """드롭커터 지그재그 피니싱."""
        ...
```

**처리 흐름**:
```
CadQuery solid
    ↓ export_stl()         (STL로 변환 - OCL 입력 포맷)
    ↓ OCL STLSurf 로드
    ↓ drop-cutter 실행     (모든 스캔라인 위치에서 Z 계산)
    ↓ ToolpathSegment 변환
    ↓ G-code 출력
```

**대안 (OCL 설치 어려운 경우)**:  
자체 구현 근사 드롭커터:
```python
def _approx_drop_cutter(self, x, y, stl_triangles, tool_r):
    """STL 삼각형들과 볼엔드밀이 접촉하는 최저 Z를 계산."""
    z_contact = -inf
    for tri in stl_triangles:
        # 삼각형-원 간섭 계산
        z = intersect_ball_triangle(x, y, tool_r, tri)
        z_contact = max(z_contact, z)
    return z_contact
```
(속도는 느리지만 의존성 없이 동작)

---

### Step 3. 2D 포켓 경로 BREP 추종 (닫힌 루프 오프셋)

**문제**: 현재 포켓은 바운딩 박스의 직사각형 지그재그로만 동작.  
자유형 포켓(비직사각형 외곽)에서 오버컷 발생.

**해결**: Shapely 라이브러리로 2D 루프 오프셋 계산

**구현** (`src/cam/pocket_planner.py` 신규):

```python
from shapely.geometry import Polygon
from shapely.ops import unary_union

class PocketPlanner:
    """포켓 외곽선에서 공구 반경 오프셋된 나선형 경로 생성."""

    def plan(self, outer_loop: list[tuple], islands: list[list[tuple]],
             tool_r: float, depth: float, stepover: float) -> list[ToolpathSegment]:
        """
        outer_loop: 포켓 외곽 꼭짓점 (XY, BREP에서 추출)
        islands: 포켓 내부 아일랜드 목록
        """
        pocket = Polygon(outer_loop)
        for isl in islands:
            pocket = pocket.difference(Polygon(isl))

        # 공구 반경 안쪽으로 오프셋
        current = pocket.buffer(-tool_r)

        segments = []
        while not current.is_empty:
            # 현재 오프셋 루프를 경로로 변환
            segments += self._polygon_to_segments(current, depth)
            current = current.buffer(-stepover)

        return segments
```

**의존성**: `pip install shapely`  
Shapely는 순수 Python + GEOS 바인딩으로 설치 쉬움.

---

### Step 4. 공구 반경 보정 (Cutter Radius Compensation)

**문제**: 현재는 공구 중심이 형상 외곽을 그대로 따라감.  
실제로는 공구 반경만큼 오프셋된 경로가 필요.

**두 가지 방식**:

#### 방식 A: 소프트웨어 오프셋 (권장)
G-code 생성 전에 경로 좌표를 공구 반경만큼 오프셋.
```python
# src/cam/crc.py
def offset_profile(segments, tool_r, side="left"):
    """
    프로파일 경로를 공구 반경만큼 오프셋.
    side: "left" = G41(하향절삭), "right" = G42(상향절삭)
    """
    # Shapely의 parallel_offset 또는 수동 법선 오프셋
    ...
```

#### 방식 B: G41/G42 CNC 보정 코드 출력
```python
# gcode_writer.py에 추가
def format_crc_on(self, tool_r, side):
    if side == "left":
        return f"G41 D{tool_r:.3f}"
    return f"G42 D{tool_r:.3f}"

def format_crc_off(self):
    return "G40"
```

**권장**: 방식 A (소프트웨어 오프셋) - 시뮬레이션에서 직접 검증 가능.

---

### Step 5. 절삭 조건 데이터베이스

**문제**: 현재 절삭 조건이 하드코딩 (`feed_rate: 600, spindle_rpm: 8000`).  
소재/공구 조합에 따라 적절한 값이 완전히 다름.

**구현** (`src/cam/cutting_params_db.py` 신규):

```python
# 소재 x 공구 x 직경 → (rpm, feed, depth)
CUTTING_DB = {
    ("Aluminum 6061", "flat_endmill", 10): {
        "spindle_rpm": 8000,
        "feed_rate": 600,
        "depth_per_pass": 3.0,
        "stepover_ratio": 0.5,
    },
    ("Aluminum 6061", "flat_endmill", 6): {
        "spindle_rpm": 10000,
        "feed_rate": 400,
        "depth_per_pass": 2.0,
        "stepover_ratio": 0.45,
    },
    ("Steel 1045", "flat_endmill", 10): {
        "spindle_rpm": 3000,
        "feed_rate": 200,
        "depth_per_pass": 1.0,
        "stepover_ratio": 0.35,
    },
    ("Steel 1045", "flat_endmill", 6): {
        "spindle_rpm": 4000,
        "feed_rate": 150,
        "depth_per_pass": 0.8,
        "stepover_ratio": 0.3,
    },
    ("Titanium Ti-6Al-4V", "flat_endmill", 10): {
        "spindle_rpm": 1500,
        "feed_rate": 100,
        "depth_per_pass": 0.5,
        "stepover_ratio": 0.25,
    },
    # ... 소재/공구별 확장
}

def lookup_params(material: str, tool_type: str, diameter: float) -> dict:
    """정확한 키가 없으면 가장 가까운 직경으로 보간."""
    ...
```

---

### Step 6. 진입/퇴출 경로 (Lead-in / Lead-out)

**문제**: 현재 공구가 수직으로 플런지(급하강)해 소재에 충돌 위험.  
현업에서는 헬리컬 진입이나 경사 진입(ramp-in)을 쓴다.

**구현** (`src/cam/approach.py` 신규):

```python
class ApproachStrategy:
    HELICAL = "helical"    # 나선형 하강 (포켓에 최적)
    RAMP    = "ramp"       # 경사면 하강 (슬롯/프로파일)
    PLUNGE  = "plunge"     # 수직 하강 (드릴링에만 허용)

def add_helical_entry(segment: ToolpathSegment, radius: float, pitch: float):
    """
    포켓 중심에서 헬리컬(나선형)으로 하강 후 포켓 가공 시작.
    공구에 가해지는 충격력 60% 이상 감소.
    """
    ...

def add_ramp_entry(segment: ToolpathSegment, ramp_angle=3.0):
    """
    경로 시작점에서 일정 각도(보통 3°)로 경사 하강.
    """
    ...

def add_arc_lead_in(segment: ToolpathSegment, radius: float):
    """
    외곽 프로파일 시작점에 접선 방향 원호 진입.
    진입 시 자국(dwell mark) 방지.
    """
    ...
```

---

### Step 7. 가공 결과 검증 파이프라인

**목표**: G-code로 가공했을 때 목표 형상이 실제로 나오는지 자동 비교.

**구현** (`src/cam/verification.py` 신규):

```python
class MachiningVerifier:
    """Voxel 시뮬레이션 결과 vs 목표 CAD 비교."""

    def verify(self, target_solid, simulated_voxel_grid) -> VerificationReport:
        """
        1. target_solid → 타깃 Voxel grid 변환
        2. simulated_grid XOR target_grid 계산
        3. 과삭(overcut): 타깃보다 많이 제거된 부분 → 빨강
        4. 미삭(undercut): 타깃보다 덜 제거된 부분 → 파랑
        5. 정확도: (일치 복셀 수) / (전체 복셀 수) * 100%
        """
        ...

@dataclass
class VerificationReport:
    accuracy_pct: float         # 목표 대비 정확도 (%)
    overcut_volume: float       # 과삭 부피 (mm³)
    undercut_volume: float      # 미삭 부피 (mm³)
    has_undercuts: bool         # 접근 불가 언더컷 여부
    worst_error_mm: float       # 최대 오차 (mm)
```

---

## 구현 우선순위 및 예상 효과

| 단계 | 구현 복잡도 | 효과 | 우선순위 |
|------|------------|------|---------|
| Step 1: BREP 피처 인식 강화 | 중 | 포켓/홀 인식 정확도 대폭 향상 | **1순위** |
| Step 3: Shapely 포켓 오프셋 | 낮 | 자유형 포켓 지원 | **2순위** |
| Step 5: 절삭 조건 DB | 낮 | 소재별 적절한 조건 | **3순위** |
| Step 6: 헬리컬 진입 | 낮 | 공구 수명 향상, 현실감 | **4순위** |
| Step 4: 공구 반경 보정 | 중 | 치수 정밀도 향상 | **5순위** |
| Step 7: 검증 파이프라인 | 중 | 자동 품질 확인 | **6순위** |
| Step 2: OCL 통합 | 높 | 자유곡면 피니싱 실현 | **7순위** |

---

## 단계별 구현 목표 (milestone)

### Milestone 1 - "포켓을 제대로 파자" (Step 1 + 3)
```
현재: 바운딩 박스 기반 포켓 (직사각형만)
목표: 임의 외곽 포켓 + 아일랜드 지원 + 언더컷 경고
검증: examples/08_auto_cam/ 브래킷의 볼트홀 포켓이 정확히 나오는가
```

### Milestone 2 - "소재에 맞는 조건" (Step 5 + 6)
```
현재: 알루미늄 하드코딩
목표: 재질 선택 → 자동으로 RPM/이송/절입 적용 + 헬리컬 진입
검증: 스틸/티타늄 선택 시 이송속도가 자동으로 낮아지는가
```

### Milestone 3 - "정밀 치수" (Step 4)
```
현재: 공구 중심이 외곽을 따름 → 반경만큼 소재 남음
목표: 소프트웨어 오프셋으로 치수 정확도 ±0.1mm
검증: 60×60 목표 형상이 실제로 60×60이 나오는가 (시뮬레이션 측정)
```

### Milestone 4 - "자동 품질 검증" (Step 7)
```
현재: 수동으로 G-code 눈으로 확인
목표: plan_and_generate() 후 자동으로 정확도 % 리포트
검증: "형상 정확도: 96.2%, 미삭 0.3mm³, 과삭 없음" 형태 출력
```

### Milestone 5 - "자유곡면 가공" (Step 2: OCL)
```
현재: 돔/임펠러 형상에서 경로가 형상을 무시
목표: OCL drop-cutter로 곡면을 정확히 추종
검증: 구형 돔 형상의 피니싱 경로가 실제 구면을 따라가는가
```

---

## 파일 구조 (추가될 파일들)

```
src/cam/
├── feature_recognition.py   ← NEW: Step 1 (BREP 분석)
├── pocket_planner.py        ← NEW: Step 3 (Shapely 오프셋)
├── cutting_params_db.py     ← NEW: Step 5 (절삭 조건 DB)
├── approach.py              ← NEW: Step 6 (진입/퇴출)
├── crc.py                   ← NEW: Step 4 (공구 반경 보정)
├── ocl_bridge.py            ← NEW: Step 2 (OCL 통합)
└── verification.py          ← NEW: Step 7 (검증)

src/cam/ (기존 수정)
├── auto_cam.py              ← 수정: feature_recognition 교체, cutting_params_db 연동
└── toolpath.py              ← 수정: approach 진입 경로 추가
```

---

## 추가 의존성 요약

```
shapely        → pip install shapely     (Step 3: 포켓 오프셋)
opencamlib     → pip install opencamlib  (Step 2: 자유곡면 - 선택)
scipy          → pip install scipy       (보간/스플라인 - 이미 있을 수 있음)
```

> OCL은 빌드 환경에 따라 설치가 어려울 수 있음.
> Milestone 1~4는 OCL 없이 shapely만으로 구현 가능.

---

## 현실적인 한계 (솔직한 선언)

AutoCAM이 고도화되어도 상업용 CAM(Mastercam, NX, Hypermill)과 동일한 수준은  
수년간의 개발이 필요하다. 이 계획의 목표는:

- ✅ **프리즘 형상** (박스, 브래킷, 포켓): 상업용 대비 80~90% 품질
- ✅ **단순 곡면** (돔, 경사면): OCL 통합 후 70~80% 품질  
- ⚠️ **복잡한 임펠러/터빈**: 5축 경로 없이는 불가
- ❌ **완전 자유곡면 고속가공**: 고도의 전용 CAM 커널 필요

이 계획은 **교육/프로토타이핑 목적**으로 충분한 수준을 목표로 한다.
