#include "pico/stdlib.h"
#include "config.h"
#include "gc9a01.h"
#include "lvgl.h"
#include "lvgl_port.h"
#include "ui.h"
#include "usb_proto.h"
#include "encoder.h"

int main(void) {
    /* USB CDC (liaison serie avec le compagnon PC). */
    stdio_init_all();

    /* Ecran + LVGL. */
    gc9a01_init();
    gc9a01_backlight(true);
    lvgl_port_init();
    ui_init();

#if USE_ENCODER
    encoder_init();
#endif

#if BRINGUP_TEST
    /* Mode validation ecran sans PC : mire + arc de volume anime. */
    ui_bringup_demo();
    while (true) {
        lv_timer_handler();
        sleep_ms(5);
    }
#else
    /* Fonctionnement normal : lecture USB -> mise a jour de l'UI. */
    while (true) {
        usb_proto_poll();
#if USE_ENCODER
        encoder_poll();
#endif
        lv_timer_handler();
        sleep_ms(5);
    }
#endif
}
