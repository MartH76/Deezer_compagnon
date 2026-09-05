#ifndef GC9A01_H
#define GC9A01_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* Initialise le SPI, les GPIO et envoie la sequence d'init du GC9A01. */
void gc9a01_init(void);

/* Definit la fenetre d'ecriture puis prepare l'envoi des pixels (RAMWR). */
void gc9a01_set_window(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1);

/* Envoie un bloc de pixels RGB565 (octets deja en big-endian). */
void gc9a01_blit(const uint8_t *data, size_t len);

/* Allume / eteint le retroeclairage. */
void gc9a01_backlight(bool on);

#endif /* GC9A01_H */
