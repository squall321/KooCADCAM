# KooCADCAM - CAD/CAM 자동화 시스템 계획서

## 1. 프로젝트 개요

**목표**: 복잡한 구조물을 단위 모듈로 분해하여 파라메트릭 CAD를 생성하고, 해당 형상의 CNC 가공 G-code를 자동 생성 + 시뮬레이션하는 통합 시스템

**핵심 파이프라인**:
```
파라메터 입력 → 모듈 라이브러리 조합 → CAD 모델 생성 → STEP 출력
                                                          ↓
시뮬레이션 ← G-code 생성 ← 후처리기 적용 ← 가공 경로 계산
                ↓
         GUI 3D 뷰포트 (실시간 미리보기)
```

## 2. 기술 스택

| 구분 | 기술 | 용도 |
|------|------|------|
| 런타임 | Python 3.12 + venv | 실행 환경 |
| CAD 엔진 | CadQuery 2.x (OCP) | 파라메트릭 3D 모델링 |
| CAD 출력 | STEP (AP214), STL | 표준 교환 포맷 |
| G-code 파싱 | pygcode | G-code 파싱/검증 |
| 3D 시각화 | PyVista + VTK | CAD 모델 및 G-code 경로 시각화 |
| GUI 프레임워크 | PySide6 (Qt6) | 크로스플랫폼 데스크탑 앱 |
| 3D 뷰포트 | pyvistaqt | Qt 내장 VTK 뷰포트 |
| 설정 관리 | YAML | 파라메트릭 입력/공구/공정 설정 |

## 3. 시스템 아키텍처

```
KooCADCAM/
├── src/
│   ├── core/                       # 핵심 인프라
│   │   ├── __init__.py
│   │   ├── config.py               # YAML 설정 로더
│   │   └── events.py               # 이벤트 버스 (모듈간 통신)
│   │
│   ├── cad/                        # CAD 모듈
│   │   ├── __init__.py
│   │   ├── primitives.py           # 기본 형상 (육면체, 실린더 등)
│   │   ├── operations.py           # 필렛, 챔퍼, 불리안 연산
│   │   ├── modular.py              # 모듈 조합기 (어셈블리)
│   │   ├── exporter.py             # STEP/STL 내보내기
│   │   └── library/                # 모듈 라이브러리
│   │       ├── __init__.py
│   │       ├── base.py             # 기본 모듈 추상 클래스
│   │       ├── holes.py            # 볼트홀, 카운터보어, 탭홀
│   │       ├── pockets.py          # 직사각/원형 포켓
│   │       └── slots.py            # T-슬롯, 도브테일, 키홈
│   │
│   ├── cam/                        # CAM 모듈
│   │   ├── __init__.py
│   │   ├── stock.py                # 원소재 정의
│   │   ├── tools.py                # 공구 DB (엔드밀, 볼엔드밀, 드릴)
│   │   ├── toolpath.py             # 공구 경로 전략
│   │   ├── gcode_writer.py         # G-code 생성기
│   │   └── postprocessor/          # 후처리기 시스템
│   │       ├── __init__.py
│   │       ├── base.py             # 후처리기 추상 클래스
│   │       ├── fanuc.py            # FANUC 계열
│   │       ├── siemens.py          # Siemens 840D
│   │       ├── haas.py             # Haas
│   │       └── grbl.py             # GRBL (오픈소스 CNC)
│   │
│   ├── sim/                        # 시뮬레이션 모듈
│   │   ├── __init__.py
│   │   ├── gcode_parser.py         # G-code 파싱 → 경로 데이터
│   │   └── visualizer.py           # 3D 경로 시각화
│   │
│   ├── gui/                        # PySide6 GUI
│   │   ├── __init__.py
│   │   ├── app.py                  # QApplication 진입점
│   │   ├── main_window.py          # 메인 윈도우
│   │   ├── viewport_3d.py          # 3D 뷰포트 (pyvistaqt)
│   │   ├── panels/                 # 사이드 패널
│   │   │   ├── __init__.py
│   │   │   ├── cad_panel.py        # CAD 파라메터 패널
│   │   │   ├── cam_panel.py        # CAM 설정 패널
│   │   │   ├── library_panel.py    # 모듈 라이브러리 브라우저
│   │   │   └── gcode_panel.py      # G-code 뷰어
│   │   ├── widgets/                # 커스텀 위젯
│   │   │   ├── __init__.py
│   │   │   ├── param_editor.py     # 파라메터 에디터
│   │   │   └── tool_selector.py    # 공구 선택기
│   │   └── themes/                 # 테마
│   │       ├── __init__.py
│   │       └── dark.py             # 다크 테마 (기본)
│   │
│   └── pipeline.py                 # 전체 파이프라인 오케스트레이터
│
├── examples/
│   └── 01_plate_fillet/            # MVP 예제
│       ├── run.py
│       └── config.yaml
│
├── output/                         # 생성 결과물
│   ├── step/
│   ├── gcode/
│   └── images/
│
├── PLAN.md
├── requirements.txt
└── venv/
```

## 4. 모듈 상세 설계

### 4.1 Core 인프라 (`src/core/`)

**config.py** - 설정 관리
- YAML 기반 프로젝트 설정 로더
- 기본값 병합, 유효성 검증

**events.py** - 이벤트 버스
- `EventBus`: 모듈 간 느슨한 결합 통신
- `model_updated`, `toolpath_generated`, `gcode_ready` 등 이벤트
- GUI ↔ 백엔드 동기화

### 4.2 CAD 모듈 (`src/cad/`)

**primitives.py** - 기본 형상
- `create_box(lx, ly, lz, center=True)` → 육면체
- `create_cylinder(r, h, center=True)` → 실린더
- `create_plate(lx, ly, thickness)` → 평판
- `create_cone(r1, r2, h)` → 원뿔/절두원뿔

**operations.py** - 형상 연산
- `apply_fillet(solid, radius, edge_selector)` → 필렛
- `apply_chamfer(solid, dist, edge_selector)` → 챔퍼
- `boolean_cut(base, tool)` → 불리안 차집합
- `boolean_union(a, b)` → 합집합
- `boolean_intersect(a, b)` → 교집합

**modular.py** - 모듈러 조합
- `ModularAssembly`: 모듈 배치/조합
- `add_module(module, position, rotation)` → 모듈 배치
- `linear_pattern(module, direction, count, spacing)` → 선형 패턴
- `grid_pattern(module, nx, ny, sx, sy)` → 그리드 패턴
- `mirror(module, plane)` → 미러 복사
- `to_solid()` → 최종 솔리드 합체

**exporter.py** - 파일 출력
- `export_step(solid, path)` → STEP AP214
- `export_stl(solid, path, tolerance)` → STL

### 4.3 모듈 라이브러리 (`src/cad/library/`)

**base.py** - 추상 기본 클래스
- `CadModule(ABC)`: 모든 모듈의 부모 클래스
  - `params: dict` → 파라메터
  - `build() → Workplane` → 형상 생성 (추상)
  - `get_param_schema() → dict` → 파라메터 스키마 (GUI 연동)
  - `bounding_box() → BBox` → 바운딩 박스

**holes.py** - 구멍 모듈
- `ThroughHole(diameter, depth)` → 관통홀
- `CounterboreHole(d_hole, d_cbore, cbore_depth, depth)` → 카운터보어
- `CountersinkHole(d_hole, d_csink, angle, depth)` → 카운터싱크
- `TappedHole(nominal_size, pitch, depth)` → 탭홀

**pockets.py** - 포켓 모듈
- `RectPocket(lx, ly, depth, corner_r)` → 직사각 포켓
- `CircularPocket(diameter, depth)` → 원형 포켓
- `ObroundPocket(lx, ly, depth)` → 오브라운드 포켓

**slots.py** - 슬롯 모듈
- `TSlot(width, depth, head_width, head_depth)` → T-슬롯
- `Dovetail(width_top, width_bottom, depth, angle)` → 도브테일
- `KeySlot(width, depth, length)` → 키홈

### 4.4 CAM 모듈 (`src/cam/`)

**stock.py** - 원소재
- `Stock(lx, ly, lz, material)` → 직육면체 원소재
- `from_bounding_box(solid, margin)` → CAD로부터 자동 생성
- `get_removal_volume(target_solid)` → 가공 볼륨 계산

**tools.py** - 공구 데이터베이스
- `ToolType` enum: FLAT_ENDMILL, BALL_ENDMILL, BULL_ENDMILL, DRILL, CHAMFER_MILL
- `CuttingTool(name, type, diameter, flute_length, shank_diameter, flutes)`
- 프리셋 공구 라이브러리 내장

**toolpath.py** - 공구 경로 전략 (Strategy 패턴)
- `ToolpathStrategy(ABC)` → 전략 추상 클래스
- `FacingStrategy` → 상면 페이싱 (지그재그)
- `ProfileStrategy` → 외곽 프로파일 (2.5D 윤곽)
- `PocketStrategy` → 포켓 가공 (나선/지그재그)
- `FilletStrategy` → 필렛 경로 (볼엔드밀 3D 경로)
- `DrillStrategy` → 드릴링 (펙드릴/스팟드릴)

**gcode_writer.py** - G-code 생성
- `GcodeWriter(post_processor)` → 후처리기 주입
- 공구 경로 → 중간 표현(IR) → 후처리기 → G-code 텍스트

### 4.5 후처리기 시스템 (`src/cam/postprocessor/`)

**base.py** - 추상 후처리기
- `PostProcessor(ABC)`: 모든 후처리기의 부모
  - `format_header()` → 프로그램 헤더
  - `format_tool_change(tool)` → 공구 교환
  - `format_spindle_on(rpm, direction)` → 스핀들 ON
  - `format_spindle_off()` → 스핀들 OFF
  - `format_coolant(on, type)` → 쿨런트 제어
  - `format_rapid(x, y, z)` → 급이송 G0
  - `format_linear(x, y, z, f)` → 직선이송 G1
  - `format_arc_cw(x, y, z, i, j, k, f)` → 시계방향 원호 G2
  - `format_arc_ccw(x, y, z, i, j, k, f)` → 반시계방향 원호 G3
  - `format_footer()` → 프로그램 종료
  - `decimal_places: int` → 좌표 소수점 자릿수
  - `line_number: bool` → N줄번호 사용 여부

**fanuc.py** - FANUC (가장 범용)
- G54 워크좌표, T/M6 공구교환, M3/M5 스핀들, M8/M9 쿨런트

**siemens.py** - Siemens 840D/Sinumerik
- CYCLE 매크로, D1 보정, SPOS 스핀들

**haas.py** - Haas VF 시리즈
- 매크로 변수, 고속가공 G187, 프로빙 G65

**grbl.py** - GRBL (오픈소스/취미용 CNC)
- 간결한 포맷, $ 설정, 소수점 3자리

### 4.6 시뮬레이션 모듈 (`src/sim/`)

**gcode_parser.py** - G-code → 경로 데이터
- pygcode 활용 파싱
- `GcodePath`: 세그먼트 리스트 (시작점, 끝점, 유형, 이송속도)
- 급이송(G0) / 절삭이송(G1) / 원호(G2,G3) 구분

**visualizer.py** - PyVista 3D 시각화
- `PathVisualizer`: 공구 경로 3D 렌더링
  - 급이송: 노란 점선 / 절삭이송: 빨간 실선 / 원호: 파란 곡선
- `ModelVisualizer`: CAD 솔리드 + 원소재 반투명 오버레이
- 스크린샷 저장 기능

### 4.7 GUI (`src/gui/`)

**PySide6 기반 크로스플랫폼 데스크탑 앱**

| 영역 | 위치 | 기능 |
|------|------|------|
| 3D 뷰포트 | 중앙 | CAD 모델 + 공구경로 실시간 렌더링 |
| CAD 패널 | 좌측 탭 | 형상 파라메터 편집, 모듈 드래그&드롭 |
| CAM 패널 | 좌측 탭 | 공구 선택, 가공 전략, 절삭 조건 |
| 라이브러리 | 좌측 탭 | 모듈 브라우저 (홀/포켓/슬롯) |
| G-code 뷰어 | 하단 | G-code 텍스트 + 줄별 하이라이트 |
| 툴바 | 상단 | 생성/내보내기/시뮬레이션 버튼 |

**다크 테마 기본 적용** (QSS 기반 커스텀 스타일시트)

## 5. 예제 1: 평판 절삭 + 필렛 (MVP)

### 시나리오
1. **입력**: 100×100×20mm 평판 원소재
2. **목표 형상**: 60×60×15mm 육면체 + 모든 상단 모서리 R3 필렛
3. **가공 공정**:
   - (a) 상면 페이싱: 20mm → 15mm (Ф10 플랫엔드밀)
   - (b) 외곽 포켓: 100×100 → 60×60 (Ф10 플랫엔드밀)
   - (c) 상단 필렛: R3 (Ф6 볼엔드밀)
4. **출력**: STEP + G-code (FANUC) + 3D 시각화

### 가공 파라메터 (config.yaml)
```yaml
stock:
  x: 100.0
  y: 100.0
  z: 20.0
  material: "Aluminum 6061"

target:
  x: 60.0
  y: 60.0
  z: 15.0
  fillet_radius: 3.0

tools:
  - name: "10mm Flat Endmill"
    type: flat_endmill
    diameter: 10.0
    flute_length: 30.0
    flutes: 3
  - name: "6mm Ball Endmill"
    type: ball_endmill
    diameter: 6.0
    flute_length: 20.0
    flutes: 2

cutting:
  spindle_rpm: 8000
  feed_rate: 500
  plunge_rate: 200
  depth_per_pass: 2.0
  stepover_ratio: 0.4

postprocessor: fanuc

output:
  step: output/step/plate_fillet.step
  gcode: output/gcode/plate_fillet.nc
  image: output/images/plate_fillet.png
```

## 6. 구현 단계

### Phase 1: 핵심 인프라 + CAD 기반
- [x] venv + 의존성 설치
- [ ] `core/config.py` - YAML 설정 로더
- [ ] `core/events.py` - 이벤트 버스
- [ ] `cad/primitives.py` - 기본 형상
- [ ] `cad/operations.py` - 필렛/불리안
- [ ] `cad/exporter.py` - STEP/STL 출력

### Phase 2: 모듈 라이브러리
- [ ] `cad/library/base.py` - 추상 모듈 클래스
- [ ] `cad/library/holes.py` - 홀 모듈
- [ ] `cad/library/pockets.py` - 포켓 모듈
- [ ] `cad/library/slots.py` - 슬롯 모듈
- [ ] `cad/modular.py` - 모듈러 조합

### Phase 3: CAM + 후처리기
- [ ] `cam/stock.py` - 원소재
- [ ] `cam/tools.py` - 공구 DB
- [ ] `cam/toolpath.py` - 공구 경로 전략 (5종)
- [ ] `cam/gcode_writer.py` - G-code 생성
- [ ] `cam/postprocessor/` - 후처리기 (4종)

### Phase 4: 시뮬레이션
- [ ] `sim/gcode_parser.py` - G-code 파싱
- [ ] `sim/visualizer.py` - 3D 시각화

### Phase 5: GUI
- [ ] `gui/app.py` - 앱 진입점
- [ ] `gui/main_window.py` - 메인 윈도우 레이아웃
- [ ] `gui/viewport_3d.py` - 3D 뷰포트
- [ ] `gui/panels/` - CAD/CAM/Library/Gcode 패널
- [ ] `gui/themes/dark.py` - 다크 테마

### Phase 6: 통합 + 예제
- [ ] `pipeline.py` - 전체 플로우 오케스트레이터
- [ ] 예제 1 완성 (CLI + GUI 양쪽)

## 7. 확장 로드맵

### 단기 (v1.x)
- 다양한 가공 전략 추가 (헬리컬, 트로코이달)
- 공구 경로 최적화 (이송 최소화)
- IGES 출력 지원

### 중기 (v2.x)
- **Multi-axis**: 3+2축, 동시 5축 가공 경로
- **공구 마모 시뮬레이션**: 절삭력/열 기반 수명 예측
- **소재 제거 시뮬레이션**: Voxel 기반 재료 제거 애니메이션
- **커스텀 모듈 플러그인**: 사용자 모듈 .py 파일 로드

### 장기 (v3.x)
- **AI 기반 공정 최적화**: 머신러닝으로 최적 절삭 조건 추천
- **클라우드 협업**: 프로젝트 공유, 팀 작업
- **FEM 연동**: 가공 후 잔류응력/변형 해석 (KooDynaAdvanced 연동)
