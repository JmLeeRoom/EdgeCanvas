# ESP32-P4 BSP 빌드 테스트 프로젝트 (T-004)

Waveshare ESP32-P4 보드용 **esp-bsp** 공식 예제를 빌드·플래시하는 Phase HW 검증 프로젝트입니다.
이 디렉터리는 소스 스캐폴딩만 저장소에 포함하며, `build/`, `sdkconfig`, `*.bin` 은 커밋하지 않습니다.

## 사전 요구 사항

1. [T-003] ESP-IDF v5.3+ 환경 (`scripts/export_idf_env.ps1`)
2. ESP32-P4 타깃 지원 IDF (v5.3+)
3. (권장) [esp-bsp](https://github.com/espressif/esp-bsp) 레포지토리 클론

## esp-bsp 예제 연동 (권장 경로)

공식 BSP 예제를 사용하려면 esp-bsp를 클론한 뒤 Waveshare/ESP32-P4 LCD 예제로 빌드합니다.

```powershell
# EdgeCanvas 루트에서
. .\scripts\export_idf_env.ps1

# esp-bsp 클론 (저장소 외부 또는 hw/ 아래, 커밋하지 않음)
git clone --recursive https://github.com/espressif/esp-bsp.git ..\esp-bsp

# 예: esp-bsp 내 ESP32-P4 / Waveshare 관련 예제 디렉터리로 이동 후
cd ..\esp-bsp\examples\display
idf.py set-target esp32p4
idf.py build
idf.py -p COM_PORT flash
```

보드별 정확한 예제 경로는 esp-bsp 릴리스 노트 및 Waveshare Wiki를 참고하세요.

## 이 저장소 스캐폴딩 프로젝트 빌드

esp-bsp 전체 클론 없이 IDF 타깃·빌드 파이프라인만 검증할 때:

```powershell
. .\scripts\export_idf_env.ps1
cd hw\esp32p4-bsp-demo
idf.py set-target esp32p4
idf.py build
idf.py -p COM_PORT flash   # 보드 연결 시
```

Python 쪽 command builder / 로그 파싱: `src/common/p4_bsp_flash.py`, `tests/test_p4_bsp_flash_plan.py`.

## COM 포트 미인식 시

장치 관리자에서 **CP210x** 또는 **CH34x** USB-UART 드라이버 설치 여부를 확인하고, 데이터 전송 가능한 USB 케이블로 교체하세요.

## 검증 기록

실기 플래시 로그: `docs/verification/T-004_flash_success.txt`
