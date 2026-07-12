/*
 * T-303 테스트용 모의(mock) ui_screens.c
 *
 * LVGL 9.x API 스타일로 작성한 표준 규격 UI 소스이다.
 * - 화면(root): lv_screen_active()
 * - 위젯 생성: lv_<type>_create(parent)  (첫 인자가 부모)
 * - 부모 재지정: lv_obj_set_parent(child, parent)
 * - 이벤트 핸들러: lv_obj_add_event_cb(widget, handler, LV_EVENT_*, NULL)
 *
 * CodeParser.parse_tree()가 이 파일로부터 위젯 계층 트리와
 * 이벤트 핸들러 연결 관계를 복원할 수 있어야 한다.
 */
#include "lvgl.h"

static void submit_event_handler(lv_event_t *e)
{
    /* 제출 버튼 클릭 처리 */
}

static void cancel_event_handler(lv_event_t *e)
{
    /* 취소 버튼 클릭 처리 */
}

void create_main_screen(void)
{
    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x202020), LV_PART_MAIN);

    /* 화면 직속 자식 1: 컨테이너 */
    lv_obj_t *panel = lv_obj_create(scr);
    lv_obj_set_size(panel, 400, 300);
    lv_obj_center(panel);

    /* 화면 직속 자식 2: 타이틀 라벨 */
    lv_obj_t *title = lv_label_create(scr);
    lv_label_set_text(title, "Manufacturing HMI");

    /* 화면 직속 자식 3: 하단 상태 라벨 */
    lv_obj_t *footer = lv_label_create(scr);
    lv_label_set_text(footer, "Ready");

    /* 패널 안의 자식 위젯들 */
    lv_obj_t *submit_btn = lv_button_create(panel);
    lv_obj_t *submit_label = lv_label_create(submit_btn);
    lv_label_set_text(submit_label, "Submit");
    lv_obj_add_event_cb(submit_btn, submit_event_handler, LV_EVENT_CLICKED, NULL);

    lv_obj_t *cancel_btn = lv_button_create(panel);
    lv_obj_add_event_cb(cancel_btn, cancel_event_handler, LV_EVENT_CLICKED, NULL);

    /* 처음엔 화면에 붙였다가 이후 패널로 재지정하는 위젯 (set_parent 역추적 검증) */
    lv_obj_t *hint_label = lv_label_create(scr);
    lv_label_set_text(hint_label, "Press submit");
    lv_obj_set_parent(hint_label, panel);
}
