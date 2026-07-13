"""T-301: 보드 프로필 매퍼 — 단위 테스트.

단위구현계획서.md 제5장 [T-301] 10항 절차를 코드로 검증한다.
- 준비: TechnologyKB JSON 및 보드 프로필 JSON.
- 실행: `pytest tests/test_board_mapper.py`
- 통과 기준: `board_config.h`에 `#define LCD_WIDTH 1024`, `#define USE_MIPI_DSI` 등
  타깃 사양에 일치하는 매크로 상수가 유효하게 텍스트 교체된다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.builder.board_profile_mapper import (
    DEFAULT_LCD_HEIGHT,
    DEFAULT_LCD_WIDTH,
    BoardProfile,
    map_board_config,
    render_board_config_header,
)
from src.common.schema import TechnologyKB

ESP32P4_PROFILE = {
    "board_id": "esp32p4",
    "idf_target": "esp32p4",
    "display_interface": "mipi_dsi",
    "bsp_component": "esp_bsp_devkit",
    "default_resolution": [1024, 600],
}

CORES3_PROFILE = {
    "board_id": "cores3",
    "idf_target": "esp32s3",
    "display_interface": "spi",
    "bsp_component": "m5stack_core_s3",
    "default_resolution": [320, 240],
}

KB_WAVESHARE = {
    "display_controller": "ILI9488",
    "resolution": [1024, 600],
    "color_depth": "RGB565",
    "touch_ic": "FT6236",
    "pin_config": {},
}


@pytest.fixture
def kb_waveshare() -> TechnologyKB:
    return TechnologyKB.model_validate(KB_WAVESHARE)


@pytest.fixture
def esp32p4_profile() -> BoardProfile:
    return BoardProfile.model_validate(ESP32P4_PROFILE)


@pytest.fixture
def cores3_profile() -> BoardProfile:
    return BoardProfile.model_validate(CORES3_PROFILE)


def test_esp32p4_header_contains_lcd_width_and_mipi_dsi(
    kb_waveshare: TechnologyKB, esp32p4_profile: BoardProfile
):
    header = render_board_config_header(kb_waveshare, esp32p4_profile)

    assert "#define LCD_WIDTH 1024" in header
    assert "#define LCD_HEIGHT 600" in header
    assert "#define USE_MIPI_DSI 1" in header
    assert '#define BOARD_ID "esp32p4"' in header
    assert '#define IDF_TARGET "esp32p4"' in header
    assert '#define DISPLAY_CONTROLLER "ILI9488"' in header


def test_cores3_header_branches_without_mipi_dsi(cores3_profile: BoardProfile):
    kb = TechnologyKB(
        display_controller="ILI9341",
        resolution=(320, 240),
        color_depth="RGB565",
        touch_ic="FT6336",
    )
    header = render_board_config_header(kb, cores3_profile)

    assert "#define LCD_WIDTH 320" in header
    assert "#define LCD_HEIGHT 240" in header
    assert "#define USE_MIPI_DSI 0" in header
    assert '#define BOARD_ID "cores3"' in header
    assert '#define IDF_TARGET "esp32s3"' in header


def test_invalid_lcd_width_falls_back_to_default_header(esp32p4_profile: BoardProfile):
    """12항: width가 240~1920 범위 밖이면 기본 디폴트 헤더로 폴백한다."""
    kb = TechnologyKB(resolution=(100, 600))
    header = render_board_config_header(kb, esp32p4_profile)

    assert "#define LCD_WIDTH 100" not in header
    assert f"#define LCD_WIDTH {DEFAULT_LCD_WIDTH}" in header
    assert f"#define LCD_HEIGHT {DEFAULT_LCD_HEIGHT}" in header
    assert "#define USE_MIPI_DSI 1" in header
    assert "#define BOARD_CONFIG_FALLBACK 1" in header


def test_map_board_config_from_json_paths(tmp_path: Path):
    """JSON 파일 경로 입력으로 헤더를 합성할 수 있어야 한다."""
    kb_path = tmp_path / "kb.json"
    profile_path = tmp_path / "esp32p4_profile.json"
    kb_path.write_text(json.dumps(KB_WAVESHARE), encoding="utf-8")
    profile_path.write_text(json.dumps(ESP32P4_PROFILE), encoding="utf-8")

    header = map_board_config(kb_path, profile_path)

    assert "#define LCD_WIDTH 1024" in header
    assert "#define USE_MIPI_DSI 1" in header


def test_header_generation_never_raises_for_valid_inputs(
    kb_waveshare: TechnologyKB,
    esp32p4_profile: BoardProfile,
    cores3_profile: BoardProfile,
):
    """DoD: 컴파일 전 단계 헤더 생성이 예외 없이 완료되어야 한다."""
    headers = [
        render_board_config_header(kb_waveshare, esp32p4_profile),
        render_board_config_header(kb_waveshare, cores3_profile),
    ]
    for header in headers:
        assert header.startswith("#ifndef BOARD_CONFIG_H")
        assert header.strip().endswith("#endif /* BOARD_CONFIG_H */")
        assert "{{" not in header
