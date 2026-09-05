#ifndef UI_H
#define UI_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

void ui_init(void);

void ui_set_connected(bool connected);
void ui_set_track(const char *title, const char *artist);
void ui_set_state(const char *st);           /* "play" ou "pause" */
void ui_set_volume(int vol);                  /* 0..100 */
void ui_set_progress(int pos, int dur);       /* secondes */
void ui_set_cover(const uint8_t *jpeg, size_t len);

void ui_bringup_demo(void);                   /* ecran de test hors USB */

#endif /* UI_H */
