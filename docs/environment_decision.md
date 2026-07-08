# 개발·시연 OS 및 Docker 사용 범위 결정 (T-012)

* **작성 시각**: 2026-07-08T16:09:13+09:00
* **범위**: 이 문서는 **2주차 SW 부분**의 결정만 다룬다. USB 플래시·카메라·시리얼 포트 접근(Docker의 하드웨어 접근 포함 여부 최종 확정 포함)은 **11주차 Phase HW**에서 `docs/verification/T-012_hw_matrix.md`로 별도 검증·기록한다.
* **선행 task**: T-001 (완료, `docs/verification/T-001_env_setup.txt`)
* **검증 기록**: `docs/verification/T-012_environment_matrix.md`

## 1. OS 후보 비교 (2주차 SW 관점)

| 후보 | 이 개발 머신에서 실측 가능? | SW 관점 결과 | 비고 |
|---|---|---|---|
| **Windows 네이티브** | 가능 | 팀 표준 가상환경(`.venv`, Python 3.13)에서 `cv2` 임포트 성공 | 현재 개발 머신의 실제 환경. T-001에서 Python 3.13 확정 |
| **WSL2** | **불가 (미설치)** | 측정 불가 | `wsl.exe` 런처 바이너리는 PATH에 존재하지만 `wsl --status` 실행 시 "Linux용 Windows 하위 시스템이 설치되어 있지 않습니다. `wsl --install`로 설치하십시오" 오류 반환. 배포판이 설치되지 않아 SW 검증 자체가 불가능 |
| **Linux 네이티브** | 불가 (이 머신에 없음) | 측정 불가 | 12항 실패 대처의 폴백 후보로만 문서화. 실측은 없음 |

## 2. 공식 개발·시연 OS 결정 (SW 부분, 2주차 기준)

* **공식 개발 OS(SW 검증 범위)**: **Windows 네이티브** — 이 개발 머신에서 팀 표준 가상환경(`.venv`, Python 3.13.14)으로 `cv2` 임포트가 실제로 성공함을 확인했다 (`docs/verification/T-012_environment_matrix.md` 참조).
* **WSL2**: 이번 세션에서는 설치되어 있지 않아 **검증 불가** 상태로 남긴다. 비지원으로 확정하지 않으며, 11주차 Phase HW에서 재검토 후 최종 결정한다.
* **Linux 네이티브**: 12항 실패 시나리오(Windows/WSL2에서 카메라·USB 포트 접근 불안정)가 11주차 HW 검증에서 실제로 발생할 경우의 **폴백 후보**로 문서화한다. 이번 SW 부분에서는 실측하지 않았다.
* **공식 시연 OS**: **11주차 Phase HW 검증 완료 후 확정** (TODO). 카메라·USB 플래시·시리얼 포트 접근 안정성이 결정 기준이며, SW 부분만으로는 확정할 수 없다.

## 3. Docker 사용 범위 결정

* **이 머신의 Docker CLI 가용성**: **미검출**. `docker --version` / `docker info` 실행 시 `docker` 명령을 찾을 수 없음 (CommandNotFoundException). 이 개발 머신(Windows 네이티브)에는 Docker Desktop/CLI가 설치되어 있지 않다.
* **팀 결정 — Docker 설치 위치**: Windows 개발 PC에는 Docker를 설치하지 않는다. Docker가 필요한 작업은 **별도 Linux 머신**에 Docker Engine(네이티브, Docker Desktop 아님)을 설치해 수행한다. 즉 이 프로젝트에서 Docker는 "Windows 로컬 상시 상주"가 아니라 "필요한 작업 시점에 Linux 머신에서만" 쓰는 선택적 도구로 확정한다.
* **2주차 SW 범위 결정**: Docker가 이 Windows 머신에 없으므로 Docker 기반 문서 빌드를 이 세션에서 실행으로 검증할 수 없었다. 대신 다음을 문서화한다:
  * Docker 설치 시 사용 범위는 카드 12항 실패 대처 원칙에 따라 **문서 빌드·순수 Python 테스트 전용**으로 우선 제한한다.
  * Docker에서 USB 시리얼·카메라 장치로의 하드웨어 접근 포함 여부는 **TODO — 11주차 Phase HW에서 최종 확정**한다.

### 3.1 Docker가 필요한 경우 (이 프로젝트 범위 내)

| 상황 | Docker 필요 여부 | 비고 |
|---|---|---|
| Python 스크립트/에이전트 실행, `pytest` 단위 테스트 | **불필요** | Windows `.venv`(Python 3.13)로 충분. 이번 T-012 SW 검증도 Docker 없이 완료됨 |
| LVGL 시뮬레이터(SDL2, T-801/802) 빌드·실행 | **불필요** | Windows 네이티브 CMake/SDL2 경로로 이미 검증됨(T-801) |
| **문서 빌드**(예: 정적 사이트/문서 생성기를 컨테이너화하는 경우) | **필요 시 Linux에서** | 카드 8-3항의 "Docker 문서 빌드" 검증 대상. Windows에는 설치하지 않으므로 Linux 머신에서 실행·검증한다 |
| ESP-IDF 빌드 환경을 컨테이너로 통일하고 싶을 때(옵션) | **필요 시 Linux에서** | ESP-IDF Docker 이미지는 USB 플래시 시 컨테이너의 USB 패스스루가 필요해 Linux 네이티브 Docker가 유리함(Windows Docker Desktop은 USB 패스스루가 더 제약적) |
| **USB 시리얼/카메라 장치 접근**(보드 플래시, LCD 촬영) — 11주차 Phase HW | **필요 시 Linux에서, 최종 확정은 11주차** | Docker에서 하드웨어 장치(`/dev/ttyUSB*`, `/dev/video*`)를 컨테이너에 노출하는 것은 Linux Docker Engine의 `--device` 옵션으로 비교적 안정적. Windows Docker Desktop(WSL2 기반)은 USB 패스스루가 불안정한 사례가 많아 12항 실패 대처의 실제 트리거가 되기 쉽다. 이 판단에 따라 하드웨어 관련 Docker 실험은 Windows가 아닌 Linux 머신에서 진행하기로 확정 |

* **결론**: Docker는 "항상 필요"가 아니라 **(a) 문서 빌드 컨테이너화, (b) ESP-IDF 빌드 통일(옵션), (c) 11주차 하드웨어(USB/카메라) 접근 실험**의 3가지 경우에만 필요하며, 이 3가지 모두 **Windows 개발 PC가 아닌 별도 Linux 머신**에서 수행한다. Windows PC의 SW 개발 흐름(CLI, 에이전트, 시뮬레이터, pytest)은 Docker 없이 완결된다.
* **TODO (11주차 Phase HW에서 마무리, Linux 머신에서 진행)**:
  - [ ] Linux 머신에 Docker Engine 설치
  - [ ] Docker 컨테이너에서 USB 시리얼 포트 접근 가능 여부 실측 (`--device=/dev/ttyUSB0` 등)
  - [ ] Docker 컨테이너에서 카메라 장치 접근 가능 여부 실측 (`--device=/dev/video0` 등)
  - [ ] 위 결과에 따라 Docker 사용 범위를 "문서 빌드 전용" 또는 "하드웨어 접근 포함"으로 최종 확정
  - [ ] `docs/verification/T-012_hw_matrix.md` 작성

## 4. 비지원 환경

* **WSL2**: 미설치로 이번 세션에서 지원 여부 판정 보류. 비지원으로 낙인하지 않음.
* **Linux 네이티브**: 이 개발 머신에 없어 검증 불가. 팀 내 다른 머신에서 실측 필요 시 11주차에 별도 진행.

## 5. 설치 순서 (Windows 네이티브 기준, SW 부분)

1. Python 3.13.x 설치 (T-001 결정: 3.14는 `tokenizers` 사전빌드 wheel 부재로 비권장).
2. `python -m venv .venv` 로 가상환경 생성.
3. `.venv\Scripts\activate` (PowerShell: `.venv\Scripts\Activate.ps1`).
4. `pip install -r requirements.txt` — `opencv-python` 포함.
5. `python -c "import cv2; print(cv2.__version__)"` 로 설치 확인.
6. Docker는 Windows 개발 PC에 설치하지 않는다. Docker가 필요한 작업(문서 빌드 컨테이너화, ESP-IDF 빌드 통일, 11주차 USB/카메라 하드웨어 접근 실험)은 **별도 Linux 머신**에서 Docker Engine을 설치해 수행한다(3.1절 참조). 하드웨어(USB/카메라) 접근은 11주차 이전에는 시도하지 않는다.

## 6. 결론 요약

| 항목 | 2주차 SW 결정 | 11주차 HW 확정 대상 |
|---|---|---|
| 공식 개발 OS | Windows 네이티브 (실측 확인) | 시연 OS 최종 확정 |
| WSL2 | 미설치 — 판정 보류 | 재검토 |
| Linux 네이티브 | 미검증 (폴백 후보) | 필요 시 재검토 |
| Docker 사용 범위 | 문서 빌드·Python 테스트 전용으로 잠정 제한, **설치 위치는 Windows PC가 아닌 별도 Linux 머신**으로 확정 (Docker 자체가 이 Windows 머신엔 미설치라 실행 검증은 못함) | 하드웨어 접근 포함/제외 최종 확정 (Linux 머신에서 실측) |
