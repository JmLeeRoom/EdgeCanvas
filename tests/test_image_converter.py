"""T-402: PNG → LVGL C 배열 변환기 — 단위 테스트.

단위구현계획서.md 제5장 [T-402] 10항·12항을 코드로 검증한다.
- 통과 기준: lv_image_dsc_t + 16진수 픽셀 배열(0x..,)이 결과 디렉토리에 생성.
- 카드 12: Node/lv_img_conv 누락 시 Pillow RGB565 폴백으로 변환 성공.
- DoD: CLI subprocess 호출 에러율 0%(mock), C 구조체가 GCC 링크 가능 필드 포함.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from src.asset.image_converter import (  # noqa: E402
    convert_png_to_c,
)


def _make_fixture_png(path: Path, *, width: int = 4, height: int = 2, color=(255, 0, 0)) -> Path:
    """작은 단색 PNG fixture를 생성한다."""
    img = Image.new("RGB", (width, height), color=color)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")
    return path


def _assert_lvgl_c_structure(c_text: str) -> None:
    """LVGL 9.x 링크 가능 C 소스의 핵심 마커를 검증한다."""
    assert "lv_image_dsc_t" in c_text
    assert re.search(r"0x[0-9a-fA-F]{2}\s*,", c_text), "hex pixel array (0xNN,) required"
    assert "LV_COLOR_FORMAT_RGB565" in c_text or "RGB565" in c_text
    # GCC 링크에 필요한 디스크립터 필드
    assert ".header.w" in c_text or "header.w" in c_text
    assert ".header.h" in c_text or "header.h" in c_text
    assert ".data" in c_text
    assert ".data_size" in c_text


# ---------------------------------------------------------------------------
# Happy path — PNG → C in output dir
# ---------------------------------------------------------------------------


def test_convert_png_produces_lv_image_dsc_and_hex_array(tmp_path: Path) -> None:
    png = _make_fixture_png(tmp_path / "fixtures" / "icon.png", width=4, height=2)
    out_dir = tmp_path / "converted"

    c_path = convert_png_to_c(png, out_dir)

    assert c_path.exists()
    assert c_path.suffix == ".c"
    assert c_path.parent == out_dir.resolve() or c_path.parent == out_dir
    text = c_path.read_text(encoding="utf-8")
    _assert_lvgl_c_structure(text)
    assert "icon" in c_path.stem or "icon" in text


def test_output_lands_in_expected_directory(tmp_path: Path) -> None:
    png = _make_fixture_png(tmp_path / "btn.png", width=8, height=4, color=(0, 128, 255))
    out_dir = tmp_path / "run_assets" / "c"
    c_path = convert_png_to_c(png, out_dir, symbol_name="btn_asset")

    assert out_dir.exists()
    assert c_path.is_file()
    assert c_path.parent.resolve() == out_dir.resolve()
    assert list(out_dir.glob("*.c")), "at least one .c must accumulate in result dir"


# ---------------------------------------------------------------------------
# CLI seam — mock success (DoD: invoke error rate 0%)
# ---------------------------------------------------------------------------


def test_lv_img_conv_subprocess_success_zero_error_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """lv_img_conv가 정상(returncode 0)이면 예외 없이 그 출력을 사용한다."""
    png = _make_fixture_png(tmp_path / "ok.png")
    out_dir = tmp_path / "out"

    def fake_run(cmd, *args, **kwargs):
        # subprocess가 쓰는 out_dir에 mock C를 기록
        out_dir.mkdir(parents=True, exist_ok=True)
        mock_c = out_dir / "ok.c"
        mock_c.write_text(
            "/* mock lv_img_conv */\n"
            "const uint8_t ok_map[] = { 0x3f, 0xff, 0x00, 0x00 };\n"
            "const lv_image_dsc_t ok = {\n"
            "  .header.cf = LV_COLOR_FORMAT_RGB565,\n"
            "  .header.w = 4,\n"
            "  .header.h = 2,\n"
            "  .data_size = 4,\n"
            "  .data = ok_map,\n"
            "};\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr("src.asset.image_converter.subprocess.run", fake_run)
    monkeypatch.setattr(
        "src.asset.image_converter.lv_img_conv_available", lambda: True
    )

    c_path = convert_png_to_c(png, out_dir, prefer_cli=True)
    assert c_path.exists()
    text = c_path.read_text(encoding="utf-8")
    assert "lv_image_dsc_t" in text
    assert "0x3f" in text


# ---------------------------------------------------------------------------
# Card 12 — missing Node / lv_img_conv → Pillow RGB565 fallback
# ---------------------------------------------------------------------------


def test_missing_lv_img_conv_falls_back_to_pillow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Node/lv_img_conv 누락(FileNotFoundError) 시 Pillow 폴백으로 C를 생성한다."""
    png = _make_fixture_png(tmp_path / "fallback.png", width=4, height=2, color=(0, 255, 0))
    out_dir = tmp_path / "fallback_out"

    def boom(*_a, **_k):
        raise FileNotFoundError("lv_img_conv / npx not found")

    monkeypatch.setattr("src.asset.image_converter.subprocess.run", boom)
    monkeypatch.setattr(
        "src.asset.image_converter.lv_img_conv_available", lambda: True
    )

    c_path = convert_png_to_c(png, out_dir, prefer_cli=True)
    assert c_path.exists()
    text = c_path.read_text(encoding="utf-8")
    _assert_lvgl_c_structure(text)
    # Pillow 경로 표시(메타 주석) 또는 map 배열이 존재
    assert "_map[]" in text or "const uint8_t" in text


def test_cli_nonzero_exit_falls_back_to_pillow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI가 비정상 종료해도 전체 변환은 Pillow로 성공(에러율 0% 목표)."""
    png = _make_fixture_png(tmp_path / "fail_cli.png")
    out_dir = tmp_path / "fail_out"

    def bad_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"conv failed")

    monkeypatch.setattr("src.asset.image_converter.subprocess.run", bad_run)
    monkeypatch.setattr(
        "src.asset.image_converter.lv_img_conv_available", lambda: True
    )

    c_path = convert_png_to_c(png, out_dir, prefer_cli=True)
    assert c_path.exists()
    _assert_lvgl_c_structure(c_path.read_text(encoding="utf-8"))


def test_cli_unavailable_falls_back_to_pillow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PATH에 npx/lv_img_conv가 없으면 CLI를 건너뛰고 Pillow로 변환한다."""
    png = _make_fixture_png(tmp_path / "no_cli.png", width=4, height=2)
    out_dir = tmp_path / "no_cli_out"

    monkeypatch.setattr(
        "src.asset.image_converter.lv_img_conv_available", lambda: False
    )

    c_path = convert_png_to_c(png, out_dir, prefer_cli=True)
    assert c_path.exists()
    text = c_path.read_text(encoding="utf-8")
    _assert_lvgl_c_structure(text)
    assert "Pillow" in text


def test_force_pillow_rgb565_produces_valid_c(tmp_path: Path) -> None:
    """명시적 Pillow 경로도 RGB565 C를 생성한다."""
    png = _make_fixture_png(tmp_path / "direct.png", width=2, height=2, color=(255, 128, 0))
    out_dir = tmp_path / "pillow_only"
    c_path = convert_png_to_c(png, out_dir, prefer_cli=False)
    text = c_path.read_text(encoding="utf-8")
    _assert_lvgl_c_structure(text)
    # 2x2 RGB565 → 8 bytes → 최소 8개 hex token
    hex_tokens = re.findall(r"0x[0-9a-fA-F]{2}", text)
    assert len(hex_tokens) >= 8
