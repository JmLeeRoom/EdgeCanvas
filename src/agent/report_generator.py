"""T-703: 체크포인트 세션 저장소 및 최종 검증 보고서 생성기.

LangGraph HMIAgentState 히스토리를 순회해 노드 실행 시각·API 크레딧·
위젯 검증 스코어를 마크다운 테이블로 조립하고
`output/<run_id>/report.md`에 기록한다.

비전 검증 이미지가 없으면 `[Image Not Available]` 플레이스홀더를 사용한다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

IMAGE_NOT_AVAILABLE = "[Image Not Available]"


def _as_mapping(state: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(state, Mapping):
        return dict(state)
    return dict(getattr(state, "__dict__", {}) or {})


def format_vision_image(vision_image_path: str | Path | None) -> str:
    """존재하면 마크다운 이미지, 미존재/미지정 시 플레이스홀더."""
    if vision_image_path is None:
        return IMAGE_NOT_AVAILABLE
    path = Path(vision_image_path)
    if not path.is_file():
        return IMAGE_NOT_AVAILABLE
    # 리포트 기준 상대 경로를 우선 (run 폴더 내부 assets)
    return f"![Vision verification]({path.as_posix()})"


def _format_widget_scores(entry: Mapping[str, Any]) -> str:
    scores = entry.get("widget_scores")
    if isinstance(scores, list) and scores:
        parts: list[str] = []
        for item in scores:
            if isinstance(item, Mapping):
                name = item.get("widget", "?")
                score = item.get("score", "")
                parts.append(f"{name}={score}")
            else:
                parts.append(str(item))
        return "; ".join(parts)
    # 단일 스코어/에러율 폴백
    if "widget_error_pct" in entry:
        return f"error_pct={entry['widget_error_pct']}"
    if "score" in entry:
        return str(entry["score"])
    return "-"


def _history_rows(history: list[Any]) -> list[str]:
    rows: list[str] = [
        "| Node | Timestamp | Credits | Widget Scores | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for raw in history:
        if not isinstance(raw, Mapping):
            continue
        node = raw.get("node", "-")
        ts = raw.get("ts", "-")
        credits = raw.get("credits", "-")
        scores = _format_widget_scores(raw)
        note = raw.get("message", "")
        # 파이프 충돌 방지
        note_s = str(note).replace("|", "/")
        scores_s = scores.replace("|", "/")
        rows.append(
            f"| {node} | {ts} | {credits} | {scores_s} | {note_s} |"
        )
    return rows


def generate_verification_report(
    state: Mapping[str, Any] | Any,
    *,
    vision_image_path: str | Path | None = None,
) -> str:
    """HMIAgentState → `# HMI Verification Report` 마크다운 본문."""
    data = _as_mapping(state)
    if vision_image_path is None:
        screenshot = data.get("screenshot_path") or None
        vision_image_path = screenshot if screenshot else None

    verdict = data.get("verdict") or "UNKNOWN"
    run_id = data.get("run_id", "")
    run_mode = data.get("run_mode", "sim")
    history = list(data.get("history") or [])

    lines: list[str] = [
        "# HMI Verification Report",
        "",
        "## Summary",
        "",
        f"- **run_id**: `{run_id}`",
        f"- **verdict**: {verdict}",
        f"- **run_mode**: {run_mode}",
        f"- **sim_gate_passed**: {data.get('sim_gate_passed', False)}",
        f"- **sim_round**: {data.get('sim_round', 0)}",
        f"- **hw_round**: {data.get('hw_round', 0)}",
        f"- **consecutive_pass_count**: {data.get('consecutive_pass_count', 0)}",
        "",
        "## Vision Capture",
        "",
        format_vision_image(vision_image_path),
        "",
        "## Generated Source",
        "",
    ]
    code = data.get("generated_code") or ""
    if code:
        lines.extend(["```c", str(code).rstrip(), "```", ""])
    else:
        lines.extend(["_(no generated source)_", ""])

    lines.extend(
        [
            "## Pipeline History",
            "",
            *_history_rows(history),
            "",
            "## Evaluation Metrics",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| verdict | {verdict} |",
            f"| last_verification_passed | {data.get('last_verification_passed', False)} |",
            f"| sim_gate_passed | {data.get('sim_gate_passed', False)} |",
            f"| history_entries | {len(history)} |",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(
    state: Mapping[str, Any] | Any,
    *,
    output_dir: str | Path = "output",
    vision_image_path: str | Path | None = None,
    also_checkpoint: bool = True,
) -> Path:
    """`output/<run_id>/report.md`에 리포트를 기록한다.

    also_checkpoint=True이면 동일 run 폴더에 세션 체크포인트 JSON도 저장한다.
    """
    data = _as_mapping(state)
    run_id = str(data.get("run_id") or "run_unknown")
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if vision_image_path is None:
        screenshot = data.get("screenshot_path") or None
        if screenshot:
            vision_image_path = screenshot

    md = generate_verification_report(data, vision_image_path=vision_image_path)
    report_path = run_dir / "report.md"
    report_path.write_text(md, encoding="utf-8")

    if also_checkpoint:
        CheckpointSessionStore(output_dir).save(data)

    return report_path


class CheckpointSessionStore:
    """런별 HMIAgentState 직렬화 저장소 (체크포인트 세션).

    경로: `<base_dir>/<run_id>/checkpoint.json`
    """

    def __init__(self, base_dir: str | Path = "output") -> None:
        self.base_dir = Path(base_dir)

    def _path(self, run_id: str) -> Path:
        return self.base_dir / run_id / "checkpoint.json"

    def save(self, state: Mapping[str, Any] | Any) -> Path:
        data = _as_mapping(state)
        run_id = str(data.get("run_id") or "run_unknown")
        path = self._path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # TypedDict / Annotated 등 JSON 직렬화 가능한 값만 기록
        serializable = json.loads(json.dumps(data, default=str))
        path.write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def load(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        return json.loads(path.read_text(encoding="utf-8"))
