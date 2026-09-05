#ifndef LV_CONF_H
#define LV_CONF_H
#include <stdint.h>

/* Profondeur couleur 16 bits (RGB565) */
#define LV_COLOR_DEPTH 16

/* Tas LVGL : doit contenir la pochette decodee (240x240x2 = 115 Ko) + marge */
#define LV_MEM_SIZE (160 * 1024U)

/* Rendu software en C pur : pas d'assembleur Helium/NEON (incompatible ici) */
#define LV_USE_DRAW_SW_ASM LV_DRAW_SW_ASM_NONE

/* Memory-FS : requis pour que TJPGD decode un JPEG depuis la RAM (pochette) */
#define LV_USE_FS_MEMFS 1
#define LV_FS_MEMFS_LETTER 'M'

/* Decodeur JPEG integre (Tiny JPEG) pour les pochettes recues du PC */
#define LV_USE_CANVAS 1
#define LV_USE_TJPGD 1

/* Polices Montserrat utilisees par l'UI */
#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_MONTSERRAT_16 1
#define LV_FONT_MONTSERRAT_22 1
#define LV_FONT_MONTSERRAT_28 1
#define LV_FONT_DEFAULT &lv_font_montserrat_16

/* Logs desactives */
#define LV_USE_LOG 0

#endif /* LV_CONF_H */
