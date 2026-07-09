"""T-203: Technology KB JSON 스키마 변환기 — 단위 테스트.

단위구현계획서.md 제5장 [T-203] 10항 절차를 코드로 검증한다.
- 준비: 원시 분석 딕셔너리 데이터(T-202 스타일 및 평범한 dict) 입력.
- 실행: `pytest tests/test_kb_converter.py`
- 통과 기준: `TechnologyKB` 모델에 어긋나는 타입(예: resolution에 문자열이
  전달된 경우) 입력 시 Pydantic `ValidationError`가 정확히 포착되고,
  정상 데이터는 규격 JSON 파일로 성공 변환 저장된다
  (`tests/data/expected_kb.json`과 구조적으로 100% 동등).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.common.schema import DEFAULT_RESOLUTION, TechnologyKB
from src.parser.kb_converter import convert_and_save, raw_dict_to_technology_kb

EXPECTED_KB_PATH = Path(__file__).parent / "data" / "expected_kb.json"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def t202_style_raw() -> dict:
    """T-202 `parse_spec_response` 반환 형태({"value": ..., ...})의 원시 딕셔너리."""
    return {
        "lcd_controller": {"value": "ILI9488", "confidence": 0.95, "assumed": False},
        "touch_ic": {"value": "FT6236", "confidence": 0.9, "assumed": False},
        "resolution_width": {"value": 1024, "confidence": 0.9, "assumed": False},
        "resolution_height": {"value": 600, "confidence": 0.9, "assumed": False},
        "data_format": {"value": "RGB565", "confidence": 0.9, "assumed": False},
    }


# ---------------------------------------------------------------------------
# 1) 정상 데이터 -> TechnologyKB 변환/검증
# ---------------------------------------------------------------------------

def test_raw_dict_to_technology_kb_maps_t202_fields(t202_style_raw):
    kb = raw_dict_to_technology_kb(t202_style_raw)

    assert isinstance(kb, TechnologyKB)
    assert kb.display_controller == "ILI9488"
    assert kb.touch_ic == "FT6236"
    assert kb.resolution == (1024, 600)
    assert kb.color_depth == "RGB565"
    assert kb.pin_config == {}


def test_raw_dict_to_technology_kb_accepts_plain_dict():
    """평범한(비-T-202) dict 입력도 그대로 지원해야 한다."""
    raw = {
        "display_controller": "ST7262",
        "resolution": (800, 480),
        "color_depth": "RGB888",
        "touch_ic": "GT911",
        "pin_config": {"SCK": 3, "MOSI": 4},
    }
    kb = raw_dict_to_technology_kb(raw)

    assert kb.display_controller == "ST7262"
    assert kb.resolution == (800, 480)
    assert kb.color_depth == "RGB888"
    assert kb.touch_ic == "GT911"
    assert kb.pin_config == {"SCK": 3, "MOSI": 4}


# ---------------------------------------------------------------------------
# 2) 통과 기준: 잘못된 타입 입력 시 ValidationError 정확히 포착
# ---------------------------------------------------------------------------

def test_raw_dict_to_technology_kb_invalid_resolution_type_raises_validation_error():
    """resolution에 문자열 하나가 전달되면 Pydantic ValidationError가 발생해야 한다."""
    raw = {
        "display_controller": "ILI9488",
        "resolution": "1024x600",
        "color_depth": "RGB565",
        "touch_ic": "FT6236",
    }

    with pytest.raises(ValidationError):
        raw_dict_to_technology_kb(raw)


def test_convert_and_save_invalid_type_does_not_write_file(tmp_path):
    """검증 실패 시 JSON 파일이 저장되지 않아야 한다."""
    raw = {"resolution": "not-a-tuple"}
    output_path = tmp_path / "bad_kb.json"

    with pytest.raises(ValidationError):
        convert_and_save(raw, output_path)

    assert not output_path.exists()


# ---------------------------------------------------------------------------
# 3) 12항 실패 시 대처: 필수 정보(해상도) 누락 -> Waveshare 1024x600 기본값 폴백
# ---------------------------------------------------------------------------

def test_raw_dict_missing_resolution_falls_back_to_waveshare_default():
    """해상도 정보가 전혀 없어도 인스턴스화가 실패하지 않고 기본값(1024x600)으로 폴백해야 한다."""
    raw = {
        "lcd_controller": {"value": "ILI9488", "confidence": 0.9, "assumed": False},
        "touch_ic": {"value": "FT6236", "confidence": 0.9, "assumed": False},
        "data_format": {"value": "RGB565", "confidence": 0.9, "assumed": False},
    }

    kb = raw_dict_to_technology_kb(raw)

    assert kb.resolution == DEFAULT_RESOLUTION
    assert kb.resolution == (1024, 600)


def test_raw_dict_empty_input_still_instantiates_with_defaults():
    """빈 딕셔너리를 넘겨도 예외 없이 모든 필드가 안전 기본값으로 채워져야 한다."""
    kb = raw_dict_to_technology_kb({})

    assert kb.display_controller == ""
    assert kb.resolution == (1024, 600)
    assert kb.color_depth == ""
    assert kb.touch_ic == ""
    assert kb.pin_config == {}


# ---------------------------------------------------------------------------
# 4) DoD(11-b): 변환된 JSON 파일 형상이 tests/data/expected_kb.json과 구조적으로 100% 동등
# ---------------------------------------------------------------------------

def test_convert_and_save_writes_json_matching_expected_fixture(t202_style_raw, tmp_path):
    output_path = tmp_path / "kb.json"

    kb = convert_and_save(t202_style_raw, output_path)

    assert isinstance(kb, TechnologyKB)
    assert output_path.exists()

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED_KB_PATH.read_text(encoding="utf-8"))

    assert saved == expected


def test_convert_and_save_creates_parent_directories(t202_style_raw, tmp_path):
    output_path = tmp_path / "nested" / "dir" / "kb.json"

    convert_and_save(t202_style_raw, output_path)

    assert output_path.exists()
