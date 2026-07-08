/**
 * @file main.c
 * @brief T-801 — LVGL PC(SDL2) 시뮬레이터 진입점 (스캐폴딩 / hello 템플릿)
 *
 * 이번 회차 범위: lv_port_pc_vscode 기반 SDL2 시뮬레이터 뼈대를 세우고
 * 1024x600 창이 뜨는 hello UI 수준까지 검증한다. 실제 생성 UI(ui_screens.c)
 * 연동은 T-303 완료 후 후속 Task 에서 붙인다.
 *
 * LVGL 9.x API 사용(레거시 8.x 구문 금지). 해상도 1024x600 고정.
 */
#include <stdio.h>
#include <unistd.h>

/* SDL2main 의 WinMain 래핑을 쓰지 않고 표준 main() 을 그대로 진입점으로 사용.
 * (LVGL 헤더가 내부적으로 SDL.h 를 include 하므로 그 전에 정의해야 한다.) */
#define SDL_MAIN_HANDLED

#include <SDL2/SDL.h>
#include "lvgl.h"

/* 타깃 실기 해상도(카드 8.3항) — 1024x600 고정 */
#define SIM_HOR_RES 1024
#define SIM_VER_RES 600

/**
 * @brief 스캐폴딩 검증용 빈 템플릿 UI.
 * T-303 이후 ui_screens.c 의 실제 화면 생성 함수로 대체된다.
 */
static void create_hello_ui(void)
{
    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x1e1e1e), LV_PART_MAIN);

    lv_obj_t *label = lv_label_create(scr);
    lv_label_set_text(label, "P10 Manufacturing\nLVGL 9.x SDL2 Simulator\n1024 x 600");
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, LV_PART_MAIN);
    lv_obj_set_style_text_color(label, lv_color_hex(0xffffff), LV_PART_MAIN);
    lv_obj_center(label);
}

int main(void)
{
    /* SDL2main 을 우회했으므로 SDL 초기화 준비를 명시적으로 알린다. */
    SDL_SetMainReady();

    /* 1. LVGL 코어 초기화 */
    lv_init();

    /* 2. SDL2 윈도우/디스플레이 생성 — 1024x600 고정 */
    lv_display_t *disp = lv_sdl_window_create(SIM_HOR_RES, SIM_VER_RES);
    if (disp == NULL) {
        fprintf(stderr, "[T-801] SDL2 윈도우 생성 실패\n");
        return 1;
    }

    /* 3. 마우스 입력(터치 이벤트 모방, DoD 11.3항) */
    lv_sdl_mouse_create();

    /* 4. hello 템플릿 UI */
    create_hello_ui();

    /* 5. 메인 루프: LVGL 타이머 핸들러 구동 */
    while (1) {
        uint32_t idle = lv_timer_handler();
        if (idle == LV_NO_TIMER_READY) {
            idle = 5;
        }
        usleep(idle * 1000);
    }

    return 0;
}
