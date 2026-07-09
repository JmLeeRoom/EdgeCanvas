"""T-201 문서 이해: Upstage Document Parse 문서 파싱 및 텍스트 청킹.

단위구현계획서.md 제5장 [T-201] 8항 구현 내용을 따른다.

- `parse_document`: PDF를 Upstage Document Parse API에 던져 layout 요소
  (text/table)를 물리 좌표·순서 정보와 함께 `LayoutElement` 리스트로 반환한다.
  Quota 초과 등 API 에러 시(카드 12항) 로컬 캐시 JSON을 강제 로드하는
  Mocking 모드로 폴백한다.
- `chunk_text` / `chunk_elements`: 청크 사이즈 1000자·오버랩 100자 기준으로
  텍스트를 파쇄/병합하는 순수 청킹 알고리즘. API 키 없이 오프라인 검증 가능.
- `parse_document_to_chunks`: 파싱 -> 청킹을 잇는 상위 진입점.

API 키는 환경변수 UPSTAGE_API_KEY에서 로딩한다(.env 경유). 키를 코드/로그에 남기지 않는다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LayoutElement:
    """Document Parse가 추출한 레이아웃 요소 1개.

    문서 내 물리적 순서 복원을 위해 페이지 번호와 정규화 좌표(y, x)를 함께 보존한다.
    좌표를 알 수 없으면 0.0으로 두고 원본 등장 순서를 보조 기준으로 사용한다.
    """

    page: int
    text: str
    y: float = 0.0
    x: float = 0.0
    category: str = "text"

    def to_dict(self) -> dict:
        return {
            "page": self.page,
            "text": self.text,
            "y": self.y,
            "x": self.x,
            "category": self.category,
        }


@dataclass
class Chunk:
    """청킹 결과 1개. 순서 인덱스와 본문 텍스트를 보존한다."""

    index: int
    text: str

    def to_dict(self) -> dict:
        return {"index": self.index, "text": self.text, "length": len(self.text)}


def chunk_text(text: str, *, size: int = 1000, overlap: int = 100) -> list[str]:
    """텍스트를 `size`자 이내 청크로 분할한다(인접 청크는 `overlap`자 겹침).

    슬라이딩 윈도로 [start, start+size)를 잘라내고 다음 시작점을
    `start + size - overlap`으로 전진시킨다. 이렇게 하면 각 청크는 이전 청크의
    마지막 `overlap`자를 머리에 그대로 이어받아 오버랩이 수학적으로 관측된다.

    Args:
        text: 원본 텍스트.
        size: 청크 최대 길이(문자 수).
        overlap: 인접 청크가 공유하는 겹침 길이(문자 수).

    Raises:
        ValueError: `overlap >= size`이면 진행이 불가능하므로 거부한다.
    """
    if overlap >= size:
        raise ValueError(
            f"overlap({overlap})은 size({size})보다 작아야 합니다."
        )
    if not text or not text.strip():
        return []
    if len(text) <= size:
        return [text]

    step = size - overlap
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        chunks.append(text[start : start + size])
        if start + size >= n:
            break
        start += step
    return chunks


def _sorted_elements(elements: list[LayoutElement]) -> list[LayoutElement]:
    """요소를 page -> y(위->아래) -> x(왼->오) 순서로 정렬한다.

    원본 리스트 순서를 안정 정렬의 최종 tie-breaker로 사용한다.
    """
    indexed = list(enumerate(elements))
    indexed.sort(key=lambda pair: (pair[1].page, pair[1].y, pair[1].x, pair[0]))
    return [el for _, el in indexed]


def chunk_elements(
    elements: list[LayoutElement], *, size: int = 1000, overlap: int = 100
) -> list[str]:
    """layout 요소들을 물리적 순서로 병합한 뒤 `chunk_text`로 청킹한다."""
    ordered = _sorted_elements(elements)
    merged = "\n".join(el.text for el in ordered if el.text and el.text.strip())
    return chunk_text(merged, size=size, overlap=overlap)


def load_cached_elements(cache_path: str | Path) -> list[LayoutElement]:
    """로컬 캐시 JSON을 `LayoutElement` 리스트로 복원한다(카드 12항 Mocking 모드)."""
    path = Path(cache_path)
    if not path.exists():
        raise FileNotFoundError(f"캐시 파일을 찾을 수 없습니다: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        LayoutElement(
            page=int(item.get("page", 1)),
            text=str(item.get("text", "")),
            y=float(item.get("y", 0.0)),
            x=float(item.get("x", 0.0)),
            category=str(item.get("category", "text")),
        )
        for item in data
    ]


def _load_elements_via_api(
    file_path: Path, *, output_format: str = "html"
) -> list[LayoutElement]:
    """Upstage Document Parse API로 문서를 파싱해 layout 요소를 반환한다(실 API 호출).

    좌표/순서 파악을 위해 `coordinates=True`로 호출하고, bounding box의
    좌상단 정규화 좌표를 요소의 (y, x)로 사용한다.
    """
    # 무거운 선택 의존성이므로 함수 내부에서 지연 임포트한다.
    from langchain_upstage import UpstageDocumentParseLoader

    loader = UpstageDocumentParseLoader(
        file_path=str(file_path),
        split="element",
        output_format=output_format,
        ocr="auto",
        coordinates=True,
    )
    docs = loader.load()
    elements: list[LayoutElement] = []
    for order, doc in enumerate(docs):
        meta = doc.metadata or {}
        page = int(meta.get("page", 1) or 1)
        y, x = _coordinates_top_left(meta.get("coordinates"))
        elements.append(
            LayoutElement(
                page=page,
                text=doc.page_content or "",
                y=y,
                x=x,
                category=str(meta.get("category", "text")),
            )
        )
    return elements


def _coordinates_top_left(coordinates) -> tuple[float, float]:
    """Document Parse 좌표 리스트에서 좌상단 (y, x) 정규화 값을 뽑는다.

    coordinates는 [{"x": .., "y": ..}, ...] 꼴의 다각형 꼭짓점 리스트다.
    좌표 정보가 없으면 (0.0, 0.0)을 반환해 원본 순서 tie-break에 맡긴다.
    """
    if not coordinates:
        return 0.0, 0.0
    try:
        ys = [float(pt["y"]) for pt in coordinates if "y" in pt]
        xs = [float(pt["x"]) for pt in coordinates if "x" in pt]
    except (TypeError, KeyError, ValueError):
        return 0.0, 0.0
    if not ys or not xs:
        return 0.0, 0.0
    return min(ys), min(xs)


def parse_document(
    file_path: str | Path,
    *,
    output_format: str = "html",
    cache_path: str | Path | None = None,
) -> list[LayoutElement]:
    """PDF를 Document Parse로 파싱해 layout 요소 리스트를 반환한다.

    카드 12항: API 호출이 실패(예: Quota 초과)하면 `cache_path`가 존재할 때
    로컬 캐시 JSON을 강제 로드하는 Mocking 모드로 폴백한다. 캐시가 없으면
    원본 에러를 그대로 전파한다(실패를 조용히 삼키지 않는다).

    Args:
        file_path: 파싱할 PDF 경로.
        output_format: 요소 본문 포맷("html" 권장).
        cache_path: API 실패 시 폴백할 캐시 JSON 경로(선택).

    Raises:
        FileNotFoundError: 입력 PDF가 없을 때.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"파싱 대상 문서를 찾을 수 없습니다: {path}")

    try:
        return _load_elements_via_api(path, output_format=output_format)
    except Exception:
        if cache_path is not None and Path(cache_path).exists():
            return load_cached_elements(cache_path)
        raise


def parse_document_to_chunks(
    file_path: str | Path,
    *,
    size: int = 1000,
    overlap: int = 100,
    output_format: str = "html",
    cache_path: str | Path | None = None,
) -> list[Chunk]:
    """문서 파싱 -> 물리 순서 병합 -> 청킹을 잇는 상위 진입점."""
    elements = parse_document(
        file_path, output_format=output_format, cache_path=cache_path
    )
    texts = chunk_elements(elements, size=size, overlap=overlap)
    return [Chunk(index=i, text=t) for i, t in enumerate(texts)]
