"""T-008 스파이크: Upstage Document Parse 표 추출 성능 검증.

단위구현계획서.md 제5장 [T-008] 8항 구현 내용을 따른다.
ESP32-P4 데이터시트류 문서의 표(Table)를 Upstage Document Parse가
누락 없이 추출하는지 검증하기 위한 로딩/파싱 루틴을 제공한다.

- `load_table_elements`: `UpstageDocumentParseLoader`를 인스턴스화해 문서에서
  category == "table" 요소만 추출한다(실 API 호출).
- `html_table_to_markdown`: 반환된 HTML 테이블 문자열을 마크다운 표 구문으로
  복원한다(순수 함수, 오프라인 검증 가능).
- `cell_loss_ratio`: 원본 기대 셀 집합 대비 추출 결과의 셀 손실율을 계산해
  카드 10항 통과 기준(손실율 < 5%)을 판정할 수 있게 한다.

API 키는 환경변수 UPSTAGE_API_KEY에서 로딩한다(.env 경유). 키를 코드/로그에 남기지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


@dataclass
class TableElement:
    """Document Parse가 추출한 표 요소 1개."""

    page: int | None
    html: str

    @property
    def markdown(self) -> str:
        return html_table_to_markdown(self.html)


class _TableHTMLParser(HTMLParser):
    """단순 HTML 테이블을 행/셀 2차원 리스트로 파싱한다.

    colspan/rowspan은 spike 범위에서 값 반복 없이 셀 텍스트만 보존한다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._current = []
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "tr" and self._current is not None:
            self.rows.append(self._current)
            self._current = None
        elif tag in ("td", "th") and self._cell is not None:
            text = " ".join("".join(self._cell).split())
            if self._current is not None:
                self._current.append(text)
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def html_table_to_markdown(html: str) -> str:
    """HTML `<table>` 문자열을 마크다운 표 구문으로 변환한다.

    첫 행을 헤더로 간주하고 `|---|---|` 구분선을 삽입한다.
    표가 없거나 셀이 하나도 없으면 빈 문자열을 반환한다.
    """
    if not html:
        return ""
    parser = _TableHTMLParser()
    parser.feed(html)
    rows = [r for r in parser.rows if r]
    if not rows:
        return ""

    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]

    def fmt(cells: list[str]) -> str:
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"

    lines = [fmt(norm[0]), "| " + " | ".join(["---"] * width) + " |"]
    lines.extend(fmt(r) for r in norm[1:])
    return "\n".join(lines)


def _iter_cells(markdown: str) -> list[str]:
    """마크다운 표에서 구분선을 제외한 모든 셀 텍스트를 평탄화한다."""
    cells: list[str] = []
    for line in markdown.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", p or "") for p in parts):
            continue
        cells.extend(parts)
    return cells


def cell_loss_ratio(expected_cells: list[str], extracted_markdown: str) -> float:
    """기대 셀 대비 추출 마크다운에서 누락된 셀 비율을 반환한다(0.0~1.0).

    공백 정규화 후 다중집합 기준으로 비교한다. 카드 10항 통과 기준은 < 0.05.
    """
    if not expected_cells:
        return 0.0

    def norm(s: str) -> str:
        return " ".join(s.split()).lower()

    extracted = [norm(c) for c in _iter_cells(extracted_markdown) if c.strip()]
    pool = list(extracted)
    missing = 0
    for cell in expected_cells:
        target = norm(cell)
        if not target:
            continue
        if target in pool:
            pool.remove(target)
        else:
            missing += 1
    denom = sum(1 for c in expected_cells if c.strip())
    return missing / denom if denom else 0.0


def load_table_elements(
    file_path: str | Path,
    *,
    output_format: str = "html",
) -> list[TableElement]:
    """Upstage Document Parse로 문서를 파싱해 표 요소만 반환한다(실 API 호출).

    Args:
        file_path: 파싱할 문서 경로.
        output_format: 요소 본문 포맷("html" 권장 — 구조 파싱에 유리).

    Raises:
        FileNotFoundError: 입력 문서가 없을 때.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"파싱 대상 문서를 찾을 수 없습니다: {path}")

    # 무거운 선택 의존성이므로 함수 내부에서 지연 임포트한다.
    from langchain_upstage import UpstageDocumentParseLoader

    loader = UpstageDocumentParseLoader(
        file_path=str(path),
        split="element",
        output_format=output_format,
        ocr="auto",
        coordinates=False,
    )
    docs = loader.load()
    tables: list[TableElement] = []
    for doc in docs:
        if doc.metadata.get("category") == "table":
            tables.append(
                TableElement(page=doc.metadata.get("page"), html=doc.page_content)
            )
    return tables
