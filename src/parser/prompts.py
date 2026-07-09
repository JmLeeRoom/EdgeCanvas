"""T-202 스펙 추출용 RAG 프롬프트 템플릿.

단위구현계획서.md 제5장 [T-202] 8-3항 구현 내용을 따른다.
Solar Pro LLM에 데이터시트 청크에서 디스플레이 해상도(가로/세로), 데이터
포맷, LCD 컨트롤러 칩셋, 터치 컨트롤러 IC 모델명을 추리라는 지시를 내리는
프롬프트를 구성한다.

12항 실패 시 대처(LLM Hallucination) 대응: 모호한 스펙에 임의 값을 상상해
채우지 않도록, 각 필드에 신뢰도 점수(confidence)와 불확실한 값에는 '가정'
라벨(assumed)을 함께 요구한다.
"""
from __future__ import annotations

from src.parser.document_parser import Chunk

# 유사도 검색(retrieval) 랭킹에 쓰이는 핵심 스펙 관련 쿼리 키워드.
SPEC_EXTRACTION_QUERY_KEYWORDS: list[str] = [
    "LCD",
    "컨트롤러",
    "해상도",
    "resolution",
    "SPI",
    "MIPI",
    "타이밍",
    "터치",
    "touch",
    "핀",
    "pin",
    "매핑",
    "인터페이스",
    "데이터",
    "포맷",
    "format",
]

_REQUIRED_FIELDS = (
    "lcd_controller",
    "touch_ic",
    "resolution_width",
    "resolution_height",
)


def build_spec_extraction_prompt(chunks: list[Chunk]) -> str:
    """검색된 청크들을 근거(context)로 붙여 Solar Pro용 RAG 프롬프트를 만든다.

    응답은 반드시 JSON 하나로, 각 필드가
    ``{"value": ..., "confidence": 0~1, "assumed": bool}`` 형태를 갖도록 지시한다.
    이는 모호한 스펙에 대해 LLM이 임의 값을 상상(Hallucination)하는 것을 막고,
    불확실한 값을 '가정'으로 명시적으로 라벨링하게 하기 위함이다.
    """
    context = "\n\n".join(
        f"[청크 {chunk.index}]\n{chunk.text}" for chunk in chunks
    )

    return f"""당신은 하드웨어 데이터시트 분석 전문가입니다. 아래 데이터시트 발췌
(청크)를 근거로, 다음 4개 하드웨어 스펙 필드를 추출하세요.

- lcd_controller: LCD 컨트롤러 칩셋 모델명
- touch_ic: 터치 컨트롤러 IC 모델명
- resolution_width: 디스플레이 가로 해상도(픽셀, 숫자만)
- resolution_height: 디스플레이 세로 해상도(픽셀, 숫자만)

또한 SPI/MIPI 인터페이스 타이밍, 핀 매핑, 데이터 포맷 등 관련 정보가 있으면
근거로 활용하되, 위 4개 필드 이외의 값은 만들어내지 마세요.

중요한 규칙(반드시 준수):
1. 근거 텍스트에 명확히 등장하지 않는 값은 임의로 상상해서 채우지 마세요.
2. 각 필드마다 0.0~1.0 사이의 신뢰도(confidence) 점수를 매기세요.
3. 근거가 모호하거나 추론에 의존한 값은 assumed=true로 명시적으로 '가정'
   라벨을 붙이세요. 명확한 근거가 있으면 assumed=false로 표시하세요.
4. 근거가 전혀 없으면 value는 빈 문자열("")로 두고 confidence=0.0,
   assumed=true로 응답하세요. 절대 그럴듯한 값을 지어내지 마세요.

응답은 다른 설명 없이 아래와 같은 JSON 객체 하나만 반환하세요:

{{
  "lcd_controller": {{"value": "...", "confidence": 0.0, "assumed": false}},
  "touch_ic": {{"value": "...", "confidence": 0.0, "assumed": false}},
  "resolution_width": {{"value": "...", "confidence": 0.0, "assumed": false}},
  "resolution_height": {{"value": "...", "confidence": 0.0, "assumed": false}}
}}

--- 데이터시트 발췌 (근거) ---
{context}
--- 발췌 끝 ---
"""
