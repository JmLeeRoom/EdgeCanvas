# LVGL PC(SDL2) 시뮬레이터 — T-801 스캐폴딩

생성된 LVGL C 코드를 PC의 SDL2(1024×600)에서 렌더링하는 시뮬레이터 빌드 뼈대다.
자가수정 루프의 **1차 검증 엔진**(시뮬 게이트)으로 사용한다.

## 이번 회차(T-801) 범위

- **빈 템플릿 UI(hello)** 수준으로 SDL2/CMake 스캐폴딩만 검증한다.
- 실제 생성 UI(`ui_screens.c`) 연동은 **T-303 완료 후 후속 Task**에서 붙인다.
  (`CMakeLists.txt` 의 `SIM_SOURCES` 주석 참고)

## 산출물

| 파일 | 설명 |
|------|------|
| `CMakeLists.txt` | 빌드 설정. LVGL 9.x 를 FetchContent 로 내려받고 SDL2 를 링크한다. |
| `main.c` | 진입점. 1024×600 SDL 창 + hello 라벨 + 마우스 입력. |
| `lv_conf.h` | LVGL 9.x 최소 설정(SDL 백엔드 활성화). |
| `check_build.ps1` | 빌드 도구 점검 + 실제 빌드 판정 스크립트(카드 10항). |

## LVGL vendoring 방침

`lv_port_pc_vscode` 전체나 LVGL 소스를 저장소에 **통째로 복사하지 않는다**.
LVGL 9.x 본체는 `CMakeLists.txt` 의 `FetchContent` 로 빌드 시점에 `lvgl/lvgl`
(`release/v9.2`)를 내려받는다. 저장소에는 스캐폴딩 4개 파일만 둔다.

## 빌드

```powershell
cmake -S src/simulator -B build_sim
cmake --build build_sim
# 산출물: build_sim/bin/lvgl_simulator(.exe)
```

또는 판정 스크립트 사용:

```powershell
pwsh src/simulator/check_build.ps1
# exit 0 = 빌드 성공, 1 = 빌드 실패, 2 = 도구 부재로 미검증(SKIPPED)
```

> `build_sim/` 은 `.gitignore` 에 등록되어 있어 산출물은 커밋되지 않는다.

## 실행 (SDL2.dll 런타임 의존)

```powershell
& .\build_sim\bin\lvgl_simulator.exe
# 또는 파일 탐색기에서 lvgl_simulator.exe 더블클릭
```

exe 는 `SDL2.dll` 을 **동적 링크**하므로 실행 시 이 DLL 을 exe 폴더 또는 `PATH` 에서 찾는다.
없으면 Windows 가 `SDL2.dll이 없어 코드 실행을 진행할 수 없습니다` 오류 창을 띄운다.

`CMakeLists.txt` 는 빌드 후(`add_custom_command(... POST_BUILD ...)`)
`SDL2.dll` 을 출력 디렉터리(`build_sim/bin/`)로 자동 복사하므로,
정상 빌드했다면 **더블클릭만으로 실행**된다. (DLL 은 `.gitignore` 대상이라 커밋되지 않는다)

DLL 오류가 나면 다음 중 하나로 해결한다.

```powershell
# (1) 최신 CMakeLists 로 재빌드 → SDL2.dll 자동 복사
cmake --build build_sim
# (2) 수동 복사
Copy-Item C:\msys64\mingw64\bin\SDL2.dll build_sim\bin\
# (3) 실행 세션 PATH 에 MSYS2 bin 추가
$env:Path = "C:\msys64\mingw64\bin;" + $env:Path
```

## 사전 요구 도구

- CMake ≥ 3.16
- C 컴파일러(MinGW-w64 gcc 또는 clang)
- SDL2 개발 라이브러리
- git (FetchContent 로 LVGL 다운로드)

## SDL2 설치 가이드 (카드 12항 — Windows 링크 실패 대처)

Windows 에서 `find_package(SDL2)` 가 실패(`SDL2 개발 라이브러리를 찾지 못했습니다`)하면
MSYS2 로 툴체인과 SDL2 를 설치한다.

1. [MSYS2](https://www.msys2.org/) 설치 후 **MSYS2 MINGW64** 셸을 연다.
2. 패키지 설치:

```bash
pacman -Syu
pacman -S --needed \
    mingw-w64-x86_64-toolchain \
    mingw-w64-x86_64-cmake \
    mingw-w64-x86_64-SDL2
```

3. `C:\msys64\mingw64\bin` 을 `PATH` 에 추가(또는 MINGW64 셸에서 빌드).
4. CMake 가 SDL2 를 못 찾으면 prefix 를 강제 지정:

```powershell
cmake -S src/simulator -B build_sim -G "MinGW Makefiles" `
    -DCMAKE_PREFIX_PATH="C:/msys64/mingw64"
cmake --build build_sim
```

## 검증 기록

빌드/창 팝업 결과는 `docs/verification/T-801_pc_simulator_run.png`(구동 스냅샷) 및
`docs/verification/T-801_build_check.txt`(도구 점검/빌드 로그)에 저장한다.
