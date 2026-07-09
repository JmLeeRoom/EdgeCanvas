# T-302 검증 기록 — Solar Pro 3 LVGL UI 레이아웃 프롬프트 설계

- **Task**: [T-302] Solar Pro 3 LVGL UI 레이아웃 프롬프트 설계
- **Issue**: #45
- **Phase/모듈**: 코드 생성, Phase A
- **선행 Task**: T-203(53f2934), T-009(0e1bf7b) — 모두 main 머지 확인
- **산출물**: `src/agent/prompts/layout_generator.py`
- **Pass**: Pass 1 (Implementer) 만 수행

## 1. 설계 개요

`build_layout_generation_prompt(user_requirement, tech_kb=None, resolution=None)` 함수는
Solar Pro 3에 전달할 **시스템 롤 + 규칙 + Few-Shot + 사용자 컨텍스트** 결합 프롬프트를
순수 문자열로 생성한다(API 키 불필요, 오프라인 단위 테스트 가능).

프롬프트 구성 순서(위 -> 아래):
1. 시스템 롤: "ui_screens.c에 삽입 가능한 LVGL 9.x C 코드만 출력하는 코드 생성기".
2. **최상단** LVGL 9.x API 금지어 및 대체 리스트 (카드 12 대책).
3. 하드웨어 제약 — 해상도 동적 매핑 (DoD 11-a).
4. 출력 형식 규칙 — main() 금지, 헤더 중복 금지, ui_screens.c 전용 (DoD 11-b).
5. LVGL 9.x 위젯 생성 함수 명명법 (카드 8-2).
6. Flex/Grid 레이아웃 규칙 + 화면 전환 이벤트 연결 양식 (카드 8-2).
7. Few-Shot C 코드 블록 예시 3개 (카드 8-3).
8. 사용자 UI 요구사항 컨텍스트.

## 2. DoD(11항) 체크리스트

- [x] **11-a**: 1024x600 해상도 제약이 런타임에 동적 매핑됨.
  - `_resolve_resolution()`이 우선순위 `resolution` 인자 > `TechnologyKB.resolution` >
    기본값(`DEFAULT_RESOLUTION` = 1024x600) 순으로 결정한다. 해상도는 f-string으로
    프롬프트에 주입되며 하드코딩이 아니다. 테스트에서 800x480 / 1280x720 을 주면
    해당 값이 프롬프트에 반영되고 기본값(1024x600)은 사라지는 것을 검증했다.
- [x] **11-b**: main() 함수/헤더 중복 배제 + ui_screens.c 전용 출력 시스템 롤 부여.
  - 시스템 롤과 "출력 형식 규칙" 절에서 `int main(...)` 금지, `#include` 중복 금지,
    ui_screens.c 화면 정의 코드만 출력을 명시했다.

## 3. 카드 12 실패 시 대처 — LVGL 9.x API 금지어 및 대체 리스트

`FORBIDDEN_LEGACY_API` dict가 (레거시 8.x -> 9.x 대체) 매핑 8건을 제공하며,
프롬프트 **최상단**(사용자 요구사항보다 앞)에 렌더링된다. 대표 항목:

- `lv_btn_create` -> `lv_button_create`
- `lv_btn_set_fit` -> `lv_obj_set_flex_grow` / `lv_obj_set_size`
- `lv_obj_set_click` -> `lv_obj_add_flag(obj, LV_OBJ_FLAG_CLICKABLE)`
- `lv_page_create` / `lv_cont_create` -> `lv_obj_create` + 레이아웃 API
- `lv_label_set_align` -> `lv_obj_set_style_text_align(...)`
- `lv_obj_set_style_local_bg_color` -> `lv_obj_set_style_bg_color(...)`
- `LV_LABEL_LONG_BREAK` -> `LV_LABEL_LONG_WRAP`

## 4. Few-Shot 예시 (카드 8-3, 3개)

1. 세로 Flex 레이아웃 홈 화면 (라벨 + 버튼)
2. 화면 전환 이벤트 연결 양식 (버튼 클릭 -> 설정 화면 `lv_scr_load`)
3. Grid 2x2 대시보드 카드 배치

세 예시 모두 `void ui_init(void)`를 진입점으로 쓰고, main()/헤더 중복이 없으며
LVGL 9.x API만 사용한다.

## 5. 단위 테스트 결과 (카드 10)

실행 명령: `.venv\Scripts\python.exe -m pytest tests/test_prompt_generation.py -v -s`
(repo venv = Python 3.13, langchain-upstage 설치됨)

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
collected 12 items

tests/test_prompt_generation.py::test_prompt_embeds_default_resolution PASSED
tests/test_prompt_generation.py::test_prompt_resolution_is_dynamic_via_kb PASSED
tests/test_prompt_generation.py::test_prompt_resolution_dynamic_via_explicit_tuple PASSED
tests/test_prompt_generation.py::test_prompt_contains_user_requirement PASSED
tests/test_prompt_generation.py::test_prompt_contains_at_least_three_c_code_blocks PASSED
tests/test_prompt_generation.py::test_prompt_contains_lvgl9_widget_naming PASSED
tests/test_prompt_generation.py::test_prompt_defines_layout_and_event_rules PASSED
tests/test_prompt_generation.py::test_prompt_enforces_ui_screens_only_output PASSED
tests/test_prompt_generation.py::test_prompt_contains_forbidden_legacy_api_list PASSED
tests/test_prompt_generation.py::test_forbidden_legacy_api_maps_to_9x_replacement PASSED
tests/test_prompt_generation.py::test_forbidden_api_list_rendered_near_top PASSED
tests/test_prompt_generation.py::test_solar_generates_lvgl9_c_code_live PASSED
============================= 12 passed in 8.75s ==============================
```

- 오프라인 테스트 11건: 프롬프트 문자열 검증(해상도 동적 매핑, C 코드 블록 >=3,
  LVGL 9.x 위젯 명명법, 금지어 리스트, ui_screens.c 전용 지시) 전부 통과.
- 라이브 API 테스트 1건(`test_solar_generates_lvgl9_c_code_live`): `UPSTAGE_API_KEY`가
  설정되어 **실제 실행됨**. Solar Pro 응답(약 2177자)에 다음이 모두 포함됨을 확인.
  - ` ```c ` Markdown C 코드 블록 존재
  - `ui_init()` 함수 존재
  - `lv_*_create` LVGL 9.x 위젯 생성 함수 존재
  - (API 키 값은 로그/기록 어디에도 남기지 않음)

## 6. 설계된 프롬프트 전문 (기본 KB, 1024x600)

아래는 `TechnologyKB()` 기본값 + 예시 요구사항으로 생성한 실제 프롬프트 전문이다.

````text
[시스템 롤]
당신은 임베디드 HMI용 LVGL 9.x C 코드를 생성하는 전문 코드 생성기입니다.
당신의 유일한 출력물은 `ui_screens.c`에 그대로 삽입 가능한 C 코드입니다.

=== 최우선 규칙: LVGL 9.x API 금지어 및 대체 리스트 (반드시 준수) ===
아래 LVGL 8.x 레거시 API는 절대 사용하지 마세요. 반드시 9.x 대체를 사용합니다.
- 금지 `lv_btn_create` -> 대체 lv_button_create (9.x에서 btn -> button 으로 개명)
- 금지 `lv_btn_set_fit` -> 대체 lv_obj_set_flex_grow / lv_obj_set_size (8.x 자동 fit 제거)
- 금지 `lv_obj_set_click` -> 대체 lv_obj_add_flag(obj, LV_OBJ_FLAG_CLICKABLE)
- 금지 `lv_page_create` -> 대체 lv_obj_create + lv_obj_set_scroll_dir (page 위젯 폐지)
- 금지 `lv_cont_create` -> 대체 lv_obj_create + lv_obj_set_flex_flow (cont 위젯 폐지)
- 금지 `lv_label_set_align` -> 대체 lv_obj_set_style_text_align(obj, align, LV_PART_MAIN)
- 금지 `lv_obj_set_style_local_bg_color` -> 대체 lv_obj_set_style_bg_color(obj, color, LV_PART_MAIN)
- 금지 `LV_LABEL_LONG_BREAK` -> 대체 LV_LABEL_LONG_WRAP (enum 개명)

위 금지어 중 하나라도 출력에 섞이면 그 코드는 컴파일되지 않으므로 실패입니다.

=== 하드웨어 제약 (런타임 동적 매핑) ===
- 디스플레이 해상도: 1024x600 (가로 1024px, 세로 600px 고정).
- 최상위 스크린 크기는 반드시 1024x600에 맞추세요.

=== 출력 형식 규칙 (ui_screens.c 전용) ===
1. 반드시 하나 이상의 Markdown C 코드 블록(```c ... ```)으로만 코드를 출력합니다.
2. 화면 구성 진입점으로 `void ui_init(void)` 함수를 반드시 정의합니다.
3. `int main(...)` 함수를 작성하지 마세요. main 함수는 금지입니다.
4. `#include` 헤더를 중복 작성하지 마세요. `ui_screens.c`는 프로젝트의
   공통 헤더를 이미 포함하므로, 위젯/레이아웃/이벤트 코드만 출력합니다.
5. `ui_screens.c`에 특화된 화면 정의 코드 외의 부수 코드는 출력하지 않습니다.

=== LVGL 9.x 위젯 생성 함수 명명법 (카드 8-2) ===
위젯은 반드시 `lv_<widget>_create(parent)` 형태로 생성합니다: `lv_obj_create`,
`lv_button_create`, `lv_label_create`, `lv_image_create`, `lv_bar_create`,
`lv_slider_create`, `lv_switch_create`, `lv_textarea_create`, `lv_dropdown_create`.

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
[예시 1: 세로 Flex 홈 화면(라벨+버튼) / 예시 2: 화면 전환 이벤트 / 예시 3: Grid 2x2]
(각 예시는 ```c 코드 블록으로 ui_init() 진입점을 포함, 전체는 layout_generator.py 참조)

=== 사용자 UI 요구사항 ===
상단에 제목 라벨, 중앙에 온도 표시 라벨, 하단에 설정 화면으로 이동하는 버튼이 있는 홈 화면을 만들어 주세요.

위 요구사항을 1024x600 화면에 맞는 LVGL 9.x C 코드로 구현하세요.
`void ui_init(void)`를 포함하고, ```c 코드 블록으로만 출력하세요.
````

> Few-Shot 예시 3개 전문은 `src/agent/prompts/layout_generator.py`의
> `FEWSHOT_EXAMPLES`에 그대로 정의되어 있다.

## 7. Pass 2 리뷰 참고 사항 / 트레이드오프

- 프롬프트는 순수 문자열 조립이라 API 키 없이 오프라인 검증 가능하도록 설계했다.
  라이브 테스트만 `UPSTAGE_API_KEY` 가드(skipif)로 분리했다.
- 금지어 리스트/위젯 명명법/Few-Shot는 카드 범위(8-2, 8-3, 12)에 맞춰 대표 항목만
  담았다. 목록 확장·정교화는 Pass 2 또는 후속 Task(T-303 파서) 피드백으로 조정 가능.
- `TechnologyKB`의 `display_controller`/`touch_ic`/`color_depth`/`pin_config`는
  카드 7 목적상 "해상도 결합"이 핵심이라 이번 프롬프트에는 해상도만 주입했다.
  추가 스펙 주입이 필요하면 Pass 2에서 범위 확장 검토(현재는 카드 범위 밖).


