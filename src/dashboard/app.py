"""T-852: Streamlit 웹 대시보드 — PDF/spec 제출, WASM sim iframe, 실기 캡처 폴링.

FastAPI(T-851) 백엔드와 Emscripten WASM index(T-850)를 브라우저 UI로 통합한다.
상태·payload·경로 검사는 Streamlit 없이 단위 테스트 가능한 순수 함수로 분리한다.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

# sdkconfig 템플릿 수준과 매칭 — Streamlit 업로드 메모리 버퍼 오버플로우 방지 (카드 12)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

DEFAULT_API_BASE = os.environ.get("P10_API_BASE", "http://127.0.0.1:8000")
DEFAULT_OUTPUT_DIR = Path(os.environ.get("P10_OUTPUT_DIR", "output"))
# Serve src/simulator/web/ over HTTP — browsers block file:// iframes from Streamlit.
DEFAULT_WASM_HTTP_URL = "http://127.0.0.1:8080/"
DEFAULT_WASM_URL = os.environ.get("P10_WASM_URL", DEFAULT_WASM_HTTP_URL)
WASM_INDEX_REL = Path("src/simulator/web/index.html")
CAPTURE_FILENAME = "captured_rectified.png"
POLL_INTERVAL_SEC = float(os.environ.get("P10_DASHBOARD_POLL_SEC", "2.0"))
DEFAULT_MAX_POLLS = 60

DashboardState = Literal[
    "ready",
    "backend_error",
    "wasm_missing",
    "upload_rejected",
    "running",
    "completed",
    "failed",
]


class HttpClient(Protocol):
    def get(self, url: str, timeout: float = 5.0) -> Any: ...

    def post(self, url: str, json: dict[str, Any], timeout: float = 30.0) -> Any: ...


@dataclass(frozen=True)
class DashboardView:
    """대시보드 UI에 바인딩할 집계 상태 (Streamlit·테스트 공용)."""

    state: DashboardState
    message: str
    iframe_src: str | None = None
    log_lines: tuple[str, ...] = ()
    capture_path: str | None = None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def validate_pdf_upload(size_bytes: int, filename: str) -> tuple[bool, str | None]:
    """PDF 업로드 용량·확장자 가드."""
    if not filename.lower().endswith(".pdf"):
        return False, "PDF files only (.pdf extension required)"
    if size_bytes > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        return False, f"File exceeds {limit_mb}MB limit"
    return True, None


def resolve_wasm_iframe_path(
    root: Path,
    wasm_index: Path | None = None,
) -> Path | None:
    """T-850 Emscripten WASM index.html 경로. 없으면 None (iframe 오류 상태)."""
    candidate = wasm_index if wasm_index is not None else root / WASM_INDEX_REL
    resolved = candidate.resolve()
    return resolved if resolved.is_file() else None


def is_file_uri(url: str) -> bool:
    """True when iframe src uses file:// (blocked by browsers under http Streamlit)."""
    return url.strip().lower().startswith("file:")


def wasm_iframe_src(
    index_path: Path | None = None,
    *,
    wasm_url: str | None = None,
) -> str:
    """iframe src for Streamlit embedding.

    Prefer explicit ``wasm_url``, then ``P10_WASM_URL``, then HTTP default
    ``http://127.0.0.1:8080/`` (serve ``src/simulator/web/`` with
    ``python -m http.server 8080``). Never defaults to ``file://``.

    ``index_path`` is accepted for call-site compatibility; existence is
    checked via ``resolve_wasm_iframe_path`` before embedding.
    """
    _ = index_path
    if wasm_url:
        return wasm_url
    override = os.environ.get("P10_WASM_URL")
    if override:
        return override
    return DEFAULT_WASM_HTTP_URL


def build_run_payload(
    pdf_path: str,
    spec_path: str,
    *,
    target: str = "esp32-p4",
    mode: str = "sim",
) -> dict[str, str]:
    """POST /api/run 요청 본문 (T-851 RunRequest 계약)."""
    return {
        "pdf_path": pdf_path,
        "spec_path": spec_path,
        "target": target,
        "mode": mode,
    }


def check_backend_health(api_base: str, client: HttpClient) -> tuple[bool, int | None]:
    """GET /api/health — 503 등 비정상 시 (False, status_code) 반환."""
    url = f"{api_base.rstrip('/')}/api/health"
    try:
        response = client.get(url, timeout=5.0)
        status = int(response.status_code)
        return status == 200, status
    except Exception:
        return False, None


def post_run_request(
    api_base: str,
    client: HttpClient,
    payload: dict[str, str],
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """POST /api/run — mock HTTP client로 payload 검증 가능."""
    url = f"{api_base.rstrip('/')}/api/run"
    try:
        response = client.post(url, json=payload, timeout=30.0)
        if response.status_code >= 500:
            return False, None, f"backend error {response.status_code}"
        body = response.json()
        ok = bool(body.get("ok", False))
        return ok, body, None if ok else str(body.get("error") or "run rejected")
    except Exception as exc:
        return False, None, str(exc)


def fetch_run_status(
    api_base: str,
    client: HttpClient,
    run_id: str,
) -> dict[str, Any] | None:
    url = f"{api_base.rstrip('/')}/api/status/{run_id}"
    try:
        response = client.get(url, timeout=5.0)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None


def format_log_lines(status_history: list[dict[str, Any]]) -> list[str]:
    """E2E 실시간 로그 리다이렉트 뷰어용 상태 전이 라인."""
    lines: list[str] = []
    for entry in status_history:
        status = entry.get("status", "?")
        node = entry.get("current_node")
        verdict = entry.get("verdict")
        parts = [f"[{status}]"]
        if node:
            parts.append(f"node={node}")
        if verdict:
            parts.append(f"verdict={verdict}")
        if entry.get("error"):
            err = entry["error"]
            if isinstance(err, dict):
                parts.append(f"error={err.get('message', err)}")
            else:
                parts.append(f"error={err}")
        lines.append(" ".join(parts))
    return lines


def find_capture_image(output_dir: Path, run_id: str | None = None) -> Path | None:
    """실기 카메라 `captured_rectified.png` 폴링 경로 탐색."""
    candidates: list[Path] = []
    if run_id:
        candidates.append(output_dir / run_id / CAPTURE_FILENAME)
    candidates.append(output_dir / CAPTURE_FILENAME)
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def compute_dashboard_view(
    *,
    backend_ok: bool,
    backend_status: int | None,
    wasm_index_path: Path | None,
    upload_error: str | None = None,
    run_status: str | None = None,
    status_history: list[dict[str, Any]] | None = None,
    capture_path: Path | None = None,
    wasm_url: str | None = None,
) -> DashboardView:
    """백엔드·WASM·업로드·실행 상태를 단일 뷰 모델로 집계."""
    log_lines = tuple(format_log_lines(status_history or []))

    if not backend_ok:
        code = backend_status if backend_status is not None else "unreachable"
        return DashboardView(
            state="backend_error",
            message=f"Backend unavailable (HTTP {code}). Start FastAPI: uvicorn src.server.app:app",
            log_lines=log_lines,
        )

    if wasm_index_path is None:
        return DashboardView(
            state="wasm_missing",
            message="WASM simulator index.html not found (T-850). Build or check src/simulator/web/",
            log_lines=log_lines,
        )

    if upload_error:
        return DashboardView(
            state="upload_rejected",
            message=upload_error,
            iframe_src=wasm_iframe_src(wasm_index_path, wasm_url=wasm_url),
            log_lines=log_lines,
        )

    iframe = wasm_iframe_src(wasm_index_path, wasm_url=wasm_url)
    capture_str = str(capture_path) if capture_path else None

    if run_status == "running":
        return DashboardView(
            state="running",
            message="Pipeline running — polling status and capture image",
            iframe_src=iframe,
            log_lines=log_lines,
            capture_path=capture_str,
        )
    if run_status == "completed":
        return DashboardView(
            state="completed",
            message="Pipeline completed",
            iframe_src=iframe,
            log_lines=log_lines,
            capture_path=capture_str,
        )
    if run_status == "failed":
        return DashboardView(
            state="failed",
            message="Pipeline failed — see log viewer",
            iframe_src=iframe,
            log_lines=log_lines,
            capture_path=capture_str,
        )

    return DashboardView(
        state="ready",
        message="Ready — upload PDF, edit UI spec, and start pipeline",
        iframe_src=iframe,
        log_lines=log_lines,
        capture_path=capture_str,
    )


def poll_run_until_terminal(
    api_base: str,
    client: HttpClient,
    run_id: str,
    *,
    max_polls: int = DEFAULT_MAX_POLLS,
    interval_sec: float = POLL_INTERVAL_SEC,
) -> tuple[list[dict[str, Any]], str]:
    """상태 폴링 — 터미널(completed/failed)까지 history 수집 (기본 60회)."""
    history: list[dict[str, Any]] = []
    terminal = "running"
    for _ in range(max_polls):
        snap = fetch_run_status(api_base, client, run_id)
        if snap:
            history.append(snap)
            terminal = str(snap.get("status", "running"))
            if terminal in ("completed", "failed"):
                break
        time.sleep(interval_sec)
    return history, terminal


def poll_run_once(
    api_base: str,
    client: HttpClient,
    run_id: str,
) -> dict[str, Any] | None:
    """단일 상태 스냅샷 — Streamlit 세션 폴링/rerun 경로용."""
    return fetch_run_status(api_base, client, run_id)


def _write_uploaded_pdf(uploaded: Any, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / uploaded.name
    dest.write_bytes(uploaded.getvalue())
    return dest


def _write_spec_text(spec_text: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "ui_spec.txt"
    dest.write_text(spec_text, encoding="utf-8")
    return dest


def render_dashboard() -> None:
    """Streamlit UI — 테스트는 순수 함수 경로로 커버."""
    import httpx
    import streamlit as st
    import streamlit.components.v1 as components

    st.set_page_config(page_title="P10 Manufacturing Dashboard", layout="wide")
    st.title("P10 Manufacturing — Web HMI Dashboard (T-852)")

    root = repo_root()
    api_base = st.sidebar.text_input("API base URL", value=DEFAULT_API_BASE)
    output_dir = Path(st.sidebar.text_input("Output directory", value=str(DEFAULT_OUTPUT_DIR)))
    wasm_url = st.sidebar.text_input(
        "WASM URL",
        value=DEFAULT_WASM_URL,
        help=(
            "HTTP URL serving src/simulator/web/ (default http://127.0.0.1:8080/). "
            "Override with env P10_WASM_URL. From web/: python -m http.server 8080"
        ),
    )
    st.sidebar.caption(
        "Serve WASM statically: `cd src/simulator/web && python -m http.server 8080` "
        "(or set P10_WASM_URL). file:// iframes are blocked by the browser."
    )
    if is_file_uri(wasm_url):
        st.sidebar.warning(
            "file:// WASM URL will not load inside Streamlit — use an HTTP URL instead."
        )

    try:
        with httpx.Client() as http:
            backend_ok, backend_status = check_backend_health(api_base, http)
    except Exception:
        backend_ok, backend_status = False, None

    wasm_path = resolve_wasm_iframe_path(root)

    if "status_history" not in st.session_state:
        st.session_state.status_history = []
    if "run_id" not in st.session_state:
        st.session_state.run_id = None
    if "run_status" not in st.session_state:
        st.session_state.run_status = None
    if "poll_count" not in st.session_state:
        st.session_state.poll_count = 0

    # Realtime log redirect: session poll + periodic rerun (DoD E2E viewer)
    if (
        st.session_state.run_status == "running"
        and st.session_state.run_id
        and st.session_state.poll_count < DEFAULT_MAX_POLLS
    ):
        with httpx.Client() as http:
            snap = poll_run_once(api_base, http, st.session_state.run_id)
        if snap:
            st.session_state.status_history.append(snap)
            terminal = str(snap.get("status", "running"))
            st.session_state.run_status = terminal
            if terminal in ("completed", "failed"):
                st.session_state.poll_count = 0
            else:
                st.session_state.poll_count += 1
                time.sleep(POLL_INTERVAL_SEC)
                st.rerun()
        else:
            st.session_state.poll_count += 1
            time.sleep(POLL_INTERVAL_SEC)
            st.rerun()

    upload_error: str | None = None

    col_upload, col_spec = st.columns(2)
    with col_upload:
        st.subheader("Datasheet PDF")
        pdf_file = st.file_uploader(
            "Drag and drop PDF datasheet",
            type=["pdf"],
            help=f"Maximum {MAX_UPLOAD_BYTES // (1024 * 1024)}MB (sdkconfig-aligned guard)",
        )
        if pdf_file is not None:
            ok, err = validate_pdf_upload(pdf_file.size, pdf_file.name)
            if not ok:
                upload_error = err
                st.error(err)
            else:
                st.success(f"Accepted: {pdf_file.name}")

    with col_spec:
        st.subheader("UI specification")
        spec_text = st.text_area(
            "Edit UI requirements text",
            height=200,
            placeholder="P10 HMI: header label, OK and Cancel buttons…",
        )

    view = compute_dashboard_view(
        backend_ok=backend_ok,
        backend_status=backend_status,
        wasm_index_path=wasm_path,
        upload_error=upload_error,
        run_status=st.session_state.run_status,
        status_history=st.session_state.status_history,
        capture_path=find_capture_image(output_dir, st.session_state.run_id),
        wasm_url=wasm_url,
    )

    if view.state == "backend_error":
        st.error(view.message)
    elif view.state == "wasm_missing":
        st.warning(view.message)
    elif view.state == "upload_rejected":
        st.error(view.message)
    elif view.state == "running":
        st.info(view.message)

    tab_sim, tab_capture, tab_logs = st.tabs(["WASM Simulator", "Camera capture", "Live logs"])

    with tab_sim:
        if view.iframe_src:
            if is_file_uri(view.iframe_src):
                st.warning("WASM iframe uses file:// — browsers block this; switch to HTTP.")
            components.iframe(view.iframe_src, height=640, scrolling=True)
        else:
            st.info("WASM simulator iframe unavailable.")

    with tab_capture:
        cap = find_capture_image(output_dir, st.session_state.run_id)
        if cap and cap.is_file():
            st.image(str(cap), caption=CAPTURE_FILENAME, use_container_width=True)
            if st.button("Refresh capture"):
                st.rerun()
        else:
            st.caption(f"Polling for `{CAPTURE_FILENAME}` under {output_dir} …")

    with tab_logs:
        if view.log_lines:
            st.code("\n".join(view.log_lines), language="text")
        else:
            st.caption("Pipeline logs appear here after Start.")

    start_disabled = (
        view.state in ("backend_error", "wasm_missing", "upload_rejected")
        or pdf_file is None
        or not spec_text.strip()
        or upload_error is not None
    )

    if st.button("Start pipeline", disabled=start_disabled, type="primary"):
        staging = output_dir / "_dashboard_uploads"
        pdf_path = _write_uploaded_pdf(pdf_file, staging)
        spec_path = _write_spec_text(spec_text.strip(), staging)
        payload = build_run_payload(str(pdf_path), str(spec_path))

        with httpx.Client() as http:
            ok, body, err = post_run_request(api_base, http, payload)
            if not ok or body is None:
                st.session_state.status_history.append(
                    {"status": "failed", "error": {"message": err or "start failed"}}
                )
                st.session_state.run_status = "failed"
                st.session_state.poll_count = 0
            else:
                run_id = body["run_id"]
                st.session_state.run_id = run_id
                st.session_state.run_status = body.get("status", "queued")
                st.session_state.status_history = [body]
                st.session_state.poll_count = 0
                # Kick realtime viewer: first snap then session + periodic rerun (default ≤60)
                if st.session_state.run_status not in ("completed", "failed"):
                    st.session_state.run_status = "running"
        st.rerun()


def main() -> None:
    render_dashboard()


if __name__ == "__main__":
    main()
