"""T-202: 데이터시트 핵심 스펙 RAG 추출기 — 단위 테스트.

단위구현계획서.md 제5장 [T-202] 10항 절차를 코드로 검증한다.
- 오프라인(API 불필요): 키워드 기반 유사도 검색(retrieval) 랭킹 로직,
  프롬프트 템플릿 생성, 결과 파싱(안전 처리/신뢰도 라벨링).
- 라이브(@REQUIRES_LIVE_API): 실제 Solar Pro API로 하드코딩된 데이터시트
  청크 fixture에서 5대 핵심 필드(lcd_controller, touch_ic,
  resolution_width, resolution_height, data_format)를 추출한다.
"""
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

from src.parser.document_parser import Chunk  # noqa: E402
from src.parser.spec_extractor import (  # noqa: E402
    extract_specs,
    parse_spec_response,
    retrieve_relevant_chunks,
)
from src.parser.prompts import SPEC_EXTRACTION_QUERY_KEYWORDS, build_spec_extraction_prompt  # noqa: E402

REQUIRES_LIVE_API = pytest.mark.skipif(
    not os.getenv("UPSTAGE_API_KEY"),
    reason="UPSTAGE_API_KEY가 .env에 설정되어 있지 않습니다.",
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_chunks() -> list[Chunk]:
    return [
        Chunk(
            index=0,
            text=(
                "본 제품의 전원 사양은 3.3V 단일 레일이며, 소비 전류는 idle 시 "
                "120mA, active 시 최대 350mA이다. 동작 온도 범위는 -20C ~ 60C이다."
            ),
        ),
        Chunk(
            index=1,
            text=(
                "LCD 컨트롤러는 ILI9488이며 해상도는 320x480, 인터페이스는 SPI "
                "(4-wire, 최대 클럭 30MHz)이다. 데이터 포맷은 RGB565를 사용한다."
            ),
        ),
        Chunk(
            index=2,
            text=(
                "터치 컨트롤러는 FT6236이며 I2C 인터페이스(주소 0x38)로 연결되고 "
                "최대 2점 멀티터치를 지원한다."
            ),
        ),
        Chunk(
            index=3,
            text=(
                "핀 매핑: VCC=1번, GND=2번, SCK=3번, MOSI=4번, MISO=5번, CS=6번, "
                "DC=7번, RESET=8번, BL=9번 이다. 커넥터는 FPC 40핀을 사용한다."
            ),
        ),
        Chunk(
            index=4,
            text=(
                "패키징 정보: 제품은 anti-static bag에 개별 포장되며 outer box "
                "당 20개씩 적재된다. 물류 라벨에는 로트 번호가 인쇄된다."
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# 1) 유사도 벡터 검색 모의 로직 (키워드 기반 랭킹)
# ---------------------------------------------------------------------------

def test_retrieve_relevant_chunks_ranks_spec_related_chunks_first(sample_chunks):
    ranked = retrieve_relevant_chunks(sample_chunks, SPEC_EXTRACTION_QUERY_KEYWORDS, top_n=3)

    assert len(ranked) == 3
    ranked_indices = [c.index for c in ranked]
    # LCD/터치/핀 관련 청크(1,2,3)가 전원/패키징 청크(0,4)보다 상위에 랭크되어야 한다.
    assert 4 not in ranked_indices


def test_retrieve_relevant_chunks_empty_input_returns_empty():
    assert retrieve_relevant_chunks([], SPEC_EXTRACTION_QUERY_KEYWORDS, top_n=3) == []


def test_retrieve_relevant_chunks_top_n_respected(sample_chunks):
    ranked = retrieve_relevant_chunks(sample_chunks, SPEC_EXTRACTION_QUERY_KEYWORDS, top_n=2)
    assert len(ranked) <= 2


# ---------------------------------------------------------------------------
# 2) 프롬프트 템플릿
# ---------------------------------------------------------------------------

def test_build_spec_extraction_prompt_includes_chunk_text_and_instructions(sample_chunks):
    prompt = build_spec_extraction_prompt(sample_chunks[1:3])

    assert "ILI9488" in prompt
    assert "FT6236" in prompt
    # 지시사항: 해상도/데이터 포맷/터치 컨트롤러 모델명을 추리라는 내용이 포함되어야 한다.
    assert "해상도" in prompt
    assert "데이터 포맷" in prompt
    assert "터치" in prompt
    # 신뢰도/가정 라벨 요구 (12항 Hallucination 대책)가 프롬프트에 명시되어야 한다.
    assert "신뢰도" in prompt
    assert "가정" in prompt


# ---------------------------------------------------------------------------
# 3) LLM 응답 파싱 — 안전 처리 & Hallucination 대책
# ---------------------------------------------------------------------------

def test_parse_spec_response_extracts_all_required_fields():
    llm_response = """
    {
      "lcd_controller": {"value": "ILI9488", "confidence": 0.95, "assumed": false},
      "touch_ic": {"value": "FT6236", "confidence": 0.9, "assumed": false},
      "resolution_width": {"value": "320", "confidence": 0.9, "assumed": false},
      "resolution_height": {"value": "480", "confidence": 0.9, "assumed": false},
      "data_format": {"value": "RGB565", "confidence": 0.9, "assumed": false}
    }
    """
    result = parse_spec_response(llm_response)

    for key in (
        "lcd_controller",
        "touch_ic",
        "resolution_width",
        "resolution_height",
        "data_format",
    ):
        assert key in result
        assert result[key]["value"] != ""
        assert result[key]["value"] is not None

    assert result["lcd_controller"]["value"] == "ILI9488"
    assert result["touch_ic"]["value"] == "FT6236"
    assert result["resolution_width"]["value"] == "320"
    assert result["resolution_height"]["value"] == "480"
    assert result["data_format"]["value"] == "RGB565"


def test_parse_spec_response_malformed_json_returns_safe_defaults():
    """12항 DoD(b): 오검출/파싱 실패 시 빈 문자열/None으로 안전 처리해야 한다."""
    result = parse_spec_response("이건 JSON이 아닌 자유 텍스트 응답입니다.")

    for key in (
        "lcd_controller",
        "touch_ic",
        "resolution_width",
        "resolution_height",
        "data_format",
    ):
        assert key in result
        assert result[key]["value"] in ("", None)
        assert result[key]["confidence"] == 0.0
        assert result[key]["assumed"] is True


def test_parse_spec_response_missing_field_defaults_to_safe_value():
    """일부 필드가 응답에 없을 때도 KeyError 없이 안전 기본값을 채워야 한다."""
    llm_response = '{"lcd_controller": {"value": "ILI9488", "confidence": 0.9, "assumed": false}}'
    result = parse_spec_response(llm_response)

    assert result["lcd_controller"]["value"] == "ILI9488"
    for key in ("touch_ic", "resolution_width", "resolution_height", "data_format"):
        assert result[key]["value"] in ("", None)
        assert result[key]["assumed"] is True


def test_parse_spec_response_low_confidence_marked_as_assumed():
    """12항: 모호한 스펙에 대해 낮은 신뢰도는 '가정' 라벨과 함께 다뤄야 한다."""
    llm_response = """
    {
      "lcd_controller": {"value": "아마도 ILI9341", "confidence": 0.2, "assumed": true},
      "touch_ic": {"value": "FT6236", "confidence": 0.9, "assumed": false},
      "resolution_width": {"value": "320", "confidence": 0.9, "assumed": false},
      "resolution_height": {"value": "480", "confidence": 0.9, "assumed": false},
      "data_format": {"value": "RGB565", "confidence": 0.9, "assumed": false}
    }
    """
    result = parse_spec_response(llm_response)

    assert result["lcd_controller"]["assumed"] is True
    assert result["lcd_controller"]["confidence"] < 0.5


# ---------------------------------------------------------------------------
# 4) end-to-end 오프라인 (mock LLM 클라이언트)
# ---------------------------------------------------------------------------

class _FakeUpstageClient:
    """실제 API 호출 없이 고정 응답을 돌려주는 테스트용 stub."""

    def __init__(self, canned_response: str) -> None:
        self._canned_response = canned_response

    def chat(self, message: str) -> str:  # noqa: ARG002
        return self._canned_response


def test_extract_specs_end_to_end_with_stub_client(sample_chunks):
    canned = """
    {
      "lcd_controller": {"value": "ILI9488", "confidence": 0.95, "assumed": false},
      "touch_ic": {"value": "FT6236", "confidence": 0.9, "assumed": false},
      "resolution_width": {"value": "320", "confidence": 0.9, "assumed": false},
      "resolution_height": {"value": "480", "confidence": 0.9, "assumed": false},
      "data_format": {"value": "RGB565", "confidence": 0.9, "assumed": false}
    }
    """
    client = _FakeUpstageClient(canned)
    result = extract_specs(sample_chunks, client=client)

    for key in (
        "lcd_controller",
        "touch_ic",
        "resolution_width",
        "resolution_height",
        "data_format",
    ):
        assert key in result
        assert result[key]["value"] != ""


def test_extract_specs_empty_chunks_returns_safe_defaults():
    client = _FakeUpstageClient("{}")
    result = extract_specs([], client=client)

    for key in (
        "lcd_controller",
        "touch_ic",
        "resolution_width",
        "resolution_height",
        "data_format",
    ):
        assert key in result
        assert result[key]["value"] in ("", None)


# ---------------------------------------------------------------------------
# 5) 라이브 API (Solar Pro 실호출)
# ---------------------------------------------------------------------------

@REQUIRES_LIVE_API
def test_extract_specs_live_api_finds_required_fields(sample_chunks):
    from src.common.upstage_client import UpstageClient

    client = UpstageClient()
    result = extract_specs(sample_chunks, client=client)

    for key in (
        "lcd_controller",
        "touch_ic",
        "resolution_width",
        "resolution_height",
        "data_format",
    ):
        assert key in result
        assert result[key]["value"] not in ("", None)
