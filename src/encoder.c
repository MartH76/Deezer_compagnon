#include "encoder.h"
#include "config.h"

#if USE_ENCODER
#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include <stdio.h>

/* ---- Etat quadrature ---- */
static uint8_t  prev_ab = 0;
static int      local_vol = 50;      /* mirroir local du volume (0..100) */

/* ---- Etat bouton ---- */
static bool     sw_prev = true;      /* actif bas -> true = relache */
static uint32_t sw_down_ms = 0;
static uint32_t last_click_ms = 0;
static bool     wait_dbl = false;

#define LONG_PRESS_MS 600
#define DBL_GAP_MS    350

static uint32_t now_ms(void) { return to_ms_since_boot(get_absolute_time()); }

void encoder_init(void) {
    gpio_init(PIN_ENC_A);  gpio_set_dir(PIN_ENC_A, GPIO_IN);  gpio_pull_up(PIN_ENC_A);
    gpio_init(PIN_ENC_B);  gpio_set_dir(PIN_ENC_B, GPIO_IN);  gpio_pull_up(PIN_ENC_B);
    gpio_init(PIN_ENC_SW); gpio_set_dir(PIN_ENC_SW, GPIO_IN); gpio_pull_up(PIN_ENC_SW);
    prev_ab = (gpio_get(PIN_ENC_A) << 1) | gpio_get(PIN_ENC_B);
}

/* Table de transition quadrature : renvoie -1, 0 ou +1. */
static int quad_step(uint8_t ab) {
    static const int8_t lut[16] = { 0,-1,+1,0, +1,0,0,-1, -1,0,0,+1, 0,+1,-1,0 };
    int idx = (prev_ab << 2) | ab;
    prev_ab = ab;
    return lut[idx & 0x0F];
}

static void send_volume(void) {
    if (local_vol < 0) local_vol = 0;
    if (local_vol > 100) local_vol = 100;
    printf("CMD:VOL=%d\n", local_vol);
}

void encoder_poll(void) {
    /* --- rotation --- */
    uint8_t ab = (gpio_get(PIN_ENC_A) << 1) | gpio_get(PIN_ENC_B);
    if (ab != (prev_ab & 0x03)) {
        int step = quad_step(ab);
        if (step) { local_vol += step * 2; send_volume(); }   /* pas de 2% */
    }

    /* --- bouton (actif bas) --- */
    bool sw = gpio_get(PIN_ENC_SW);   /* true = relache */
    uint32_t t = now_ms();

    if (sw_prev && !sw) {             /* front descendant : appui */
        sw_down_ms = t;
    } else if (!sw_prev && sw) {      /* front montant : relache */
        uint32_t held = t - sw_down_ms;
        if (held >= LONG_PRESS_MS) {
            printf("CMD:PREV\n");
        } else {
            if (wait_dbl && (t - last_click_ms) < DBL_GAP_MS) {
                printf("CMD:NEXT\n");
                wait_dbl = false;
            } else {
                wait_dbl = true;
                last_click_ms = t;
            }
        }
    }
    /* clic simple confirme si pas de 2e clic dans le delai */
    if (wait_dbl && (t - last_click_ms) >= DBL_GAP_MS) {
        printf("CMD:TOGGLE\n");
        wait_dbl = false;
    }
    sw_prev = sw;
}

#else  /* USE_ENCODER == 0 : stubs vides tant que l'encodeur n'est pas cable */
void encoder_init(void) {}
void encoder_poll(void) {}
#endif
