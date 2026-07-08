"""T-201: Upstage Document Parse 문서 파싱 및 텍스트 청킹 — 단위 테스트.

단위구현계획서.md 제5장 [T-201] 10항 절차를 코드로 검증한다.
- 오프라인(API 불필요): layout 요소 정렬/병합 및 청크 사이즈·오버랩 로직.
  청킹 알고리즘은 순수 함수로 분리되어 API 키 없이 검증 가능하다.
- 라이브(@REQUIRES_LIVE_API): 실제 Upstage Document Parse API로 데이터시트
  PDF를 파싱해 청크를 생성하고 1000자 제한/오버랩을 판정한다.
- Quota 초과 대처(카드 12항): 로컬 캐시 JSON을 강제 로드하는 Mocking 모드.
"""
import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

from src.parser.document_parser import (  # noqa: E402
    Chunk,
    LayoutElement,
    chunk_elements,
    chunk_text,
    load_cached_elements,
    parse_document,
    parse_document_to_chunks,
)

REQUIRES_LIVE_API = pytest.mark.skipif(
    not os.getenv("UPSTAGE_API_KEY"),
    reason="UPSTAGE_API_KEY가 .env에 설정되어 있지 않습니다.",
)

SAMPLE_PDF = Path(__file__).parent / "data" / "esp32-p4_datasheet_en.pdf"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100


# ---------------------------------------------------------------------------
# 오프라인 청킹 로직 검증 (API 불필요, 순수 함수)
# ---------------------------------------------------------------------------
def test_chunk_text_respects_size_limit():
    """카드 10: 모든 청크가 1000자 이내를 유지해야 한다."""
    text = "".join(f"sentence {i}. " for i in range(2000))
    chunks = chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    assert len(chunks) > 1
    assert all(len(c) <= CHUNK_SIZE for c in chunks)


def test_chunk_text_overlap_is_observable():
    """카드 10: 인접 청크 사이에 오버랩 구간이 수학적으로 관측돼야 한다."""
    text = "".join(f"{i:04d}-" for i in range(1000))  # 5000자
    chunks = chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    assert len(chunks) >= 2
    for prev, nxt in zip(chunks, chunks[1:]):
        tail = prev[-CHUNK_OVERLAP:]
        # 이전 청크의 마지막 overlap 문자가 다음 청크 시작에 그대로 이어진다.
        assert nxt.startswith(tail)


def test_chunk_text_is_mece_when_no_overlap():
    """카드 11(MECE): overlap=0이면 청크 이어붙임이 원본과 정확히 일치(누락/중복 없음)."""
    text = "abcdefghij" * 300  # 3000자
    chunks = chunk_text(text, size=CHUNK_SIZE, overlap=0)
    assert "".join(chunks) == text


def test_chunk_text_short_input_single_chunk():
    """1000자 이하 입력은 청크 1개로 유지된다."""
    text = "short body"
    chunks = chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    assert chunks == [text]


def test_chunk_text_empty_returns_empty():
    assert chunk_text("", size=CHUNK_SIZE, overlap=CHUNK_OVERLAP) == []
    assert chunk_text("   ", size=CHUNK_SIZE, overlap=CHUNK_OVERLAP) == []


def test_chunk_text_overlap_must_be_smaller_than_size():
    """오버랩이 사이즈 이상이면 무한 루프가 되므로 방어적으로 거부한다."""
    with pytest.raises(ValueError):
        chunk_text("some text", size=100, overlap=100)


def test_chunk_elements_orders_by_page_then_coordinates():
    """카드 8-2: layout 요소를 page -> 물리 좌표(y, x) 순서로 정렬해 병합한다."""
    elements = [
        LayoutElement(page=2, text="second page body", y=0.1, x=0.1),
        LayoutElement(page=1, text="alpha top", y=0.1, x=0.1),
        LayoutElement(page=1, text="beta below", y=0.5, x=0.1),
    ]
    chunks = chunk_elements(elements, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    joined = "\n".join(chunks)
    assert joined.index("alpha top") < joined.index("beta below")
    assert joined.index("beta below") < joined.index("second page body")


def test_chunk_elements_returns_chunk_objects_within_limit():
    elements = [
        LayoutElement(page=1, text="x" * 800, y=0.1, x=0.1),
        LayoutElement(page=1, text="y" * 800, y=0.2, x=0.1),
    ]
    chunks = chunk_elements(elements, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    assert all(len(c) <= CHUNK_SIZE for c in chunks)
    assert sum(len(c) for c in chunks) >= 1600


# ---------------------------------------------------------------------------
# 카드 12항: Quota 초과 시 로컬 캐시 강제 로드(Mocking 모드)
# ---------------------------------------------------------------------------
def test_load_cached_elements_from_json(tmp_path):
    """캐시 JSON을 LayoutElement 리스트로 복원한다."""
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps(
            [
                {"page": 1, "text": "cached alpha", "y": 0.1, "x": 0.1},
                {"page": 1, "text": "cached beta", "y": 0.4, "x": 0.1},
            ]
        ),
        encoding="utf-8",
    )
    elements = load_cached_elements(cache)
    assert len(elements) == 2
    assert all(isinstance(e, LayoutElement) for e in elements)
    assert elements[0].text == "cached alpha"


def test_parse_document_falls_back_to_cache_on_quota_error(tmp_path, monkeypatch):
    """카드 12: API가 Quota 초과 에러를 던지면 로컬 캐시를 강제 로드한다."""
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps([{"page": 1, "text": "from cache", "y": 0.1, "x": 0.1}]),
        encoding="utf-8",
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("429 Too Many Requests: quota exceeded")

    monkeypatch.setattr(
        "src.parser.document_parser._load_elements_via_api", _boom
    )

    elements = parse_document(SAMPLE_PDF, cache_path=cache)
    assert len(elements) == 1
    assert elements[0].text == "from cache"


def test_parse_document_raises_without_cache_on_error(tmp_path, monkeypatch):
    """캐시가 없으면 Quota 에러를 그대로 전파한다(조용히 삼키지 않음)."""
    def _boom(*args, **kwargs):
        raise RuntimeError("429 quota exceeded")

    monkeypatch.setattr(
        "src.parser.document_parser._load_elements_via_api", _boom
    )
    with pytest.raises(RuntimeError):
        parse_document(SAMPLE_PDF, cache_path=tmp_path / "missing.json")


def test_parse_document_missing_file_raises():
    """12: 입력 문서가 없으면 명확한 예외를 던진다."""
    with pytest.raises(FileNotFoundError):
        parse_document("tests/data/__does_not_exist__.pdf")


# ---------------------------------------------------------------------------
# 라이브 API 검증 — 카드 10/11 통과 기준 판정
# ---------------------------------------------------------------------------
@REQUIRES_LIVE_API
def test_parse_document_to_chunks_live():
    """10, 11: 실제 Document Parse API가 PDF를 파싱해 청크 리스트를 만들고
    모든 청크가 1000자 이내이며 오버랩이 관측돼야 한다."""
    assert SAMPLE_PDF.exists(), f"샘플 PDF가 없습니다: {SAMPLE_PDF}"

    chunks = parse_document_to_chunks(
        SAMPLE_PDF, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP
    )
    assert len(chunks) > 0, "청크가 하나도 생성되지 않았습니다."
    assert all(isinstance(c, Chunk) for c in chunks)
    assert all(len(c.text) <= CHUNK_SIZE for c in chunks)

    # 오버랩 관측: 여러 청크가 나왔다면 최소 한 쌍에서 꼬리-머리 중첩이 보인다.
    if len(chunks) >= 2:
        observed = any(
            chunks[i + 1].text.startswith(chunks[i].text[-CHUNK_OVERLAP:])
            for i in range(len(chunks) - 1)
        )
        assert observed, "청크 간 오버랩 구간이 관측되지 않았습니다."

    avg = sum(len(c.text) for c in chunks) / len(chunks)
    print(f"[T-201] 청크 {len(chunks)}개, 평균 길이 {avg:.1f}자")
