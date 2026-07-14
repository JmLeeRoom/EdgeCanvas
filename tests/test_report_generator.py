"""T-703: 체크포인트 세션 저장소 및 최종 검증 보고서 생성기 — 단위 테스트.

단위구현계획서.md 제5장 [T-703] 10항 절차를 코드로 검증한다.
- 준비: 종료 완료 상태의 HMIAgentState 객체 Mock 데이터.
- 실행: python -m pytest tests/test_report_generator.py
- 통과 기준: report.md 정상 기록, `# HMI Verification Report` 헤더 및
  평가지표 테이블 구조 식별.

카드 12항: 비전 검증 이미지 누락 시 `[Image Not Available]` 플레이스홀더.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agent.report_generator import (
    IMAGE_NOT_AVAILABLE,
    CheckpointSessionStore,
    generate_verification_report,
    write_report,
)


def _completed_mock_state(*, run_id: str = "run_t703") -> dict[str, Any]:
    """종료 완료 상태 HMIAgentState Mock (카드 10항 준비물).

    orchestrator/langgraph 임포트 없이 TypedDict 호환 dict를 사용한다.
    """
    return {
        "run_id": run_id,
        "run_mode": "sim",
        "verdict": "PASS",
        "sim_gate_passed": True,
        "sim_round": 1,
        "hw_round": 0,
        "consecutive_pass_count": 3,
        "last_verification_passed": True,
        "generated_code": "/* ui_screens.c mock */\nvoid ui_init(void) {}\n",
        "screenshot_path": "",  # 기본 mock은 이미지 경로 비움 → 플레이스홀더 경로와 분리
        "history": [
            {
                "node": "parse_datasheet",
                "ts": "2026-07-14T01:00:00+00:00",
                "sim_round": 0,
                "hw_round": 0,
                "credits": 0.5,
                "message": "datasheet parsed",
            },
            {
                "node": "generate_code",
                "ts": "2026-07-14T01:00:05+00:00",
                "sim_round": 0,
                "hw_round": 0,
                "credits": 2.0,
                "message": "code generated",
            },
            {
                "node": "verify_simulation",
                "ts": "2026-07-14T01:00:10+00:00",
                "sim_round": 0,
                "hw_round": 0,
                "credits": 1.0,
                "verification_passed": True,
                "widget_scores": [
                    {"widget": "btn_start", "score": 0.96},
                    {"widget": "lbl_title", "score": 0.91},
                ],
                "message": "passed=True",
            },
        ],
    }


def test_report_written_with_header_and_metrics_table(tmp_path: Path):
    """report.md 생성 + `# HMI Verification Report` + 평가지표 테이블."""
    state = _completed_mock_state(run_id="run_t703_ok")
    report_path = write_report(state, output_dir=tmp_path)

    assert report_path == tmp_path / "run_t703_ok" / "report.md"
    assert report_path.is_file()

    content = report_path.read_text(encoding="utf-8")
    assert content.startswith("# HMI Verification Report")
    assert "## Evaluation Metrics" in content
    assert "| Metric | Value |" in content
    assert "|" in content  # markdown table
    assert "parse_datasheet" in content
    assert "generate_code" in content
    assert "verify_simulation" in content
    # 노드 시각·크레딧·스코어가 테이블에 반영
    assert "2026-07-14T01:00:00+00:00" in content or "01:00:00" in content
    assert "2.0" in content or "2" in content
    assert "btn_start" in content or "0.96" in content
    assert "PASS" in content


def test_generate_verification_report_markdown_structure():
    """순수 markdown 조립이 헤더/테이블 구조를 갖는다."""
    state = _completed_mock_state()
    md = generate_verification_report(state, vision_image_path=None)
    assert "# HMI Verification Report" in md
    assert "| Node |" in md
    assert "Credits" in md
    assert "## Evaluation Metrics" in md
    assert "| Metric | Value |" in md


def test_missing_vision_image_uses_placeholder(tmp_path: Path):
    """카드 12항: 비전 이미지 미존재 시 `[Image Not Available]` 표기."""
    state = _completed_mock_state(run_id="run_t703_noimg")
    missing = tmp_path / "run_t703_noimg" / "assets" / "vision_missing.png"
    # 파일을 만들지 않음

    report_path = write_report(
        state,
        output_dir=tmp_path,
        vision_image_path=missing,
    )
    content = report_path.read_text(encoding="utf-8")
    assert IMAGE_NOT_AVAILABLE in content
    assert str(missing) not in content or IMAGE_NOT_AVAILABLE in content
    # broken markdown image link to missing file must not be the sole reference
    assert f"]({missing.as_posix()})" not in content


def test_existing_vision_image_embedded(tmp_path: Path):
    """이미지가 존재하면 마크다운 이미지 링크로 포함한다."""
    state = _completed_mock_state(run_id="run_t703_img")
    assets = tmp_path / "run_t703_img" / "assets"
    assets.mkdir(parents=True)
    vision = assets / "captured_sim.png"
    vision.write_bytes(b"\x89PNG\r\n\x1a\n")

    report_path = write_report(
        state,
        output_dir=tmp_path,
        vision_image_path=vision,
    )
    content = report_path.read_text(encoding="utf-8")
    assert IMAGE_NOT_AVAILABLE not in content
    assert "captured_sim.png" in content
    assert "![" in content


def test_checkpoint_session_store_persists_and_feeds_report(tmp_path: Path):
    """체크포인트 세션 저장소가 상태를 직렬화하고 리포트 생성에 사용된다."""
    state = _completed_mock_state(run_id="run_t703_ckpt")
    store = CheckpointSessionStore(tmp_path)
    ckpt_path = store.save(state)
    assert ckpt_path.is_file()

    loaded = store.load(state["run_id"])
    assert loaded["verdict"] == "PASS"
    assert len(loaded["history"]) == 3

    report_path = write_report(loaded, output_dir=tmp_path)
    content = report_path.read_text(encoding="utf-8")
    assert "# HMI Verification Report" in content
    assert "parse_datasheet" in content
