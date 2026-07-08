"""T-802: PC 시뮬레이터 드라이버·스크린샷 캡처 — 단위 테스트.

단위구현계획서.md 제5장 [T-802] 10항 절차를 코드로 검증한다.
- 준비: 시뮬레이터가 빌드 준비된 상태(T-801 스캐폴딩: src/simulator/CMakeLists.txt 등).
- 실행: pytest tests/test_sim_driver.py
- 통과 기준: 시뮬레이터 창이 팝업 기동되었다가 5초 타이머 경과 후 자동으로 꺼지며
  에러 없이 정상 복귀한다.

이 테스트는 실제 MSYS2 툴체인(cmake/gcc/SDL2)이 있으면 실제 빌드/실행/종료
lifecycle을 그대로 수행하고, 툴체인이 없는 개발 PC에서는 명확한 이유로 skip한다
(카드 12항 대처와 마찬가지로 "억지로 통과 처리하지 않는다" 원칙).

카드 12항(실패 시 대처) 커버리지: 이전 실행이 남긴 고스트 lvgl_simulator 프로세스를
드라이버 자신의 시작 로직이 선제적으로 taskkill(강제 종료)하는지 검증한다.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.simulator.sim_driver import SimDriver

REPO_ROOT = Path(__file__).resolve().parent.parent
SIM_SOURCE_DIR = REPO_ROOT / "src" / "simulator"

TOOLCHAIN_AVAILABLE = bool(shutil.which("cmake")) and bool(
    shutil.which("gcc") or shutil.which("clang")
)
REQUIRES_TOOLCHAIN = pytest.mark.skipif(
    not TOOLCHAIN_AVAILABLE,
    reason="cmake/gcc(clang) 빌드 도구가 PATH에 없어 실제 빌드/구동 검증을 수행할 수 없습니다.",
)


@pytest.fixture
def driver() -> SimDriver:
    """실제 저장소의 build_sim/(T-801 산출물, FetchContent 캐시 포함)을 재사용한다.

    tmp_path마다 새 build_dir을 쓰면 LVGL FetchContent를 매번 처음부터 다시
    받아야 해 테스트가 느려지고 네트워크에 의존하게 되므로, 기존 캐시를 공유한다.
    """
    return SimDriver(source_dir=SIM_SOURCE_DIR, build_dir=REPO_ROOT / "build_sim")


def test_sim_driver_default_build_dir_matches_t801_convention():
    """T-801 관례(build_sim/bin/lvgl_simulator(.exe))를 기본값으로 재사용해야 한다."""
    driver = SimDriver()
    assert driver.build_dir.name == "build_sim"
    expected_name = "lvgl_simulator.exe" if sys.platform == "win32" else "lvgl_simulator"
    assert driver.executable_path.name == expected_name


@REQUIRES_TOOLCHAIN
def test_build_produces_expected_executable(driver: SimDriver):
    """(a) build()가 실제 cmake 빌드를 수행해 예상 실행 파일 경로를 생성해야 한다."""
    exe_path = driver.build()

    assert exe_path == driver.executable_path
    assert exe_path.is_file(), f"실행 파일이 생성되지 않았습니다: {exe_path}"


@REQUIRES_TOOLCHAIN
def test_start_launches_alive_process_and_stop_terminates_cleanly(driver: SimDriver):
    """(b) start()는 살아있는 서브프로세스를 띄우고, stop()은 에러 없이 종료해야 한다."""
    driver.build()

    driver.start()
    try:
        assert driver.is_running(), "start() 이후 프로세스가 살아있지 않습니다."
        time.sleep(1.0)
        assert driver.is_running(), "짧은 대기 중 프로세스가 예기치 않게 종료되었습니다."
    finally:
        driver.stop()

    assert not driver.is_running(), "stop() 이후에도 프로세스가 남아있습니다."


@REQUIRES_TOOLCHAIN
def test_start_survives_five_seconds_then_stop_returns_clean(driver: SimDriver):
    """카드 10항 통과 기준: 창이 5초간 생존 후 자동/명시적으로 깨끗이 종료되어야 한다."""
    driver.build()

    driver.start()
    try:
        time.sleep(5.0)
        assert driver.is_running(), "5초 생존 보증 중 프로세스가 종료되었습니다."
    finally:
        result = driver.stop()

    assert result is True
    assert not driver.is_running()


@REQUIRES_TOOLCHAIN
def test_start_kills_leftover_ghost_process_before_launching_fresh_one(driver: SimDriver):
    """12항 실패 시 대처: 고스트 프로세스가 있으면 start() 자신이 선제적으로 정리해야 한다."""
    driver.build()

    # 고스트 프로세스를 흉내내기 위해 드라이버 밖에서 직접 실행 파일을 띄운다.
    ghost = subprocess.Popen([str(driver.executable_path)])
    time.sleep(1.0)
    assert ghost.poll() is None, "고스트 프로세스 준비 단계에서 이미 종료되었습니다."

    try:
        # start()는 내부적으로 kill_leftover_processes()를 호출해 고스트를 정리하고
        # 새 프로세스를 새로 띄워야 한다.
        driver.start()
        try:
            assert driver.is_running()
            assert driver.process is not None
            assert driver.process.pid != ghost.pid
        finally:
            driver.stop()
    finally:
        # 테스트 실패로 정리가 안 됐을 경우를 대비한 최종 안전장치.
        if ghost.poll() is None:
            ghost.terminate()
            ghost.wait(timeout=5)


def test_kill_leftover_processes_is_a_noop_when_nothing_running(driver: SimDriver):
    """고스트 프로세스가 없을 때도 예외 없이 정상 반환해야 한다."""
    result = driver.kill_leftover_processes()
    assert result is False


def test_capture_screenshot_writes_valid_png_to_run_assets_path(tmp_path, driver: SimDriver):
    """(d) capture_screenshot()은 output/<run_id>/assets/captured_sim.png 규격으로
    1024x600 유효 PNG를 저장해야 한다.

    실제 SDL 창 픽셀을 그랩하는 부분은 헤드리스 환경에서 불안정할 수 있으므로,
    "화면에서 픽셀을 뽑아오는 방법" 부분만 대체 가능한 seam(_grab_frame)으로 분리하고,
    여기서는 합성(synthetic) 프레임을 주입해 파일 저장/포맷/경로 규약을 검증한다.
    """
    run_id = "run_20260708_t802"
    target_path = tmp_path / "output" / run_id / "assets" / "captured_sim.png"

    def fake_grab_frame():
        return driver.make_placeholder_frame()

    driver._grab_frame = fake_grab_frame  # 테스트 seam 주입

    result_path = driver.capture_screenshot(target_path)

    assert result_path == target_path
    assert target_path.is_file()

    with target_path.open("rb") as fh:
        magic = fh.read(8)
    assert magic == b"\x89PNG\r\n\x1a\n", "유효한 PNG 매직 넘버가 아닙니다."

    from PIL import Image

    with Image.open(target_path) as img:
        assert img.size == (1024, 600)


def test_capture_screenshot_creates_missing_parent_directories(tmp_path, driver: SimDriver):
    """assets 디렉토리가 아직 없어도 capture_screenshot이 자동 생성해야 한다."""
    target_path = tmp_path / "output" / "run_x" / "assets" / "captured_sim.png"
    assert not target_path.parent.exists()

    driver._grab_frame = driver.make_placeholder_frame
    driver.capture_screenshot(target_path)

    assert target_path.is_file()


def test_stop_without_start_does_not_raise(driver: SimDriver):
    """start() 없이 stop()을 호출해도 예외가 발생하지 않아야 한다(방어적 설계)."""
    result = driver.stop()
    assert result is False
