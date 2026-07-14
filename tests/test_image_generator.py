"""T-401: VARCO Art API 연동 HMI 이미지 생성기 — 단위 테스트.

단위구현계획서.md 제5장 [T-401] 10항 절차를 코드로 검증한다.
- Red: NC_VARCO_API_KEY 미설정 또는 API 401/5xx fixture → 정적 placeholder fallback.
- Green: API client mock 200/201 → output/<run_id>/assets/ 저장·PNG 매직넘버·fallback 분기.
- 카드 12: 손상 PNG 응답 → 즉시 차단 후 기본 폴백 이미지 파일명으로 교체.
라이브 200/201은 T-010 확인 슬롯 증거로만 승격한다(본 테스트는 mock/fallback만).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.agent.varco_art import PNG_MAGIC, is_valid_png, make_placeholder_png

# 구현 전 Red 확인용 — 모듈이 없으면 ImportError로 실패(기능 부재 확인).
from src.asset.image_generator import (  # noqa: E402
    DEFAULT_FALLBACK_BASENAME,
    build_generation_profile,
    collect_image_widgets,
    generate_images,
)


def _sample_tree() -> dict:
    """이미지 필요 위젯(image_button)과 일반 위젯이 섞인 모의 레이아웃 트리."""
    return {
        "var": "scr",
        "type": "screen",
        "children": [
            {
                "var": "title",
                "type": "label",
                "children": [],
                "event_handlers": [],
            },
            {
                "var": "submit_img_btn",
                "type": "image_button",
                "width": 100,
                "height": 50,
                "prompt": "100x50 blue rectangular submit button",
                "children": [],
                "event_handlers": [],
            },
            {
                "var": "icon_img",
                "type": "image",
                "width": 64,
                "height": 64,
                "prompt": "64x64 factory gear icon",
                "children": [],
                "event_handlers": [],
            },
            {
                "var": "needs_flag",
                "type": "button",
                "needs_image": True,
                "width": 80,
                "height": 40,
                "prompt": "80x40 green start button",
                "children": [],
                "event_handlers": [],
            },
        ],
        "event_handlers": [],
    }


# ---------------------------------------------------------------------------
# 메타데이터 수집 / 생성 프로파일
# ---------------------------------------------------------------------------


def test_collect_image_widgets_from_tree() -> None:
    widgets = collect_image_widgets(_sample_tree())
    vars_ = {w["var"] for w in widgets}
    assert vars_ == {"submit_img_btn", "icon_img", "needs_flag"}
    assert all("type" in w for w in widgets)


def test_build_generation_profile_uses_widget_pixels() -> None:
    profile = build_generation_profile(
        {
            "var": "submit_img_btn",
            "type": "image_button",
            "width": 100,
            "height": 50,
            "prompt": "100x50 blue rectangular submit button",
        }
    )
    assert profile["width"] == 100
    assert profile["height"] == 50
    assert "prompt" in profile and profile["prompt"]
    assert profile["prompt"] == "100x50 blue rectangular submit button"


# ---------------------------------------------------------------------------
# Red: API 키 없음 / 401 / 5xx → placeholder fallback
# ---------------------------------------------------------------------------


def test_missing_api_key_selects_placeholder_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("NC_VARCO_API_KEY", raising=False)
    run_id = "run_test_no_key"
    results = generate_images(
        _sample_tree(),
        run_id=run_id,
        output_dir=tmp_path,
    )
    assert results, "이미지 필요 위젯에 대한 결과가 있어야 한다"
    assert all(r["used_fallback"] is True for r in results)
    for r in results:
        path = Path(r["path"])
        assert path.exists()
        assert is_valid_png(path.read_bytes())
        assert path.parent == tmp_path / run_id / "assets"


def test_http_401_fixture_uses_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NC_VARCO_API_KEY", "test-key-not-used-by-mock")

    def fake_request(prompt, *, width, height, save_path, **kwargs):
        dst = Path(save_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        # API 401 → 호출자가 fallback으로 전환했다고 보고
        from src.agent.varco_art import save_image_bytes

        save_image_bytes(make_placeholder_png(width, height), dst)
        return {
            "ok": False,
            "status_code": 401,
            "used_fallback": True,
            "path": str(dst),
            "reason": "HTTP 401",
        }

    results = generate_images(
        {
            "var": "scr",
            "type": "screen",
            "children": [
                {
                    "var": "btn",
                    "type": "image_button",
                    "width": 100,
                    "height": 50,
                    "prompt": "button",
                    "children": [],
                }
            ],
        },
        run_id="run_401",
        output_dir=tmp_path,
        request_fn=fake_request,
    )
    assert len(results) == 1
    assert results[0]["used_fallback"] is True
    assert results[0]["status_code"] == 401
    assert is_valid_png(Path(results[0]["path"]).read_bytes())


def test_http_5xx_fixture_uses_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NC_VARCO_API_KEY", "test-key-not-used-by-mock")

    def fake_request(prompt, *, width, height, save_path, **kwargs):
        dst = Path(save_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        from src.agent.varco_art import save_image_bytes

        save_image_bytes(make_placeholder_png(width, height), dst)
        return {
            "ok": False,
            "status_code": 503,
            "used_fallback": True,
            "path": str(dst),
            "reason": "HTTP 503",
        }

    results = generate_images(
        {
            "var": "scr",
            "type": "screen",
            "children": [
                {
                    "var": "icon",
                    "type": "image",
                    "width": 32,
                    "height": 32,
                    "prompt": "icon",
                    "children": [],
                }
            ],
        },
        run_id="run_5xx",
        output_dir=tmp_path,
        request_fn=fake_request,
    )
    assert len(results) == 1
    assert results[0]["used_fallback"] is True
    assert results[0]["status_code"] == 503
    assert is_valid_png(Path(results[0]["path"]).read_bytes())


# ---------------------------------------------------------------------------
# Green: mock 200/201 → assets 경로·PNG 매직·성공 분기
# ---------------------------------------------------------------------------


def test_mock_200_saves_valid_png_under_assets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NC_VARCO_API_KEY", "mock-key")
    run_id = "run_ok_200"
    png = make_placeholder_png(100, 50, color=(0, 128, 255))

    def fake_request(prompt, *, width, height, save_path, **kwargs):
        assert width == 100
        assert height == 50
        dst = Path(save_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(png)
        return {
            "ok": True,
            "status_code": 200,
            "used_fallback": False,
            "path": str(dst),
            "reason": None,
        }

    tree = {
        "var": "scr",
        "type": "screen",
        "children": [
            {
                "var": "submit_img_btn",
                "type": "image_button",
                "width": 100,
                "height": 50,
                "prompt": "100x50 blue rectangular submit button",
                "children": [],
            }
        ],
    }
    results = generate_images(
        tree,
        run_id=run_id,
        output_dir=tmp_path,
        request_fn=fake_request,
    )
    assert len(results) == 1
    result = results[0]
    assert result["ok"] is True
    assert result["used_fallback"] is False
    assert result["status_code"] == 200
    path = Path(result["path"])
    assert path == tmp_path / run_id / "assets" / "submit_img_btn.png"
    data = path.read_bytes()
    assert data.startswith(PNG_MAGIC)
    assert is_valid_png(data)


def test_mock_201_saves_valid_png(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NC_VARCO_API_KEY", "mock-key")
    png = make_placeholder_png(64, 64, color=(255, 0, 0))

    def fake_request(prompt, *, width, height, save_path, **kwargs):
        dst = Path(save_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(png)
        return {
            "ok": True,
            "status_code": 201,
            "used_fallback": False,
            "path": str(dst),
            "reason": None,
        }

    results = generate_images(
        {
            "var": "scr",
            "type": "screen",
            "children": [
                {
                    "var": "gear",
                    "type": "image",
                    "width": 64,
                    "height": 64,
                    "prompt": "gear",
                    "children": [],
                }
            ],
        },
        run_id="run_ok_201",
        output_dir=tmp_path,
        request_fn=fake_request,
    )
    assert results[0]["status_code"] == 201
    assert results[0]["used_fallback"] is False
    assert is_valid_png(Path(results[0]["path"]).read_bytes())


# ---------------------------------------------------------------------------
# 카드 12: 손상 PNG → 거부 후 기본 폴백 파일명으로 교체
# ---------------------------------------------------------------------------


def test_corrupted_png_rejected_and_replaced_with_default_fallback(
    tmp_path, monkeypatch
) -> None:
    """손상 PNG 응답을 강제 차단하고 DEFAULT_FALLBACK_BASENAME으로 교체한다."""
    monkeypatch.setenv("NC_VARCO_API_KEY", "mock-key")
    run_id = "run_corrupt"

    def fake_request(prompt, *, width, height, save_path, **kwargs):
        dst = Path(save_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        # 매직만 있거나 깨진 바이너리 — 유효 PNG가 아님
        dst.write_bytes(b"\x89PNG\r\n\x1a\n" + b"CORRUPT")
        return {
            "ok": True,  # API는 200처럼 보이지만 본문이 손상
            "status_code": 200,
            "used_fallback": False,
            "path": str(dst),
            "reason": None,
        }

    results = generate_images(
        {
            "var": "scr",
            "type": "screen",
            "children": [
                {
                    "var": "broken_btn",
                    "type": "image_button",
                    "width": 100,
                    "height": 50,
                    "prompt": "button",
                    "children": [],
                }
            ],
        },
        run_id=run_id,
        output_dir=tmp_path,
        request_fn=fake_request,
    )
    assert len(results) == 1
    result = results[0]
    assert result["used_fallback"] is True
    assert result["ok"] is False
    path = Path(result["path"])
    assert path.name == DEFAULT_FALLBACK_BASENAME
    assert path.parent == tmp_path / run_id / "assets"
    assert is_valid_png(path.read_bytes())
    # 손상 원본은 남아 있으면 안 되거나, 있어도 결과 경로는 폴백 파일명이어야 한다.
    broken = tmp_path / run_id / "assets" / "broken_btn.png"
    if broken.exists():
        assert not is_valid_png(broken.read_bytes()) or broken.read_bytes() != path.read_bytes()


def test_generate_images_does_not_require_live_api_key(tmp_path, monkeypatch) -> None:
    """통과 기준: API 키 없이도 mock/fallback 자동 테스트가 통과한다."""
    monkeypatch.delenv("NC_VARCO_API_KEY", raising=False)
    assert os.getenv("NC_VARCO_API_KEY") is None
    results = generate_images(
        {
            "var": "scr",
            "type": "screen",
            "children": [
                {
                    "var": "x",
                    "type": "image",
                    "width": 16,
                    "height": 16,
                    "children": [],
                }
            ],
        },
        run_id="run_offline",
        output_dir=tmp_path,
    )
    assert results[0]["used_fallback"] is True
    assert is_valid_png(Path(results[0]["path"]).read_bytes())
