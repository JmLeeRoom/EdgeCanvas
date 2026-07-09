"""T-302: Solar Pro 3 LVGL UI 레이아웃 생성 프롬프트 설계.

단위구현계획서.md 제5장 [T-302] 8항 구현 내용을 따른다.
기술 지식 베이스(T-203 `TechnologyKB`)의 하드웨어 사양(특히 1024x600 해상도)과
사용자 UI 요구사항을 결합하여, Solar Pro 3가 컴파일 가능한 LVGL 9.x C 코드
(`ui_screens.c`)를 합성하도록 시스템 프롬프트 및 컨텍스트를 구성한다.

DoD(11항) 반영:
- 11-a: 해상도 제약(1024x600)을 하드코딩하지 않고 런타임 입력(`TechnologyKB`
  또는 `resolution` 인자)으로 동적 매핑한다.
- 11-b: `main()` 함수/헤더 중복 작성을 배제하고 `ui_screens.c`에 특화된 코드만
  출력하도록 시스템 롤을 명시적으로 부여한다.

12항 실패 시 대처: Solar Pro 3가 LVGL 8.x 레거시 API를 섞어 생성하는 문제를
막기 위해, 프롬프트 최상단에 "LVGL 9.x API 금지어 및 대체 리스트"를 규정한다.
"""
from __future__ import annotations

from src.common.schema import DEFAULT_RESOLUTION, TechnologyKB

# ---------------------------------------------------------------------------
# 카드 12항: LVGL 9.x API 금지어 및 대체 리스트 (레거시 8.x -> 9.x)
# ---------------------------------------------------------------------------
# Solar Pro 3가 8.x 레거시 API를 섞어 생성하는 문제(카드 12)를 막기 위해,
# 금지할 8.x API와 그 9.x 대체 방식을 명시적으로 매핑한다.
FORBIDDEN_LEGACY_API: dict[str, str] = {
    "lv_btn_create": "lv_button_create (9.x에서 btn -> button 으로 개명)",
    "lv_btn_set_fit": "lv_obj_set_flex_grow / lv_obj_set_size (8.x 자동 fit 제거)",
    "lv_obj_set_click": "lv_obj_add_flag(obj, LV_OBJ_FLAG_CLICKABLE)",
    "lv_page_create": "lv_obj_create + lv_obj_set_scroll_dir (page 위젯 폐지)",
    "lv_cont_create": "lv_obj_create + lv_obj_set_flex_flow (cont 위젯 폐지)",
    "lv_label_set_align": "lv_obj_set_style_text_align(obj, align, LV_PART_MAIN)",
    "lv_obj_set_style_local_bg_color": (
        "lv_obj_set_style_bg_color(obj, color, LV_PART_MAIN)"
    ),
    "LV_LABEL_LONG_BREAK": "LV_LABEL_LONG_WRAP (enum 개명)",
}

# 카드 8-2: LVGL 9.x 전용 위젯 생성 함수 명명법(대표 위젯).
LVGL9_WIDGET_FACTORIES: list[str] = [
    "lv_obj_create",
    "lv_button_create",
    "lv_label_create",
    "lv_image_create",
    "lv_bar_create",
    "lv_slider_create",
    "lv_switch_create",
    "lv_textarea_create",
    "lv_dropdown_create",
]

# ---------------------------------------------------------------------------
# 카드 8-3: Few-Shot LVGL 9.x C 코드 블록 예시 (최소 3개)
# ---------------------------------------------------------------------------
# 모두 ui_screens.c에 그대로 들어갈 수 있는 형태이며, main()/헤더 중복이 없고
# LVGL 9.x API만 사용한다. Flex/Grid 레이아웃과 화면 전환 이벤트 연결 양식을
# 대표적으로 보여준다.
_FEWSHOT_LABEL_BUTTON = """```c
/* 예시 1: 세로 Flex 레이아웃 홈 화면 (라벨 + 버튼) */
void ui_init(void)
{
    lv_obj_t *screen = lv_obj_create(NULL);
    lv_obj_set_size(screen, 1024, 600);
    lv_obj_set_flex_flow(screen, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(screen, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    lv_obj_t *title = lv_label_create(screen);
    lv_label_set_text(title, "EdgeCanvas");

    lv_obj_t *btn = lv_button_create(screen);
    lv_obj_set_size(btn, 200, 60);
    lv_obj_t *btn_label = lv_label_create(btn);
    lv_label_set_text(btn_label, "Start");

    lv_scr_load(screen);
}
```"""

_FEWSHOT_SCREEN_TRANSITION = """```c
/* 예시 2: 화면 전환 이벤트 연결 양식 (버튼 클릭 -> 설정 화면 로드) */
static lv_obj_t *settings_screen;

static void go_settings_cb(lv_event_t *e)
{
    (void)e;
    lv_scr_load(settings_screen);
}

void ui_init(void)
{
    lv_obj_t *home = lv_obj_create(NULL);
    lv_obj_set_size(home, 1024, 600);

    settings_screen = lv_obj_create(NULL);
    lv_obj_set_size(settings_screen, 1024, 600);

    lv_obj_t *nav_btn = lv_button_create(home);
    lv_obj_add_event_cb(nav_btn, go_settings_cb, LV_EVENT_CLICKED, NULL);

    lv_scr_load(home);
}
```"""

_FEWSHOT_GRID = """```c
/* 예시 3: Grid 레이아웃 대시보드 (2x2 카드 배치) */
void ui_init(void)
{
    static lv_coord_t col_dsc[] = {LV_GRID_FR(1), LV_GRID_FR(1),
                                   LV_GRID_TEMPLATE_LAST};
    static lv_coord_t row_dsc[] = {LV_GRID_FR(1), LV_GRID_FR(1),
                                   LV_GRID_TEMPLATE_LAST};

    lv_obj_t *screen = lv_obj_create(NULL);
    lv_obj_set_size(screen, 1024, 600);
    lv_obj_set_grid_dsc_array(screen, col_dsc, row_dsc);
    lv_obj_set_layout(screen, LV_LAYOUT_GRID);

    for (int i = 0; i < 4; i++) {
        lv_obj_t *card = lv_obj_create(screen);
        lv_obj_set_grid_cell(card, LV_GRID_ALIGN_STRETCH, i % 2, 1,
                             LV_GRID_ALIGN_STRETCH, i / 2, 1);
        lv_obj_t *label = lv_label_create(card);
        lv_label_set_text_fmt(label, "Card %d", i + 1);
    }

    lv_scr_load(screen);
}
```"""

FEWSHOT_EXAMPLES: list[str] = [
    _FEWSHOT_LABEL_BUTTON,
    _FEWSHOT_SCREEN_TRANSITION,
    _FEWSHOT_GRID,
]


def _resolve_resolution(
    tech_kb: TechnologyKB | None,
    resolution: tuple[int, int] | None,
) -> tuple[int, int]:
    """해상도 제약을 런타임 입력에서 동적으로 결정한다(DoD 11-a).

    우선순위: 명시적 `resolution` 인자 > `TechnologyKB.resolution` > 기본값.
    어떤 입력도 없으면 Waveshare 기본 사양(1024x600)으로 폴백한다.
    """
    if resolution is not None:
        return resolution
    if tech_kb is not None:
        return tech_kb.resolution
    return DEFAULT_RESOLUTION


def _render_forbidden_api_block() -> str:
    """카드 12: 금지어/대체 리스트를 프롬프트 텍스트 블록으로 렌더링한다."""
    lines = [
        f"- 금지 `{legacy}` -> 대체 {replacement}"
        for legacy, replacement in FORBIDDEN_LEGACY_API.items()
    ]
    return "\n".join(lines)


def build_layout_generation_prompt(
    user_requirement: str,
    tech_kb: TechnologyKB | None = None,
    resolution: tuple[int, int] | None = None,
) -> str:
    """Solar Pro 3용 LVGL UI 레이아웃 생성 프롬프트를 구성한다.

    Args:
        user_requirement: 사용자 UI 요구사항 자연어 텍스트.
        tech_kb: 기술 지식 베이스(T-203). 해상도 등 하드웨어 사양을 동적 주입한다.
        resolution: 해상도를 직접 지정할 때 사용(``tech_kb``보다 우선).

    Returns:
        시스템 롤 + 규칙 + Few-Shot + 사용자 컨텍스트를 결합한 전체 프롬프트 문자열.
        API 키 없이도 순수하게 구성 가능하며(오프라인 테스트 대상), 그대로
        `UpstageClient.chat()`에 전달한다.
    """
    width, height = _resolve_resolution(tech_kb, resolution)

    forbidden_block = _render_forbidden_api_block()
    widget_naming = ", ".join(f"`{fn}`" for fn in LVGL9_WIDGET_FACTORIES)
    fewshot_block = "\n\n".join(FEWSHOT_EXAMPLES)

    return f"""[시스템 롤]
당신은 임베디드 HMI용 LVGL 9.x C 코드를 생성하는 전문 코드 생성기입니다.
당신의 유일한 출력물은 `ui_screens.c`에 그대로 삽입 가능한 C 코드입니다.

=== 최우선 규칙: LVGL 9.x API 금지어 및 대체 리스트 (반드시 준수) ===
아래 LVGL 8.x 레거시 API는 절대 사용하지 마세요. 반드시 9.x 대체를 사용합니다.
{forbidden_block}

위 금지어 중 하나라도 출력에 섞이면 그 코드는 컴파일되지 않으므로 실패입니다.

=== 하드웨어 제약 (런타임 동적 매핑) ===
- 디스플레이 해상도: {width}x{height} (가로 {width}px, 세로 {height}px 고정).
- 최상위 스크린 크기는 반드시 {width}x{height}에 맞추세요.

=== 출력 형식 규칙 (ui_screens.c 전용) ===
1. 반드시 하나 이상의 Markdown C 코드 블록(```c ... ```)으로만 코드를 출력합니다.
2. 화면 구성 진입점으로 `void ui_init(void)` 함수를 반드시 정의합니다.
3. `int main(...)` 함수를 작성하지 마세요. main 함수는 금지입니다.
4. `#include` 헤더를 중복 작성하지 마세요. `ui_screens.c`는 프로젝트의
   공통 헤더를 이미 포함하므로, 위젯/레이아웃/이벤트 코드만 출력합니다.
5. `ui_screens.c`에 특화된 화면 정의 코드 외의 부수 코드는 출력하지 않습니다.

=== LVGL 9.x 위젯 생성 함수 명명법 (카드 8-2) ===
위젯은 반드시 `lv_<widget>_create(parent)` 형태로 생성합니다: {widget_naming}.

=== 레이아웃 규칙 (Flex / Grid) ===
- Flex: `lv_obj_set_flex_flow(obj, LV_FLEX_FLOW_COLUMN|ROW)` 와
  `lv_obj_set_flex_align(...)` 으로 정렬합니다.
- Grid: `lv_obj_set_grid_dsc_array(obj, col_dsc, row_dsc)`,
  `lv_obj_set_layout(obj, LV_LAYOUT_GRID)`, `lv_obj_set_grid_cell(...)` 을 씁니다.

=== 화면 전환 이벤트 연결 양식 ===
- 이벤트 콜백은 `static void <name>_cb(lv_event_t *e)` 형태로 정의합니다.
- 위젯에 `lv_obj_add_event_cb(widget, <name>_cb, LV_EVENT_CLICKED, NULL)` 로 연결합니다.
- 화면 전환은 콜백 안에서 `lv_scr_load(target_screen)` 으로 수행합니다.

=== Few-Shot 예시 (아래 스타일을 그대로 따르세요) ===
{fewshot_block}

=== 사용자 UI 요구사항 ===
{user_requirement}

위 요구사항을 {width}x{height} 화면에 맞는 LVGL 9.x C 코드로 구현하세요.
`void ui_init(void)`를 포함하고, ```c 코드 블록으로만 출력하세요.
"""
