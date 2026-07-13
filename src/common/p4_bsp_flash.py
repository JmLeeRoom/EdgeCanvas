"""T-004: ESP32-P4 BSP 빌드/플래시 계획 및 로그 파싱 모듈.

단위구현계획서.md 제5장 [T-004] 8~12항을 코드로 지원한다.
보드 없이도 command builder seam과 fixture 로그 파싱으로 PASS/FAIL을 판정한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.common.idf_env import resolve_idf_py

ESP32P4_TARGET = "esp32p4"

_BUILD_SUCCESS_RE = re.compile(r"Project build complete", re.IGNORECASE)
_BUILD_FAILURE_RE = re.compile(
    r"ninja failed with exit code|build stopped: subcommand failed",
    re.IGNORECASE,
)
_FLASH_SUCCESS_RE = re.compile(
    r"Hash of data verified",
    re.IGNORECASE,
)
_FLASH_PROGRESS_RE = re.compile(
    r"Writing at 0x[0-9a-fA-F]+\.\.\.\s*\(\s*100\s*%\s*\)",
    re.IGNORECASE,
)
_FLASH_FAILURE_RE = re.compile(
    r"fatal error occurred|Failed to connect",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IdfBuildFlashPlan:
    """idf.py set-target / build / flash 명령 계획."""

    project_dir: Path
    set_target: list[str]
    build: list[str]
    flash: list[str] | None = None


@dataclass(frozen=True)
class FlashDiagnosisResult:
    status: Literal["PASS", "FAIL"]
    message: str
    remediation: str | None = None
    set_target_commands: list[str] | None = None
    build_commands: list[str] | None = None
    flash_commands: list[str] | None = None


def suggest_com_port_remediation() -> str:
    """카드 12항: COM 포트 미인식 시 드라이버·케이블 점검 안내."""
    return (
        "장치 관리자에서 CP210x 또는 CH34x USB-UART 드라이버가 정상 설치되어 있는지 확인하세요. "
        "드라이버가 설치되어 있어도 인식되지 않으면 USB 케이블(데이터 전송 지원)을 교체하거나 "
        "다른 USB 포트에 연결한 뒤 `idf.py -p COM_PORT flash` 를 다시 시도하세요."
    )


def _normalize_project_dir(project_dir: Path | str) -> Path:
    return Path(project_dir).resolve()


def _is_valid_port(port: str | None) -> bool:
    if port is None:
        return False
    return bool(port.strip())


def build_idf_commands(
    project_dir: Path | str,
    port: str | None = None,
    idf_py: str = "idf.py",
) -> IdfBuildFlashPlan:
    """`idf.py set-target esp32p4`, `build`, `flash` 명령 목록을 생성한다.

    COM 포트가 없으면 flash 명령은 None이다 (flash는 포트 필수).
    """
    resolved_dir = _normalize_project_dir(project_dir)
    resolved_idf = resolve_idf_py(idf_py)
    project_flag = ["-C", str(resolved_dir)]

    set_target = [resolved_idf, *project_flag, "set-target", ESP32P4_TARGET]
    build = [resolved_idf, *project_flag, "build"]
    flash: list[str] | None = None
    if _is_valid_port(port):
        flash = [resolved_idf, *project_flag, "-p", port.strip(), "flash"]

    return IdfBuildFlashPlan(
        project_dir=resolved_dir,
        set_target=set_target,
        build=build,
        flash=flash,
    )


def parse_build_log(log: str) -> bool:
    """ESP-IDF 빌드 로그에서 성공 여부를 판정한다."""
    if _BUILD_FAILURE_RE.search(log):
        return False
    return bool(_BUILD_SUCCESS_RE.search(log))


def parse_flash_log(log: str) -> bool:
    """esptool 플래시 로그에서 성공 여부를 판정한다."""
    if _FLASH_FAILURE_RE.search(log):
        return False
    has_verified = bool(_FLASH_SUCCESS_RE.search(log))
    has_progress = bool(_FLASH_PROGRESS_RE.search(log))
    return has_verified and has_progress


def diagnose_flash_plan(
    port: str | None,
    project_dir: Path | str,
) -> FlashDiagnosisResult:
    """COM 포트와 프로젝트 경로로 flash 계획 PASS/FAIL을 진단한다."""
    resolved_dir = _normalize_project_dir(project_dir)
    remediation = suggest_com_port_remediation()

    if not resolved_dir.is_dir():
        return FlashDiagnosisResult(
            status="FAIL",
            message=f"ESP32-P4 프로젝트 디렉터리를 찾을 수 없습니다: {resolved_dir}",
            remediation=None,
        )

    if not _is_valid_port(port):
        return FlashDiagnosisResult(
            status="FAIL",
            message=(
                "플래시에 필요한 COM 포트가 지정되지 않았거나 인식되지 않았습니다. "
                "Waveshare ESP32-P4 보드를 USB로 연결한 뒤 장치 관리자에서 COM 포트 번호를 확인하세요."
            ),
            remediation=remediation,
        )

    plan = build_idf_commands(resolved_dir, port=port)
    if plan.flash is None:
        return FlashDiagnosisResult(
            status="FAIL",
            message="flash 명령을 생성할 수 없습니다. COM 포트를 확인하세요.",
            remediation=remediation,
        )

    return FlashDiagnosisResult(
        status="PASS",
        message=f"ESP32-P4 flash 계획이 준비되었습니다 (포트: {port.strip()}, 프로젝트: {resolved_dir}).",
        set_target_commands=plan.set_target,
        build_commands=plan.build,
        flash_commands=plan.flash,
    )
