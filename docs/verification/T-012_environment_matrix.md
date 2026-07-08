T-012 검증 기록 (SW부분, 2주차) — 개발·시연 OS 및 Docker 접근 범위 결정
생성 시각: 2026-07-08T16:09:13+09:00

## 범위 안내
이 문서는 단위구현계획서.md [T-012] 10항의 **2주차 SW 테스트**(`python -c "import cv2"`,
Docker 문서 빌드 확인)만 다룬다. `idf.py --version`, 카메라 프레임 획득, 시리얼 포트
인식 등 11주차 Phase HW 테스트는 이 세션의 범위가 아니며 향후
`docs/verification/T-012_hw_matrix.md`에 별도 기록한다.

## OS별 SW 검증 결과 표

| OS 후보 | cv2 임포트 | Docker 문서 빌드 검증 | 판정 |
|---|---|---|---|
| Windows 네이티브 (.venv, Python 3.13.14) | PASS | Docker 미검출 (검증 불가) | SW 부분 조건부 PASS |
| Windows 네이티브 (시스템 기본 python, 3.14.3) | FAIL (`ModuleNotFoundError: No module named 'cv2'`) | 해당 없음 | 참고용 실패 기록 (팀 표준은 .venv 3.13이므로 영향 없음) |
| WSL2 | 측정 불가 (미설치) | 측정 불가 | 보류 |
| Linux 네이티브 | 측정 불가 (이 머신에 없음) | 측정 불가 | 보류 |

## 실제 명령 출력

### 1. 팀 표준 가상환경(.venv, Python 3.13) — cv2 임포트

```
> .venv\Scripts\python.exe --version
Python 3.13.14

> .venv\Scripts\python.exe -c "import cv2; print(cv2.__version__)"
5.0.0
```

결과: **PASS**

### 2. 시스템 기본 python(3.14) — cv2 임포트 (참고/정직한 실패 기록)

```
> python --version
Python 3.14.3

> python -c "import cv2; print(cv2.__version__)"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
    import cv2
ModuleNotFoundError: No module named 'cv2'
```

결과: **FAIL** — opencv-python이 시스템 기본 인터프리터 환경에는 설치되어 있지 않음.
팀 표준 개발 환경은 `.venv`(Python 3.13, T-001 확정)이므로 이 실패는 T-012 SW 판정에
영향을 주지 않으나, "가상환경을 활성화하지 않고 실행하면 실패한다"는 12항 실패 유형의
실측 근거로 기록한다.

### 3. Docker CLI 가용성 (문서 빌드 검증의 전제 조건)

```
> docker --version
docker : 'docker' 용어가 cmdlet, 함수, 스크립트 파일 또는 실행할 수 있는 프로그램 이름으로 인식되지 않습니다.
CategoryInfo          : ObjectNotFound: (docker:String) [], CommandNotFoundException
FullyQualifiedErrorId : CommandNotFoundException
```

결과: **미검출** — 이 개발 머신에는 Docker CLI/Desktop이 설치되어 있지 않다. 따라서
"Docker 컨테이너에서 문서 빌드가 되는가"는 이번 세션에서 실행으로 검증하지 못했다.
이는 실패를 숨기지 않고 명시적으로 기록하는 정직한 결과이며,
`docs/environment_decision.md`에 TODO로 남겼다.

### 4. WSL2 가용성

```
> wsl --status
Linux용 Windows 하위 시스템이 설치되어 있지 않습니다. 'wsl --install'로 설치하십시오.
자세한 내용은 https://aka.ms/wslinstall 항목을 참조하십시오.
```

결과: **미설치** — WSL2 배포판이 없어 OS 후보로서 SW 항목을 실측할 수 없다.

### 5. pytest 실행 결과 (`tests/test_env_os_docker.py`)

```
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- D:\EdgeCanvas\.venv\Scripts\python.exe
rootdir: D:\EdgeCanvas
collected 4 items

tests/test_env_os_docker.py::test_project_venv_python_can_import_cv2 PASSED
tests/test_env_os_docker.py::test_system_default_python_cv2_import_result_is_recorded_honestly PASSED
tests/test_env_os_docker.py::test_docker_cli_availability_is_detected Docker CLI 미검출: 이 개발 머신에는 Docker가 설치되어 있지 않음 (정직한 기록).
PASSED
tests/test_env_os_docker.py::test_hw_matrix_file_is_not_created_in_sw_only_scope PASSED

============================== 4 passed in 0.59s ==============================
```

## DoD 대조 (11항, SW 부분 기준)

- [x] 공식 개발·시연 **개발** OS 1개가 문서로 확정됨 — Windows 네이티브(.venv, Python 3.13) SW 부분 확정. **단, "시연 OS" 최종 확정은 11주차 Phase HW 카메라/USB 검증 이후로 유보**된다.
- [x] Docker 사용 범위가 하드웨어 접근 포함/제외로 "잠정" 정리됨 — Docker 미설치로 실행 검증은 못했으나, 12항 원칙에 따라 "문서 빌드·Python 테스트 전용"으로 잠정 제한하고 하드웨어 접근 여부는 11주차 TODO로 명시함.
- [ ] **카메라와 보드 포트 확인 로그가 evidence로 저장됨 — OUT OF SCOPE.** 이 세션은 SW부분(2주차)만 다루며, 이 항목은 11주차 Phase HW에서 B와 함께 별도로 완료해야 한다. **이 체크박스는 이번 패스에서 체크하지 않는다.**

## 11주차 Phase HW로 이관되는 항목 (요약)

- `idf.py --version` 실행 확인
- 카메라 장치 열기 및 프레임 획득
- 보드 시리얼 포트 인식 (`list_serial_ports`)
- Docker 컨테이너의 USB 시리얼/카메라 장치 접근 가능 여부 실측 및 Docker 사용 범위 최종 확정
- WSL2/Linux 네이티브 실측 (이 머신에서 불가했던 부분)
- 결과를 `docs/verification/T-012_hw_matrix.md`에 신규 기록
