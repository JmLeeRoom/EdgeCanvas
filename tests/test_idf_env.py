"""T-003: ESP-IDF v5.3+ 개발 환경 구축 — 단위 테스트.

단위구현계획서.md 제5장 [T-003] 10항 절차를 코드로 검증한다.
- Red: idf.py 미발견 fixture가 명확한 실패 메시지를 반환하는지 확인.
- Green: fixture 출력(ESP-IDF v5.3+)으로 파서·환경 진단 로직을 통과.
- 카드 12항: 파이썬 가상환경 충돌(모듈 누락) 시 install.bat 재실행 안내.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

import pytest

from src.common.idf_env import (
    DEFAULT_IDF_ROOT,
    RISCV_GCC,
    XTENSA_GCC,
    IdfCommandResult,
    diagnose_idf_environment,
    parse_idf_version,
    run_idf_version,
    suggest_venv_conflict_remediation,
)


@dataclass
class FakeProcessResult:
  returncode: int
  stdout: str
  stderr: str


def test_idf_not_found_returns_clear_failure_message():
    """Red: idf.py 미발견 시 명확한 실패 메시지를 반환해야 한다."""

    def missing_runner(_cmd: list[str]) -> IdfCommandResult:
        return IdfCommandResult(
            returncode=127,
            stdout="",
            stderr="",
            error="idf.py를 찾을 수 없습니다. scripts/export_idf_env.ps1 실행 후 다시 시도하세요.",
        )

    result = run_idf_version(runner=missing_runner)
    diagnosis = diagnose_idf_environment(
        path_entries=[],
        runner=missing_runner,
        which=shutil.which,
    )

    assert result.error is not None
    assert "idf.py" in result.error
    assert diagnosis.status == "FAIL"
    assert "idf.py" in diagnosis.message


def test_parse_idf_version_accepts_v5_3_plus():
    """Green: fixture 출력 ESP-IDF v5.3+ 를 파싱해 최소 버전을 만족해야 한다."""
    version = parse_idf_version("ESP-IDF v5.3.2")
    assert version == (5, 3, 2)

    version_patch = parse_idf_version("ESP-IDF v5.4.1")
    assert version_patch == (5, 4, 1)


def test_parse_idf_version_rejects_below_minimum():
    """5.3 미만 버전은 환경 진단에서 FAIL이어야 한다."""
    version = parse_idf_version("ESP-IDF v5.2.1")
    assert version == (5, 2, 1)

    def old_version_runner(_cmd: list[str]) -> IdfCommandResult:
        return IdfCommandResult(
            returncode=0,
            stdout="ESP-IDF v5.2.1\n",
            stderr="",
            error=None,
        )

    diagnosis = diagnose_idf_environment(
        path_entries=["C:\\fake\\xtensa-esp32-elf\\bin", "C:\\fake\\riscv32-esp-elf\\bin"],
        runner=old_version_runner,
        which=lambda name: f"C:\\fake\\{name}\\bin\\{name}.exe",
    )
    assert diagnosis.status == "FAIL"
    assert "5.3" in diagnosis.message


def test_diagnose_passes_with_fixture_idf_and_compilers_in_path():
    """보드 없이도 fixture로 PASS/FAIL을 결정할 수 있어야 한다."""

    def ok_runner(_cmd: list[str]) -> IdfCommandResult:
        return IdfCommandResult(
            returncode=0,
            stdout="ESP-IDF v5.3.2\n",
            stderr="",
            error=None,
        )

    def fake_which(name: str) -> str | None:
        if name in (XTENSA_GCC, RISCV_GCC):
            return f"C:\\Espressif\\tools\\{name}\\bin\\{name}.exe"
        return None

    diagnosis = diagnose_idf_environment(
        path_entries=[],
        runner=ok_runner,
        which=fake_which,
    )

    assert diagnosis.status == "PASS"
    assert diagnosis.idf_version == (5, 3, 2)
    assert diagnosis.xtensa_gcc_found is True
    assert diagnosis.riscv_gcc_found is True


def test_diagnose_fails_when_cross_compilers_missing_from_path():
    """DoD: Xtensa·RISC-V 크로스 컴파일러가 PATH에 없으면 FAIL."""

    def ok_runner(_cmd: list[str]) -> IdfCommandResult:
        return IdfCommandResult(
            returncode=0,
            stdout="ESP-IDF v5.3.2\n",
            stderr="",
            error=None,
        )

    diagnosis = diagnose_idf_environment(
        path_entries=[],
        runner=ok_runner,
        which=lambda _name: None,
    )

    assert diagnosis.status == "FAIL"
    assert XTENSA_GCC in diagnosis.message or "xtensa" in diagnosis.message.lower()
    assert RISCV_GCC in diagnosis.message or "riscv" in diagnosis.message.lower()


def test_python_venv_conflict_suggests_install_bat_rerun():
    """카드 12항: 모듈 누락 에러 시 install.bat 재실행을 안내해야 한다."""
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "idf.py", line 1, in <module>\n'
        "ModuleNotFoundError: No module named 'click'\n"
    )

    remediation = suggest_venv_conflict_remediation(stderr, idf_root=DEFAULT_IDF_ROOT)
    assert "install.bat" in remediation
    assert str(DEFAULT_IDF_ROOT) in remediation

    def module_error_runner(_cmd: list[str]) -> IdfCommandResult:
        return IdfCommandResult(
            returncode=1,
            stdout="",
            stderr=stderr,
            error=None,
        )

    diagnosis = diagnose_idf_environment(
        path_entries=[],
        runner=module_error_runner,
        which=lambda name: f"C:\\tools\\{name}.exe" if name in (XTENSA_GCC, RISCV_GCC) else None,
    )

    assert diagnosis.status == "FAIL"
    assert diagnosis.remediation is not None
    assert "install.bat" in diagnosis.remediation


def test_export_script_references_default_idf_root():
    """산출물: 환경변수보내기 스크립트가 기본 ESP-IDF 경로를 참조해야 한다."""
    script = (
        pytest.importorskip("pathlib").Path(__file__).resolve().parents[1]
        / "scripts"
        / "export_idf_env.ps1"
    )
    content = script.read_text(encoding="utf-8")
    assert "esp-idf-v5.3" in content
    assert "export.ps1" in content or "export.bat" in content


def test_setup_manual_documents_install_path_and_verification():
    """산출물: 셋업 매뉴얼이 설치 경로·검증 절차를 문서화해야 한다."""
    manual = (
        pytest.importorskip("pathlib").Path(__file__).resolve().parents[1]
        / "docs"
        / "setup"
        / "esp-idf-windows.md"
    )
    assert manual.is_file(), "docs/setup/esp-idf-windows.md 가 없습니다."
    content = manual.read_text(encoding="utf-8")
    assert r"C:\Espressif\frameworks\esp-idf-v5.3" in content
    assert "idf.py --version" in content
    assert XTENSA_GCC in content
    assert RISCV_GCC in content
