"""T-008 스파이크: Upstage Document Parse 표 추출 성능 검증 — 단위 테스트.

단위구현계획서.md 제5장 [T-008] 10항 절차를 코드로 검증한다.
- 오프라인: HTML->마크다운 변환 및 셀 손실율 계산 로직.
- 라이브(@REQUIRES_LIVE_API): 실제 Upstage Document Parse API 호출로
  데이터시트 샘플의 표를 추출하고 마크다운 구문/셀 손실율(<5%)을 판정한다.
"""
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

from src.agent.document_parser import (  # noqa: E402
    cell_loss_ratio,
    html_table_to_markdown,
    load_table_elements,
)

REQUIRES_LIVE_API = pytest.mark.skipif(
    not os.getenv("UPSTAGE_API_KEY"),
    reason="UPSTAGE_API_KEY가 .env에 설정되어 있지 않습니다.",
)

SAMPLE_PDF = Path(__file__).parent / "data" / "p4_datasheet_sample.pdf"

# 카드 7 목적: 핀맵 + 레지스터 맵 표가 검증 대상.
# 손실율 판정의 분모는 이 두 표의 '전체 셀' 그라운드 트루스로 둔다
# (fixture 생성기 내용과 1:1로 일치). 임의 부분집합이 아니라 전수 비교여야
# 카드 10항의 '셀 텍스트 손실율 < 5%'를 정직하게 측정할 수 있다.
PIN_MAP_CELLS = [
    "Pin", "Signal", "Direction", "Default Level", "Description",
    "GPIO0", "DSI_CLK_P", "OUT", "Low", "MIPI-DSI clock lane positive",
    "GPIO1", "DSI_CLK_N", "OUT", "Low", "MIPI-DSI clock lane negative",
    "GPIO2", "DSI_D0_P", "OUT", "Low", "Data lane 0 positive",
    "GPIO3", "DSI_D0_N", "OUT", "Low", "Data lane 0 negative",
    "GPIO4", "DSI_D1_P", "OUT", "Low", "Data lane 1 positive",
    "GPIO5", "DSI_D1_N", "OUT", "Low", "Data lane 1 negative",
    "GPIO23", "LCD_RESET", "OUT", "High", "Panel hardware reset (active low)",
    "GPIO24", "LCD_BL_EN", "OUT", "Low", "Backlight enable",
]
REGISTER_MAP_CELLS = [
    "Address", "Register", "Reset Value", "Access", "Function",
    "0x00", "CTRL_MODE", "0x0000", "R/W", "Display controller mode select",
    "0x04", "H_RES", "0x0400", "R/W", "Horizontal resolution (1024)",
    "0x08", "V_RES", "0x0258", "R/W", "Vertical resolution (600)",
    "0x0C", "PIX_FMT", "0x0002", "R/W", "Pixel format RGB565",
    "0x10", "FB_ADDR", "0x00000000", "R/W", "Framebuffer base address",
    "0x14", "INT_STAT", "0x0000", "R", "Interrupt status flags",
    "0x18", "INT_MASK", "0xFFFF", "R/W", "Interrupt mask register",
]
EXPECTED_KEY_CELLS = PIN_MAP_CELLS + REGISTER_MAP_CELLS

MARKDOWN_SEPARATOR = "| --- |"


# ---------------------------------------------------------------------------
# 오프라인 로직 검증 (API 불필요)
# ---------------------------------------------------------------------------
def test_html_table_to_markdown_emits_separator_row():
    """HTML 테이블이 마크다운 표 구문(`|---|`)으로 포맷팅돼야 한다."""
    html = (
        "<table><thead><tr><td>Pin</td><td>Signal</td></tr></thead>"
        "<tbody><tr><td>GPIO0</td><td>DSI_CLK_P</td></tr></tbody></table>"
    )
    md = html_table_to_markdown(html)
    lines = md.splitlines()
    assert lines[0] == "| Pin | Signal |"
    assert set(lines[1].replace(" ", "")) <= set("|-")
    assert "GPIO0" in md and "DSI_CLK_P" in md


def test_html_table_to_markdown_handles_empty_input():
    """12: 표가 없거나 빈 입력이면 빈 문자열을 반환한다(예외 없이)."""
    assert html_table_to_markdown("") == ""
    assert html_table_to_markdown("<p>no table here</p>") == ""


def test_cell_loss_ratio_zero_when_all_present():
    md = html_table_to_markdown(
        "<table><tr><td>GPIO0</td><td>DSI_CLK_P</td></tr></table>"
    )
    assert cell_loss_ratio(["GPIO0", "DSI_CLK_P"], md) == 0.0


def test_cell_loss_ratio_detects_missing_cells():
    """12: 셀이 어긋나 텍스트가 누락되면 손실율이 그만큼 잡혀야 한다."""
    md = html_table_to_markdown("<table><tr><td>GPIO0</td></tr></table>")
    ratio = cell_loss_ratio(["GPIO0", "DSI_CLK_P"], md)
    assert ratio == pytest.approx(0.5)


def test_load_table_elements_missing_file_raises():
    """12: 입력 문서가 없으면 명확한 예외를 던진다."""
    with pytest.raises(FileNotFoundError):
        load_table_elements("tests/data/__does_not_exist__.pdf")


# ---------------------------------------------------------------------------
# 라이브 API 검증 — 카드 10항 통과 기준 판정
# ---------------------------------------------------------------------------
@REQUIRES_LIVE_API
def test_table_extraction():
    """10, 11: 실제 Document Parse API가 데이터시트 표를 추출하고(200 응답),
    핀맵+레지스터맵 전체 셀 기준 손실율이 5% 미만이어야 한다."""
    assert SAMPLE_PDF.exists(), f"샘플 데이터시트 fixture가 없습니다: {SAMPLE_PDF}"

    tables = load_table_elements(SAMPLE_PDF, output_format="html")

    assert len(tables) > 0, "표 요소가 하나도 추출되지 않았습니다."

    combined_md = "\n\n".join(t.markdown for t in tables)
    assert MARKDOWN_SEPARATOR in combined_md, "마크다운 표 구분선이 없습니다."

    loss = cell_loss_ratio(EXPECTED_KEY_CELLS, combined_md)
    print(f"[T-008] 추출 표 {len(tables)}개, 셀 손실율 {loss:.2%}")
    assert loss < 0.05, f"셀 손실율 {loss:.1%} >= 5% (통과 기준 미달)"
