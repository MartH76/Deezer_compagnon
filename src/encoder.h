#ifndef ENCODER_H
#define ENCODER_H

/* Module encodeur rotatif + poussoir.
 * NON CABLE pour l'instant : actif seulement si USE_ENCODER=1 (config.h).
 * Schema prevu : rotation = volume, clic = play/pause,
 *                double-clic = piste suivante, appui long = piste precedente.
 * Les commandes sont emises sur l'USB CDC (memes chaines que le compagnon attend).
 */
void encoder_init(void);
void encoder_poll(void);

#endif /* ENCODER_H */
