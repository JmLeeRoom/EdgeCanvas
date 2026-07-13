"""T-401: VARCO Art API 연동 HMI 이미지 생성기.

단위구현계획서.md 제5장 [T-401] 8항 구현 내용을 따른다.
위젯 트리에서 이미지가 필요한 컴포넌트 메타데이터를 수집하고, 위젯 픽셀 크기에
맞는 생성 프로파일로 VARCO Art API(`src.agent.varco_art.request_image`)를 호출해
`output/<run_id>/assets/`에 PNG를 저장한다.

API 실패·손상 PNG(카드 12) 시 로컬 기본 도형 placeholder로 전환하며,
폴백 산출물 파일명은 ``placeholder_default.png`` 로 교체한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from src.agent.varco_art import (
    is_valid_png,
    make_placeholder_png,
    request_image,
    save_image_bytes,
)
from src.common.run_manager import DEFAULT_OUTPUT_DIR

# 이미지 소스가 필요한 위젯 타입 (T-303 트리 type 필드 / LVGL image 계열).
IMAGE_WIDGET_TYPES = frozenset(
    {
        "image",
        "img",
        "image_button",
        "imagebutton",
        "imgbtn",
        "image_btn",
    }
)

DEFAULT_WIDTH = 100
DEFAULT_HEIGHT = 50
DEFAULT_FALLBACK_BASENAME = "placeholder_default.png"

RequestFn = Callable[..., dict]


def needs_image(node: dict) -> bool:
    """노드가 이미지 생성이 필요한지 판정한다."""
    if node.get("needs_image") is True:
        return True
    raw_type = str(node.get("type", "")).strip().lower().replace("-", "_")
    return raw_type in IMAGE_WIDGET_TYPES


def collect_image_widgets(tree: dict) -> list[dict]:
    """위젯 트리를 DFS로 순회해 이미지 소스가 필요한 컴포넌트 메타데이터를 수집한다."""
    found: list[dict] = []

    def walk(node: dict) -> None:
        if not isinstance(node, dict):
            return
        if needs_image(node):
            found.append(node)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    walk(tree)
    return found


def build_generation_profile(widget: dict) -> dict[str, Any]:
    """컴포넌트 가로/세로 픽셀에 맞춰 VARCO 이미지 생성 프로파일을 구성한다."""
    width = int(widget.get("width") or widget.get("w") or DEFAULT_WIDTH)
    height = int(widget.get("height") or widget.get("h") or DEFAULT_HEIGHT)
    if width <= 0:
        width = DEFAULT_WIDTH
    if height <= 0:
        height = DEFAULT_HEIGHT

    prompt = widget.get("prompt") or widget.get("image_prompt")
    if not prompt:
        wtype = widget.get("type", "image")
        var = widget.get("var", "widget")
        prompt = f"{width}x{height} {wtype} asset for {var}"

    return {
        "width": width,
        "height": height,
        "prompt": str(prompt),
        "var": widget.get("var") or "asset",
    }


def assets_dir_for_run(
    run_id: str, output_dir: Path | str = DEFAULT_OUTPUT_DIR
) -> Path:
    """``output/<run_id>/assets/`` 경로를 반환한다(필요 시 생성)."""
    path = Path(output_dir) / run_id / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_stem(var: str) -> str:
    """파일명에 안전한 위젯 변수명 stem을 만든다."""
    cleaned = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in var)
    return cleaned or "asset"


def _write_default_fallback(
    assets_dir: Path, width: int, height: int, *, reason: str, status_code: int | None
) -> dict:
    """카드 12: 손상/실패 시 기본 폴백 파일명으로 placeholder PNG를 저장한다."""
    fallback_path = assets_dir / DEFAULT_FALLBACK_BASENAME
    save_image_bytes(make_placeholder_png(width, height, color=(0, 0, 255)), fallback_path)
    return {
        "ok": False,
        "status_code": status_code,
        "used_fallback": True,
        "path": str(fallback_path),
        "filename": DEFAULT_FALLBACK_BASENAME,
        "reason": reason,
    }


def _ensure_valid_asset(
    result: dict,
    *,
    assets_dir: Path,
    width: int,
    height: int,
    widget_path: Path,
) -> dict:
    """저장된 파일이 유효 PNG인지 검사하고, 손상 시 폴백 파일명으로 교체한다."""
    path = Path(result.get("path") or widget_path)
    data = path.read_bytes() if path.exists() else b""

    if result.get("used_fallback") and is_valid_png(data):
        # request_image 등이 이미 유효 placeholder를 위젯 경로에 저장한 경우.
        # 정규 폴백 파일명도 함께 두어 카드 12 파일명 교체 경로를 만족한다.
        fallback_path = assets_dir / DEFAULT_FALLBACK_BASENAME
        if not fallback_path.exists():
            save_image_bytes(data if is_valid_png(data) else make_placeholder_png(width, height), fallback_path)
        out = dict(result)
        out["filename"] = path.name
        out["var"] = result.get("var")
        return out

    if result.get("ok") and is_valid_png(data):
        out = dict(result)
        out["filename"] = path.name
        return out

    # 손상 PNG 또는 비정상 성공 보고 → 강제 차단 후 기본 폴백 파일명으로 교체.
    if path.exists() and path.name != DEFAULT_FALLBACK_BASENAME:
        try:
            path.unlink()
        except OSError:
            pass

    reason = result.get("reason") or "corrupted or invalid PNG response"
    if result.get("ok") and data and not is_valid_png(data):
        reason = "corrupted PNG rejected; replaced with default fallback"

    out = _write_default_fallback(
        assets_dir,
        width,
        height,
        reason=reason,
        status_code=result.get("status_code"),
    )
    out["var"] = result.get("var")
    return out


def generate_widget_image(
    widget: dict,
    *,
    run_id: str,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    request_fn: RequestFn | None = None,
    api_key: str | None = None,
) -> dict:
    """단일 위젯에 대해 이미지를 생성·저장하고 결과 dict를 반환한다."""
    profile = build_generation_profile(widget)
    assets_dir = assets_dir_for_run(run_id, output_dir)
    stem = _safe_stem(str(profile["var"]))
    widget_path = assets_dir / f"{stem}.png"
    fn = request_fn or request_image

    result = fn(
        profile["prompt"],
        width=profile["width"],
        height=profile["height"],
        save_path=widget_path,
        api_key=api_key,
    )
    if not isinstance(result, dict):
        result = {
            "ok": False,
            "status_code": None,
            "used_fallback": True,
            "path": str(widget_path),
            "reason": "invalid request_fn return",
        }

    result = dict(result)
    result["var"] = profile["var"]
    result["profile"] = {
        "width": profile["width"],
        "height": profile["height"],
        "prompt": profile["prompt"],
    }
    return _ensure_valid_asset(
        result,
        assets_dir=assets_dir,
        width=profile["width"],
        height=profile["height"],
        widget_path=widget_path,
    )


def generate_images(
    tree: dict,
    *,
    run_id: str,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    request_fn: RequestFn | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """트리 전체에서 이미지 필요 위젯을 수집·생성해 결과 목록을 반환한다."""
    widgets = collect_image_widgets(tree)
    return [
        generate_widget_image(
            w,
            run_id=run_id,
            output_dir=output_dir,
            request_fn=request_fn,
            api_key=api_key,
        )
        for w in widgets
    ]
