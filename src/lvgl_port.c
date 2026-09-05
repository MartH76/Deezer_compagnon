#include "lvgl_port.h"
#include "gc9a01.h"
#include "config.h"
#include "lvgl.h"
#include "pico/time.h"

/* Deux buffers PLEIN ECRAN (240x240 RGB565 = 115 Ko chacun) -> double buffering.
   Buffer plein => toute zone invalide (pochette comprise) est rendue en UNE passe
   (donc UN seul decodage JPEG) puis envoyee en UN transfert DMA. */
#define FB_BYTES (LCD_W * LCD_H * 2)
static uint8_t buf1[FB_BYTES];
static uint8_t buf2[FB_BYTES];

static lv_display_t *g_disp;

static uint32_t tick_ms(void) {
    return to_ms_since_boot(get_absolute_time());
}

/* Fin de transfert DMA -> LVGL peut rendre la frame suivante. */
static void flush_done(void) {
    lv_display_flush_ready(g_disp);
}

static void flush_cb(lv_display_t *disp, const lv_area_t *area, uint8_t *px_map) {
    (void)disp;
    const uint32_t w = (area->x2 - area->x1 + 1);
    const uint32_t h = (area->y2 - area->y1 + 1);

    /* LVGL rend en RGB565 little-endian ; le GC9A01 attend du big-endian. */
    lv_draw_sw_rgb565_swap(px_map, w * h);

    gc9a01_set_window(area->x1, area->y1, area->x2, area->y2);
    gc9a01_blit_dma(px_map, w * h * 2);
    /* flush_ready() est appele depuis l'IRQ DMA (flush_done). */
}

void lvgl_port_init(void) {
    lv_init();
    lv_tick_set_cb(tick_ms);

    gc9a01_set_done_cb(flush_done);

    g_disp = lv_display_create(LCD_W, LCD_H);
    lv_display_set_flush_cb(g_disp, flush_cb);
    lv_display_set_buffers(g_disp, buf1, buf2, sizeof(buf1),
                           LV_DISPLAY_RENDER_MODE_PARTIAL);
}
