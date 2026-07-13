"""T-004: ESP32-P4 BSP 빌드/플래시 계획 — 단위 테스트.

단위구현계획서.md 제5장 [T-004] 10항 절차를 코드로 검증한다.
- Red: idf.py build/flash command builder seam, COM 포트 미지정 시 실패.
- Green: fixture build/esptool 로그 파싱으로 성공 판정.
- 카드 12항: COM 포트 미인식 시 드라이버/케이블 안내.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.common.p4_bsp_flash import (
    ESP32P4_TARGET,
    build_idf_commands,
    diagnose_flash_plan,
    parse_build_log,
    parse_flash_log,
    suggest_com_port_remediation,
)

PROJECT_DIR = Path("hw/esp32p4-bsp-demo")

BUILD_SUCCESS_LOG = """
[100%] Built target esp32p4-bsp-demo.elf
Project build complete. To flash, run:
 idf.py flash
or
 idf.py -p PORT flash
"""

BUILD_FAILURE_LOG = """
ninja: build stopped: subcommand failed.
ninja failed with exit code 1
"""

FLASH_SUCCESS_LOG = """
esptool.py v4.8.1
Serial port COM7
Connecting....
Chip is ESP32-P4 (revision v1.0)
...
Writing at 0x00010000... (100 %)
Wrote 524288 bytes (compressed 198432) at 0x00010000 in 4.5 seconds (effective 932.1 kbit/s)...
Hash of data verified.
Leaving...
Hard resetting via RTS pin...
Done
"""

FLASH_FAILURE_LOG = """
esptool.py v4.8.1
Serial port COM7
Connecting....
A fatal error occurred: Failed to connect to ESP32-P4: No serial data received.
"""


def test_build_idf_commands_includes_set_target_and_build():
    """command builder seam: set-target esp32p4 및 build 명령을 생성해야 한다."""
    plan = build_idf_commands(PROJECT_DIR, port="COM7")

    resolved = PROJECT_DIR.resolve()
    assert plan.set_target[-2:] == ["set-target", ESP32P4_TARGET]
    assert plan.set_target[1:3] == ["-C", str(resolved)]
    assert plan.build == [plan.set_target[0], "-C", str(resolved), "build"]
    assert plan.flash == [plan.set_target[0], "-C", str(resolved), "-p", "COM7", "flash"]
    assert plan.project_dir == resolved
    assert plan.set_target[0].endswith("idf.py") or plan.set_target[0].endswith("idf.py.EXE")


def test_flash_plan_fails_when_com_port_missing():
    """Red: COM 포트 미지정 시 flash 계획이 FAIL이어야 한다."""
    plan = build_idf_commands(PROJECT_DIR, port=None)
    assert plan.flash is None

    diagnosis = diagnose_flash_plan(port=None, project_dir=PROJECT_DIR)
    assert diagnosis.status == "FAIL"
    assert "COM" in diagnosis.message or "포트" in diagnosis.message
    assert diagnosis.remediation is not None


def test_parse_build_log_accepts_success_fixture():
    """Green: fixture build log로 빌드 성공을 판정해야 한다."""
    assert parse_build_log(BUILD_SUCCESS_LOG) is True
    assert parse_build_log(BUILD_FAILURE_LOG) is False


def test_parse_flash_log_accepts_esptool_progress_fixture():
    """Green: esptool progress fixture로 플래시 성공을 판정해야 한다."""
    assert parse_flash_log(FLASH_SUCCESS_LOG) is True
    assert parse_flash_log(FLASH_FAILURE_LOG) is False


def test_com_port_not_recognized_suggests_driver_and_cable_remediation():
    """카드 12항: COM 포트 미인식 시 CP210x/CH34x 드라이버·케이블 안내."""
    remediation = suggest_com_port_remediation()
    assert "CP210" in remediation or "CH34" in remediation
    assert "USB" in remediation or "케이블" in remediation

    diagnosis = diagnose_flash_plan(port="", project_dir=PROJECT_DIR)
    assert diagnosis.status == "FAIL"
    assert diagnosis.remediation is not None
    assert "CP210" in diagnosis.remediation or "CH34" in diagnosis.remediation


def test_diagnose_flash_plan_passes_with_valid_port_and_project():
    """유효한 COM 포트와 프로젝트 경로면 flash 계획이 PASS여야 한다."""
    diagnosis = diagnose_flash_plan(port="COM7", project_dir=PROJECT_DIR)
    assert diagnosis.status == "PASS"
    assert diagnosis.flash_commands is not None
    assert "-p" in diagnosis.flash_commands
    assert "COM7" in diagnosis.flash_commands


def test_diagnose_flash_plan_fails_when_project_dir_missing():
    """프로젝트 디렉터리가 없으면 FAIL이어야 한다."""
    missing = Path("hw/nonexistent-p4-project")
    diagnosis = diagnose_flash_plan(port="COM7", project_dir=missing)
    assert diagnosis.status == "FAIL"
    assert "프로젝트" in diagnosis.message or str(missing) in diagnosis.message


def test_hw_project_readme_exists():
    """산출물: ESP32-P4 빌드 테스트 프로젝트 README가 존재해야 한다."""
    readme = (
        pytest.importorskip("pathlib").Path(__file__).resolve().parents[1]
        / "hw"
        / "esp32p4-bsp-demo"
        / "README.md"
    )
    assert readme.is_file(), "hw/esp32p4-bsp-demo/README.md 가 없습니다."
    content = readme.read_text(encoding="utf-8")
    assert "esp32p4" in content.lower()
    assert "esp-bsp" in content.lower() or "idf.py" in content
