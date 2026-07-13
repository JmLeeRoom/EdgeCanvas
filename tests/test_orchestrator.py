"""T-701: LangGraph 2단계 상태머신 (Sim + HW) 그래프 — 단위 테스트.

단위구현계획서.md 제5장 [T-701] 10항 절차를 코드로 검증한다.
- 준비: 각 모듈 동작을 모킹(Mock) 노드 세트로 구성.
- 실행: python -m pytest tests/test_orchestrator.py -v -s
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.agent.orchestrator import (
    CONSECUTIVE_PASS_REQUIRED,
    HW_ROUND_MAX,
    SIM_ROUND_MAX,
    HMIAgentState,
    OrchestratorMocks,
    build_orchestrator_graph,
    initial_state,
    write_report_markdown,
)


@dataclass
class MockScenario:
    """verify_simulation / verify_physical 판정 시퀀스."""

    sim_verdicts: list[bool] = field(default_factory=lambda: [True])
    sim_widget_errors: list[float] = field(default_factory=lambda: [2.0])
    hw_verdicts: list[bool] = field(default_factory=lambda: [True])
    _sim_idx: int = 0
    _hw_idx: int = 0

    def next_sim(self) -> tuple[bool, float]:
        idx = min(self._sim_idx, len(self.sim_verdicts) - 1)
        self._sim_idx += 1
        verdict = self.sim_verdicts[idx]
        err = self.sim_widget_errors[min(idx, len(self.sim_widget_errors) - 1)]
        return verdict, err

    def next_hw(self) -> bool:
        idx = min(self._hw_idx, len(self.hw_verdicts) - 1)
        self._hw_idx += 1
        return self.hw_verdicts[idx]


def _make_mocks(
    scenario: MockScenario,
    tmp_path: Path,
    *,
    run_id: str = "run_test_701",
) -> OrchestratorMocks:
    assets = tmp_path / run_id / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    def capture_screenshot(path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return path

    def combined_verify(image_path: Path) -> dict[str, Any]:
        passed, widget_error_pct = scenario.next_sim()
        return {
            "passed": passed,
            "widget_error_pct": widget_error_pct,
            "text_passed": passed,
            "details": "mock vision",
        }

    return OrchestratorMocks(
        parse_datasheet=lambda _state: {"chunks": ["spec"]},
        generate_code=lambda _state: {"code": "lvgl ui"},
        capture_screenshot=capture_screenshot,
        vision_judge=combined_verify,
        build_and_flash=lambda _state: {"flash_ok": True},
        capture_physical=lambda _state: {"image": str(assets / "hw.png")},
        physical_judge=lambda _state: {"passed": scenario.next_hw(), "details": "mock hw"},
        output_dir=tmp_path,
    )


def _run_graph(
    mocks: OrchestratorMocks,
    *,
    run_mode: str = "sim",
    run_id: str = "run_test_701",
) -> HMIAgentState:
    graph = build_orchestrator_graph(mocks)
    state = initial_state(run_mode=run_mode, run_id=run_id)  # type: ignore[arg-type]
    return graph.invoke(state)


def test_sim_mode_reaches_end_pass_with_markdown_report(tmp_path):
    """sim 모드: parse→generate→verify PASS 후 END(PASS) 및 리포트 기록."""
    scenario = MockScenario(sim_verdicts=[True], sim_widget_errors=[3.0])
    mocks = _make_mocks(scenario, tmp_path)
    final = _run_graph(mocks, run_mode="sim")

    assert final["verdict"] == "PASS"
    assert final["sim_round"] <= SIM_ROUND_MAX
    report_path = Path(final["report_path"])
    assert report_path.is_file()
    content = report_path.read_text(encoding="utf-8")
    assert "PASS" in content
    assert "history" in content.lower() or "라운드" in content or "round" in content.lower()


def test_sim_mode_self_correct_stops_at_max_rounds(tmp_path):
    """sim 모드: 연속 FAIL 시 self_correct 최대 5회 후 END(FAIL)."""
    scenario = MockScenario(sim_verdicts=[False] * 10, sim_widget_errors=[10.0] * 10)
    mocks = _make_mocks(scenario, tmp_path)
    final = _run_graph(mocks, run_mode="sim")

    assert final["verdict"] == "FAIL"
    assert final["sim_round"] == SIM_ROUND_MAX
    assert len(final["history"]) >= SIM_ROUND_MAX


def test_self_correct_preserves_history_across_rounds(tmp_path):
    """12항 실패 시나리오: self_correct 진입 후 history 누적(상태 손실 방지)."""
    scenario = MockScenario(
        sim_verdicts=[False, False, True],
        sim_widget_errors=[8.0, 6.0, 2.0],
    )
    mocks = _make_mocks(scenario, tmp_path)
    final = _run_graph(mocks, run_mode="sim")

    assert final["verdict"] == "PASS"
  # self_correct가 최소 2회 기록되어야 이전 라운드 정보가 보존됨
    self_correct_entries = [h for h in final["history"] if h.get("node") == "self_correct"]
    assert len(self_correct_entries) >= 2
    assert self_correct_entries[0]["sim_round"] < self_correct_entries[-1]["sim_round"]


def test_hw_mode_requires_sim_gate_before_build_and_flash(tmp_path):
    """hw 모드: sim_gate_passed 후 build_and_flash→verify_physical PASS."""
    passes = [True] * CONSECUTIVE_PASS_REQUIRED
    scenario = MockScenario(sim_verdicts=passes, sim_widget_errors=[1.0] * len(passes), hw_verdicts=[True])
    mocks = _make_mocks(scenario, tmp_path)
    final = _run_graph(mocks, run_mode="hw")

    assert final["sim_gate_passed"] is True
    assert final["verdict"] == "PASS"
    nodes = [h["node"] for h in final["history"]]
    assert "build_and_flash" in nodes
    assert "verify_physical" in nodes


def test_hw_mode_self_correct_hw_stops_at_max_rounds(tmp_path):
    """hw 모드: verify_physical 연속 FAIL 시 hw_round 상한 2회 후 END(FAIL)."""
    passes = [True] * CONSECUTIVE_PASS_REQUIRED
    scenario = MockScenario(
        sim_verdicts=passes,
        sim_widget_errors=[1.0] * len(passes),
        hw_verdicts=[False, False, False],
    )
    mocks = _make_mocks(scenario, tmp_path)
    final = _run_graph(mocks, run_mode="hw")

    assert final["verdict"] == "FAIL"
    assert final["hw_round"] == HW_ROUND_MAX


def test_graph_terminates_without_infinite_loop(tmp_path):
    """DoD: 모킹 전체 루프가 교착 없이 종료된다."""
    scenario = MockScenario(sim_verdicts=[False, True], sim_widget_errors=[4.0, 2.0])
    mocks = _make_mocks(scenario, tmp_path)
    graph = build_orchestrator_graph(mocks)
    state = initial_state(run_mode="sim", run_id="run_loop_guard")
    final = graph.invoke(state, {"recursion_limit": 100})
    assert final["verdict"] in ("PASS", "FAIL")


def test_sim_mode_widget_tolerance_failure_triggers_self_correct(tmp_path):
    """위젯 오차 >5%이면 verify FAIL로 self_correct 경로에 진입한다."""
    scenario = MockScenario(sim_verdicts=[True, True], sim_widget_errors=[8.0, 2.0])
    mocks = _make_mocks(scenario, tmp_path)
    final = _run_graph(mocks, run_mode="sim")

    assert final["verdict"] == "PASS"
    verify_entries = [h for h in final["history"] if h.get("node") == "verify_simulation"]
    assert any(e.get("widget_error_pct", 0) > 5 for e in verify_entries)
    assert any(h.get("node") == "self_correct" for h in final["history"])


def test_write_report_markdown_serializes_state(tmp_path):
    state: HMIAgentState = {
        "run_mode": "sim",
        "sim_gate_passed": False,
        "sim_round": 1,
        "hw_round": 0,
        "verdict": "FAIL",
        "history": [{"node": "self_correct", "sim_round": 1, "message": "mock"}],
        "run_id": "run_md",
    }
    path = write_report_markdown(state, tmp_path / "run_md")
    text = path.read_text(encoding="utf-8")
    assert "FAIL" in text
    assert "self_correct" in text
