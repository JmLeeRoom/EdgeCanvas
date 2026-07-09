"""T-203: Technology KB JSON 스키마 변환기.

단위구현계획서.md 제5장 [T-203] 8-2항 구현 내용을 따른다.
T-202(`spec_extractor.parse_spec_response`) 등이 만든 원시 분석 딕셔너리를
`TechnologyKB` Pydantic 모델로 검증/직렬화하고 JSON 파일로 저장한다.

12항 실패 시 대처: 해상도 등 필수 정보가 누락된 원시 딕셔너리가 들어와도
`TechnologyKB`의 Default Factory(Waveshare 1024x600)가 안전하게 값을
채우므로 인스턴스화가 실패하지 않는다. 반면 타입이 명백히 잘못된 값
(예: resolution에 문자열 하나가 전달됨)은 Pydantic `ValidationError`로
그대로 전파해 호출자가 인지할 수 있게 한다(10항 통과 기준).
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from src.common.schema import TechnologyKB


def _extract_value(raw: dict, key: str, default: object = "") -> object:
    """T-202 스타일 `{"value": ..., "confidence": ..., "assumed": ...}` 필드 또는
    평범한 값을 모두 지원해 `key`의 실제 값을 뽑아낸다.

    `raw[key]`가 dict이고 "value" 키를 가지면 그 값을 사용하고, 그렇지 않으면
    `raw[key]` 자체를 값으로 사용한다. 키가 없으면 `default`를 반환한다.
    """
    if key not in raw:
        return default
    field = raw[key]
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def raw_dict_to_technology_kb(raw: dict) -> TechnologyKB:
    """원시 분석 딕셔너리를 `TechnologyKB` 인스턴스로 검증/변환한다.

    T-202 산출물 필드 매핑:
    - display_controller <- raw["lcd_controller"]["value"]
    - touch_ic <- raw["touch_ic"]["value"]
    - resolution <- (raw["resolution_width"]["value"], raw["resolution_height"]["value"])
    - color_depth <- raw["data_format"]["value"] (없으면 빈 문자열)
    - pin_config <- raw.get("pin_config", {})

    `display_controller`/`touch_ic`/`color_depth`/`pin_config`처럼 T-202
    형태가 아닌 평범한 dict(예: `{"display_controller": "ILI9488", ...}`)도
    `_extract_value`가 그대로 지원한다.

    resolution 값이 폭/높이 모두 없으면 `TechnologyKB`의 Default Factory가
    Waveshare 1024x600으로 폴백한다(12항 대책). 반면 resolution에 명백히
    잘못된 타입(예: 문자열 하나)이 전달되면 Pydantic `ValidationError`가
    그대로 발생한다.
    """
    kwargs: dict = {}

    display_controller = _extract_value(raw, "display_controller")
    if not display_controller:
        display_controller = _extract_value(raw, "lcd_controller")
    if display_controller:
        kwargs["display_controller"] = display_controller

    touch_ic = _extract_value(raw, "touch_ic")
    if touch_ic:
        kwargs["touch_ic"] = touch_ic

    color_depth = _extract_value(raw, "color_depth")
    if not color_depth:
        color_depth = _extract_value(raw, "data_format")
    if color_depth:
        kwargs["color_depth"] = color_depth

    if "resolution" in raw:
        kwargs["resolution"] = raw["resolution"]
    else:
        width = _extract_value(raw, "resolution_width", default=None)
        height = _extract_value(raw, "resolution_height", default=None)
        if width is not None and height is not None:
            kwargs["resolution"] = (width, height)

    if "pin_config" in raw and raw["pin_config"] is not None:
        kwargs["pin_config"] = raw["pin_config"]

    return TechnologyKB(**kwargs)


def convert_and_save(raw: dict, output_path: str | Path) -> TechnologyKB:
    """원시 분석 딕셔너리를 검증해 `TechnologyKB` JSON 파일로 저장한다.

    변환/검증에 실패하면(`ValidationError`) 파일을 저장하지 않고 예외를
    그대로 호출자에게 전파한다.
    """
    kb = raw_dict_to_technology_kb(raw)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(kb.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return kb


__all__ = ["ValidationError", "convert_and_save", "raw_dict_to_technology_kb"]
