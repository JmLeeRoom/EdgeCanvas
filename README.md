# EdgeCanvas (P10_Manufacturing)

문서·스펙에서 LVGL 기반 HMI UI를 자동 생성·검증하는 에이전트 파이프라인입니다.
**Phase A**는 PC SDL2 시뮬레이터로 장비 없이 E2E(`p10 run --mode sim`)를 돌리고,
**Phase HW**에서 Waveshare ESP32-P4 + USB 카메라로 실기 검증합니다.

---

## Quick start (권장 설치 순서)

제3자 개발자가 README + 설치 스크립트만으로 **약 60분 내** sim 환경을 재현하는 것이 목표입니다 (T-904 / REQ-DEMO-01).

### 1) 사전 도구

| 도구 | 최소 / 권장 | 다운로드 |
|---|---|---|
| Git | 필수 | https://git-scm.com/downloads |
| Python | **3.10+** / 권장 **3.13.x** | https://www.python.org/downloads/ |

> Python **3.14+** 는 `langchain-upstage` / `tokenizers` 휠 충돌(Issue #71)로 설치가 깨질 수 있습니다. 3.13.x 를 쓰세요.

### 2) 클론 후 자동 설치

```powershell
git clone https://github.com/JmLeeRoom/EdgeCanvas.git
cd EdgeCanvas
.\install.bat
```

```bash
git clone https://github.com/JmLeeRoom/EdgeCanvas.git
cd EdgeCanvas
chmod +x install.sh
./install.sh
```

스크립트는 Git/Python 최소 버전을 검사하고, 미충족 시 위 다운로드 링크를 출력한 뒤 **즉시 중단**합니다.
통과하면 `.venv` 생성, `requirements.txt` 설치, 없으면 `.env.example` → `.env` 복사를 수행합니다.

### 3) 가상환경 활성화 · 의존성 확인

```powershell
.\.venv\Scripts\activate
python -c "import cv2; print(cv2.__version__)"
```

```bash
source .venv/bin/activate
python -c "import cv2; print(cv2.__version__)"
```

수동으로만 설치할 때:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 4) API 키 (`.env`)

1. 루트에 `.env` 가 없으면: `copy .env.example .env` (Windows) / `cp .env.example .env` (Unix)
2. 아래 키를 콘솔에서 발급해 **값만** 채웁니다. 키를 코드·로그·커밋에 넣지 마세요.

| 변수 | 용도 | 발급 |
|---|---|---|
| `UPSTAGE_API_KEY` | Document Parse / Solar 등 Upstage API | [Upstage Console](https://console.upstage.ai/) |
| `NC_VARCO_API_KEY` | NC AI VARCO Art 이미지 생성 (T-010/T-401) | NC AI OpenAPI 콘솔 |

선택 변수(`NC_VARCO_API_URL`, `NC_VARCO_AUTH_HEADER` 등)는 `.env.example` 주석을 참고하세요.
`.env` 는 `.gitignore` 대상이며 커밋하지 않습니다.

### 5) CLI 스모크 · 시뮬 E2E

```powershell
python -m src.cli.main --help
python -m src.cli.main run --mode sim --help
```

장비 없이 시뮬 E2E(가짜 API/픽스처 Vision) 예:

```powershell
python -m src.cli.main run --mode sim
```

산출물은 `output/<run_id>/` 에 생성됩니다 (`report.md`, 스크린샷 등). 이 폴더는 커밋하지 않습니다.

---

## Python 환경 변수 가이드

| 변수 | 설명 | 기본 |
|---|---|---|
| `UPSTAGE_API_KEY` | Upstage API 키 (필수) | — |
| `NC_VARCO_API_KEY` | VARCO Art 키 (에셋 생성 시) | — |
| `P10_OUTPUT_DIR` | 런 산출물 루트 | `output` |
| `IDF_PATH` | ESP-IDF 루트 (Phase HW) | install 경로에 따름 |
| `PYTHONPATH` | 저장소 루트를 모듈 경로에 포함 | `install.*` 가 설정 |

PowerShell에서 세션만 임시 주입:

```powershell
$env:UPSTAGE_API_KEY = "up_..."   # 로컬 전용, 커밋 금지
$env:P10_OUTPUT_DIR = "output"
```

Windows/WSL/Linux 매트릭스 참고: `docs/verification/T-012_environment_matrix.md`

---

## ESP-IDF 버전 호환 범위 (Phase HW)

| 항목 | 값 |
|---|---|
| 호환 범위 | **ESP-IDF v5.3+** (검증 기준 v5.3.x) |
| Windows 기본 경로 | `C:\Espressif\frameworks\esp-idf-v5.3` |
| 환경보내기 | `. .\scripts\export_idf_env.ps1` |
| 상세 매뉴얼 | [`docs/setup/esp-idf-windows.md`](docs/setup/esp-idf-windows.md) |

```powershell
. .\scripts\export_idf_env.ps1
idf.py --version
# 기대: ESP-IDF v5.3.x 이상
```

에이전트용 `.venv` 와 Espressif 전용 Python 환경을 **섞지 마세요**.
보드 BSP 예제: [`hw/esp32p4-bsp-demo/README.md`](hw/esp32p4-bsp-demo/README.md)

---

## 하드웨어 결선도 (Phase HW / 시연)

시뮬(Phase A)만 재현할 때는 보드·카메라 **불필요**합니다. 아래는 실기·시연용입니다.

```
  [노트북 / Host PC]
         |  USB-A/C (데이터)
         +---------------------+
         |                     |
    [USB-UART]            [USB Webcam]
         |                     |
  [Waveshare ESP32-P4]    LCD 정면 촬영
   7" LCD 1024x600         (암막 후드 권장)
         |
    외부 5V (필요 시) / USB 허브
```

권장 결선 순서:

1. Host PC 전원·드라이버(CP210x/CH34x) 확인
2. ESP32-P4 를 **데이터 전송 가능** USB 케이블로 PC에 연결 → COM 포트 확인
3. USB 웹캠을 PC에 연결 (LCD를 정면에서 비추도록 지그 고정)
4. 형광등 난반사가 심하면 암막 후드/조명을 추가 (T-011/T-905)
5. Phase HW CLI: `python -m src.cli.main run --mode hw` (보드·카메라 준비 후)

시연 부스 물리 고정은 T-905 범위입니다.

---

## PC 시뮬레이터 (SDL2)

LVGL 9.x / 1024×600. 상세: [`src/simulator/README.md`](src/simulator/README.md)

```powershell
cmake -S src/simulator -B build_sim
cmake --build build_sim
.\build_sim\bin\lvgl_simulator.exe
```

사전 도구: CMake ≥ 3.16, MinGW/clang, SDL2, Git(FetchContent).

---

## 테스트

```powershell
.\.venv\Scripts\activate
python -m pytest tests/test_install_scripts.py -v
python -m pytest tests/ -q
```

---

## 저장소 구조 (요약)

| 경로 | 역할 |
|---|---|
| `src/` | CLI·에이전트·비전·시뮬 드라이버 |
| `tests/` | 단위·E2E 테스트 |
| `hw/` | ESP32-P4 BSP 스캐폴딩 |
| `docs/` | 셋업·검증 기록 |
| `config/` | 설정 |
| `install.bat` / `install.sh` | 환경 부트스트랩 (T-904) |

---

## 기여 / 워크플로

Task 단위 개발: `단위구현계획서.md` 제5장 + `.cursor/rules/task-workflow.mdc`.
GitHub 브랜치·PR·라벨: `GITHUB_워크플로_가이드.md`.
