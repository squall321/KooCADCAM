# KooCADCAM 확장 로드맵

## 현재 완성 상태 (v0.1.0) - 2026-04-04

```
[완료] Core     : Config(YAML), EventBus
[완료] CAD      : primitives(4종), operations(5종), exporter(STEP/STL)
[완료] Library  : holes(4종), pockets(3종), slots(3종) = 10개 모듈
[완료] CAM      : stock, tools(10 프리셋), toolpath(5전략), gcode_writer
[완료] Post     : FANUC, Siemens 840D, Haas, GRBL = 4종
[완료] Sim      : gcode_parser(pygcode), visualizer(PyVista)
[완료] GUI      : PySide6, dark theme, 4 panels, 3D viewport
[완료] Pipeline : 전체 플로우 오케스트레이터
```

---

## Phase A: CAM 고도화 (v0.2.0)

> 목표: 실제 산업용 CAM에 가까운 경로 품질 달성

### A-1. 고급 가공 전략
```
src/cam/toolpath.py 확장:
├── HelicalStrategy      → 헬리컬 진입 (수직 플런지 대체)
├── TrocoidalStrategy    → 트로코이달 밀링 (고경도 소재)
├── SpiralPocketStrategy → 나선형 포켓 (안→밖 또는 밖→안)
├── ContourStrategy      → 등고선 3D 가공 (곡면 피니싱)
├── ScanlineStrategy     → 주사선 피니싱 (곡면)
└── RestMachiningStrategy→ 잔삭 가공 (대경 공구 후 소경 공구 마무리)
```

### A-2. 공구 경로 최적화
```
src/cam/optimizer.py (신규):
├── RapidOptimizer       → 급이송 거리 최소화 (TSP 근사)
├── LinkOptimizer        → 패스 간 연결 최적화 (리트랙트 최소)
├── FeedOverride         → 곡률 기반 이송속도 자동 조절
└��─ ToolpathSmoother     → 미소선분 → 스플라인 근사 (G5.1)
```

### A-3. 충돌 감지
```
src/cam/collision.py (신규):
├── ToolHolderCheck      → 공구 홀더-소재 간섭 체크
├── GougeDetector        → 과삭 (gouge) 검출
└── StockBoundaryCheck   → 소재 이탈 경고
```

### A-4. 예제 확장
```
examples/
├── 01_plate_fillet/     [완료]
├── 02_bolt_pattern/     → 볼트홀 패턴 + 카운터보어 (모듈 라이브러리 활용)
├── 03_pocket_array/     → 다중 포켓 그리드 가공
├── 04_contour_3d/       → 곡면 형상 3D 피니싱
└── 05_multi_tool/       → 다공구 자동 교환 공정
```

**의존성**: numpy (이미 설치), scipy (TSP/스플라인)

---

## Phase B: CNC 연동 레이어 (v0.3.0)

> 목표: G-code 생성 → 실제 CNC 기계 전송까지 연결

### B-1. LinuxCNC 직접 연동
```
src/cnc/                 (신규 모듈)
├── __init__.py
├── base.py              → CNC 연결 추상 클래스
├── linuxcnc_client.py   → LinuxCNC Python API 연동
│                          - 프로그램 전송 (MDI, Auto 모드)
│                          - 상태 폴링 (위치, 속도, 알람)
│                          - 원점 설정 (G54 세팅)
├── grbl_serial.py       → GRBL 시리얼 직접 전송
│                          - pyserial 기반 스트리밍
│                          - 실시간 상태 ($? 폴링)
│                          - 버퍼 관리
└── simulator.py         → 소프트 시뮬레이터 (기계 없이 검증)
```

### B-2. 산업 프로토콜
```
src/cnc/protocols/       (신규)
├── opcua_client.py      → OPC UA 클라이언트
│                          - 머신 상태 구독
│                          - 변수 읽기/쓰기
│                          - 알람/이벤트 모니터링
├── mtconnect_agent.py   → MTConnect HTTP Agent
│                          - current/sample 스트림 파싱
│                          - 상태 대시보드 데이터 소스
└── focas_client.py      → FANUC FOCAS2 라이브러리
                           - CNC 직접 읽기 (실제 FANUC 기계)
```

### B-3. 실시간 대시보드
```
src/gui/panels/
├── machine_panel.py     → 기계 연결/상태 패널
│                          - 연결 상태 표시등
│                          - 실시간 좌표 (X/Y/Z/A/B)
│                          - 스핀들 RPM, 이송속도
│                          - 프로그램 진행률
└── alarm_panel.py       → 알람/경고 로그 패널
```

**의존성**: opcua(python-opcua), pyserial, requests(MTConnect)

---

## Phase C: 소재 제거 시뮬레이션 (v0.4.0)

> 목표: Voxel 기반 실시간 소재 제거 렌더링 (Vericut 경량 대안)

### C-1. Voxel 엔진
```
src/sim/
├── voxel_engine.py      → Voxel 기반 소재 모델
│                          - Octree 자료구조 (메모리 효율)
│                          - 공구 형상 → Voxel subtraction
│                          - 해상도: 0.1mm ~ 1.0mm 선택 가능
├── tool_geometry.py     → 공구 3D 형상 모델
│                          - Flat endmill: 원기둥
│                          - Ball endmill: 반구 + 원기둥
│                          - Bull endmill: 토러스 + 원기둥
├── material_removal.py  → 제거 시뮬레이션 엔진
│                          - G-code 경로 따라 step-by-step 제거
│                          - 과삭/미삭 자동 검출
│                          - 제거 볼륨 계산
└── sim_visualizer.py    → 실시간 제거 렌더링
                           - PyVista + Voxel → Mesh 변환
                           - 프레임별 애니메이션
                           - 과삭 영역 빨간색 하이라이트
```

### C-2. GUI 통합
```
src/gui/panels/
└── sim_panel.py         → 시뮬레이션 제어 패널
                           - 재생/정지/스텝/되감기
                           - 속도 조절 슬라이더
                           - 과삭/미삭 리포트
```

**의존성**: numpy, scipy.ndimage (Voxel ops), 선택적으로 PyOpenCL(GPU 가속)

---

## Phase D: Multi-axis 가공 (v0.5.0)

> 목표: 3+2축 인덱싱 + 동시 5축 경로 생성

### D-1. 기구학
```
src/cam/multiaxis/       (신규)
├── __init__.py
├── kinematics.py        → 5축 기구학 (table-table, head-table, head-head)
│                          - 역기구학: 공구 벡터 → AB/BC 각도
│                          - 특이점 검출 및 회피
├── orientation.py       → 공구 방향 전략
│                          - surface normal 추종
│                          - lead/tilt angle 설정
│                          - 스무스 보간
├── toolpath_5axis.py    → 5축 경로 전략
│                          - Swarf milling (측면 절삭)
│                          - Point milling (점접촉)
│                          - Flank milling (플랭크)
└── postprocessor_5axis/ → 5축 후처리기
    ├── base.py          → 5축 PP 기본 클래스 (RTCP 보정)
    ├── fanuc_5axis.py   → FANUC 30i (G43.4/G43.5)
    └── siemens_5axis.py → Siemens 840D (TRAORI)
```

### D-2. 3+2 인덱싱
```
src/cam/multiaxis/
└── indexing.py          → 3+2축 인덱싱
                           - 자동 최적 인덱싱 각도 결정
                           - 면별 2.5D 가공 → 인덱스 회전 → 다음 면
                           - 워크 좌표계 자동 전환 (G54.1 Pn)
```

---

## Phase E: 지능형 공정 최적화 (v1.0.0)

> 목표: AI/데이터 기반 절삭 조건 최적화 + 피드백 루프

### E-1. 절삭력 모델
```
src/cam/physics/         (신규)
├── cutting_force.py     → 절삭력 해석 모델
│                          - Mechanistic model (비절삭저항)
│                          - 소재 DB (Al, Steel, Ti, Inconel)
│                          - Chip thickness → Force → Power
├── tool_wear.py         → 공구 마모 예측
│                          - Taylor 공구수명 모델
│                          - 절삭 온도 추정
│                          - VB (플랭크 마모량) 추적
└── chatter.py           → 채터 안정성 해석
                           - Stability Lobe Diagram (SLD)
                           - 최적 스핀들 RPM 추천
```

### E-2. 공정 최적화 엔진
```
src/cam/optimizer/       (신규)
├── feed_optimizer.py    → 이송속도 최적화
│                          - 절삭력 일정 유지 (Adaptive Feed)
│                          - 소재 제거율(MRR) 극대화
├── strategy_selector.py → 가공 전략 자동 선택
│                          - 형상 분석 → 전략 추천 (rule-based)
│                          - 가공 시간 추정/비교
└── ml_optimizer.py      → ML 기반 최적화 (장기)
                           - 과거 가공 데이터 학습
                           - Bayesian Optimization
```

### E-3. 폐루프 연동 (CNC → 피드백 → 최적화)
```
src/cnc/
└── feedback_loop.py     → 실시간 피드백
                           - OPC UA로 실부하 데이터 수집
                           - 절삭력 이상 감지 → 이송 자동 조절
                           - 가공 이력 DB 축적
```

**의존성**: scikit-learn, optuna (Bayesian), sqlite3 (이력 DB)

---

## Phase F: 플러그인 시스템 + 배포 (v1.5.0)

> 목표: 사용자 확장성 + 패키징

### F-1. 플러그인 아키텍처
```
src/plugins/             (신규)
├── __init__.py
├── loader.py            → .py 파일 동적 로드
├── registry.py          → 모듈/전략/후처리기 레지스트리
└── api.py               → 플러그인 API (안정 인터페이스)

plugins/                 (사용자 플러그인 폴더)
├── my_custom_hole/      → 커스텀 홀 모듈
├── my_machine_post/     → 커스텀 후처리기
└── my_toolpath/         → 커스텀 가공 전략
```

### F-2. 배포
```
├── pyproject.toml       → pip install koocadcam
├── Dockerfile           → 컨테이너 배포
├── .github/workflows/   → CI/CD
│   ├── test.yml         → 자동 테스트
│   └── release.yml      → PyPI 배포 + AppImage/DMG/MSI
├── installer/
│   ├── linux/           → AppImage
│   ├── macos/           → DMG
│   └── windows/         → MSI (cx_Freeze or PyInstaller)
└── docs/
    ├── user_guide/      → 사용자 매뉴얼
    ├── api_reference/   → 개발자 API 문서
    └── tutorials/       → 단계별 튜토리얼
```

### F-3. 국제화
```
src/gui/i18n/            → 다국어 지원
├── ko.ts                → 한국어
├── en.ts                → 영어
├── ja.ts                → 일본어
└── zh.ts                → 중국어
```

---

## 버전 릴리즈 타임라인 (추정)

```
v0.1.0  [완료]  기본 시스템 (CAD + CAM + GUI + 4 후처리기)
  │
v0.2.0  ──────  Phase A: CAM 고도화 (고급 전략 6종, 경로 최적화, 충돌감지)
  │
v0.3.0  ──────  Phase B: CNC 연동 (LinuxCNC, GRBL 시리얼, OPC UA, MTConnect)
  │
v0.4.0  ───��──  Phase C: Voxel 소재 제거 시뮬레이션
  │
v0.5.0  ──────  Phase D: 5축 가공 (기구학, 3+2 인덱싱, 5축 후처리기)
  │
v1.0.0  ──────  Phase E: 지능형 공정 최적화 (절삭력, 채터, ML)
  │
v1.5.0  ──────  Phase F: 플러그인 시스템 + 크로스플랫폼 배포
```

---

## 최종 목표 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    KooCADCAM GUI (PySide6)                   │
│  ┌────────┐  ┌──────────────┐  ┌──────────┐  ┌���──────────┐ ��
│  │ CAD    │  │ 3D Viewport  │  │ G-code   │  │ Machine   │ │
│  │ Panel  │  │  + Voxel Sim │  │ Viewer   │  │ Dashboard │ │
│  └────┬───┘  └──────┬───────┘  └────┬─────┘  └─────┬─────┘ │
├───────┼──────────────┼───────────────┼──────────────┼───────┤
│       │         Event Bus            │              │       │
├───────┼──────────────┼───────────────┼──────────────┼───────┤
│  ┌────▼───┐   ┌──────▼──────┐  ┌────▼────┐  ┌──────▼─────┐ │
│  │ CAD    │   │ CAM Engine  │  │  Sim    │  │ CNC Link   │ │
│  │ Engine │   │ ┌─────────┐ │  │ Engine  │  │ ┌────────┐ │ │
│  │ CadQ.  │   │ │Toolpath │ │  │ Voxel   │  │ │LinuxCNC│ │ │
│  │        │   │ │Optimizer│ │  │ G-parse │  │ │GRBL    │ │ │
│  │ Module │   │ │Physics  │ │  │ Visual  │  │ │OPC UA  │ │ │
│  │Library │   │ │PostProc │ │  │         │  │ │MTConn. │ │ │
│  └────────┘   │ └─────────┘ │  └─────────┘  │ │FOCAS   │ │ │
│               └─────────────┘                │ └────────┘ │ │
│                                              └────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Plugin System                             │
│  [Custom Modules] [Custom Strategies] [Custom Post-Proc]    │
└─────────────────────────────────────────────────────────────┘
         │                    │                  │
         ▼                    ▼                  ▼
    STEP / IGES          G-code (.nc)     Real CNC Machine
```
