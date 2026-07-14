"""T-901 Phase HW E2E stub (13주차 확장).

보드·웹캠이 필요한 HW 스위트는 Phase HW에서 `tests/e2e/test_cli_pipeline_sim.py`
패턴을 `--mode hw`로 확장한다. 현재는 skip placeholder만 둔다.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Phase HW — T-901 week 13: board/webcam HIL E2E not enabled yet")
def test_cli_pipeline_hw_placeholder():
    """Phase HW: `p10 run --mode hw` E2E placeholder."""
    assert False, "implement when Phase HW cutline / T-502 board path is ready"
