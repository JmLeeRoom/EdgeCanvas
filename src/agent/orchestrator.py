"""LangGraph 2단계 오케스트레이터 (Sim + HW).

단위구현계획서.md 제5장 [T-701] 8항 구현.
시뮬레이션 루프와 실기 검증 루프를 단일 StateGraph 내 2단계로 연결한다.

라운드 상한: sim 5회 / hw 2회. history는 Annotated reducer로 self_correct 간 상태 손실을 방지한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from operator import add
from pathlib import Path
from typing import Annotated, Any, Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

SIM_ROUND_MAX = 5
HW_ROUND_MAX = 2
CONSECUTIVE_PASS_REQUIRED = 3
WIDGET_TOLERANCE_PCT = 5.0

RunMode = Literal["sim", "hw"]
Verdict = Literal["PASS", "FAIL"]


class HMIAgentState(TypedDict, total=False):
    """LangGraph 공유 상태. history는 라운드별 직렬화 가능 누적."""

    run_mode: RunMode
    sim_gate_passed: bool
    sim_round: int
    hw_round: int
    verdict: Verdict | None
    history: Annotated[list[dict[str, Any]], add]
    consecutive_pass_count: int
    run_id: str
    report_path: str
    last_verification_passed: bool
    datasheet: dict[str, Any]
    generated_code: str
    screenshot_path: str


@dataclass
class OrchestratorMocks:
    """T-802/603/604 및 빌드·실기 경로를 주입 가능한 모킹 노드 세트."""

    parse_datasheet: Callable[[HMIAgentState], dict[str, Any]]
    generate_code: Callable[[HMIAgentState], dict[str, Any]]
    capture_screenshot: Callable[[Path], Path]
    vision_judge: Callable[[Path], dict[str, Any]]
    build_and_flash: Callable[[HMIAgentState], dict[str, Any]]
    capture_physical: Callable[[HMIAgentState], dict[str, Any]]
    physical_judge: Callable[[HMIAgentState], dict[str, Any]]
    output_dir: Path = field(default_factory=lambda: Path("output"))


def initial_state(
    *,
    run_mode: RunMode = "sim",
    run_id: str = "run_orchestrator",
) -> HMIAgentState:
    return {
        "run_mode": run_mode,
        "sim_gate_passed": False,
        "sim_round": 0,
        "hw_round": 0,
        "verdict": None,
        "history": [],
        "consecutive_pass_count": 0,
        "run_id": run_id,
        "last_verification_passed": False,
    }


def _append_history(
    state: HMIAgentState,
    node: str,
    **payload: Any,
) -> list[dict[str, Any]]:
    entry: dict[str, Any] = {
        "node": node,
        "ts": datetime.now(timezone.utc).isoformat(),
        "sim_round": state.get("sim_round", 0),
        "hw_round": state.get("hw_round", 0),
    }
    entry.update(payload)
    return [entry]


def _assets_dir(mocks: OrchestratorMocks, state: HMIAgentState) -> Path:
    run_id = state.get("run_id", "run_orchestrator")
    return mocks.output_dir / run_id / "assets"


def _finalize_report(state: HMIAgentState, mocks: OrchestratorMocks) -> dict[str, Any]:
    """T-703 `write_report`로 `output/<run_id>/report.md`를 기록한다.

    레거시 `write_report_markdown`는 하위 호환용으로 유지한다.
    """
    from src.agent.report_generator import write_report

    report_path = write_report(
        state,
        output_dir=mocks.output_dir,
        vision_image_path=state.get("screenshot_path") or None,
        also_checkpoint=True,
    )
    return {"report_path": str(report_path)}


def write_report_markdown(state: HMIAgentState, run_dir: Path) -> Path:
    """최종 상태를 마크다운 리포트로 기록한다."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.md"

    verdict = state.get("verdict") or "UNKNOWN"
    lines = [
        "# HMI Agent Run Report",
        "",
        f"- **verdict**: {verdict}",
        f"- **run_mode**: {state.get('run_mode', 'sim')}",
        f"- **sim_gate_passed**: {state.get('sim_gate_passed', False)}",
        f"- **sim_round**: {state.get('sim_round', 0)} / {SIM_ROUND_MAX}",
        f"- **hw_round**: {state.get('hw_round', 0)} / {HW_ROUND_MAX}",
        f"- **consecutive_pass_count**: {state.get('consecutive_pass_count', 0)}",
        "",
        "## History",
        "",
    ]
    for item in state.get("history", []):
        lines.append(f"- `{item.get('node')}` sim={item.get('sim_round')} hw={item.get('hw_round')}: {item.get('message', item)}")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def build_orchestrator_graph(mocks: OrchestratorMocks):
    """LangGraph StateGraph를 컴파일해 반환한다."""

    def parse_datasheet(state: HMIAgentState) -> dict[str, Any]:
        result = mocks.parse_datasheet(state)
        return {
            "datasheet": result,
            "history": _append_history(state, "parse_datasheet", message="datasheet parsed"),
        }

    def generate_code(state: HMIAgentState) -> dict[str, Any]:
        result = mocks.generate_code(state)
        code = result.get("code", "")
        return {
            "generated_code": code,
            "history": _append_history(state, "generate_code", message="code generated"),
        }

    def verify_simulation(state: HMIAgentState) -> dict[str, Any]:
        assets = _assets_dir(mocks, state)
        screenshot_path = assets / "captured_sim.png"
        try:
            mocks.capture_screenshot(screenshot_path)
            judge = mocks.vision_judge(screenshot_path)
        except Exception as exc:  # noqa: BLE001 — E2E에서 캡처/판정 실패를 FAIL로 정규화
            return {
                "screenshot_path": str(screenshot_path),
                "last_verification_passed": False,
                "consecutive_pass_count": 0,
                "history": _append_history(
                    state,
                    "verify_simulation",
                    message=f"capture/vision error: {exc}",
                    verification_passed=False,
                    widget_error_pct=100.0,
                    error=str(exc),
                ),
            }

        passed = bool(judge.get("passed", False))
        widget_error = float(judge.get("widget_error_pct", 100.0))
        widget_ok = widget_error <= WIDGET_TOLERANCE_PCT
        verification_passed = passed and widget_ok

        consecutive = state.get("consecutive_pass_count", 0)
        if verification_passed:
            consecutive += 1
        else:
            consecutive = 0

        sim_gate_passed = consecutive >= CONSECUTIVE_PASS_REQUIRED and widget_ok

        return {
            "screenshot_path": str(screenshot_path),
            "last_verification_passed": verification_passed,
            "consecutive_pass_count": consecutive,
            "sim_gate_passed": sim_gate_passed or state.get("sim_gate_passed", False),
            "history": _append_history(
                state,
                "verify_simulation",
                message=(
                    f"passed={verification_passed} widget_error={widget_error}% "
                    f"streak={consecutive}"
                ),
                verification_passed=verification_passed,
                widget_error_pct=widget_error,
            ),
        }

    def self_correct(state: HMIAgentState) -> dict[str, Any]:
        sim_round = state.get("sim_round", 0) + 1
        return {
            "sim_round": sim_round,
            "history": _append_history(
                state,
                "self_correct",
                message="sim self-correct round",
                sim_round=sim_round,
            ),
        }

    def build_and_flash(state: HMIAgentState) -> dict[str, Any]:
        result = mocks.build_and_flash(state)
        return {
            "history": _append_history(
                state,
                "build_and_flash",
                message="build and flash complete",
                flash_ok=result.get("flash_ok", True),
            ),
        }

    def verify_physical(state: HMIAgentState) -> dict[str, Any]:
        capture = mocks.capture_physical(state)
        judge = mocks.physical_judge(state)
        passed = bool(judge.get("passed", False))
        return {
            "last_verification_passed": passed,
            "history": _append_history(
                state,
                "verify_physical",
                message=f"physical verification passed={passed}",
                capture=capture,
            ),
        }

    def self_correct_hw(state: HMIAgentState) -> dict[str, Any]:
        hw_round = state.get("hw_round", 0) + 1
        return {
            "hw_round": hw_round,
            "history": _append_history(
                state,
                "self_correct_hw",
                message="hw self-correct round",
                hw_round=hw_round,
            ),
        }

    def end_pass(state: HMIAgentState) -> dict[str, Any]:
        update: dict[str, Any] = {"verdict": "PASS"}
        update.update(_finalize_report({**state, **update}, mocks))
        return update

    def end_fail(state: HMIAgentState) -> dict[str, Any]:
        update: dict[str, Any] = {"verdict": "FAIL"}
        update.update(_finalize_report({**state, **update}, mocks))
        return update

    def route_after_verify_sim(state: HMIAgentState) -> str:
        if state.get("sim_round", 0) >= SIM_ROUND_MAX and not state.get(
            "last_verification_passed"
        ):
            return "end_fail"
        if state.get("last_verification_passed"):
            if state.get("run_mode") == "sim":
                return "end_pass"
            if state.get("sim_gate_passed"):
                return "build_and_flash"
            return "generate_code"
        return "self_correct"

    def route_after_self_correct(state: HMIAgentState) -> str:
        if state.get("sim_round", 0) >= SIM_ROUND_MAX:
            return "end_fail"
        return "generate_code"

    def route_after_verify_physical(state: HMIAgentState) -> str:
        if state.get("hw_round", 0) >= HW_ROUND_MAX and not state.get(
            "last_verification_passed"
        ):
            return "end_fail"
        if state.get("last_verification_passed"):
            return "end_pass"
        return "self_correct_hw"

    def route_after_self_correct_hw(state: HMIAgentState) -> str:
        if state.get("hw_round", 0) >= HW_ROUND_MAX:
            return "end_fail"
        return "build_and_flash"

    graph = StateGraph(HMIAgentState)
    graph.add_node("parse_datasheet", parse_datasheet)
    graph.add_node("generate_code", generate_code)
    graph.add_node("verify_simulation", verify_simulation)
    graph.add_node("self_correct", self_correct)
    graph.add_node("build_and_flash", build_and_flash)
    graph.add_node("verify_physical", verify_physical)
    graph.add_node("self_correct_hw", self_correct_hw)
    graph.add_node("end_pass", end_pass)
    graph.add_node("end_fail", end_fail)

    graph.add_edge(START, "parse_datasheet")
    graph.add_edge("parse_datasheet", "generate_code")
    graph.add_edge("generate_code", "verify_simulation")
    graph.add_conditional_edges("verify_simulation", route_after_verify_sim)
    graph.add_conditional_edges("self_correct", route_after_self_correct)
    graph.add_edge("build_and_flash", "verify_physical")
    graph.add_conditional_edges("verify_physical", route_after_verify_physical)
    graph.add_conditional_edges("self_correct_hw", route_after_self_correct_hw)
    graph.add_edge("end_pass", END)
    graph.add_edge("end_fail", END)

    return graph.compile()


def save_graph_diagram_png(output_path: Path) -> Path:
    """컴파일된 LangGraph 구조 다이어그램을 PNG로 저장한다 (T-701 검증 기록)."""
    default_mocks = OrchestratorMocks(
        parse_datasheet=lambda _s: {},
        generate_code=lambda _s: {"code": ""},
        capture_screenshot=lambda p: p,
        vision_judge=lambda _p: {"passed": True, "widget_error_pct": 0.0},
        build_and_flash=lambda _s: {},
        capture_physical=lambda _s: {},
        physical_judge=lambda _s: {"passed": True},
        output_dir=Path("output"),
    )
    app = build_orchestrator_graph(default_mocks)
    png_bytes = app.get_graph().draw_mermaid_png()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(png_bytes)
    return output_path
