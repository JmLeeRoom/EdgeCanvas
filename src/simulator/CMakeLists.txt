# =============================================================================
# T-801 — LVGL PC(SDL2) 시뮬레이터 스캐폴딩
#
# 목적: 생성 LVGL C 코드를 PC SDL2(1024x600)에서 렌더링하는 시뮬레이터의 빌드
#       뼈대를 세운다. 이번 회차는 "빈 템플릿 UI(hello)"로 스캐폴딩만 검증한다.
#       (실제 ui_screens.c 연동은 T-303 완료 후 후속으로 붙인다.)
#
# vendoring 방침: LVGL 본체는 저장소에 대량 복사하지 않고 CMake FetchContent 로
#       빌드 시점에 lvgl/lvgl v9.x 를 내려받는다. lv_port_pc_vscode 전체를 통째로
#       가져오는 대신, 필요한 스캐폴딩(CMakeLists.txt, main.c, lv_conf.h)만 둔다.
# =============================================================================
cmake_minimum_required(VERSION 3.16)
project(lvgl_simulator C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# 실행 파일은 build_sim/bin/ 에 생성 (카드 10항 통과 기준 경로)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# --- lv_conf.h 활성화 -------------------------------------------------------
# 이 디렉토리의 lv_conf.h 를 LVGL 이 include 하도록 강제한다.
add_compile_definitions(LV_CONF_INCLUDE_SIMPLE)
add_compile_definitions(LV_CONF_PATH=${CMAKE_CURRENT_SOURCE_DIR}/lv_conf.h)

# --- SDL2 -------------------------------------------------------------------
# Windows 에서 SDL2 를 못 찾으면 CMake configure 단계에서 실패한다.
# 그 경우 README.md 의 MSYS2 설치 가이드를 따른다(카드 12항).
find_package(SDL2 QUIET)
if(NOT SDL2_FOUND)
    message(FATAL_ERROR
        "SDL2 개발 라이브러리를 찾지 못했습니다. "
        "src/simulator/README.md 의 설치 가이드(MSYS2: pacman -S mingw-w64-x86_64-SDL2, "
        "-DCMAKE_PREFIX_PATH 지정)를 따르세요.")
endif()

# --- LVGL (FetchContent, 대량 vendoring 회피) --------------------------------
include(FetchContent)
FetchContent_Declare(
    lvgl
    GIT_REPOSITORY https://github.com/lvgl/lvgl.git
    GIT_TAG        release/v9.2   # LVGL 9.x (coding-standards: 8.x 금지)
    GIT_SHALLOW    TRUE
)
FetchContent_MakeAvailable(lvgl)

# --- 시뮬레이터 실행 파일 ----------------------------------------------------
# 이번 회차 소스: main.c (hello 템플릿). T-303 이후 ui_screens.c 추가 예정:
#   list(APPEND SIM_SOURCES ${CMAKE_SOURCE_DIR}/../ui/ui_screens.c)
set(SIM_SOURCES main.c)

add_executable(lvgl_simulator ${SIM_SOURCES})

target_include_directories(lvgl_simulator PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${SDL2_INCLUDE_DIRS}
)

target_link_libraries(lvgl_simulator PRIVATE
    lvgl
    ${SDL2_LIBRARIES}
)
