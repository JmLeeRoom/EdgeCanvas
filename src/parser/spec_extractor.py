"""T-202: 데이터시트 핵심 스펙 RAG 추출기.

단위구현계획서.md 제5장 [T-202] 8항 구현 내용을 따른다.

- `retrieve_relevant_chunks`: 실제 임베딩 API 없이, 키워드 빈도 기반의
  순수 파이썬 TF 스코어링으로 스펙 관련 청크를 랭킹해 상위 N개만 골라내는
  유사도 벡터 검색 모의(mock retrieval) 로직. API 키 없이 단위 테스트 가능.
- `build_spec_extraction_prompt`(prompts.py): Solar Pro용 RAG 프롬프트 템플릿.
- `parse_spec_response`: LLM 응답(JSON 텍스트)을 파싱해 4대 필수 필드
  (lcd_controller, touch_ic, resolution_width, resolution_height)를
  안전하게 추출한다. 파싱 실패/필드 누락 시 빈 문자열/None + confidence=0.0
  + assumed=True로 안전 처리한다(11-b항 DoD).
- `extract_specs`: retrieval -> 프롬프트 생성 -> LLM 호출 -> 파싱까지
  잇는 상위 진입점. `client`(예: UpstageClient)는 `chat(message: str) -> str`
  인터페이스만 만족하면 되므로 테스트에서는 stub으로 대체 가능하다.

12항 실패 시 대처(LLM Hallucination): 모호한 스펙에 대해 LLM이 임의 값을
상상해 채우는 것을 막기 위해, 프롬프트에서 confidence/assumed를 요구하고,
파싱 단계에서도 값이 비어 있거나 JSON이 깨졌을 때는 항상 confidence=0.0,
assumed=True인 안전 기본값으로 대체한다.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from src.parser.document_parser import Chunk
from src.parser.prompts import SPEC_EXTRACTION_QUERY_KEYWORDS, build_spec_extraction_prompt

REQUIRED_SPEC_FIELDS: tuple[str, ...] = (
    "lcd_controller",
    "touch_ic",
    "resolution_width",
    "resolution_height",
)

_SAFE_DEFAULT_FIELD: dict = {"value": "", "confidence": 0.0, "assumed": True}


def _tokenize(text: str) -> list[str]:
    """텍스트를 대소문자 무시한 영문/한글/숫자 토큰 리스트로 분리한다."""
    return re.findall(r"[A-Za-z가-힣0-9]+", text.lower())


def retrieve_relevant_chunks(
    chunks: list[Chunk],
    query_keywords: list[str],
    *,
    top_n: int = 5,
) -> list[Chunk]:
    """키워드 빈도(TF) 기반 스코어링으로 청크를 랭킹해 상위 `top_n`개를 반환한다.

    실제 임베딩 벡터 검색 대신, 쿼리 키워드가 각 청크 텍스트에 등장하는
    빈도를 세어 점수화하는 순수 파이썬 모의(mock) retrieval이다. 외부
    의존성 없이(re/collections만 사용) API 키 없는 오프라인 단위 테스트가
    가능하다. 점수가 0인 청크는 결과에서 제외한다(관련 없는 청크가
    상위 N에 끼어 LLM 컨텍스트를 오염시키지 않도록).
    """
    if not chunks:
        return []

    normalized_keywords = [kw.lower() for kw in query_keywords]

    scored: list[tuple[float, Chunk]] = []
    for chunk in chunks:
        token_counts = Counter(_tokenize(chunk.text))
        score = 0.0
        for keyword in normalized_keywords:
            if len(keyword) > 1 and any(keyword in token for token in token_counts):
                score += sum(
                    count for token, count in token_counts.items() if keyword in token
                )
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda pair: (-pair[0], pair[1].index))
    return [chunk for _, chunk in scored[:top_n]]


def _coerce_field(raw: object) -> dict:
    """LLM이 돌려준 필드 하나를 안전한 표준 형태로 정규화한다.

    구조가 예상과 다르거나 값이 비어 있으면 안전 기본값으로 대체한다.
    """
    if not isinstance(raw, dict):
        return dict(_SAFE_DEFAULT_FIELD)

    value = raw.get("value")
    if value is None or (isinstance(value, str) and value.strip() == ""):
        value = ""

    confidence = raw.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)):
        confidence = 0.0
    confidence = max(0.0, min(1.0, float(confidence)))

    assumed = raw.get("assumed", True)
    if not isinstance(assumed, bool):
        assumed = True

    if value == "":
        confidence = 0.0
        assumed = True

    return {"value": value, "confidence": confidence, "assumed": assumed}


def parse_spec_response(llm_response: str) -> dict:
    """Solar Pro 응답 텍스트를 파싱해 4대 필수 필드 딕셔너리를 반환한다.

    응답이 JSON이 아니거나 일부 필드가 빠져 있어도 KeyError 없이 항상
    `REQUIRED_SPEC_FIELDS` 전체가 채워진 딕셔너리를 반환한다(11-b항 DoD:
    오검출/누락 시 빈 문자열 또는 None 안전 처리).
    """
    parsed: dict = {}
    try:
        match = re.search(r"\{.*\}", llm_response, re.DOTALL)
        raw_json = match.group(0) if match else llm_response
        parsed = json.loads(raw_json)
        if not isinstance(parsed, dict):
            parsed = {}
    except (json.JSONDecodeError, AttributeError):
        parsed = {}

    return {
        field: _coerce_field(parsed.get(field))
        for field in REQUIRED_SPEC_FIELDS
    }


def extract_specs(chunks: list[Chunk], *, client, top_n: int = 5) -> dict:
    """청크 리스트에서 RAG로 하드웨어 핵심 스펙 4종을 추출한다.

    1) `retrieve_relevant_chunks`로 스펙 관련 청크만 상위 `top_n`개 선별한다.
    2) 선별된 청크로 RAG 프롬프트를 구성한다.
    3) `client.chat(prompt)`(Solar Pro 등)를 호출해 응답을 받는다.
    4) `parse_spec_response`로 안전하게 파싱해 반환한다.

    청크가 비어 있으면 LLM을 호출하지 않고 즉시 안전 기본값을 반환한다.
    """
    if not chunks:
        return {field: dict(_SAFE_DEFAULT_FIELD) for field in REQUIRED_SPEC_FIELDS}

    relevant_chunks = retrieve_relevant_chunks(
        chunks, SPEC_EXTRACTION_QUERY_KEYWORDS, top_n=top_n
    )
    if not relevant_chunks:
        relevant_chunks = chunks[:top_n]

    prompt = build_spec_extraction_prompt(relevant_chunks)
    response_text = client.chat(prompt)
    return parse_spec_response(response_text)
