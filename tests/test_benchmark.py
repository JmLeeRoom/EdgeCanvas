"""T-902: 평가 지표 4종 자동 정량 측정 — 단위 테스트.

단위구현계획서 / Task28 [T-902]:
- Red: 10회 실행 중 timeout/FAIL fixture를 섞어 실패율·평균 라운드를 올바르게 계산
- Green: 고정 run manifest 10개 fixture로 4종 지표를 재현
- 카드 12: 매 Run 3분 타임아웃 → FAIL 마크 후 다음 회차 진행 (≥1 테스트)
- 통과 기준: 실제 장시간 E2E 없이 수식·리포트 포맷이 자동 테스트됨
  (hw 지표는 Phase HW 0.5인일 슬롯 — fixture/placeholder 허용)
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.evaluation.benchmark import (
    RUN_TIMEOUT_SEC,
    BenchmarkRunner,
    RunResult,
    Scoreboard,
    compute_scoreboard,
    format_scoreboard,
    invoke_run_with_timeout,
    load_manifests,
    write_scoreboard_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_MANIFESTS = REPO_ROOT / "tests" / "data" / "benchmark" / "manifests"

# 고정 fixture 기대값 (run_01..run_10)
# compile: 8/10, device_boot: 7/10, vision: 6/10, avg rounds: 2.3
EXPECTED_COMPILE_RATE = 80.0
EXPECTED_BOOT_RATE = 70.0
EXPECTED_VISION_RATE = 60.0
EXPECTED_AVG_ROUNDS = 2.3
EXPECTED_N_RUNS = 10


def test_run_timeout_constant_is_3_minutes():
    """카드 12: 매 시행 최대 강제 타임아웃은 3분(180초)."""
    assert RUN_TIMEOUT_SEC == 180.0


def test_fixed_manifests_reproduce_scoreboard():
    """Green: 고정 manifest 10개 → 재현 가능한 4종 지표 스코어보드."""
    results = load_manifests(FIXTURE_MANIFESTS)
    assert len(results) == EXPECTED_N_RUNS

    board = compute_scoreboard(results)

    assert board.n_runs == EXPECTED_N_RUNS
    assert board.compile_success_rate == pytest.approx(EXPECTED_COMPILE_RATE)
    assert board.device_boot_success_rate == pytest.approx(EXPECTED_BOOT_RATE)
    assert board.vision_match_rate == pytest.approx(EXPECTED_VISION_RATE)
    assert board.self_heal_avg_rounds == pytest.approx(EXPECTED_AVG_ROUNDS)
    # FAIL/TIMEOUT mix가 반영됨
    assert board.n_fail >= 1
    assert board.n_timeout >= 1
    assert board.n_pass + board.n_fail + board.n_timeout == EXPECTED_N_RUNS


def test_mixed_fail_timeout_fail_rates_and_avg_rounds():
    """Red: timeout/FAIL 혼합 fixture → 실패율·평균 라운드 정확 계산."""
    mixed = [
        RunResult(
            run_id="m1",
            status="PASS",
            compile_success=True,
            device_boot_success=True,
            vision_match=True,
            self_heal_rounds=1,
        ),
        RunResult(
            run_id="m2",
            status="FAIL",
            compile_success=False,
            device_boot_success=False,
            vision_match=False,
            self_heal_rounds=5,
        ),
        RunResult(
            run_id="m3",
            status="TIMEOUT",
            compile_success=False,
            device_boot_success=False,
            vision_match=False,
            self_heal_rounds=0,
        ),
        RunResult(
            run_id="m4",
            status="PASS",
            compile_success=True,
            device_boot_success=True,
            vision_match=False,
            self_heal_rounds=2,
        ),
    ]
    board = compute_scoreboard(mixed)

    assert board.n_runs == 4
    assert board.compile_success_rate == pytest.approx(50.0)  # 2/4
    assert board.device_boot_success_rate == pytest.approx(50.0)  # 2/4
    assert board.vision_match_rate == pytest.approx(25.0)  # 1/4
    assert board.self_heal_avg_rounds == pytest.approx(2.0)  # (1+5+0+2)/4
    assert board.n_fail == 1
    assert board.n_timeout == 1
    assert board.n_pass == 2


def test_per_run_timeout_marks_fail_and_continues():
    """카드 12: Run이 hang 되면 FAIL(TIMEOUT) 마크 후 다음 회차로 진행."""
    calls: list[int] = []

    def flaky_run(index: int) -> RunResult:
        calls.append(index)
        if index == 1:
            time.sleep(5.0)  # 타임아웃보다 길게 hang
            return RunResult(
                run_id=f"hang_{index}",
                status="PASS",
                compile_success=True,
                device_boot_success=True,
                vision_match=True,
                self_heal_rounds=1,
            )
        return RunResult(
            run_id=f"ok_{index}",
            status="PASS",
            compile_success=True,
            device_boot_success=True,
            vision_match=True,
            self_heal_rounds=index,
        )

    # index 0 OK → 1 hang(timeout) → 2 OK 가 모두 수집되어야 함
    results: list[RunResult] = []
    for i in range(3):
        results.append(
            invoke_run_with_timeout(flaky_run, i, timeout_sec=0.2)
        )

    assert len(results) == 3
    assert results[0].status == "PASS"
    assert results[1].status == "TIMEOUT"
    assert results[1].compile_success is False
    assert results[2].status == "PASS"
    # hang 회차 포함 3회 모두 호출 시도됨 (다음 회차 진행)
    assert calls == [0, 1, 2]


def test_benchmark_runner_ten_runs_from_manifests():
    """BenchmarkRunner가 manifest 디렉터리에서 10회를 취합한다."""
    runner = BenchmarkRunner(manifests_dir=FIXTURE_MANIFESTS, n_runs=10)
    board = runner.run()
    assert isinstance(board, Scoreboard)
    assert board.n_runs == 10
    assert board.compile_success_rate == pytest.approx(EXPECTED_COMPILE_RATE)


def test_scoreboard_pretty_format_and_verification_write(tmp_path: Path):
    """스코어보드 pretty 터미널 포맷 + 검증 기록 파일 쓰기."""
    results = load_manifests(FIXTURE_MANIFESTS)
    board = compute_scoreboard(results)
    text = format_scoreboard(board)

    assert "Compile Success Rate" in text or "컴파일 성공률" in text
    assert "Vision" in text
    assert "80.0%" in text or "80%" in text
    assert "2.3" in text

    out = tmp_path / "T-902_benchmark_scores.txt"
    written = write_scoreboard_report(board, out)
    assert written == out
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert "T-902" in body
    assert "80" in body
    assert "2.3" in body


def test_device_boot_placeholder_none_when_unmeasured():
    """Phase A: device_boot_success=None 이면 기동률은 None(미측정) 처리."""
    results = [
        RunResult(
            run_id="s1",
            status="PASS",
            compile_success=True,
            device_boot_success=None,
            vision_match=True,
            self_heal_rounds=1,
        ),
        RunResult(
            run_id="s2",
            status="PASS",
            compile_success=True,
            device_boot_success=None,
            vision_match=True,
            self_heal_rounds=2,
        ),
    ]
    board = compute_scoreboard(results)
    assert board.device_boot_success_rate is None
    assert board.compile_success_rate == pytest.approx(100.0)
    text = format_scoreboard(board)
    assert "N/A" in text or "미측정" in text or "placeholder" in text.lower()
