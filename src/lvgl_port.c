#include "lvgl_port.h"
#include "gc9a01.h"
#include "config.h"
#include "lvgl.h"
#include "pico/time.h"

/* Buffer de rendu partiel : 240 x 40 pixels en RGB565 (~19 Ko). */
#define BUF_LINES 40
static uint8_t draw_buf[LCD_W * BUF_LINES * 2];

/* Source de temps pour LVGL (ms depuis le boot). */
static uint32_t tick_ms(void) {
    return to_ms_since_boot(get_absolute_time());
}

/* Envoi d'une zone rendue vers l'ecran. */
static void flush_cb(lv_display_t *disp, const lv_area_t *area, uint8_t *px_map) {
    const uint32_t w = (area->x2 - area->x1 + 1);
    const uint32_t h = (area->y2 - area->y1 + 1);

    /* LVGL rend en RGB565 little-endian ; le GC9A01 attend du big-endian. */
    lv_draw_sw_rgb565_swap(px_map, w * h);

    gc9a01_set_window(area->x1, area->y1, area->x2, area->y2);
    gc9a01_blit(px_map, w * h * 2);

    lv_display_flush_ready(disp);
}

void lvgl_port_init(void) {
    lv_init();
    lv_tick_set_cb(tick_ms);

    lv_display_t *disp = lv_display_create(LCD_W, LCD_H);
    lv_display_set_flush_cb(disp, flush_cb);
    lv_display_set_buffers(disp, draw_buf, NULL, sizeof(draw_buf),
                           LV_DISPLAY_RENDER_MODE_PARTIAL);
}
