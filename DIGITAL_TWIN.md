# KooCADCAM Digital Twin - 설계 계획서

## 0. 비전

**"화면 안에서 실제 CNC 가공이 재현되는 디지털 트윈"**

- 파라미터 변경 → 실시간 CAD/CAM 재생성 → 깎이는 과정 시각화 → 시간 예측 → 최적화 제안
- 실제 기계 가동 전에 **화면에서 완전히 검증**하고 최적화할 수 있는 환경
- "해보고 안되면 시도"가 아닌, "해보기 전에 최적값 도출"

## 1. 현재 구현 상태 (v0.4.0 완료)

| 레이어 | 구현 | 파일 |
|--------|------|------|
| CAD 엔진 | CadQuery 기반 파라메트릭 | `src/cad/` |
| 모듈 라이브러리 | 10개 (홀/포켓/슬롯) | `src/cad/library/` |
| CAM 전략 | 11종 (기본5 + 고급6) | `src/cam/toolpath*.py` |
| 최적화 | TSP, Link, Feed, Smooth | `src/cam/optimizer.py` |
| 충돌감지 | 4종 검사 | `src/cam/collision.py` |
| 후처리기 | 4종 (FANUC/Siemens/Haas/GRBL) | `src/cam/postprocessor/` |
| **Voxel 엔진** | **3D 제거 시뮬** | `src/sim/voxel_engine.py` |
| **시간 예측** | **가/감속 포함** | `src/sim/time_estimator.py` |
| **애니메이션** | **PyVista 실시간** | `src/sim/removal_animator.py` |
| CNC 연동 | LinuxCNC/GRBL/OPC UA/MTConnect/FOCAS | `src/cnc/` |
| GUI | PySide6, 5 패널 | `src/gui/` |

**검증**: 예제 6종, 17 단위테스트, GUI 렌더링 모두 통과.

## 2. 디지털 트윈 완성을 위한 확장 로드맵

### Phase D-1: 정확도 강화 (v0.5.0) - 시뮬레이션 신뢰도

> 목표: 실제 기계와의 오차 <5%

#### D-1-1. 정밀 시간 예측 모델
```
src/sim/time_estimator.py 확장:
  현재: 단순 거리/속도 + 가감속 러프
  목표: ISO 16090-1 기반 S-curve 가속도 프로파일
        - 각 축별 가속도/저크(jerk) 한계
        - Lookahead 버퍼 (실제 CNC의 전방참조)
        - 코너 스무딩 반경
        - 스핀들 관성 (가감속 시간)
```

**신규 클래스**:
- `SCurveProfile`: 7단계 S-curve (가속-등속-감속)
- `LookaheadBuffer`: 코너 진입 속도 재계산
- `SpindleDynamics`: 스핀들 RPM 변화 시간

#### D-1-2. 소재 제거 정밀도 향상
```
src/sim/voxel_engine.py 확장:
  현재: 균일 Voxel 그리드 (메모리 비효율)
  목표: Sparse Voxel Octree (SVO)
        - 계층적 해상도 (표면 근처만 고해상도)
        - 메모리 10x 절감
        - 과삭/미삭 서브밀리미터 정확도
```

**신규 파일**:
- `src/sim/svo_grid.py`: Octree 기반 희소 그리드
- `src/sim/tool_sweep.py`: 공구 궤적 sweep volume 생성
- `src/sim/material_model.py`: 소재별 물성 (절삭력 계수 포함)

#### D-1-3. 절삭력 / 열 시뮬레이션
```
src/sim/physics/ (신규):
├── cutting_force.py    - Mechanistic 절삭력 모델 (Kc, Ks)
├── thermal_model.py    - 절삭열 분포 (Shaw/Komanduri)
├── deflection.py       - 공구 처짐 → 치수 오차 예측
└── chip_load.py        - 실제 칩 두께 계산 (radial engagement)
```

### Phase D-2: UX 완성도 (v0.6.0) - 디지털 트윈 앱

> 목표: 상업용 CAM SW 수준의 사용자 경험

#### D-2-1. 통합 워크스페이스 레이아웃

```
┌─────────────────────────────────────────────────────────────────────┐
│  [Menu Bar]  File | Edit | View | CAD | CAM | Simulate | Machine    │
├─────────────────────────────────────────────────────────────────────┤
│  [Ribbon Toolbar]  [Parameters] [Generate] [Simulate] [Optimize]    │
├──────────┬──────────────────────────────────────┬──────────────────┤
│          │                                      │                  │
│ [Tree]   │        [3D Viewport]                 │ [Properties]     │
│ - Stock  │                                      │                  │
│ - Target │   • Stock (wireframe)                │ Feed: 600 mm/min │
│ - Ops    │   • Part (solid)                     │ RPM:  8000       │
│   └ Face │   • Tool (animated)                  │ Stepover: 40%    │
│   └ Pocket│  • Toolpath trail                   │ DOC:  2.5 mm     │
│   └ Fillet│  • Voxel cut-away                   │                  │
│          │                                      │ [Apply Changes]  │
│          ├──────────────────────────────────────┤                  │
│          │  [Timeline Scrubber]  ◄ ▶ ⏸          │                  │
│          │  0%══════════●═══════════════100%    │                  │
│          │  Op 2/4: Pocket Clear  T:8m12s/47m   │                  │
├──────────┴──────────────────────────────────────┴──────────────────┤
│ [Bottom Panel]  [G-code] [Time Analysis] [Optimize] [Machine Log] │
│                                                                     │
│   Cutting: 31m (65%) ████████████░░░░░░░                           │
│   Rapid:    25s (1%) ░                                              │
│   Accel:   15m (34%) ██████░░░░                                     │
│   TOTAL:   47m 25s                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

#### D-2-2. 타임라인 스크러버 (핵심 UX)

**요구사항**:
- 마우스로 시간축 드래그 → 그 시점의 가공 상태를 즉시 3D로 표시
- 현재 공정 단계 표시 (Op 2/4: Pocket Clear)
- 현재 공구 위치 오버레이
- 현재 이송속도/RPM/부하 그래프
- 키프레임 북마크 (공구 교환, 도구 진입/이탈)

**신규 파일**:
- `src/gui/widgets/timeline_scrubber.py`
- `src/gui/widgets/operation_tree.py`
- `src/sim/state_snapshot.py` - 시점별 상태 복원

#### D-2-3. 실시간 파라미터 튜닝

**요구사항**:
- 우측 패널에서 Feed/RPM/Stepover 변경 → **200ms 이내** G-code 재생성
- 변경 전/후 가공시간 실시간 비교
- 최적값 Suggest 버튼 ("추천 조건 적용")

**구현**:
```python
class ParameterController:
    def on_param_change(self, name, value):
        self.debounce(200)  # 200ms 쓰로틀
        self.regenerate_toolpath_async()
        self.update_time_estimate_delta()  # "−3m 24s" 표시
        self.update_3d_preview()
```

#### D-2-4. Split View (비교 모드)

**A/B 가공 전략 비교**:
- 화면 좌우 분할
- 좌: Zigzag 포켓 (현재)
- 우: Spiral 포켓 (제안)
- 시간/거리/표면품질 비교 표

#### D-2-5. 테마 & 접근성

**다크 테마** (이미 구현)
- 색맹 대응 팔레트 옵션
- 고대비 모드
- 폰트 크기 조절
- 한국어/영어 다국어 (Qt Linguist)

### Phase D-3: 공정 최적화 엔진 (v0.7.0) - AI 없이도 강력하게

> 목표: 파라미터 공간을 자동 탐색해 최적 조건 도출

#### D-3-1. 규칙 기반 최적화 (Rule-based)
```
src/optimize/ (신규):
├── rules.py            - 소재별 절삭조건 규칙 DB
│                         Al6061: Vc=300m/min, fz=0.05mm
│                         Steel: Vc=120m/min, fz=0.03mm
├── recipe.py           - 공구/소재 조합 → 추천 파라미터
└── validator.py        - 채터/파손 위험도 계산
```

**예시 UI**:
```
[Suggest Parameters] 버튼 클릭
  ↓
┌──────────────────────────────┐
│ Recommendation               │
│ ─────────────────────────── │
│ Material: Al 6061            │
│ Tool: 10mm 3FL Carbide       │
│                              │
│ Feed:    800 → 1200 mm/min  │
│ RPM:     8000 → 10500        │
│ Stepover: 40% → 55%          │
│                              │
│ Expected: −12m (26% faster) │
│ Risk: Low                    │
│                              │
│ [Apply] [Cancel] [Explain]   │
└──────────────────────────────┘
```

#### D-3-2. 자동 파라미터 스위프
```
src/optimize/sweep.py:
  - 파라미터 그리드 탐색 (Feed × RPM × Stepover)
  - 각 조합의 시간/품질/위험도 평가
  - 파레토 프런티어 시각화
```

**UI**: 히트맵 시각화 (Feed vs Stepover → 가공시간 컬러맵)

#### D-3-3. Adaptive Feed Control
```
src/sim/adaptive_feed.py:
  - 소재 절입량 기반 실시간 이송속도 조절
  - 급증하는 절삭력 감지 → 감속
  - 노출 구간 → 가속
  - G-code에 M 매크로로 삽입
```

### Phase D-4: 실시간 연동 (v0.8.0) - 트윈 ↔ 실기계

> 목표: 시뮬과 실제 기계가 동시에 같은 상태로 동기화

#### D-4-1. Live Sync 모드
```
디지털 트윈 ←→ 실제 CNC
    ↓              ↓
 [예측 상태]    [실제 상태]
    ↓              ↓
     \          /
      [Diff 표시]
         ↓
   오차 > 임계값 → 알림 + 원인 분석
```

**신규 기능**:
- `src/cnc/live_sync.py`: 1초 간격 실제↔예측 비교
- `src/gui/panels/sync_panel.py`: 차이값 시각화
- 오차 누적 시 경고 ("공구 파손 의심")

#### D-4-2. Record & Replay
- 실제 가공 데이터 기록 (OPC UA → SQLite)
- 나중에 재생 (소재제거 시뮬과 동기화)
- 학습 데이터로 활용

### Phase D-5: 고급 디지털 트윈 기능 (v1.0.0)

#### D-5-1. 멀티 소재 지원
- Bi-metal 스톡 (층별 다른 소재)
- 주조품에서 마감 가공
- 기존 STL → Voxel 변환

#### D-5-2. 공구 마모 모델
- Taylor 공구수명 (T·V^n·f^m = C)
- 누적 절삭 거리 → VB 예측
- 마모 진행에 따른 표면조도 변화

#### D-5-3. 5축 디지털 트윈
- 3+2 / 동시 5축 기구학
- 테이블/헤드 회전 시각화
- RTCP 검증

---

## 3. 우선순위 및 즉시 실행 계획

### 🔴 즉시 착수 (Phase D-2: UX 완성)

**이유**: 이미 동작하는 백엔드를 사용자가 "쓸만하게" 만드는 가장 중요한 단계

#### Week 1-2: 타임라인 스크러버
1. `timeline_scrubber.py` - Qt QSlider 기반 커스텀 위젯
2. 사전 시뮬레이션: 가공 전체를 미리 실행해서 시점별 voxel 상태 저장
3. 스크러버 이동 → 해당 시점 voxel 렌더링

#### Week 3: 작업 트리 패널
1. `operation_tree.py` - 가공 공정 계층 표시
2. 각 노드 더블클릭 → 해당 공정 시점으로 점프
3. 노드별 소요시간/공구/파라미터 표시

#### Week 4: 실시간 파라미터 튜닝
1. 우측 속성 패널 동기화
2. Debounced 재생성 (200ms)
3. Delta 표시 (−3m 24s)

### 🟡 단기 (Phase D-1: 정확도)

#### Week 5-6: S-curve 가감속 모델
- 현재 시간 예측이 57분인데 실제는 45분일 수 있음
- 정확한 lookahead 모델 필요

#### Week 7-8: 절삭력 모델
- 채터 발생 지점 예측
- 실제 이송속도 Adjust 제안

### 🟢 중기 (Phase D-3, D-4, D-5)

- Rule-based 최적화
- Live Sync
- 5축

---

## 4. 기술 스택 (확장)

| 신규 의존성 | 용도 |
|-------------|------|
| `imageio` | GIF 애니메이션 출력 (설치 완료) |
| `sqlite3` (stdlib) | 가공 이력 DB |
| `scipy.optimize` | 파라미터 최적화 |
| `numba` (선택) | Voxel 계산 JIT 가속 |

## 5. 성능 목표

| 지표 | v0.4 현재 | v1.0 목표 |
|------|-----------|-----------|
| 시뮬 파라미터 변경 → 결과 | 수 초 | <200ms |
| Voxel 1mm 해상도, 100×100×20 | 5초 | <1초 |
| 시간 예측 오차 | ~10% | <5% |
| GUI FPS | 20 | 60 |
| 지원 G-code 크기 | 10K lines | 100K lines |

## 6. 참고: 상용 도구 대비 포지션

| 기능 | Vericut (상용) | Fusion 360 | **KooCADCAM 목표** |
|------|----------------|------------|--------------------|
| Voxel 시뮬 | 있음 (유료) | 제한적 | **있음 (오픈)** |
| 시간 예측 | 있음 | 있음 | **있음** |
| 파라미터 튜닝 | 제한적 | 있음 | **실시간** |
| 5축 지원 | 있음 | 있음 | 계획 중 |
| 가격 | $수천만원 | 구독형 | **무료/오픈** |
| 커스터마이징 | 어려움 | 중간 | **완전 자유** |
