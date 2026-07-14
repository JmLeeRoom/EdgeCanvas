"""T-902: 평가 지표 4종 자동 정량 측정.

10회 연속 E2E(또는 fixture manifest) 결과를 취합해
① 컴파일 성공률 ② 실기 기동률 ③ Vision 판정 일치율 ④ 자가수정 수렴 라운드 평균
을 스코어보드로 산출한다.

카드 12: 매 Run 호출에 3분 강제 타임아웃 감시 스레드를 두어 hang 시
해당 세션을 FAIL(TIMEOUT) 마크하고 다음 회차로 진행한다.

hw 기동률은 Phase A에서 fixture/placeholder(None=미측정)를 허용한다.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

RUN_TIMEOUT_SEC = 180.0  # 3분 — 카드 12 강제 타임아웃
DEFAULT_N_RUNS = 10


@dataclass
class RunResult:
    """단일 벤치마크 시행(Run) 결과 / manifest."""

    run_id: str
    status: str  # PASS | FAIL | TIMEOUT
    compile_success: bool
    device_boot_success: bool | None  # None = Phase A 미측정 placeholder
    vision_match: bool
    self_heal_rounds: int
    mode: str = "sim"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> RunResult:
        status = str(data.get("status", "FAIL")).upper()
        if status not in {"PASS", "FAIL", "TIMEOUT"}:
            status = "FAIL"
        boot_raw = data.get("device_boot_success", None)
        boot: bool | None
        if boot_raw is None:
            boot = None
        else:
            boot = bool(boot_raw)
        return cls(
            run_id=str(data.get("run_id", "unknown")),
            status=status,
            compile_success=bool(data.get("compile_success", False)),
            device_boot_success=boot,
            vision_match=bool(data.get("vision_match", False)),
            self_heal_rounds=int(data.get("self_heal_rounds", 0) or 0),
            mode=str(data.get("mode", "sim")),
        )

    @classmethod
    def timeout_fail(cls, run_id: str, *, mode: str = "sim") -> RunResult:
        """타임아웃 강제 FAIL 마크."""
        return cls(
            run_id=run_id,
            status="TIMEOUT",
            compile_success=False,
            device_boot_success=False,
            vision_match=False,
            self_heal_rounds=0,
            mode=mode,
        )


@dataclass
class Scoreboard:
    """4종 지표 점수 카드."""

    n_runs: int
    compile_success_rate: float
    device_boot_success_rate: float | None  # None = 미측정
    vision_match_rate: float
    self_heal_avg_rounds: float
    n_pass: int = 0
    n_fail: int = 0
    n_timeout: int = 0
    results: list[RunResult] = field(default_factory=list)


def load_manifests(manifests_dir: Path | str) -> list[RunResult]:
    """디렉터리 내 `*.json` run manifest를 정렬 로드한다."""
    root = Path(manifests_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"manifests directory not found: {root}")
    paths = sorted(root.glob("*.json"))
    results: list[RunResult] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError(f"manifest must be object: {path}")
        results.append(RunResult.from_mapping(data))
    return results


def compute_scoreboard(results: list[RunResult]) -> Scoreboard:
    """Run 결과 리스트 → 4종 지표 스코어보드.

    산출식 (아키텍트 유효성):
    - 성공률(%) = (성공 횟수 / N) * 100
    - 기동률: device_boot_success 가 전부 None 이면 미측정(None)
    - 수렴 라운드 평균 = sum(rounds) / N
    """
    n = len(results)
    if n == 0:
        return Scoreboard(
            n_runs=0,
            compile_success_rate=0.0,
            device_boot_success_rate=None,
            vision_match_rate=0.0,
            self_heal_avg_rounds=0.0,
        )

    compile_ok = sum(1 for r in results if r.compile_success)
    vision_ok = sum(1 for r in results if r.vision_match)
    rounds_sum = sum(r.self_heal_rounds for r in results)

    boot_values = [r.device_boot_success for r in results]
    if all(v is None for v in boot_values):
        boot_rate: float | None = None
    else:
        # None 은 미측정으로 제외하지 않고 False 취급(혼합 시 분모=N 유지)
        boot_ok = sum(1 for v in boot_values if v is True)
        boot_rate = (boot_ok / n) * 100.0

    n_pass = sum(1 for r in results if r.status == "PASS")
    n_timeout = sum(1 for r in results if r.status == "TIMEOUT")
    n_fail = sum(1 for r in results if r.status == "FAIL")

    return Scoreboard(
        n_runs=n,
        compile_success_rate=(compile_ok / n) * 100.0,
        device_boot_success_rate=boot_rate,
        vision_match_rate=(vision_ok / n) * 100.0,
        self_heal_avg_rounds=rounds_sum / n,
        n_pass=n_pass,
        n_fail=n_fail,
        n_timeout=n_timeout,
        results=list(results),
    )


def format_scoreboard(board: Scoreboard) -> str:
    """터미널용 pretty 스코어보드 문자열."""
    def _pct(value: float | None) -> str:
        if value is None:
            return "N/A (Phase A placeholder / 미측정)"
        return f"{value:.1f}%"

    width = 52
    bar = "=" * width
    mid = "-" * width
    lines = [
        bar,
        " P10 EdgeCanvas Benchmark Scoreboard (T-902)",
        bar,
        f" Runs                 : {board.n_runs}"
        f"  (PASS={board.n_pass} FAIL={board.n_fail} TIMEOUT={board.n_timeout})",
        mid,
        f" 1. Compile Success Rate   : {_pct(board.compile_success_rate)}",
        f" 2. Device/Boot Success    : {_pct(board.device_boot_success_rate)}",
        f" 3. Vision Match Rate      : {_pct(board.vision_match_rate)}",
        f" 4. Self-heal Avg Rounds   : {board.self_heal_avg_rounds:.1f}",
        mid,
        " (ko) 컴파일 성공률 / 실기 기동률 / Vision 일치율 / 수렴 라운드 평균",
        bar,
    ]
    return "\n".join(lines)


def write_scoreboard_report(board: Scoreboard, path: Path | str) -> Path:
    """검증 기록 파일에 스코어보드 + JSON 요약을 저장한다."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": "T-902",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_runs": board.n_runs,
        "compile_success_rate": board.compile_success_rate,
        "device_boot_success_rate": board.device_boot_success_rate,
        "vision_match_rate": board.vision_match_rate,
        "self_heal_avg_rounds": board.self_heal_avg_rounds,
        "n_pass": board.n_pass,
        "n_fail": board.n_fail,
        "n_timeout": board.n_timeout,
        "run_timeout_sec": RUN_TIMEOUT_SEC,
        "results": [asdict(r) for r in board.results],
    }
    body = "\n".join(
        [
            "# T-902 Benchmark Scores",
            "",
            format_scoreboard(board),
            "",
            "## JSON",
            json.dumps(payload, ensure_ascii=False, indent=2),
            "",
        ]
    )
    out.write_text(body, encoding="utf-8")
    return out


def invoke_run_with_timeout(
    run_fn: Callable[[int], RunResult],
    index: int,
    timeout_sec: float = RUN_TIMEOUT_SEC,
    *,
    mode: str = "sim",
) -> RunResult:
    """감시 스레드로 Run을 실행하고, timeout_sec 초과 시 TIMEOUT FAIL 마크.

    hang 스레드는 daemon 으로 남겨 두고 다음 회차로 진행한다(카드 12).
    """
    box: dict[str, Any] = {}

    def _target() -> None:
        try:
            box["result"] = run_fn(index)
        except Exception as exc:  # noqa: BLE001 — Run 예외도 FAIL로 흡수
            box["error"] = exc

    worker = threading.Thread(target=_target, name=f"bench-run-{index}", daemon=True)
    worker.start()
    worker.join(timeout=timeout_sec)

    if worker.is_alive():
        return RunResult.timeout_fail(run_id=f"run_timeout_{index}", mode=mode)

    if "error" in box:
        return RunResult(
            run_id=f"run_error_{index}",
            status="FAIL",
            compile_success=False,
            device_boot_success=False,
            vision_match=False,
            self_heal_rounds=0,
            mode=mode,
        )

    result = box.get("result")
    if not isinstance(result, RunResult):
        return RunResult.timeout_fail(run_id=f"run_invalid_{index}", mode=mode)
    return result


class BenchmarkRunner:
    """manifest 디렉터리 또는 실행 callable로 N회 벤치마크를 수행한다."""

    def __init__(
        self,
        *,
        manifests_dir: Path | str | None = None,
        run_fn: Callable[[int], RunResult] | None = None,
        n_runs: int = DEFAULT_N_RUNS,
        timeout_sec: float = RUN_TIMEOUT_SEC,
        mode: str = "sim",
    ) -> None:
        self.manifests_dir = Path(manifests_dir) if manifests_dir else None
        self.run_fn = run_fn
        self.n_runs = n_runs
        self.timeout_sec = timeout_sec
        self.mode = mode

    def run(self) -> Scoreboard:
        if self.run_fn is not None:
            results: list[RunResult] = []
            for i in range(self.n_runs):
                results.append(
                    invoke_run_with_timeout(
                        self.run_fn,
                        i,
                        timeout_sec=self.timeout_sec,
                        mode=self.mode,
                    )
                )
            return compute_scoreboard(results)

        if self.manifests_dir is None:
            raise ValueError("manifests_dir or run_fn is required")

        loaded = load_manifests(self.manifests_dir)
        if len(loaded) < self.n_runs:
            raise ValueError(
                f"need at least {self.n_runs} manifests, found {len(loaded)}"
            )
        return compute_scoreboard(loaded[: self.n_runs])


def _default_fixture_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "data"
        / "benchmark"
        / "manifests"
    )


def main(argv: list[str] | None = None) -> int:
    """CLI: `python src/evaluation/benchmark.py --runs 10`."""
    parser = argparse.ArgumentParser(
        description="T-902: 평가 지표 4종 자동 정량 측정"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_N_RUNS,
        help="벤치마크 시행 횟수 (기본 10)",
    )
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=None,
        help="run manifest JSON 디렉터리 (미지정 시 tests/data/benchmark/manifests)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/verification/T-902_benchmark_scores.txt"),
        help="검증 기록 출력 경로",
    )
    args = parser.parse_args(argv)

    manifests = args.manifests_dir or _default_fixture_dir()
    runner = BenchmarkRunner(manifests_dir=manifests, n_runs=args.runs)
    board = runner.run()
    text = format_scoreboard(board)
    print(text)
    write_scoreboard_report(board, args.report)
    print(f"\n[report] wrote {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
