"""T-901: Typer CLI 시뮬 E2E 파이프라인 통합 테스트.

단위구현계획서 / Task27 [T-901]:
- Red: PDF/요구사항 누락, sim_driver 실패, Vision FAIL → 실패 리포트
- Green: fake API/LLM/HW + T-802 스크린샷 fixture + T-603/604 판정 → 5회 이내 PASS
- 카드 12: sim_driver 캡처 렌더 대기 5초 마진
- 외부 live API는 별도 marker로 분리
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.simulator.sim_driver import SimDriver

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "tests" / "data"
UI_MISPLACED = DATA_DIR / "ui_misplaced.png"
LAYOUT_JSON = DATA_DIR / "ui_layout_expected.json"
SAMPLE_PDF = DATA_DIR / "p4_datasheet_sample.pdf"
UI_SCREENS_C = DATA_DIR / "ui_screens.c"
VERIFY_JSON = REPO_ROOT / "docs" / "verification" / "T-901_e2e_pass_report.json"
SIM_ROUND_MAX = 5

REQUIRES_LIVE_API = pytest.mark.skipif(
    True,
    reason="T-901: 외부 live API는 별도 스위트 — 기본 E2E는 fake adapter만 사용",
)

runner = CliRunner()


def _write_spec(tmp_path: Path) -> Path:
    spec = tmp_path / "requirements.txt"
    spec.write_text("P10 HMI: header + OK/Cancel buttons\n", encoding="utf-8")
    return spec


def _pdf_path() -> Path:
    if SAMPLE_PDF.is_file():
        return SAMPLE_PDF
    alt = DATA_DIR / "esp32-p4_datasheet_en.pdf"
    assert alt.is_file(), "tests/data PDF fixture missing"
    return alt


@pytest.fixture
def e2e_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """산출물을 tmp output에 모은다."""
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setenv("P10_OUTPUT_DIR", str(out))
    monkeypatch.chdir(tmp_path)
    return out


def test_missing_pdf_writes_fail_report(e2e_env: Path, tmp_path: Path):
    """Red: PDF 누락 시 실패 리포트(또는 명확한 실패 종료)를 남긴다."""
    spec = _write_spec(tmp_path)
    result = runner.invoke(
        app,
        [
            "run",
            "--mode",
            "sim",
            "--pdf-path",
            str(tmp_path / "missing_datasheet.pdf"),
            "--spec-path",
            str(spec),
            "--target",
            "esp32-p4",
        ],
    )
    assert result.exit_code != 0
    reports = list(e2e_env.glob("*/report.md"))
    assert reports, "누락 입력 시 output/<run_id>/report.md 실패 리포트가 있어야 한다"
    content = reports[0].read_text(encoding="utf-8")
    assert "# HMI Verification Report" in content
    assert "FAIL" in content


def test_missing_spec_writes_fail_report(e2e_env: Path, tmp_path: Path):
    """Red: 요구사항 파일 누락 시 실패 리포트."""
    pdf = tmp_path / "sheet.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy")
    result = runner.invoke(
        app,
        [
            "run",
            "--mode",
            "sim",
            "--pdf-path",
            str(pdf),
            "--spec-path",
            str(tmp_path / "missing_spec.txt"),
            "--target",
            "esp32-p4",
        ],
    )
    assert result.exit_code != 0
    reports = list(e2e_env.glob("*/report.md"))
    assert reports
    assert "FAIL" in reports[0].read_text(encoding="utf-8")


def test_sim_driver_failure_writes_fail_report(
    e2e_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Red: sim_driver/캡처 실패 시 FAIL 리포트."""
    from src.cli import main as cli_main

    def boom_factory(**_kwargs: Any):
        from src.agent.orchestrator import OrchestratorMocks

        def capture_fail(path: Path) -> Path:
            raise RuntimeError("sim_driver capture failed: SDL window not ready")

        return OrchestratorMocks(
            parse_datasheet=lambda _s: {"chunks": ["ok"]},
            generate_code=lambda _s: {"code": "void ui_init(void) {}"},
            capture_screenshot=capture_fail,
            vision_judge=lambda _p: {"passed": True, "widget_error_pct": 0.0},
            build_and_flash=lambda _s: {"flash_ok": True},
            capture_physical=lambda _s: {},
            physical_judge=lambda _s: {"passed": True},
            output_dir=e2e_env,
        )

    monkeypatch.setattr(cli_main, "build_sim_e2e_mocks", boom_factory)

    spec = _write_spec(tmp_path)
    result = runner.invoke(
        app,
        [
            "run",
            "--mode",
            "sim",
            "--pdf-path",
            str(_pdf_path()),
            "--spec-path",
            str(spec),
            "--target",
            "esp32-p4",
        ],
    )
    assert result.exit_code != 0
    reports = list(e2e_env.glob("*/report.md"))
    assert reports
    content = reports[0].read_text(encoding="utf-8")
    assert "FAIL" in content
    assert "# HMI Verification Report" in content


def test_vision_fail_fixture_writes_fail_report(
    e2e_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Red: Vision FAIL fixture → FAIL 리포트 (5라운드 내 종료)."""
    from src.cli import main as cli_main
    from src.agent.orchestrator import OrchestratorMocks
    from src.verifier.vision_evaluator import (
        SimCaptureProvider,
        WidgetLocationEvaluator,
    )

    layout = json.loads(LAYOUT_JSON.read_text(encoding="utf-8"))
    evaluator = WidgetLocationEvaluator(layout, tolerance=0.05)

    def factory(**_kwargs: Any):
        def capture(path: Path) -> Path:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(UI_MISPLACED.read_bytes())
            return path

        def vision_judge(image_path: Path) -> dict[str, Any]:
            result = evaluator.evaluate(SimCaptureProvider(image_path))
            passed = result.get("verdict") == "PASS"
            return {
                "passed": passed,
                "widget_error_pct": 0.0 if passed else 25.0,
                "details": result,
            }

        return OrchestratorMocks(
            parse_datasheet=lambda _s: {"chunks": ["ok"]},
            generate_code=lambda _s: {
                "code": UI_SCREENS_C.read_text(encoding="utf-8")
                if UI_SCREENS_C.is_file()
                else "void ui_init(void) {}"
            },
            capture_screenshot=capture,
            vision_judge=vision_judge,
            build_and_flash=lambda _s: {"flash_ok": True},
            capture_physical=lambda _s: {},
            physical_judge=lambda _s: {"passed": True},
            output_dir=e2e_env,
        )

    monkeypatch.setattr(cli_main, "build_sim_e2e_mocks", factory)

    spec = _write_spec(tmp_path)
    result = runner.invoke(
        app,
        [
            "run",
            "--mode",
            "sim",
            "--pdf-path",
            str(_pdf_path()),
            "--spec-path",
            str(spec),
            "--target",
            "esp32-p4",
        ],
    )
    assert result.exit_code != 0
    reports = list(e2e_env.glob("*/report.md"))
    assert reports
    content = reports[0].read_text(encoding="utf-8")
    assert "FAIL" in content
    assert "**sim_round**" in content or "sim_round" in content.lower()
    checkpoint = json.loads((reports[0].parent / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint.get("verdict") == "FAIL"
    assert int(checkpoint.get("sim_round", 99)) <= SIM_ROUND_MAX


def test_sim_e2e_pass_within_5_rounds(e2e_env: Path, tmp_path: Path):
    """Green: fake adapters + T-802 PNG + T-603/604 → 5회 이내 PASS 리포트."""
    spec = _write_spec(tmp_path)
    result = runner.invoke(
        app,
        [
            "run",
            "--mode",
            "sim",
            "--pdf-path",
            str(_pdf_path()),
            "--spec-path",
            str(spec),
            "--target",
            "esp32-p4",
        ],
    )
    assert result.exit_code == 0, result.output
    run_dirs = [p for p in e2e_env.iterdir() if p.is_dir()]
    assert run_dirs, "output/<run_id>/ 가 생성되어야 한다"
    run_dir = run_dirs[0]
    report = run_dir / "report.md"
    assert report.is_file()
    content = report.read_text(encoding="utf-8")
    assert "# HMI Verification Report" in content
    assert "PASS" in content
    assert (run_dir / "assets" / "captured_sim.png").is_file()
    assert (run_dir / "generated_ui_screens.c").is_file()
    checkpoint_path = run_dir / "checkpoint.json"
    assert checkpoint_path.is_file()
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint.get("verdict") == "PASS"
    assert int(checkpoint.get("sim_round", 99)) <= SIM_ROUND_MAX
    assert VERIFY_JSON.is_file(), "docs/verification/T-901_e2e_pass_report.json 이 커밋되어 있어야 한다"
    saved = json.loads(VERIFY_JSON.read_text(encoding="utf-8"))
    assert saved.get("task") == "T-901"
    assert saved.get("verdict") == "PASS"
    assert saved.get("card_12", {}).get("CAPTURE_RENDER_WAIT_SEC") == 5.0


def test_capture_render_wait_margin_is_5_seconds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """카드 12: SDL 렌더 완료 안전을 위해 캡처 전 대기 마진이 5초다.

    빈 화면 Vision 오탐 FAIL을 막기 위해 CAPTURE_RENDER_WAIT_SEC=5.0 이며,
    캡처 실패는 orchestrator에서 FAIL 리포트로 정규화된다
    (test_sim_driver_failure_writes_fail_report).
    """
    import src.simulator.sim_driver as sim_driver_mod

    assert getattr(sim_driver_mod, "CAPTURE_RENDER_WAIT_SEC", None) == 5.0

    sleeps: list[float] = []
    monkeypatch.setattr(sim_driver_mod.time, "sleep", lambda s: sleeps.append(float(s)))

    driver = SimDriver(build_dir=tmp_path / "build_sim")
    driver._started_at = time.monotonic() - 0.1  # type: ignore[attr-defined]
    monkeypatch.setattr(driver, "_grab_frame", driver.make_placeholder_frame)

    out = tmp_path / "captured_sim.png"
    driver.capture_screenshot(out)

    assert out.is_file()
    assert sleeps, "capture_screenshot는 렌더 대기 sleep을 호출해야 한다"
    assert max(sleeps) >= 4.0 or sum(sleeps) >= 4.0


@REQUIRES_LIVE_API
def test_live_external_api_separated():
    """실제 외부 API live 호출은 기본 E2E에 포함하지 않는다."""
    assert False, "live marker suite placeholder"
