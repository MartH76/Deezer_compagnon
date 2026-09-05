# Deezer Desk Gadget

Petit ecran rond (GC9A01) pilote par un **Raspberry Pi Pico 2 (RP2350)**, branche
en USB au PC, qui affiche le titre / artiste / pochette en cours sur Deezer et
permet de controler la lecture. Un **compagnon Python** tourne sur le PC (Windows)
et fait le pont entre Deezer (media session SMTC) et le micro (USB CDC).

```
[GC9A01 (+encodeur)] --SPI--> [Pico 2] --USB CDC--> [compagnon Python] --> SMTC/pycaw --> Deezer
```

## Cible materielle

Deux cibles, selectionnees par `TARGET_PAMI` dans `src/config.h` :

- **`TARGET_PAMI 1`** (par defaut) : **PAMI de l'equipe** avec un **Pico 2 W** et
  l'ecran GC9A01 deja cable. Plateforme de dev en attendant le materiel final.
- **`TARGET_PAMI 0`** : carte finale **RP2350-Zero** (cablage a definir).

> Flasher le firmware Deezer sur le Pico du PAMI **remplace le firmware PAMI**.
> Pour rendre le robot, reflasher le `.uf2` d'origine de l'equipe.

## Cablage ecran

### PAMI (Pico 2 W) — impose par leur `lib_screen`
| GC9A01 | GPIO | 
|--------|------|
| SCK    | GP18 |
| MOSI/SDA | GP19 |
| DC     | GP20 |
| CS     | GP21 |
| RST    | GP22 |
| BL     | (cable au 3V3, pas de controle) |
| VCC / GND | 3V3 / GND |

SPI0, 62.5 MHz. `MADCTL=0x88` (identique au driver PAMI).

### Carte finale RP2350-Zero (`TARGET_PAMI 0`)
SCK=GP2, MOSI=GP3, DC=GP6, CS=GP5, RST=GP7, BL=GP8. Encodeur : A=GP10, B=GP11,
SW=GP12 (`USE_ENCODER 1`).

## Build du firmware (VS Code)

1. Extension **Raspberry Pi Pico** (fournit SDK, toolchain ARM, CMake/Ninja).
2. Ouvrir ce dossier. *Raspberry Pi Pico: Configure CMake*.
3. Carte : **Pico 2 W** (le CMake force deja `PICO_BOARD=pico2_w`), SDK **2.x**.
4. Compiler -> `build/deezer_gadget.uf2`.
   Au 1er build, CMake telecharge LVGL v9.2.2 (internet requis).
5. Brancher le Pico en **BOOTSEL** et copier le `.uf2`.

### Valider l'ecran sans le PC
`BRINGUP_TEST 1` dans `config.h`, flasher : mire titre + arc de volume, sans USB.
Remettre a 0 ensuite.

## Compagnon PC (Windows)

```
cd companion
pip install -r requirements.txt
python deezer_companion.py          # auto-detecte le port du Pico (VID Raspberry Pi)
```

Lit la session Deezer (appli desktop) et pousse titre/artiste/pochette/volume vers
l'ecran. Lancement au demarrage : tache planifiee ou raccourci .pyw dans Demarrage.

## Protocole serie

PC -> micro :
- `ST {"t":..,"a":..,"st":"play|pause","vol":0..100,"pos":s,"dur":s}\n`
- `ART:<len>\n` suivi de `<len>` octets JPEG (pochette 240x240)

micro -> PC :
- `CMD:TOGGLE` `CMD:NEXT` `CMD:PREV` `CMD:PLAY` `CMD:PAUSE` `CMD:VOL=NN`
- `HELLO` au boot (force le renvoi complet de l'etat)

## Arborescence

```
.vscode/                # config extension Pico (SDK, toolchain, debug)
CMakeLists.txt          # projet Pico SDK, LVGL via FetchContent, board pico2_w
pico_sdk_import.cmake
lv_conf.h               # config LVGL (RGB565, JPEG, polices)
src/
  config.h              # TARGET_PAMI + PINOUT + options
  gc9a01.c/.h           # driver ecran (SPI + init + blit)
  lvgl_port.c/.h        # display LVGL + tick + flush (swap RGB565)
  usb_proto.c/.h        # reception USB : ST {json} + pochette ART
  ui.c/.h               # interface LVGL (pochette, titre, arc volume...)
  encoder.c/.h          # encodeur (STUB, carte finale)
  main.c
companion/
  deezer_companion.py   # pont Windows <-> Deezer
  requirements.txt
```

## Points a valider sur le vrai materiel

- **Couleurs / orientation** : MADCTL est aligne sur le driver PAMI (`0x88`). Si un
  souci, ajuster `0x36` ou l'inversion `0x21` dans `gc9a01.c`.
- **Pochette JPEG** : decodeur TJPGD integre a LVGL (`LV_USE_TJPGD`). Si le titre
  s'affiche mais pas la pochette, on basculera sur un decodage TJpgDec manuel.
- **RAM** : `LV_MEM_SIZE` (200 Ko) contient la pochette decodee. Le Pico 2 a 520 Ko.
