#ifndef GC9A01_H
#define GC9A01_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* Initialise SPI + GPIO + DMA et envoie la sequence d'init du GC9A01. */
void gc9a01_init(void);

/* Definit la fenetre d'ecriture puis prepare l'envoi des pixels (RAMWR). */
void gc9a01_set_window(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1);

/* Envoie un bloc de pixels RGB565 (big-endian) par DMA. NON bloquant :
   la callback enregistree via gc9a01_set_done_cb() est appelee en fin de transfert. */
void gc9a01_blit_dma(const uint8_t *data, size_t len);

/* Enregistre la callback de fin de transfert DMA (appelee depuis l'IRQ). */
void gc9a01_set_done_cb(void (*cb)(void));

/* Retroeclairage (no-op si HAVE_BACKLIGHT=0). */
void gc9a01_backlight(bool on);

#endif /* GC9A01_H */
