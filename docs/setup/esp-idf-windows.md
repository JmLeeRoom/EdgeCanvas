# ESP-IDF v5.3+ Windows 개발 환경 셋업 매뉴얼 (T-003)

Phase HW(10주차) 전용. M2 시뮬 게이트 통과 후 ESP32-P4/S3 펌웨어 빌드·플래시를 위해 ESP-IDF 툴체인을 구축한다.

## 1. 사전 조건

- Windows 10/11 64-bit
- 관리자 권한(설치 시에만 필요할 수 있음)
- 디스크 여유 공간 약 3GB 이상(툴체인 포함)
- EdgeCanvas Python `.venv`는 **에이전트/CLI 전용**이며, ESP-IDF는 **별도 Espressif Python 환경**을 사용한다. 두 venv를 섞지 말 것.

## 2. ESP-IDF v5.3 설치

1. [Espressif ESP-IDF Windows 설치 가이드 (v5.3)](https://docs.espressif.com/projects/esp-idf/en/v5.3/esp32/get-started/windows-setup.html)에서 **ESP-IDF v5.3 Windows Installer**를 다운로드한다.
2. 설치 마법사에서 설치 경로를 아래로 **고정**한다.

   ```
   C:\Espressif\frameworks\esp-idf-v5.3
   ```

3. 설치가 끝나면 동일 디렉터리에서 `install.bat`이 이미 실행되었는지 확인한다. 중단되었거나 오류가 있었다면 해당 폴더에서 `install.bat`을 다시 실행한다.

## 3. 환경변수보내기 (매 터미널 세션)

저장소 루트에서 PowerShell을 연 뒤:

```powershell
. .\scripts\export_idf_env.ps1
```

이 스크립트는 `C:\Espressif\frameworks\esp-idf-v5.3\export.ps1`(또는 `export.bat`)을 호출해 `IDF_PATH`와 크로스 컴파일러 PATH를 현재 세션에 바인딩한다.

### 쉘 프로필에 영구 등록 (선택)

매번 수동 dot-source 하지 않으려면 PowerShell 프로필(`$PROFILE`)에 다음을 추가한다.

```powershell
. D:\EdgeCanvas\scripts\export_idf_env.ps1
```

경로는 실제 EdgeCanvas 클론 위치에 맞게 수정한다.

## 4. 검증 절차

### 4.1 idf.py 버전

```powershell
idf.py --version
```

기대 출력 예: `ESP-IDF v5.3.x` (5.3 이상)

### 4.2 크로스 컴파일러 PATH

```powershell
xtensa-esp32-elf-gcc --version
riscv32-esp-elf-gcc --version
```

둘 다 버전 문자열이 출력되어야 한다.

### 4.3 자동 진단 (보드 불필요)

```powershell
python -m pytest tests/test_idf_env.py -v
```

또는 Python에서:

```python
from src.common.idf_env import diagnose_idf_environment
print(diagnose_idf_environment())
```

`status`가 `PASS`이면 DoD 충족 가능 상태이다.

### 4.4 검증 기록

실환경 `idf.py --version` 로그는 `docs/verification/T-003_idf_env_log.txt`에 저장한다.

## 5. 실패 시 대처

### idf.py를 찾을 수 없음

- `scripts/export_idf_env.ps1`을 dot-source 했는지 확인
- 터미널을 닫았다가 다시 열고 export 재실행
- `C:\Espressif\frameworks\esp-idf-v5.3` 설치 여부 확인

### ModuleNotFoundError (파이썬 venv 충돌)

EdgeCanvas `.venv`가 활성화된 상태에서 `idf.py`를 실행하면 ESP-IDF 전용 패키지가 누락될 수 있다.

**대처:**

1. EdgeCanvas `.venv` 비활성화 (`deactivate`)
2. `C:\Espressif\frameworks\esp-idf-v5.3\install.bat` 재실행
3. `scripts/export_idf_env.ps1` 다시 dot-source
4. `idf.py --version` 재시도

### 크로스 컴파일러 미검출

- export 스크립트가 성공했는지 확인
- `echo $env:PATH`에 `xtensa-esp32-elf` 및 `riscv32-esp-elf` 경로가 포함되는지 확인
- 필요 시 ESP-IDF Tools 설치를 `install.bat`으로 복구

## 6. 관련 산출물

| 파일 | 용도 |
|------|------|
| `scripts/export_idf_env.ps1` | 환경변수보내기 |
| `src/common/idf_env.py` | PASS/FAIL 환경 진단 로직 |
| `tests/test_idf_env.py` | subprocess seam 단위 테스트 |
| `docs/verification/T-003_idf_env_log.txt` | 실환경 검증 로그 |

## 7. 다음 Task

T-004(ESP32-P4 BSP 예제 빌드·플래시) 착수 전 본 매뉴얼의 검증 절차를 모두 통과해야 한다.
