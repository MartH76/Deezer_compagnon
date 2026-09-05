#include "usb_proto.h"
#include "ui.h"
#include "config.h"

#include "pico/stdlib.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

/* ================= Mini-parseur JSON (champs plats connus) =================
 * Suffisant pour les objets emis par le compagnon :
 *   {"t":"...","a":"...","st":"play","vol":42,"pos":12,"dur":210}
 */

/* Extrait la chaine associee a "key" dans out (gere les echappements JSON). */
static bool json_get_str(const char *js, const char *key, char *out, size_t outsz) {
    char pat[24];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    const char *p = strstr(js, pat);
    if (!p) { if (outsz) out[0] = 0; return false; }
    p += strlen(pat);
    while (*p == ' ' || *p == ':') p++;
    if (*p != '"') { if (outsz) out[0] = 0; return false; }
    p++;
    size_t i = 0;
    while (*p && *p != '"' && i < outsz - 1) {
        if (*p == '\\' && p[1]) {
            p++;
            switch (*p) {
                case 'n': out[i++] = '\n'; break;
                case 't': out[i++] = '\t'; break;
                case 'r': break;
                case 'b': out[i++] = '\b'; break;
                case 'f': out[i++] = '\f'; break;
                default:  out[i++] = *p; break;   /* \" \\ \/ et autres */
            }
            p++;
        } else {
            out[i++] = *p++;
        }
    }
    out[i] = 0;
    return true;
}

/* Extrait l'entier associe a "key", ou def si absent. */
static int json_get_int(const char *js, const char *key, int def) {
    char pat[24];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    const char *p = strstr(js, pat);
    if (!p) return def;
    p += strlen(pat);
    while (*p == ' ' || *p == ':') p++;
    return (int)strtol(p, NULL, 10);
}

static void handle_state(const char *js) {
    static char title[128], artist[96], stt[8];
    json_get_str(js, "t", title, sizeof(title));
    json_get_str(js, "a", artist, sizeof(artist));
    json_get_str(js, "st", stt, sizeof(stt));
    int vol = json_get_int(js, "vol", -1);
    int pos = json_get_int(js, "pos", 0);
    int dur = json_get_int(js, "dur", 0);

    ui_set_connected(true);
    ui_set_track(title, artist);
    ui_set_state(stt);
    if (vol >= 0) ui_set_volume(vol);
    ui_set_progress(pos, dur);
}

/* ================= Machine a etats de reception ================= */

static uint8_t art_buf[ART_MAX_BYTES];
static enum { M_LINE, M_ART } mode = M_LINE;

static char   line[512];
static size_t line_len = 0;

static size_t art_exp = 0;   /* octets JPEG attendus */
static size_t art_got = 0;   /* octets JPEG recus    */

static void handle_line(const char *l) {
    if (strncmp(l, "ST ", 3) == 0) {
        handle_state(l + 3);
    } else if (strncmp(l, "ART:", 4) == 0) {
        art_exp = (size_t)strtoul(l + 4, NULL, 10);
        art_got = 0;
        if (art_exp > 0) mode = M_ART;
    }
    /* toute autre ligne est ignoree */
}

static void feed(uint8_t b) {
    if (mode == M_ART) {
        if (art_got < ART_MAX_BYTES) art_buf[art_got] = b;
        art_got++;
        if (art_got >= art_exp) {
            size_t n = (art_exp <= ART_MAX_BYTES) ? art_exp : ART_MAX_BYTES;
            ui_set_cover(art_buf, n);
            mode = M_LINE;
        }
        return;
    }

    /* mode ligne texte */
    if (b == '\r') return;
    if (b == '\n') {
        line[line_len] = 0;
        handle_line(line);
        line_len = 0;
        return;
    }
    if (line_len < sizeof(line) - 1) line[line_len++] = b;
}

void usb_proto_poll(void) {
    /* Draine le buffer USB, borne pour ne pas affamer LVGL. */
    int budget = 8192;
    while (budget-- > 0) {
        int c = getchar_timeout_us(0);
        if (c == PICO_ERROR_TIMEOUT) break;
        feed((uint8_t)c);
    }
}
