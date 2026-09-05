#include "ui.h"
#include "config.h"
#include "lvgl.h"
#include <string.h>

/* Polices Montserrat avec accents (generees, cf. lv_font_dz_*.c) */
LV_FONT_DECLARE(lv_font_dz_title_22);
LV_FONT_DECLARE(lv_font_dz_artist_16);

#define ACCENT  0x8B5CF6   /* violet accent */

static lv_obj_t *canvas;
static uint8_t   cover_buf[LCD_W * LCD_H * 2];   /* fond RGB565 (pochette pre-decodee) */
static lv_obj_t *arc_vol;
static lv_obj_t *scrim;
static lv_obj_t *lbl_title;
static lv_obj_t *lbl_artist;
static lv_obj_t *bar_prog;
static lv_obj_t *lbl_state;
static lv_obj_t *lbl_wait;

static lv_image_dsc_t cover_dsc;   /* pochette JPEG (source variable pour LVGL) */
static bool connected = false;

void ui_init(void) {
    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);

    /* Fond = canvas RGB565 : la pochette y est DECODEE UNE FOIS puis affichee
       comme bitmap. Evite tout re-decodage JPEG pendant le defilement du titre. */
    canvas = lv_canvas_create(scr);
    lv_canvas_set_buffer(canvas, cover_buf, LCD_W, LCD_H, LV_COLOR_FORMAT_RGB565);
    lv_obj_center(canvas);
    lv_canvas_fill_bg(canvas, lv_color_black(), LV_OPA_COVER);

    /* Anneau de volume au bord, gap en bas */
    arc_vol = lv_arc_create(scr);
    lv_obj_set_size(arc_vol, 238, 238);
    lv_obj_center(arc_vol);
    lv_arc_set_bg_angles(arc_vol, 135, 45);
    lv_arc_set_range(arc_vol, 0, 100);
    lv_arc_set_value(arc_vol, 0);
    lv_obj_remove_flag(arc_vol, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_remove_style(arc_vol, NULL, LV_PART_KNOB);
    lv_obj_set_style_arc_width(arc_vol, 8, LV_PART_MAIN);
    lv_obj_set_style_arc_width(arc_vol, 8, LV_PART_INDICATOR);
    lv_obj_set_style_arc_color(arc_vol, lv_color_hex(0x333333), LV_PART_MAIN);
    lv_obj_set_style_arc_color(arc_vol, lv_color_hex(ACCENT), LV_PART_INDICATOR);

    /* Voile sombre en bas pour lisibilite du texte */
    scrim = lv_obj_create(scr);
    lv_obj_set_size(scrim, LCD_W, 88);
    lv_obj_align(scrim, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(scrim, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(scrim, LV_OPA_50, 0);
    lv_obj_set_style_border_width(scrim, 0, 0);
    lv_obj_set_style_radius(scrim, 0, 0);
    lv_obj_set_style_pad_all(scrim, 0, 0);
    lv_obj_remove_flag(scrim, LV_OBJ_FLAG_SCROLLABLE);

    /* Symbole etat (play/pause) en haut */
    lbl_state = lv_label_create(scr);
    lv_obj_set_style_text_font(lbl_state, &lv_font_montserrat_28, 0);
    lv_obj_set_style_text_color(lbl_state, lv_color_white(), 0);
    lv_label_set_text(lbl_state, LV_SYMBOL_PAUSE);
    lv_obj_align(lbl_state, LV_ALIGN_TOP_MID, 0, 20);

    /* Titre defilant */
    lbl_title = lv_label_create(scr);
    lv_obj_set_style_text_font(lbl_title, &lv_font_dz_title_22, 0);
    lv_obj_set_style_text_color(lbl_title, lv_color_white(), 0);
    lv_label_set_long_mode(lbl_title, LV_LABEL_LONG_SCROLL_CIRCULAR);
    lv_obj_set_width(lbl_title, 190);
    lv_obj_set_style_text_align(lbl_title, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(lbl_title, LV_ALIGN_BOTTOM_MID, 0, -50);
    lv_label_set_text(lbl_title, "");

    /* Artiste */
    lbl_artist = lv_label_create(scr);
    lv_obj_set_style_text_font(lbl_artist, &lv_font_dz_artist_16, 0);
    lv_obj_set_style_text_color(lbl_artist, lv_color_hex(0xBBBBBB), 0);
    lv_label_set_long_mode(lbl_artist, LV_LABEL_LONG_DOT);
    lv_obj_set_width(lbl_artist, 190);
    lv_obj_set_style_text_align(lbl_artist, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(lbl_artist, LV_ALIGN_BOTTOM_MID, 0, -28);
    lv_label_set_text(lbl_artist, "");

    /* Barre de progression fine */
    bar_prog = lv_bar_create(scr);
    lv_obj_set_size(bar_prog, 150, 4);
    lv_obj_align(bar_prog, LV_ALIGN_BOTTOM_MID, 0, -14);
    lv_bar_set_range(bar_prog, 0, 1000);
    lv_bar_set_value(bar_prog, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar_prog, lv_color_hex(0x444444), LV_PART_MAIN);
    lv_obj_set_style_bg_color(bar_prog, lv_color_hex(ACCENT), LV_PART_INDICATOR);

    /* Message d'attente tant que le PC n'a rien envoye */
    lbl_wait = lv_label_create(scr);
    lv_obj_set_style_text_font(lbl_wait, &lv_font_montserrat_16, 0);
    lv_obj_set_style_text_color(lbl_wait, lv_color_hex(0x888888), 0);
    lv_label_set_text(lbl_wait, "En attente du PC...");
    lv_obj_center(lbl_wait);
}

void ui_set_connected(bool c) {
    if (c == connected) return;
    connected = c;
    if (c) lv_obj_add_flag(lbl_wait, LV_OBJ_FLAG_HIDDEN);
    else   lv_obj_remove_flag(lbl_wait, LV_OBJ_FLAG_HIDDEN);
}

void ui_set_track(const char *title, const char *artist) {
    static char lt[128] = "", la[96] = "";
    if (strncmp(lt, title, sizeof(lt)) != 0) {
        lv_label_set_text(lbl_title, title);
        strncpy(lt, title, sizeof(lt) - 1); lt[sizeof(lt) - 1] = 0;
    }
    if (strncmp(la, artist, sizeof(la)) != 0) {
        lv_label_set_text(lbl_artist, artist);
        strncpy(la, artist, sizeof(la) - 1); la[sizeof(la) - 1] = 0;
    }
}

void ui_set_state(const char *st) {
    bool playing = (strcmp(st, "play") == 0);
    lv_label_set_text(lbl_state, playing ? LV_SYMBOL_PLAY : LV_SYMBOL_PAUSE);
    lv_obj_set_style_text_color(lbl_state,
        playing ? lv_color_hex(ACCENT) : lv_color_hex(0x888888), 0);
}

void ui_set_volume(int vol) {
    if (vol < 0) vol = 0; if (vol > 100) vol = 100;
    lv_arc_set_value(arc_vol, vol);
}

void ui_set_progress(int pos, int dur) {
    int v = (dur > 0) ? (int)((int64_t)pos * 1000 / dur) : 0;
    if (v < 0) v = 0; if (v > 1000) v = 1000;
    lv_bar_set_value(bar_prog, v, LV_ANIM_OFF);
}

void ui_set_cover(const uint8_t *jpeg, size_t len) {
    memset(&cover_dsc, 0, sizeof(cover_dsc));
    cover_dsc.header.magic = LV_IMAGE_HEADER_MAGIC;
    cover_dsc.header.cf    = LV_COLOR_FORMAT_RAW;   /* JPEG encode -> decode par TJPGD */
    cover_dsc.header.w     = LCD_W;
    cover_dsc.header.h     = LCD_H;
    cover_dsc.data         = jpeg;
    cover_dsc.data_size    = len;

    /* Forcer le decodage du NOUVEau JPEG (meme pointeur dsc reutilise). */
    lv_image_cache_drop(&cover_dsc);

    /* Decoder la pochette UNE seule fois dans le buffer RGB565 du canvas. */
    lv_layer_t layer;
    lv_canvas_init_layer(canvas, &layer);
    lv_draw_image_dsc_t idsc;
    lv_draw_image_dsc_init(&idsc);
    idsc.src = &cover_dsc;
    lv_area_t area = { 0, 0, LCD_W - 1, LCD_H - 1 };
    lv_draw_image(&layer, &idsc, &area);
    lv_canvas_finish_layer(canvas, &layer);

    lv_obj_invalidate(canvas);
}

void ui_bringup_demo(void) {
    ui_set_connected(true);
    ui_set_track("Bring-up OK", "GC9A01 + LVGL");
    ui_set_state("play");
    ui_set_volume(66);
    ui_set_progress(80, 200);
}
