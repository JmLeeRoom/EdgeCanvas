"""T-303: LLM 생성 LVGL C 코드로부터 위젯 트리·이벤트 핸들러 파서.

단위구현계획서.md 제5장 [T-303]의 8항 구현 내용을 따른다.
LLM(T-302 프롬프트)이 작성한 LVGL 9.x C 소스 코드를 리버스 엔지니어링하여
UI 구성요소의 부모-자식 계층 및 이벤트 함수 호출 관계를 내부 모델 트리
(Nested Dictionary)로 구문 분석(Parsing)한다.

파싱 전략(2단계)
----------------
1) 1차 정규식 파싱: 규격 변수명 기준으로 다음 패턴을 인식한다.
   - `lv_obj_t *<var> = lv_<type>_create(<parent>);`  (첫 인자가 부모)
   - `lv_obj_set_parent(<child>, <parent>);`            (부모 재지정)
   - `lv_obj_add_event_cb(<widget>, <handler>, ...);`   (이벤트 연결)
2) 폴백 토큰 파서(카드 12항): LLM이 변수명을 비규격(난수/대문자·언더스코어
   시작 등)으로 생성해 1차 정규식이 놓친 위젯은, 라인을 토큰 단위로 끊어
   `lv_` 접두사(`lv_<type>_create`)를 기준으로 변수를 역추출한다.

parse_tree() 반환 구조(노드)
----------------------------
    {
        "var": <변수명>,
        "type": <위젯 타입: screen|obj|label|button|slider|...>,
        "children": [ <자식 노드>, ... ],
        "event_handlers": [ <핸들러 함수명>, ... ],
    }
루트 노드는 화면(`lv_screen_active()` / `lv_obj_create(NULL)`)이다.
"""
from __future__ import annotations

import re

# 화면(root)으로 취급하는 부모 인자 표현.
_SCREEN_PARENTS = {"NULL", "lv_screen_active()", "lv_scr_act()"}

# 1차 파싱: `lv_obj_t *<var> = lv_<type>_create(<parent>);`
_CREATE_RE = re.compile(
    r"lv_obj_t\s*\*\s*(?P<var>[A-Za-z_]\w*)\s*=\s*"
    r"lv_(?P<type>\w+)_create\s*\(\s*(?P<parent>[^,\)]+?)\s*[,\)]"
)

# 부모 재지정: `lv_obj_set_parent(<child>, <parent>);`
_SET_PARENT_RE = re.compile(
    r"lv_obj_set_parent\s*\(\s*(?P<child>[A-Za-z_]\w*)\s*,\s*(?P<parent>[A-Za-z_]\w*)\s*\)"
)

# 이벤트 연결: `lv_obj_add_event_cb(<widget>, <handler>, ...);`
_EVENT_RE = re.compile(
    r"lv_obj_add_event_cb\s*\(\s*(?P<widget>[A-Za-z_]\w*)\s*,\s*(?P<handler>[A-Za-z_]\w*)"
)

# 화면 핸들 변수 인식: `lv_obj_t *<var> = lv_screen_active();`
_SCREEN_VAR_RE = re.compile(
    r"lv_obj_t\s*\*\s*(?P<var>[A-Za-z_]\w*)\s*=\s*"
    r"(?:lv_screen_active|lv_scr_act)\s*\(\s*\)"
)

# 폴백 토큰 파서: 임의 좌변에서 `= lv_<type>_create(<parent>` 형태를 느슨하게 잡는다.
# 변수명은 `<식별자> =` 마지막 토큰으로 역추출한다.
_FALLBACK_CREATE_RE = re.compile(
    r"(?P<var>[A-Za-z_]\w*)\s*=\s*lv_(?P<type>\w+)_create\s*\(\s*(?P<parent>[^,\)]+?)\s*[,\)]"
)


class CodeParser:
    """LVGL 9.x C 소스를 위젯 트리로 구문 분석하는 파서."""

    def __init__(self, source: str) -> None:
        self.source = source
        # var -> 노드. 파싱 도중 부모/자식·이벤트를 채워 나간다.
        self._nodes: dict[str, dict] = {}
        # var -> 부모 var. 화면(root)은 None.
        self._parent_of: dict[str, str | None] = {}
        # 화면(root) 변수명. 없으면 가상의 "scr" 루트를 만든다.
        self._screen_var: str | None = None

    # ------------------------------------------------------------------ #
    # public
    # ------------------------------------------------------------------ #
    def parse_tree(self) -> dict:
        """소스를 파싱해 UI 계층 Nested Dictionary(루트=화면)를 반환한다."""
        self._collect_screen()
        self._collect_widgets()
        self._collect_reparenting()
        self._collect_events()
        return self._build_tree()

    # ------------------------------------------------------------------ #
    # 1차 파싱 단계
    # ------------------------------------------------------------------ #
    def _collect_screen(self) -> None:
        """`lv_screen_active()`로 얻은 화면 핸들 변수를 루트로 등록한다."""
        match = _SCREEN_VAR_RE.search(self.source)
        if match:
            var = match.group("var")
            self._screen_var = var
            self._ensure_node(var, "screen")
            self._parent_of[var] = None

    def _collect_widgets(self) -> None:
        """규격 생성 라인을 1차 정규식으로, 나머지는 폴백으로 위젯을 수집한다."""
        matched_spans: list[tuple[int, int]] = []
        for m in _CREATE_RE.finditer(self.source):
            matched_spans.append(m.span())
            self._register_widget(m.group("var"), m.group("type"), m.group("parent"))

        # 폴백(카드 12항): 1차 정규식이 잡지 못한 create 호출을 토큰 기반으로 복구.
        for m in _FALLBACK_CREATE_RE.finditer(self.source):
            if self._overlaps(m.span(), matched_spans):
                continue
            self._register_widget(m.group("var"), m.group("type"), m.group("parent"))

    def _collect_reparenting(self) -> None:
        """`lv_obj_set_parent`로 부모를 재지정한다(최신 호출이 우선)."""
        for m in _SET_PARENT_RE.finditer(self.source):
            child, parent = m.group("child"), m.group("parent")
            self._ensure_node(child)
            self._ensure_node(parent)
            self._parent_of[child] = parent

    def _collect_events(self) -> None:
        """`lv_obj_add_event_cb`에서 위젯-핸들러 연결을 수집한다."""
        for m in _EVENT_RE.finditer(self.source):
            widget, handler = m.group("widget"), m.group("handler")
            node = self._ensure_node(widget)
            if handler not in node["event_handlers"]:
                node["event_handlers"].append(handler)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _register_widget(self, var: str, wtype: str, parent: str) -> None:
        node = self._ensure_node(var, wtype)
        if wtype and node["type"] in (None, "obj") and wtype != node["type"]:
            node["type"] = wtype
        parent = parent.strip()
        if parent in _SCREEN_PARENTS:
            # 화면 직속 자식. 명시적 화면 변수가 있으면 그 밑에, 없으면 가상 루트.
            self._parent_of[var] = self._screen_var
        else:
            self._ensure_node(parent)
            self._parent_of[var] = parent

    def _ensure_node(self, var: str, wtype: str | None = None) -> dict:
        node = self._nodes.get(var)
        if node is None:
            node = {"var": var, "type": wtype, "children": [], "event_handlers": []}
            self._nodes[var] = node
            self._parent_of.setdefault(var, None)
        elif wtype and node["type"] is None:
            node["type"] = wtype
        return node

    @staticmethod
    def _overlaps(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
        s, e = span
        return any(not (e <= a or s >= b) for a, b in spans)

    def _build_tree(self) -> dict:
        """수집한 부모-자식 관계로 Nested Dictionary 트리를 조립한다."""
        # 자식 노드를 부모의 children 에 연결.
        for var, parent in self._parent_of.items():
            if parent is None or parent == var:
                continue
            parent_node = self._nodes.get(parent)
            if parent_node is None:
                parent_node = self._ensure_node(parent)
            child_node = self._nodes[var]
            if child_node not in parent_node["children"]:
                parent_node["children"].append(child_node)

        root_var = self._resolve_root()
        return self._nodes[root_var]

    def _resolve_root(self) -> str:
        """루트(화면) 노드 변수명을 결정한다."""
        if self._screen_var is not None:
            return self._screen_var
        # 화면 핸들이 명시되지 않은 경우: 부모가 없는 노드를 가상 루트로 사용.
        roots = [v for v, p in self._parent_of.items() if p is None]
        if roots:
            self._nodes[roots[0]]["type"] = self._nodes[roots[0]]["type"] or "screen"
            return roots[0]
        # 완전 폴백: 임의 노드.
        return next(iter(self._nodes))
