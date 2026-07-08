"""T-802: PC 시뮬레이터 드라이버 — 백그라운드 빌드/구동/종료 및 스크린샷 캡처.

단위구현계획서.md 제5장 [T-802] 8항 구현 내용을 따른다.
T-801 스캐폴딩(`src/simulator/CMakeLists.txt`, `check_build.ps1`)의 빌드/실행
관례(build_sim/bin/lvgl_simulator(.exe), MSYS2 SDL2.dll 런타임 의존)를 그대로
재사용하여, `subprocess`로 CMake 빌드와 시뮬레이터 바이너리 백그라운드 실행/종료를
자동화하고, SDL 창 화면을 `output/<run_id>/assets/captured_sim.png`로 저장한다.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

DEFAULT_SIM_HOR_RES = 1024
DEFAULT_SIM_VER_RES = 600

# T-801 관례: build_sim/bin/lvgl_simulator(.exe)
_EXECUTABLE_NAME = "lvgl_simulator.exe" if sys.platform == "win32" else "lvgl_simulator"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SOURCE_DIR = REPO_ROOT / "src" / "simulator"
DEFAULT_BUILD_DIR = REPO_ROOT / "build_sim"

# 카드 12항: 이전 실행이 남긴 고스트 프로세스를 정리할 실행 파일 이름.
_PROCESS_IMAGE_NAME = _EXECUTABLE_NAME


class SimDriver:
    """PC(SDL2) LVGL 시뮬레이터의 빌드·구동·종료·스크린샷 캡처를 담당한다.

    T-801에서 세운 CMake 스캐폴딩(build_sim/bin/lvgl_simulator(.exe))을 그대로
    재사용하며, 이 클래스 자체는 신규 CMake/C 코드를 추가하지 않는다.
    """

    def __init__(
        self,
        source_dir: Path | str = DEFAULT_SOURCE_DIR,
        build_dir: Path | str = DEFAULT_BUILD_DIR,
        cmake_generator: str | None = "MinGW Makefiles" if sys.platform == "win32" else None,
    ) -> None:
        self.source_dir = Path(source_dir)
        self.build_dir = Path(build_dir)
        self.cmake_generator = cmake_generator
        self.process: subprocess.Popen | None = None

    @property
    def executable_path(self) -> Path:
        """T-801 관례에 따른 빌드 산출물 경로: <build_dir>/bin/lvgl_simulator(.exe)."""
        return self.build_dir / "bin" / _EXECUTABLE_NAME

    # ------------------------------------------------------------------
    # 카드 12항: 고스트 프로세스 방어적 정리
    # ------------------------------------------------------------------
    def kill_leftover_processes(self) -> bool:
        """이전 실행이 남긴 lvgl_simulator 고스트 프로세스를 강제 종료한다.

        Windows: ``taskkill /F /IM lvgl_simulator.exe``
        Linux/기타: ``pkill -f lvgl_simulator``

        대상 프로세스가 없어도 예외 없이 False를 반환한다(방어적 설계).
        """
        if sys.platform == "win32":
            result = subprocess.run(
                ["taskkill", "/F", "/IM", _PROCESS_IMAGE_NAME],
                capture_output=True,
                text=True,
            )
            killed = result.returncode == 0
        else:
            result = subprocess.run(
                ["pkill", "-f", _PROCESS_IMAGE_NAME],
                capture_output=True,
                text=True,
            )
            killed = result.returncode == 0

        if killed:
            # OS가 핸들을 완전히 회수할 시간을 잠깐 준다(파일 잠금/포트 점유 해제).
            time.sleep(0.5)
        return killed

    # ------------------------------------------------------------------
    # 빌드
    # ------------------------------------------------------------------
    def build(self) -> Path:
        """cmake configure + build를 구동해 시뮬레이터 실행 파일을 생성한다.

        빌드 시작 전 카드 12항 대처로 고스트 프로세스를 선제 정리한다(잠긴
        실행 파일을 새로 덮어쓰지 못하는 문제를 방지).

        Raises:
            RuntimeError: cmake configure/build가 실패했을 때, 어떤 단계가
                실패했는지와 원본 stderr를 포함해 명확히 알린다.
        """
        self.kill_leftover_processes()

        configure_cmd = ["cmake", "-S", str(self.source_dir), "-B", str(self.build_dir)]
        if self.cmake_generator:
            configure_cmd += ["-G", self.cmake_generator]

        configure = subprocess.run(configure_cmd, capture_output=True, text=True)
        if configure.returncode != 0:
            raise RuntimeError(
                "cmake configure 실패:\n"
                f"cmd: {' '.join(configure_cmd)}\n"
                f"stdout: {configure.stdout}\nstderr: {configure.stderr}"
            )

        build = subprocess.run(
            ["cmake", "--build", str(self.build_dir)],
            capture_output=True,
            text=True,
        )
        if build.returncode != 0:
            raise RuntimeError(
                "cmake build 실패:\n"
                f"stdout: {build.stdout}\nstderr: {build.stderr}"
            )

        if not self.executable_path.is_file():
            raise RuntimeError(
                f"빌드는 종료됐지만 실행 파일을 찾지 못했습니다: {self.executable_path}"
            )
        return self.executable_path

    # ------------------------------------------------------------------
    # 프로세스 lifecycle
    # ------------------------------------------------------------------
    def start(self) -> subprocess.Popen:
        """시뮬레이터 바이너리를 백그라운드로 기동한다.

        기동 전 카드 12항 대처로 고스트 프로세스를 선제 정리해, 이전 실행이
        남긴 인스턴스가 새 창/파일 잠금과 충돌하지 않도록 한다.
        """
        if not self.executable_path.is_file():
            raise FileNotFoundError(
                f"실행 파일이 없습니다: {self.executable_path}. 먼저 build()를 호출하세요."
            )

        self.kill_leftover_processes()

        self.process = subprocess.Popen(
            [str(self.executable_path)],
            cwd=str(self.executable_path.parent),
        )
        # SDL 창이 실제로 뜰 시간을 잠깐 준다(즉시 크래시하는 경우를 조기 감지).
        time.sleep(0.5)
        return self.process

    def is_running(self) -> bool:
        """현재 드라이버가 기동한 프로세스가 살아있는지 확인한다."""
        return self.process is not None and self.process.poll() is None

    def stop(self) -> bool:
        """기동한 시뮬레이터 프로세스를 안전하게 종료하고 자원을 해제한다.

        start() 없이 호출해도(프로세스가 없어도) 예외를 던지지 않는다(방어적 설계).
        정상 종료(terminate)가 시간 내 반영되지 않으면 강제 종료(kill)로 보강한다.

        Returns:
            실제로 종료 대상 프로세스가 있었는지 여부.
        """
        if self.process is None:
            return False

        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

        self.process = None
        return True

    # ------------------------------------------------------------------
    # 스크린샷 캡처
    # ------------------------------------------------------------------
    def make_placeholder_frame(self):
        """1024x600 크기의 합성(placeholder) 프레임을 만든다.

        헤드리스 환경 등에서 실제 SDL 창 픽셀을 가져올 수 없을 때의 대체
        경로이자, _grab_frame() 테스트 seam의 기본 구현이다.
        """
        import numpy as np

        return np.zeros((DEFAULT_SIM_VER_RES, DEFAULT_SIM_HOR_RES, 3), dtype=np.uint8)

    def _grab_frame(self):
        """SDL 창 화면 픽셀을 캡처하는 seam.

        실제 구현은 데스크톱 화면 영역을 그랩(예: PIL.ImageGrab)하는 방식으로
        동작하지만, 헤드리스/CI 환경에서는 실제 창이 없어 신뢰할 수 없다.
        테스트에서는 이 메서드를 합성 프레임을 반환하는 함수로 교체(monkeypatch)해
        capture_screenshot()의 파일 저장/포맷/경로 로직만 독립적으로 검증한다.
        """
        try:
            from PIL import ImageGrab

            img = ImageGrab.grab()
            return img.resize((DEFAULT_SIM_HOR_RES, DEFAULT_SIM_VER_RES))
        except Exception:
            return self.make_placeholder_frame()

    def capture_screenshot(self, path: Path) -> Path:
        """시뮬레이터 창 화면을 1024x600 PNG로 저장한다.

        상위 디렉토리(output/<run_id>/assets/)가 없으면 생성한다.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        from PIL import Image

        frame = self._grab_frame()
        image = frame if isinstance(frame, Image.Image) else Image.fromarray(frame)
        if image.size != (DEFAULT_SIM_HOR_RES, DEFAULT_SIM_VER_RES):
            image = image.resize((DEFAULT_SIM_HOR_RES, DEFAULT_SIM_VER_RES))
        image.save(path, format="PNG")
        return path
