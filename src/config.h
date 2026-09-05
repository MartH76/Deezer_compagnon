#ifndef CONFIG_H
#define CONFIG_H

/* ================= Choix de la cible =================
 * 1 = PAMI de l'equipe (Raspberry Pi Pico 2 W) : ecran GC9A01 deja cable,
 *     sert de plateforme de dev en attendant le materiel final.
 * 0 = carte finale RP2350-Zero (cablage a definir).
 */
#define TARGET_PAMI 1

#if TARGET_PAMI
  /* --- Cablage impose par le PAMI (cf. lib_screen / PAMI_2026_IO.h) --- */
  #define PIN_SCK   18     /* SPI0 SCK */
  #define PIN_MOSI  19     /* SPI0 TX  */
  #define PIN_DC    20
  #define PIN_CS    21
  #define PIN_RST   22
  #define HAVE_BACKLIGHT 0 /* pas de pin retroeclairage sur le PAMI (cable au 3V3) */
#else
  /* --- Carte finale RP2350-Zero (a cabler) --- */
  #define PIN_SCK   2
  #define PIN_MOSI  3
  #define PIN_DC    6
  #define PIN_CS    5
  #define PIN_RST   7
  #define PIN_BL    8
  #define HAVE_BACKLIGHT 1
#endif

#define LCD_SPI     spi0
#define LCD_SPI_HZ  (62500000u)   /* 62.5 MHz (identique au driver PAMI) */
#define LCD_W       240
#define LCD_H       240

/* ==== Encodeur rotatif (carte finale, a cabler plus tard) ==== */
#define USE_ENCODER 0
#define PIN_ENC_A   10
#define PIN_ENC_B   11
#define PIN_ENC_SW  12

/* ==== Mode bring-up : ecran de test sans PC ==== */
#define BRINGUP_TEST 0

/* ==== Protocole serie ==== */
#define ART_MAX_BYTES (48 * 1024)

#endif /* CONFIG_H */
