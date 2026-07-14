"""T-852: Streamlit dashboard — 단위 테스트.

Task32 [T-852] 10항:
- Red: 백엔드 503 fixture·WASM iframe 누락 fixture → 오류 상태 표시
- Green: 상태 생성 로직 함수 분리, 업로드/시작 payload mock HTTP 검증
- 카드 12: PDF 업로드 10MB 초과 시 거부 가드
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from src.dashboard.app import (
    CAPTURE_FILENAME,
    MAX_UPLOAD_BYTES,
    WASM_INDEX_REL,
    build_run_payload,
    check_backend_health,
    compute_dashboard_view,
    find_capture_image,
    format_log_lines,
    post_run_request,
    resolve_wasm_iframe_path,
    validate_pdf_upload,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WASM_INDEX = REPO_ROOT / WASM_INDEX_REL
SAMPLE_PDF = REPO_ROOT / "tests" / "data" / "esp32-p4_datasheet_en.pdf"


class MockHttpClient:
    """Task32 Green: mock HTTP client for payload/status 검증."""

    def __init__(self, responses: dict[str, tuple[int, dict[str, Any] | str]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def get(self, url: str, timeout: float = 5.0) -> MagicMock:
        self.calls.append(("GET", url, None))
        status, body = self.responses.get(url, (404, {}))
        response = MagicMock()
        response.status_code = status
        if isinstance(body, dict):
            response.json.return_value = body
        else:
            response.text = body
        return response

    def post(self, url: str, json: dict[str, Any], timeout: float = 30.0) -> MagicMock:
        self.calls.append(("POST", url, json))
        status, body = self.responses.get(url, (404, {}))
        response = MagicMock()
        response.status_code = status
        response.json.return_value = body
        return response


# ---------------------------------------------------------------------------
# Red: backend 503 + WASM iframe missing → error state
# ---------------------------------------------------------------------------


def test_backend_503_shows_backend_error_state() -> None:
    client = MockHttpClient(
        {"http://127.0.0.1:8000/api/health": (503, {"detail": "unavailable"})}
    )

    ok, status_code = check_backend_health("http://127.0.0.1:8000", client)

    assert ok is False
    assert status_code == 503
    view = compute_dashboard_view(
        backend_ok=ok,
        backend_status=status_code,
        wasm_index_path=None,
    )
    assert view.state == "backend_error"
    assert "503" in view.message


def test_missing_wasm_iframe_shows_wasm_error_state(tmp_path: Path) -> None:
    missing = tmp_path / "no_index.html"
    assert resolve_wasm_iframe_path(REPO_ROOT, missing) is None

    view = compute_dashboard_view(
        backend_ok=True,
        backend_status=200,
        wasm_index_path=None,
    )
    assert view.state == "wasm_missing"
    assert "WASM" in view.message or "simulator" in view.message.lower()


def test_wasm_iframe_path_resolves_when_index_exists() -> None:
    assert WASM_INDEX.is_file(), "T-850 index.html fixture missing"
    resolved = resolve_wasm_iframe_path(REPO_ROOT)
    assert resolved == WASM_INDEX.resolve()


def test_healthy_backend_and_wasm_ready_state() -> None:
    view = compute_dashboard_view(
        backend_ok=True,
        backend_status=200,
        wasm_index_path=WASM_INDEX,
    )
    assert view.state == "ready"
    assert view.iframe_src is not None
    assert "index.html" in view.iframe_src


# ---------------------------------------------------------------------------
# Green: payload + mock HTTP start request
# ---------------------------------------------------------------------------


def test_build_run_payload_matches_api_contract(tmp_path: Path) -> None:
    pdf = tmp_path / "sheet.pdf"
    spec = tmp_path / "spec.txt"
    pdf.write_bytes(b"%PDF-1.4")
    spec.write_text("Header + OK button\n", encoding="utf-8")

    payload = build_run_payload(
        pdf_path=str(pdf),
        spec_path=str(spec),
        target="esp32-p4",
        mode="sim",
    )

    assert payload == {
        "pdf_path": str(pdf),
        "spec_path": str(spec),
        "target": "esp32-p4",
        "mode": "sim",
    }


def test_post_run_request_sends_payload_via_mock_client(tmp_path: Path) -> None:
    pdf = tmp_path / "sheet.pdf"
    spec = tmp_path / "spec.txt"
    pdf.write_bytes(b"%PDF-1.4")
    spec.write_text("UI spec\n", encoding="utf-8")
    payload = build_run_payload(str(pdf), str(spec))

    api_base = "http://127.0.0.1:8000"
    client = MockHttpClient(
        {
            f"{api_base}/api/run": (
                200,
                {"ok": True, "run_id": "run-abc", "status": "queued", "error": None},
            )
        }
    )

    ok, body, err = post_run_request(api_base, client, payload)

    assert ok is True
    assert body is not None
    assert body["run_id"] == "run-abc"
    assert err is None
    assert ("POST", f"{api_base}/api/run", payload) in client.calls


def test_poll_status_formats_log_redirect_lines() -> None:
    lines = format_log_lines(
        [
            {"status": "queued", "current_node": None},
            {"status": "running", "current_node": "parse_datasheet"},
            {"status": "completed", "current_node": "end_pass", "verdict": "PASS"},
        ]
    )
    assert any("parse_datasheet" in line for line in lines)
    assert any("PASS" in line for line in lines)


def test_find_capture_image_polls_output_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "output" / "run-001"
    run_dir.mkdir(parents=True)
    capture = run_dir / CAPTURE_FILENAME
    capture.write_bytes(b"\x89PNG\r\n\x1a\n")

    found = find_capture_image(tmp_path / "output", run_id="run-001")
    assert found == capture


# ---------------------------------------------------------------------------
# 카드 12: upload size guard (10MB)
# ---------------------------------------------------------------------------


def test_validate_pdf_upload_accepts_valid_pdf() -> None:
    ok, err = validate_pdf_upload(MAX_UPLOAD_BYTES, "datasheet.pdf")
    assert ok is True
    assert err is None


def test_validate_pdf_upload_rejects_oversized_file() -> None:
    ok, err = validate_pdf_upload(MAX_UPLOAD_BYTES + 1, "big.pdf")
    assert ok is False
    assert err is not None
    assert "10" in err and "MB" in err


def test_validate_pdf_upload_rejects_non_pdf_extension() -> None:
    ok, err = validate_pdf_upload(1024, "notes.txt")
    assert ok is False
    assert err is not None
    assert "PDF" in err


def test_oversized_upload_sets_upload_rejected_view_state() -> None:
    view = compute_dashboard_view(
        backend_ok=True,
        backend_status=200,
        wasm_index_path=WASM_INDEX,
        upload_error="File exceeds 10MB limit",
    )
    assert view.state == "upload_rejected"
    assert "10MB" in view.message
