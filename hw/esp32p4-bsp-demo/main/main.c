/*
 * T-004: ESP32-P4 최소 빌드 스캐폴딩.
 * LCD/BSP 렌더링은 esp-bsp 공식 예제 연동 후 Phase HW에서 검증한다.
 */
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "p4_bsp_demo";

void app_main(void)
{
    ESP_LOGI(TAG, "ESP32-P4 BSP demo scaffold (T-004)");
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
