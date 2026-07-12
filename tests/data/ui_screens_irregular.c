/*
 * T-303 폴백 파서 검증용 비규격(irregular) ui_screens.c
 *
 * LLM이 비규격 형식으로 위젯을 생성해 1차 정규식
 * (`lv_obj_t *<var> = lv_<type>_create(...)`)이 깨지는 상황을 재현한다.
 * CodeParser는 폴백 토큰 파서로 `lv_` 접두사 기반 위젯을 역추출해야 한다.
 */
#include "lvgl.h"

/* 전역/재사용 핸들: lv_obj_t* 선언 없이 대입만 함 -> 1차 정규식 실패 */
lv_obj_t *_R7xQ;
lv_obj_t *Z9k;

void create_irregular_screen(void)
{
    lv_obj_t *scr = lv_screen_active();

    /* 규격 변수명: 1차 정규식으로 정상 매칭 */
    lv_obj_t *panel = lv_obj_create(scr);

    /* 비규격: lv_obj_t* 선언 없이 대입만 -> 1차 실패, 폴백으로 역추출 */
    _R7xQ = lv_slider_create(panel);

    /* 비규격: 마찬가지로 선언 없는 대입 -> 폴백으로 역추출 */
    Z9k = lv_switch_create(scr);
}
