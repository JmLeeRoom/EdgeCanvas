"""T-850: Emscripten WASM 브라우저 파이프라인 — 단위 테스트.

단위구현계획서.md 제5장 [T-850] / Task30 테스트 절차:
- Red: emcc 미설치 fixture와 컴파일 오류 로그 fixture로 skip/fail 구분
- Green: mock emcc가 .js/.wasm fixture를 생성 → 경로·MIME·index.html 참조 검사
- 카드 12: emsdk 없으면 WASM 자동 스킵 + SDL2 데스크탑 폴백 문서화

실제 emcc 빌드는 선택(미설치 시 deterministic skip). pytest는 mock으로 통과한다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.simulator.wasm_build import (
    WASM_MIME_TYPES,
    WasmBuildOutcome,
    WasmCompileError,
    build_wasm,
    mime_for,
    resolve_emcc,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "src" / "simulator" / "web"
INDEX_HTML = WEB_DIR / "index.html"
MAKEFILE = WEB_DIR / "Makefile"

EMCC_AVAILABLE = bool(shutil.which("emcc"))


def _mock_emcc_success(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    """Green fixture: emcc -o <out.js> 를 흉내 내 .js/.wasm 파일 생성."""
    out_js: Path | None = None
    for i, arg in enumerate(cmd):
        if arg == "-o" and i + 1 < len(cmd):
            out_js = Path(cmd[i + 1])
            break
    if out_js is None:
        return subprocess.CompletedProcess(cmd, 1, "", "mock emcc: missing -o")
    out_js.parent.mkdir(parents=True, exist_ok=True)
    out_js.write_text("// mock lvgl_sim.js glue\nvar Module = Module || {};\n", encoding="utf-8")
    out_js.with_suffix(".wasm").write_bytes(b"\x00asm\x01\x00\x00\x00")  # minimal wasm magic
    return subprocess.CompletedProcess(cmd, 0, "emcc: mock success\n", "")


def _mock_emcc_compile_error(
    cmd: list[str], **_kwargs: object
) -> subprocess.CompletedProcess[str]:
    """Red fixture: 컴파일 오류 로그."""
    log = (
        "error: undeclared identifier 'lv_init'\n"
        "emcc: error: '/tmp/fail.c' failed\n"
    )
    return subprocess.CompletedProcess(cmd, 1, "", log)


# ---------------------------------------------------------------------------
# 산출물 존재 / index.html / Makefile
# ---------------------------------------------------------------------------


def test_web_pipeline_artifacts_exist():
    """카드 9항: Makefile + index.html 이 src/simulator/web/ 에 있어야 한다."""
    assert MAKEFILE.is_file(), f"missing {MAKEFILE}"
    assert INDEX_HTML.is_file(), f"missing {INDEX_HTML}"


def test_index_html_references_canvas_and_lvgl_sim_js():
    """HTML5 Canvas + lvgl_sim.js 글루 스크립트 참조."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="canvas"' in html or "getElementById('canvas')" in html or 'getElementById("canvas")' in html
    assert "lvgl_sim.js" in html
    assert "<canvas" in html.lower()


def test_makefile_targets_lvgl_sim_via_emcc():
    """Makefile 이 emcc 로 lvgl_sim.js / .wasm 을 내도록 명시."""
    text = MAKEFILE.read_text(encoding="utf-8")
    assert "emcc" in text.lower() or "$(EMCC)" in text
    assert "lvgl_sim.js" in text


def test_mime_types_for_wasm_web_assets():
    """Green: MIME — .wasm / .js / .html 매핑."""
    assert mime_for(".wasm") == "application/wasm"
    assert mime_for(".js") == "application/javascript"
    assert mime_for(".html") == "text/html"
    assert WASM_MIME_TYPES[".wasm"] == "application/wasm"


# ---------------------------------------------------------------------------
# Red: skip vs fail 구분
# ---------------------------------------------------------------------------


def test_emcc_missing_is_skipped_not_failed(tmp_path: Path):
    """Red: emcc 미설치 → SKIPPED (FAILED 가 아님), SDL2 폴백 표시."""
    missing = tmp_path / "no_such_emcc"
    result = build_wasm(
        web_dir=WEB_DIR,
        out_dir=tmp_path / "build_web",
        emcc=missing,
    )
    assert result.outcome == WasmBuildOutcome.SKIPPED
    assert result.outcome != WasmBuildOutcome.FAILED
    assert result.js_path is None
    assert result.wasm_path is None
    assert result.fallback == "sdl2_desktop"
    assert "sdl2" in result.log.lower() or "SDL2" in result.log


def test_compile_error_fixture_is_failed_not_skipped(tmp_path: Path):
    """Red: 컴파일 오류 fixture → FAILED (SKIPPED 와 구분)."""
    fake_emcc = tmp_path / "emcc"
    fake_emcc.write_text("#!/bin/sh\n", encoding="utf-8")
    out_dir = tmp_path / "build_web"

    result = build_wasm(
        web_dir=WEB_DIR,
        out_dir=out_dir,
        emcc=fake_emcc,
        runner=_mock_emcc_compile_error,
        raise_on_compile_error=False,
    )
    assert result.outcome == WasmBuildOutcome.FAILED
    assert result.outcome != WasmBuildOutcome.SKIPPED
    assert "undeclared" in result.log.lower() or "error" in result.log.lower()
    assert result.fallback is None


def test_compile_error_can_raise_wasm_compile_error(tmp_path: Path):
    """컴파일 실패 시 WasmCompileError 로 표면화할 수 있어야 한다."""
    fake_emcc = tmp_path / "emcc"
    fake_emcc.write_text("#!/bin/sh\n", encoding="utf-8")

    with pytest.raises(WasmCompileError) as exc_info:
        build_wasm(
            web_dir=WEB_DIR,
            out_dir=tmp_path / "build_web",
            emcc=fake_emcc,
            runner=_mock_emcc_compile_error,
            raise_on_compile_error=True,
        )
    assert "emcc" in str(exc_info.value).lower() or "compile" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Green: mock emcc 산출물
# ---------------------------------------------------------------------------


def test_mock_emcc_produces_js_and_wasm_paths(tmp_path: Path):
    """Green: mock emcc 가 lvgl_sim.js / lvgl_sim.wasm 을 만들고 경로를 반환."""
    fake_emcc = tmp_path / "emcc"
    fake_emcc.write_text("#!/bin/sh\n", encoding="utf-8")
    out_dir = tmp_path / "build_web"

    result = build_wasm(
        web_dir=WEB_DIR,
        out_dir=out_dir,
        emcc=fake_emcc,
        runner=_mock_emcc_success,
    )
    assert result.outcome == WasmBuildOutcome.SUCCESS
    assert result.js_path is not None and result.js_path.is_file()
    assert result.wasm_path is not None and result.wasm_path.is_file()
    assert result.js_path.name == "lvgl_sim.js"
    assert result.wasm_path.name == "lvgl_sim.wasm"
    assert result.js_path.parent == out_dir
    assert result.wasm_path.read_bytes()[:4] == b"\x00asm"


def test_card12_no_emsdk_auto_skip_documents_sdl2_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """카드 12: emsdk/emcc 없으면 WASM 단계 자동 스킵 + SDL2 데스크탑 대체."""
    monkeypatch.setattr(
        "src.simulator.wasm_build.resolve_emcc",
        lambda emcc=None: None,
    )
    result = build_wasm(web_dir=WEB_DIR, out_dir=tmp_path / "build_web", emcc=None)
    assert result.outcome == WasmBuildOutcome.SKIPPED
    assert result.fallback == "sdl2_desktop"
    # 로그에 폴백 안내가 남아 이후 검증 기록/오케스트레이터가 참조 가능
    assert "fallback" in result.log.lower() or "sdl2" in result.log.lower()


def test_resolve_emcc_none_when_missing(monkeypatch: pytest.MonkeyPatch):
    """resolve_emcc 는 PATH 에 없으면 None."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert resolve_emcc() is None


@pytest.mark.skipif(not EMCC_AVAILABLE, reason="real emcc not on PATH — optional Phase B live build")
def test_optional_real_emcc_build_when_installed(tmp_path: Path):
    """선택: 실제 emcc 가 있으면 빌드 시도(실패해도 파이프라인 호출은 가능해야 함)."""
    result = build_wasm(
        web_dir=WEB_DIR,
        out_dir=tmp_path / "build_web",
        raise_on_compile_error=False,
    )
    assert result.outcome in (
        WasmBuildOutcome.SUCCESS,
        WasmBuildOutcome.FAILED,
        WasmBuildOutcome.SKIPPED,
    )
