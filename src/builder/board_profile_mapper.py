"""T-301: 보드 프로필 매퍼 및 board_config.h 합성.

TechnologyKB(T-203) JSON과 타깃 보드 하드웨어 프로필을 비교·병합하여
`board_config.h` C 헤더 매크로를 동적으로 생성한다.

12항 실패 시 대처: LCD width가 240~1920 범위를 벗어나면 Waveshare 기본
사양(1024x600, MIPI-DSI) 디폴트 헤더로 폴백한다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.common.schema import DEFAULT_RESOLUTION, TechnologyKB

DEFAULT_LCD_WIDTH, DEFAULT_LCD_HEIGHT = DEFAULT_RESOLUTION
MIN_LCD_WIDTH = 240
MAX_LCD_WIDTH = 1920

_TEMPLATE_PATH = Path(__file__).resolve().parent / "template" / "board_config.h.in"


class BoardProfile(BaseModel):
    """타깃 보드 하드웨어 프로필(JSON) 스키마."""

    board_id: str
    idf_target: str
    display_interface: str
    bsp_component: str = ""
    default_resolution: tuple[int, int] = Field(default_factory=lambda: DEFAULT_RESOLUTION)

    @field_validator("default_resolution", mode="before")
    @classmethod
    def _coerce_resolution(cls, value: Any) -> tuple[int, int]:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return int(value[0]), int(value[1])
        raise ValueError("default_resolution must be a [width, height] pair")


def _load_json_source(source: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(source, dict):
        return source
    path = Path(source)
    return json.loads(path.read_text(encoding="utf-8"))


def load_technology_kb(source: dict[str, Any] | str | Path) -> TechnologyKB:
    """TechnologyKB JSON(dict/경로)을 검증·로드한다."""
    return TechnologyKB.model_validate(_load_json_source(source))


def load_board_profile(source: dict[str, Any] | str | Path) -> BoardProfile:
    """보드 프로필 JSON(dict/경로)을 검증·로드한다."""
    return BoardProfile.model_validate(_load_json_source(source))


def is_valid_lcd_width(width: int) -> bool:
    """LCD width 유효 범위(240~1920) 검사."""
    return MIN_LCD_WIDTH <= width <= MAX_LCD_WIDTH


def _use_mipi_dsi(profile: BoardProfile) -> int:
    return 1 if profile.display_interface.lower() == "mipi_dsi" else 0


def _render_template(values: dict[str, str]) -> str:
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _default_header_values() -> dict[str, str]:
    return {
        "BOARD_ID": "esp32p4",
        "IDF_TARGET": "esp32p4",
        "LCD_WIDTH": str(DEFAULT_LCD_WIDTH),
        "LCD_HEIGHT": str(DEFAULT_LCD_HEIGHT),
        "USE_MIPI_DSI": "1",
        "DISPLAY_CONTROLLER": "",
        "COLOR_DEPTH": "",
        "TOUCH_IC": "",
        "FALLBACK_LINE": "#define BOARD_CONFIG_FALLBACK 1",
    }


def render_board_config_header(
    tech_kb: TechnologyKB,
    board_profile: BoardProfile,
    *,
    use_fallback: bool = False,
) -> str:
    """TechnologyKB + 보드 프로필을 병합해 `board_config.h` 텍스트를 반환한다."""
    width, height = tech_kb.resolution

    if use_fallback or not is_valid_lcd_width(width):
        return _render_template(_default_header_values())

    values = {
        "BOARD_ID": board_profile.board_id,
        "IDF_TARGET": board_profile.idf_target,
        "LCD_WIDTH": str(width),
        "LCD_HEIGHT": str(height),
        "USE_MIPI_DSI": str(_use_mipi_dsi(board_profile)),
        "DISPLAY_CONTROLLER": tech_kb.display_controller,
        "COLOR_DEPTH": tech_kb.color_depth,
        "TOUCH_IC": tech_kb.touch_ic,
        "FALLBACK_LINE": "",
    }
    return _render_template(values)


def map_board_config(
    tech_kb_source: dict[str, Any] | str | Path,
    board_profile_source: dict[str, Any] | str | Path,
) -> str:
    """JSON 소스를 로드해 `board_config.h` 헤더 문자열을 합성한다."""
    tech_kb = load_technology_kb(tech_kb_source)
    board_profile = load_board_profile(board_profile_source)
    return render_board_config_header(tech_kb, board_profile)


def write_board_config(
    tech_kb_source: dict[str, Any] | str | Path,
    board_profile_source: dict[str, Any] | str | Path,
    output_path: str | Path,
) -> str:
    """헤더를 합성해 파일로 저장하고 내용을 반환한다."""
    header = map_board_config(tech_kb_source, board_profile_source)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header, encoding="utf-8")
    return header
