"""T-850: Emscripten WASM 웹 시뮬 빌드 파이프라인.

카드 12 대처: emsdk/emcc 가 없으면 WASM 단계를 자동 스킵하고
PC SDL2 데스크탑 빌드(T-801/T-802)로 대체하도록 안내한다.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_WEB_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_OUT_DIR_NAME = "build_web"
JS_NAME = "lvgl_sim.js"
WASM_NAME = "lvgl_sim.wasm"

# 정적 서빙 / 브라우저 로드 시 기대 MIME (Green 검사)
WASM_MIME_TYPES: dict[str, str] = {
    ".js": "application/javascript",
    ".wasm": "application/wasm",
    ".html": "text/html",
}

Runner = Callable[..., subprocess.CompletedProcess[str]]


class WasmBuildOutcome(str, Enum):
    """skip(emcc 없음) vs fail(컴파일 오류) vs success 구분."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


class WasmCompileError(RuntimeError):
    """emcc 가 존재하나 컴파일이 실패한 경우."""


@dataclass(frozen=True)
class WasmBuildResult:
    outcome: WasmBuildOutcome
    js_path: Path | None = None
    wasm_path: Path | None = None
    log: str = ""
    fallback: str | None = None


def mime_for(suffix: str) -> str:
    """웹 자산 확장자 → MIME 타입."""
    key = suffix if suffix.startswith(".") else f".{suffix}"
    try:
        return WASM_MIME_TYPES[key.lower()]
    except KeyError as exc:
        raise KeyError(f"unsupported wasm web asset suffix: {suffix}") from exc


def resolve_emcc(emcc: str | Path | None = None) -> Path | None:
    """명시 경로 또는 PATH 에서 emcc 를 찾는다. 없으면 None."""
    if emcc is not None:
        path = Path(emcc)
        if path.is_file():
            return path
        return None
    found = shutil.which("emcc")
    return Path(found) if found else None


def _default_runner(cmd: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        **kwargs,  # type: ignore[arg-type]
    )


def build_wasm(
    *,
    web_dir: Path | str = DEFAULT_WEB_DIR,
    out_dir: Path | str | None = None,
    emcc: str | Path | None = None,
    sources: Sequence[Path | str] | None = None,
    runner: Runner | None = None,
    raise_on_compile_error: bool = False,
) -> WasmBuildResult:
    """emcc 로 ``lvgl_sim.js`` / ``lvgl_sim.wasm`` 을 생성한다.

    - emcc 미발견 → ``SKIPPED`` + ``fallback="sdl2_desktop"`` (카드 12)
    - 컴파일 실패 → ``FAILED`` (또는 ``WasmCompileError``)
    - 성공 → ``SUCCESS`` + 산출물 경로
    """
    web = Path(web_dir)
    out = Path(out_dir) if out_dir is not None else web / DEFAULT_OUT_DIR_NAME
    emcc_path = resolve_emcc(emcc)

    if emcc_path is None:
        log = (
            "[T-850] emcc/emsdk not found — skipping WebAssembly compile.\n"
            "fallback: use desktop SDL2 simulator (T-801/T-802, src/simulator).\n"
            "Install guide: src/simulator/web/README.md\n"
        )
        return WasmBuildResult(
            outcome=WasmBuildOutcome.SKIPPED,
            log=log,
            fallback="sdl2_desktop",
        )

    out.mkdir(parents=True, exist_ok=True)
    js_out = out / JS_NAME
    wasm_out = out / WASM_NAME

    if sources is None:
        # 기본: Makefile 과 동일하게 상위 main.c (LVGL+SDL2 emscripten 포트)
        src_main = web.parent / "main.c"
        src_list = [src_main] if src_main.is_file() else []
    else:
        src_list = [Path(s) for s in sources]

    # emcc … -o lvgl_sim.js  (동시 생성: lvgl_sim.wasm)
    cmd: list[str] = [
        str(emcc_path),
        *[str(s) for s in src_list],
        "-O2",
        "-sUSE_SDL=2",
        "-sALLOW_MEMORY_GROWTH=1",
        "-sEXPORTED_RUNTIME_METHODS=ccall,cwrap",
        "-o",
        str(js_out),
    ]

    run = runner or _default_runner
    completed = run(cmd)

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    combined = (stdout + "\n" + stderr).strip()

    if completed.returncode != 0:
        log = f"[T-850] emcc compile FAILED (exit {completed.returncode})\n{combined}\n"
        if raise_on_compile_error:
            raise WasmCompileError(log)
        return WasmBuildResult(outcome=WasmBuildOutcome.FAILED, log=log)

    if not js_out.is_file():
        log = f"[T-850] emcc exited 0 but missing {js_out}\n{combined}\n"
        if raise_on_compile_error:
            raise WasmCompileError(log)
        return WasmBuildResult(outcome=WasmBuildOutcome.FAILED, log=log)

    # 일부 링크 모드에서는 .wasm 이 같은 stem 으로 나온다.
    if not wasm_out.is_file():
        sibling = js_out.with_suffix(".wasm")
        if sibling.is_file() and sibling != wasm_out:
            sibling.replace(wasm_out)

    log = f"[T-850] emcc SUCCESS → {js_out}\n{combined}\n"
    return WasmBuildResult(
        outcome=WasmBuildOutcome.SUCCESS,
        js_path=js_out,
        wasm_path=wasm_out if wasm_out.is_file() else None,
        log=log,
    )
