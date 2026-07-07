/**
 * @file lv_conf.h
 * @brief T-801 — LVGL 9.x 최소 설정 (PC SDL2 시뮬레이터용)
 *
 * lv_port_pc_vscode 의 lv_conf.h 를 통째로 vendoring 하지 않고, SDL2 시뮬레이터
 * 스캐폴딩에 필요한 항목만 활성화한 최소본이다. 상세 기본값은 LVGL 배포본의
 * lv_conf_template.h 를 따르며, 지정하지 않은 매크로는 LVGL 기본값을 사용한다.
 *
 * 주의: LVGL 9.x 전용. 레거시 8.x 구문 금지(coding-standards).
 */
#ifndef LV_CONF_H
#define LV_CONF_H

#include <stdint.h>

/*====================
 *   COLOR / MEMORY
 *====================*/
#define LV_COLOR_DEPTH 32

/* 시뮬레이터는 표준 malloc 사용 */
#define LV_USE_STDLIB_MALLOC  LV_STDLIB_CLIB
#define LV_USE_STDLIB_STRING  LV_STDLIB_CLIB
#define LV_USE_STDLIB_SPRINTF LV_STDLIB_CLIB

/*====================
 *   HAL / TICK
 *====================*/
/* SDL 백엔드가 자체 tick 을 제공하므로 커스텀 tick 사용 */
#define LV_USE_SDL 1
#if LV_USE_SDL
    #define LV_SDL_INCLUDE_PATH   <SDL2/SDL.h>
    #define LV_SDL_RENDER_MODE    LV_DISPLAY_RENDER_MODE_DIRECT
    #define LV_SDL_BUF_COUNT      1
    #define LV_SDL_FULLSCREEN     0
    #define LV_SDL_DIRECT_EXIT    1
#endif

/* SDL 드라이버가 SDL_GetTicks 로 tick 을 커스텀 공급 */
#define LV_TICK_CUSTOM 0

/*====================
 *   FEATURES
 *====================*/
#define LV_USE_LOG 1
#if LV_USE_LOG
    #define LV_LOG_LEVEL LV_LOG_LEVEL_WARN
#endif

/*====================
 *   FONTS
 *====================*/
#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_DEFAULT &lv_font_montserrat_14

/*====================
 *   WIDGETS / THEME
 *====================*/
#define LV_USE_LABEL 1
#define LV_USE_THEME_DEFAULT 1

#endif /* LV_CONF_H */
