"""T-003: ESP-IDF v5.3+ 개발 환경 진단 모듈.

단위구현계획서.md 제5장 [T-003] 8~12항을 코드로 지원한다.
보드 없이도 `idf.py --version` 및 크로스 컴파일러 PATH 연동 여부로 PASS/FAIL을 판정한다.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

DEFAULT_IDF_ROOT = Path(r"C:\Espressif\frameworks\esp-idf-v5.3")
MIN_IDF_VERSION = (5, 3, 0)

XTENSA_GCC = "xtensa-esp32-elf-gcc"
RISCV_GCC = "riscv32-esp-elf-gcc"

_IDF_VERSION_RE = re.compile(r"ESP-IDF\s+v(\d+)\.(\d+)(?:\.(\d+))?", re.IGNORECASE)
_MODULE_MISSING_RE = re.compile(r"ModuleNotFoundError:\s+No module named", re.IGNORECASE)

Runner = Callable[[list[str]], "IdfCommandResult"]
WhichFn = Callable[[str], str | None]


@dataclass(frozen=True)
class IdfCommandResult:
    returncode: int
    stdout: str
    stderr: str
    error: str | None = None


@dataclass(frozen=True)
class DiagnosisResult:
    status: Literal["PASS", "FAIL"]
    message: str
    idf_version: tuple[int, int, int] | None = None
    xtensa_gcc_found: bool = False
    riscv_gcc_found: bool = False
    remediation: str | None = None


def parse_idf_version(output: str) -> tuple[int, int, int] | None:
    """`idf.py --version` stdout에서 ESP-IDF 버전 튜플을 추출한다."""
    match = _IDF_VERSION_RE.search(output)
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def _version_meets_minimum(version: tuple[int, int, int]) -> bool:
    return version >= MIN_IDF_VERSION


def suggest_venv_conflict_remediation(stderr: str, idf_root: Path = DEFAULT_IDF_ROOT) -> str | None:
    """카드 12항: 파이썬 가상환경 충돌(모듈 누락) 시 install.bat 재실행 안내."""
    if not _MODULE_MISSING_RE.search(stderr):
        return None
    install_bat = idf_root / "install.bat"
    return (
        "ESP-IDF 전용 파이썬 환경이 손상되었거나 프로젝트 venv와 충돌한 것으로 보입니다. "
        f"`{install_bat}` 을 관리자 권한 없이 재실행한 뒤 "
        f"`scripts/export_idf_env.ps1` 로 환경을 다시보내세요."
    )


def default_runner(cmd: list[str]) -> IdfCommandResult:
    """실제 subprocess로 idf.py를 호출하는 기본 runner(seam 기본 구현)."""
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return IdfCommandResult(
            returncode=127,
            stdout="",
            stderr="",
            error=(
                "idf.py를 찾을 수 없습니다. "
                "ESP-IDF 설치 후 `scripts/export_idf_env.ps1` 을 실행하거나 "
                f"`{DEFAULT_IDF_ROOT}` 의 export.ps1/export.bat을 소싱하세요."
            ),
        )
    except subprocess.TimeoutExpired:
        return IdfCommandResult(
            returncode=124,
            stdout="",
            stderr="",
            error="idf.py --version 실행이 시간 초과되었습니다.",
        )

    return IdfCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        error=None,
    )


def run_idf_version(
    idf_py: str = "idf.py",
    runner: Runner | None = None,
) -> IdfCommandResult:
    """`idf.py --version` 실행을 subprocess seam으로 감싼다."""
    execute = runner or default_runner
    return execute([idf_py, "--version"])


def _compiler_on_path(which: WhichFn, compiler_name: str) -> bool:
    return which(compiler_name) is not None


def diagnose_idf_environment(
    path_entries: list[str] | None = None,
    runner: Runner | None = None,
    which: WhichFn | None = None,
    idf_root: Path = DEFAULT_IDF_ROOT,
) -> DiagnosisResult:
    """보드 없이 ESP-IDF 툴체인 환경을 PASS/FAIL로 진단한다.

  path_entries는 테스트용 PATH 오버라이드 훅이며, 실제 호출 시에는 shutil.which가
  현재 프로세스 PATH를 사용한다.
    """
    del path_entries  # reserved for future PATH-scoped checks; compilers use `which` seam.

    lookup = which or shutil.which
    xtensa_found = _compiler_on_path(lookup, XTENSA_GCC)
    riscv_found = _compiler_on_path(lookup, RISCV_GCC)

    cmd_result = run_idf_version(runner=runner)

    if cmd_result.error:
        return DiagnosisResult(
            status="FAIL",
            message=cmd_result.error,
            xtensa_gcc_found=xtensa_found,
            riscv_gcc_found=riscv_found,
        )

    combined_output = f"{cmd_result.stdout}\n{cmd_result.stderr}"
    remediation = suggest_venv_conflict_remediation(cmd_result.stderr, idf_root=idf_root)

    if cmd_result.returncode != 0:
        message = (
            remediation
            or f"idf.py --version 이 실패했습니다 (exit {cmd_result.returncode})."
        )
        if cmd_result.stderr.strip():
            message = f"{message} stderr: {cmd_result.stderr.strip()}"
        return DiagnosisResult(
            status="FAIL",
            message=message,
            xtensa_gcc_found=xtensa_found,
            riscv_gcc_found=riscv_found,
            remediation=remediation,
        )

    version = parse_idf_version(combined_output)
    if version is None:
        return DiagnosisResult(
            status="FAIL",
            message="idf.py --version 출력에서 ESP-IDF 버전을 파싱할 수 없습니다.",
            xtensa_gcc_found=xtensa_found,
            riscv_gcc_found=riscv_found,
        )

    if not _version_meets_minimum(version):
        return DiagnosisResult(
            status="FAIL",
            message=f"ESP-IDF v{version[0]}.{version[1]}.{version[2]} 은 최소 v5.3 미만입니다.",
            idf_version=version,
            xtensa_gcc_found=xtensa_found,
            riscv_gcc_found=riscv_found,
        )

    missing_compilers: list[str] = []
    if not xtensa_found:
        missing_compilers.append(XTENSA_GCC)
    if not riscv_found:
        missing_compilers.append(RISCV_GCC)

    if missing_compilers:
        return DiagnosisResult(
            status="FAIL",
            message=(
                "크로스 컴파일러가 PATH에 없습니다: "
                + ", ".join(missing_compilers)
                + ". `scripts/export_idf_env.ps1` 실행 후 터미널을 재시작하세요."
            ),
            idf_version=version,
            xtensa_gcc_found=xtensa_found,
            riscv_gcc_found=riscv_found,
        )

    return DiagnosisResult(
        status="PASS",
        message=(
            f"ESP-IDF v{version[0]}.{version[1]}.{version[2]} 및 "
            f"{XTENSA_GCC}, {RISCV_GCC} PATH 연동이 확인되었습니다."
        ),
        idf_version=version,
        xtensa_gcc_found=xtensa_found,
        riscv_gcc_found=riscv_found,
    )
