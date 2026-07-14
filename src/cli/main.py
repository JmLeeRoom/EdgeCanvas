"""P10_Manufacturing HMI 자동 생성/검증 CLI 엔트리포인트.

단위구현계획서.md 제5장 [T-101] 8항 구현 내용을 따른다.
Typer로 단일 진입점(`p10`)을 구성하고 3종 명령을 매핑한다:

- ``run``      : E2E 파이프라인 기동 (코딩 표준상 ``--mode {sim|hw}`` 유지)
- ``evaluate`` : 지표 측정
- ``cleanup``  : 임시 run ID 정리

12항(실패 시 대처) 대응: 파일 입력값은 파이프라인에 전달하기 전에
``os.path.abspath``로 정규화된 절대경로를 확보해 윈도우 경로/인코딩
문제를 예방한다.

T-901: ``p10 run --mode sim`` 은 fake API/LLM/HW adapter + T-802 스크린샷
fixture + T-603/604 Vision 판정 + T-703 리포트로 장비 없이 E2E를 실행한다.
"""

from __future__ import annotations

import json
import os
import shutil
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import typer

from src.agent.orchestrator import (
    OrchestratorMocks,
    build_orchestrator_graph,
    initial_state,
)
from src.agent.report_generator import write_report
from src.common.run_manager import create_run_dirs, generate_run_id

app = typer.Typer(
    name="p10",
    help="P10_Manufacturing HMI 자동 생성/검증 CLI.",
    add_completion=False,
    no_args_is_help=True,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "tests" / "data"
_DEFAULT_LAYOUT = DATA_DIR / "ui_layout_expected.json"
_DEFAULT_UI_NORMAL = DATA_DIR / "ui_normal.png"
_DEFAULT_UI_SCREENS = DATA_DIR / "ui_screens.c"


class RunMode(str, Enum):
    """파이프라인 실행 모드. 코딩 표준(`p10 run --mode {sim|hw}`)을 따른다."""

    SIM = "sim"
    HW = "hw"


def normalize_path(raw_path: str) -> str:
    """입력 경로를 정규화된 절대경로로 변환한다 (12항 대처).

    윈도우 경로/인코딩 인식 문제를 예방하기 위해 파일 입력값을
    받는 즉시 ``os.path.abspath``로 절대경로를 확보한다.
    """
    return os.path.abspath(raw_path)


def _require_existing_file(raw_path: str, label: str) -> Path:
    """경로를 절대경로로 정규화하고 실제 파일 존재 여부를 검증한다 (11항).

    Raises:
        typer.BadParameter: 파일이 존재하지 않거나 디렉토리일 때.
    """
    absolute = normalize_path(raw_path)
    path = Path(absolute)
    if not path.is_file():
        raise typer.BadParameter(f"{label} 경로에 파일이 없습니다: {absolute}")
    return path


def _output_dir() -> Path:
    return Path(os.environ.get("P10_OUTPUT_DIR", "output"))


def _write_input_fail_report(*, reason: str, mode: str = "sim") -> Path:
    """입력 검증 실패 시에도 output/<run_id>/report.md 를 남긴다 (T-901 Red)."""
    run_id = generate_run_id()
    out = _output_dir()
    create_run_dirs(run_id, out)
    state = {
        "run_id": run_id,
        "run_mode": mode,
        "verdict": "FAIL",
        "sim_gate_passed": False,
        "sim_round": 0,
        "hw_round": 0,
        "consecutive_pass_count": 0,
        "last_verification_passed": False,
        "generated_code": "",
        "history": [
            {
                "node": "input_validation",
                "ts": "",
                "credits": 0,
                "message": reason,
            }
        ],
    }
    return write_report(state, output_dir=out, also_checkpoint=True)


class _ScriptedOcr:
    """T-604 TextMatchEvaluator용 deterministic OCR (live API 없음)."""

    def __init__(self, texts: list[str]) -> None:
        self._texts = texts

    def read_texts(self, image: Any) -> list[str]:  # noqa: ANN401
        return list(self._texts)


def build_sim_e2e_mocks(
    *,
    output_dir: Path,
    pdf_path: Path | None = None,
    spec_path: Path | None = None,
    screenshot_fixture: Path | None = None,
    layout_path: Path | None = None,
) -> OrchestratorMocks:
    """fake API/LLM/HW + T-802 fixture + T-603/604 실제 판정 모듈."""
    from src.verifier.text_evaluator import TextMatchEvaluator
    from src.verifier.vision_evaluator import SimCaptureProvider, WidgetLocationEvaluator

    layout_file = layout_path or _DEFAULT_LAYOUT
    shot_src = screenshot_fixture or _DEFAULT_UI_NORMAL
    layout = json.loads(layout_file.read_text(encoding="utf-8"))
    widget_eval = WidgetLocationEvaluator(layout, tolerance=0.05)
    text_eval = TextMatchEvaluator(
        ["P10 System Status"],
        ocr_engine=_ScriptedOcr(["P10 System Status"]),
        use_vlm=False,
    )

    code_src = (
        _DEFAULT_UI_SCREENS.read_text(encoding="utf-8")
        if _DEFAULT_UI_SCREENS.is_file()
        else "void ui_init(void) {}\n"
    )

    def parse_datasheet(_state: Any) -> dict[str, Any]:
        # 외부 Upstage/LLM 없이 로컬 fixture·입력 경로만 반영 (fake API)
        return {
            "pdf": str(pdf_path) if pdf_path else "",
            "spec": str(spec_path) if spec_path else "",
            "chunks": ["fake-datasheet-chunk"],
        }

    def generate_code(_state: Any) -> dict[str, Any]:
        return {"code": code_src}

    def capture_screenshot(path: Path) -> Path:
        # T-802 스크린샷 fixture 복사 (보드/SDL 창 불필요). 렌더 대기 경로는
        # SimDriver.capture_screenshot 단위/E2E 카드 12 테스트로 검증한다.
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(shot_src, path)
        return path

    def vision_judge(image_path: Path) -> dict[str, Any]:
        provider = SimCaptureProvider(image_path)
        widget = widget_eval.evaluate(provider)
        text = text_eval.evaluate(provider)
        widget_pass = widget.get("verdict") == "PASS"
        text_pass = text.get("verdict") == "PASS"
        passed = widget_pass and text_pass
        return {
            "passed": passed,
            "widget_error_pct": 0.0 if widget_pass else 25.0,
            "text_passed": text_pass,
            "details": {"widget": widget, "text": text},
        }

    return OrchestratorMocks(
        parse_datasheet=parse_datasheet,
        generate_code=generate_code,
        capture_screenshot=capture_screenshot,
        vision_judge=vision_judge,
        build_and_flash=lambda _s: {"flash_ok": True},  # fake HW
        capture_physical=lambda _s: {"image": ""},
        physical_judge=lambda _s: {"passed": True},
        output_dir=Path(output_dir),
    )


def execute_pipeline(
    *,
    mode: str,
    pdf_path: Path,
    spec_path: Path,
    target: str,
    output_dir: Path | None = None,
    mocks: OrchestratorMocks | None = None,
    mocks_factory: Callable[..., OrchestratorMocks] | None = None,
) -> dict[str, Any]:
    """오케스트레이터를 실행하고 상태 dict를 반환한다."""
    out = Path(output_dir or _output_dir())
    run_id = generate_run_id()
    create_run_dirs(run_id, out)

    factory = mocks_factory or build_sim_e2e_mocks
    graph_mocks = mocks or factory(
        output_dir=out,
        pdf_path=pdf_path,
        spec_path=spec_path,
    )

    graph = build_orchestrator_graph(graph_mocks)
    final = graph.invoke(
        initial_state(run_mode=mode, run_id=run_id)  # type: ignore[arg-type]
    )

    # 생성 코드를 run 폴더에 남겨 DoD 산출물 체계를 충족
    code = final.get("generated_code") or ""
    if code:
        (out / run_id / "generated_ui_screens.c").write_text(code, encoding="utf-8")

    final["_target"] = target
    final["_output_dir"] = str(out)
    return final


@app.command()
def run(
    pdf_path: str = typer.Option(
        ..., "--pdf-path", help="데이터시트 PDF 파일 경로."
    ),
    spec_path: str = typer.Option(
        ..., "--spec-path", help="요구사항 텍스트 파일 경로."
    ),
    target: str = typer.Option(
        ..., "--target", help="타깃 보드명 (예: esp32-p4)."
    ),
    mode: RunMode = typer.Option(
        RunMode.SIM, "--mode", help="실행 모드: sim(시뮬) 또는 hw(실기)."
    ),
) -> None:
    """E2E HMI 자동 생성/검증 파이프라인을 기동한다."""
    try:
        pdf = _require_existing_file(pdf_path, "데이터시트 PDF")
        spec = _require_existing_file(spec_path, "요구사항 파일")
    except typer.BadParameter as exc:
        report = _write_input_fail_report(reason=str(exc), mode=mode.value)
        typer.echo(f"[run] FAIL report={report}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"[run] mode={mode.value} target={target}")
    typer.echo(f"[run] pdf-path={pdf}")
    typer.echo(f"[run] spec-path={spec}")

    if mode == RunMode.HW:
        typer.echo("[run] HW mode E2E는 Phase HW 스위트에서 확장됩니다.")
        report = _write_input_fail_report(
            reason="HW mode not enabled in Phase A (use tests/e2e/test_cli_pipeline_hw.py)",
            mode="hw",
        )
        typer.echo(f"[run] FAIL report={report}")
        raise typer.Exit(code=1)

    try:
        final = execute_pipeline(
            mode=mode.value,
            pdf_path=pdf,
            spec_path=spec,
            target=target,
            output_dir=_output_dir(),
        )
    except Exception as exc:  # noqa: BLE001
        report = _write_input_fail_report(reason=f"pipeline error: {exc}", mode=mode.value)
        typer.echo(f"[run] FAIL report={report} error={exc}")
        raise typer.Exit(code=1) from exc

    verdict = final.get("verdict") or "FAIL"
    report_path = final.get("report_path", "")
    typer.echo(f"[run] verdict={verdict} report={report_path}")
    if verdict != "PASS":
        raise typer.Exit(code=1)


@app.command()
def evaluate(
    target: str = typer.Option(
        ..., "--target", help="지표를 측정할 타깃 보드명."
    ),
    run_id: str = typer.Option(
        None, "--run-id", help="측정 대상 Run ID (미지정 시 최신 실행)."
    ),
) -> None:
    """생성된 HMI 결과물의 지표를 측정한다."""
    typer.echo(f"[evaluate] target={target} run_id={run_id or '(latest)'}")
    # TODO(T-9xx): 지표 측정 로직과 연결한다.
    typer.echo("[evaluate] 지표 측정 로직은 후속 Task에서 구현됩니다.")


@app.command()
def cleanup(
    run_id: str = typer.Option(
        None, "--run-id", help="정리할 특정 Run ID (미지정 시 임시 run 전체)."
    ),
) -> None:
    """임시 run ID 산출물을 정리한다."""
    typer.echo(f"[cleanup] target run_id={run_id or '(all temporary)'}")
    # TODO(T-005 연계): output/<run_id>/ 정리 로직과 연결한다.
    typer.echo("[cleanup] 정리 로직은 후속 Task에서 구현됩니다.")


if __name__ == "__main__":
    app()
