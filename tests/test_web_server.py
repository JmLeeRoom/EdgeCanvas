"""T-851: FastAPI 백엔드 — 단위 테스트.

단위구현계획서.md / Task31 [T-851] 10항:
- Red: LangGraph runner fake 예외 시 /api/run이 500이 아니라 구조화된 실패 JSON
- Green: TestClient로 /api/health, /api/run, /api/status/{run_id} (uvicorn 불필요)
- 카드 12: 동시 Run 요청 시 세마포어로 순차 실행
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.server.app import RunRequest, create_app

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "tests" / "data"
SAMPLE_PDF = DATA_DIR / "esp32-p4_datasheet_en.pdf"


def _write_spec(tmp_path: Path) -> Path:
    spec = tmp_path / "requirements.txt"
    spec.write_text("P10 HMI: header + OK/Cancel buttons\n", encoding="utf-8")
    return spec


def _run_payload(tmp_path: Path) -> dict[str, str]:
    spec = _write_spec(tmp_path)
    pdf = str(SAMPLE_PDF)
    assert Path(pdf).is_file(), "PDF fixture missing"
    return {
        "pdf_path": pdf,
        "spec_path": str(spec),
        "target": "esp32-p4",
        "mode": "sim",
    }


@pytest.fixture
def output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setenv("P10_OUTPUT_DIR", str(out))
    return out


def test_health_returns_healthy(output_dir: Path) -> None:
    app = create_app(output_dir=output_dir)
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_run_returns_structured_failure_not_500_when_runner_raises(
    output_dir: Path,
) -> None:
    def failing_runner(
        _request: RunRequest, _run_id: str, _output_dir: Path
    ) -> dict[str, Any]:
        raise RuntimeError("LangGraph runner fake failure")

    app = create_app(
        output_dir=output_dir,
        pipeline_runner=failing_runner,
        run_sync=True,
    )
    client = TestClient(app)
    payload = {
        "pdf_path": str(SAMPLE_PDF),
        "spec_path": str(output_dir / "missing_spec_for_fail.txt"),
        "target": "esp32-p4",
        "mode": "sim",
    }
    # spec file optional for sync fail path — runner throws before file checks
    _write_spec(output_dir.parent)

    response = client.post("/api/run", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["status"] == "failed"
    assert "run_id" in body
    assert body["error"]["code"] == "pipeline_error"
    assert "LangGraph runner fake failure" in body["error"]["message"]


def test_run_status_and_background_queue(output_dir: Path, tmp_path: Path) -> None:
    app = create_app(output_dir=output_dir)
    client = TestClient(app)
    payload = _run_payload(tmp_path)

    start = client.post("/api/run", json=payload)
    assert start.status_code == 200
    start_body = start.json()
    assert start_body["ok"] is True
    run_id = start_body["run_id"]
    assert start_body["status"] in ("queued", "running", "completed")

    status = client.get(f"/api/status/{run_id}")
    assert status.status_code == 200
    status_body = status.json()
    assert status_body["run_id"] == run_id
    assert status_body["status"] in ("queued", "running", "completed", "failed")

    # BackgroundTasks flush — pipeline should finish for sim mocks
    for _ in range(50):
        poll = client.get(f"/api/status/{run_id}").json()
        if poll["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert poll["status"] == "completed"


def test_report_returns_markdown(output_dir: Path, tmp_path: Path) -> None:
    app = create_app(output_dir=output_dir, run_sync=True)
    client = TestClient(app)
    payload = _run_payload(tmp_path)

    run_resp = client.post("/api/run", json=payload)
    run_id = run_resp.json()["run_id"]

    report = client.get(f"/api/report/{run_id}")
    assert report.status_code == 200
    body = report.json()
    assert body["run_id"] == run_id
    assert body["found"] is True
    assert "# " in body["report_markdown"] or "Report" in body["report_markdown"]


def test_concurrent_runs_execute_serially_via_semaphore(output_dir: Path) -> None:
    active = {"count": 0, "max": 0}
    gate = threading.Lock()

    def slow_runner(
        _request: RunRequest, _run_id: str, _output_dir: Path
    ) -> dict[str, Any]:
        with gate:
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
        time.sleep(0.15)
        with gate:
            active["count"] -= 1
        return {"verdict": "PASS", "history": [{"node": "end_pass"}], "report_path": ""}

    app = create_app(output_dir=output_dir, pipeline_runner=slow_runner)
    client = TestClient(app)
    payload = {
        "pdf_path": str(SAMPLE_PDF),
        "spec_path": str(_write_spec(output_dir.parent)),
        "target": "esp32-p4",
        "mode": "sim",
    }

    t1 = threading.Thread(
        target=lambda: client.post("/api/run", json={**payload, "target": "esp32-p4-a"})
    )
    t2 = threading.Thread(
        target=lambda: client.post("/api/run", json={**payload, "target": "esp32-p4-b"})
    )
    t1.start()
    time.sleep(0.02)
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert active["max"] == 1, "세마포어 미적용: 동시에 2개 이상 실행됨"


def test_cors_middleware_present(output_dir: Path) -> None:
    app = create_app(output_dir=output_dir)
    client = TestClient(app)

    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" in {
        k.lower() for k in response.headers.keys()
    }
