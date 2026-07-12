"""T-303: LVGL 생성 코드 위젯 트리·이벤트 핸들러 파서 — 단위 테스트.

단위구현계획서.md 제5장 [T-303] 10항 절차를 코드로 검증한다.
- 준비: 모의 생성된 `ui_screens.c` 소스(tests/data/ui_screens.c).
- 실행: `pytest tests/test_code_parser.py`
- 통과 기준: `CodeParser.parse_tree()` 결과로 UI 계층을 나타내는 Nested
  Dictionary가 도출되며, 루트 노드 밑에 자식 위젯 3개 이상이 정상 파싱된다.

카드 11항 DoD(위젯 100% 인식, 부모-자식 트리 복원)와
카드 12항 폴백(비규격 변수명) 시나리오를 함께 검증한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.code_parser import CodeParser

DATA_DIR = Path(__file__).parent / "data"
UI_SCREENS_C = DATA_DIR / "ui_screens.c"
UI_SCREENS_IRREGULAR_C = DATA_DIR / "ui_screens_irregular.c"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source() -> str:
    return UI_SCREENS_C.read_text(encoding="utf-8")


@pytest.fixture
def tree(source: str) -> dict:
    return CodeParser(source).parse_tree()


def _find_node(node: dict, var: str) -> dict | None:
    """트리에서 변수명이 일치하는 노드를 재귀 탐색한다."""
    if node.get("var") == var:
        return node
    for child in node.get("children", []):
        found = _find_node(child, var)
        if found is not None:
            return found
    return None


def _all_vars(node: dict) -> set[str]:
    vars_: set[str] = set()
    if node.get("var"):
        vars_.add(node["var"])
    for child in node.get("children", []):
        vars_ |= _all_vars(child)
    return vars_


# ---------------------------------------------------------------------------
# 카드 10항: parse_tree() Nested Dictionary + 루트 밑 자식 3개 이상
# ---------------------------------------------------------------------------

def test_parse_tree_returns_nested_dict(tree: dict) -> None:
    assert isinstance(tree, dict)
    assert "children" in tree
    assert isinstance(tree["children"], list)


def test_root_is_screen(tree: dict) -> None:
    assert tree["type"] == "screen"
    assert tree["var"] == "scr"


def test_root_has_at_least_three_children(tree: dict) -> None:
    # panel, title, footer 3개가 화면 직속 자식이어야 한다.
    assert len(tree["children"]) >= 3


# ---------------------------------------------------------------------------
# 카드 11항 (a): 위젯 목록 100% 인식
# ---------------------------------------------------------------------------

def test_all_widgets_recognized(tree: dict) -> None:
    expected = {
        "scr",
        "panel",
        "title",
        "footer",
        "submit_btn",
        "submit_label",
        "cancel_btn",
        "hint_label",
    }
    assert _all_vars(tree) == expected


def test_widget_types_are_classified(tree: dict) -> None:
    assert _find_node(tree, "panel")["type"] == "obj"
    assert _find_node(tree, "title")["type"] == "label"
    assert _find_node(tree, "submit_btn")["type"] == "button"


# ---------------------------------------------------------------------------
# 카드 11항 (b): 부모-자식 트리 복원
# ---------------------------------------------------------------------------

def test_parent_child_hierarchy(tree: dict) -> None:
    panel = _find_node(tree, "panel")
    panel_children = {c["var"] for c in panel["children"]}
    # submit_btn, cancel_btn 은 panel 직속 자식
    assert {"submit_btn", "cancel_btn"} <= panel_children
    # submit_label 은 submit_btn 의 자식(중첩)
    submit_btn = _find_node(tree, "submit_btn")
    assert {c["var"] for c in submit_btn["children"]} == {"submit_label"}


def test_set_parent_reparenting(tree: dict) -> None:
    # hint_label 은 lv_obj_set_parent 로 scr -> panel 재지정되었다.
    panel = _find_node(tree, "panel")
    panel_children = {c["var"] for c in panel["children"]}
    assert "hint_label" in panel_children
    # 재지정 후에는 화면 직속 자식이 아니어야 한다.
    root_children = {c["var"] for c in tree["children"]}
    assert "hint_label" not in root_children


# ---------------------------------------------------------------------------
# 카드 7항: 이벤트 함수 호출 관계 파싱
# ---------------------------------------------------------------------------

def test_event_handlers_linked(tree: dict) -> None:
    submit_btn = _find_node(tree, "submit_btn")
    assert "submit_event_handler" in submit_btn["event_handlers"]
    cancel_btn = _find_node(tree, "cancel_btn")
    assert "cancel_event_handler" in cancel_btn["event_handlers"]
    # 이벤트가 없는 위젯은 빈 리스트
    assert _find_node(tree, "title")["event_handlers"] == []


# ---------------------------------------------------------------------------
# 카드 12항: 비규격 변수명 폴백 파서
# ---------------------------------------------------------------------------

def test_fallback_recovers_irregular_variables() -> None:
    source = UI_SCREENS_IRREGULAR_C.read_text(encoding="utf-8")
    tree = CodeParser(source).parse_tree()
    recovered = _all_vars(tree)
    # 비규격 변수명(_R7xQ, Z9k)도 폴백으로 역추출되어야 한다.
    assert "_R7xQ" in recovered
    assert "Z9k" in recovered
    # 규격 변수(panel)와 함께 총 위젯 수(scr 포함) 인식
    assert {"scr", "panel", "_R7xQ", "Z9k"} <= recovered
