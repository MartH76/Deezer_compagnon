# Deezer Desk Gadget

Un petit **écran rond (GC9A01, 240×240)** posé à côté du PC qui affiche en temps
réel ce qui joue sur **Deezer** — pochette, titre, artiste, volume, progression —
et (à terme, via un encodeur) permet de changer de piste et de régler le volume.

L'écran est piloté par un **microcontrôleur RP2350** relié au PC en **USB**. Un
petit **compagnon Windows** lit la lecture Deezer (media session du système) et
l'envoie au micro par liaison série USB.

```
[GC9A01 + encodeur] --SPI--> [RP2350] --USB CDC--> [Compagnon Windows] --SMTC/pycaw--> Deezer
        ▲                                    │                                            │
        └────── état (titre / artiste / pochette / volume / play-pause) ◀────────────────┘
```

## Deux composants

| Composant | Où | Rôle |
|-----------|----|------|
| **Firmware** (`src/`, C, Pico SDK + LVGL) | sur le RP2350 | affichage LVGL sur le GC9A01, réception série |
| **Compagnon** (`companion/`, Python/Windows) | sur le PC | lit Deezer, envoie l'état + la pochette au micro, icône dans la zone de notification |

---

## Utilisation (utilisateur final — sans rien compiler)

À partir d'une *release* GitHub (voir plus bas) :

1. **Flasher le firmware** : brancher le Pico en maintenant **BOOTSEL** → il
   apparaît comme lecteur USB → y glisser le fichier **`.uf2`**. C'est tout.
2. **Lancer le compagnon** : double-cliquer **`DeezerCompanion.exe`**.
   Une icône apparaît dans la zone de notification (clic droit : état, Pause,
   Quitter).
3. Ouvrir **Deezer** et lancer une musique. L'écran se remplit.
4. *(option)* Lancement auto : `Win + R` → `shell:startup` → y déposer un
   raccourci vers `DeezerCompanion.exe`.

Prérequis côté utilisateur : **Windows**, l'appli **Deezer** (version desktop /
Store) et le gadget branché en USB. Aucun Python à installer.

---

## Câblage écran (SPI0)

Configurable dans `src/config.h` via le sélecteur `TARGET_PAMI`.

**Cible PAMI / Pico 2 W** (`TARGET_PAMI 1`, défaut) :

| GC9A01 | GPIO |
|--------|------|
| SCK    | GP18 |
| MOSI/SDA | GP19 |
| DC     | GP20 |
| CS     | GP21 |
| RST    | GP22 |
| BL     | 3V3 (pas de contrôle) |
| VCC / GND | 3V3 / GND |

**Carte finale RP2350-Zero** (`TARGET_PAMI 0`) : SCK=GP2, MOSI=GP3, DC=GP6,
CS=GP5, RST=GP7, BL=GP8. Encodeur (à venir) : A=GP10, B=GP11, SW=GP12
(`USE_ENCODER 1`).

---

## Build depuis les sources (développeur)

### Firmware (VS Code)
1. Installer l'extension **Raspberry Pi Pico** (fournit SDK, toolchain, CMake).
2. Ouvrir **ce dossier** (racine du dépôt). Carte : **Pico 2 W** (déjà fixée dans
   `CMakeLists.txt`).
3. *Configure CMake* puis *Compile*. Au 1er build, LVGL v9.2.2 est récupéré
   automatiquement (connexion internet requise).
4. Résultat : `build/Deezer_compagnon.uf2` → flasher via BOOTSEL.

Astuce : `BRINGUP_TEST 1` dans `config.h` affiche une mire de test sans PC.

### Compagnon (Python)
```
cd companion
python -m pip install -r requirements.txt
python deezer_companion.py          # port du Pico auto-détecté
```

### Compagnon → exécutable autonome
```
cd companion
build.bat                            # PyInstaller -> dist\DeezerCompanion.exe
```
Détails et dépannage : `companion/BUILD.md`.

---

## Contenu du dépôt

```
CMakeLists.txt, pico_sdk_import.cmake, lv_conf.h   # projet firmware Pico SDK
.vscode/                                           # config extension Pico (build/debug)
src/
  config.h            # TARGET_PAMI + pinout + options
  gc9a01.{c,h}        # driver écran (SPI + init + DMA)
  lvgl_port.{c,h}     # display LVGL (double-buffer plein écran, flush DMA)
  usb_proto.{c,h}     # réception série : ST {json} + pochette ART
  ui.{c,h}            # interface LVGL (pochette, titre, arc volume, progression)
  encoder.{c,h}       # encodeur rotatif (stub, à câbler)
  lv_font_dz_*.c      # polices Montserrat avec accents (générées)
  main.c
companion/
  deezer_companion.py # le compagnon (SMTC + pycaw + série + icône tray)
  requirements.txt
  start_companion.vbs # lanceur sans fenêtre (mode Python)
  build.bat, BUILD.md # génération de l'exécutable autonome
  app.ico
  smtc_debug.py       # utilitaire de diagnostic SMTC
```

---

## Fonctionnement (résumé technique)

- **Affichage** : LVGL v9, double framebuffer plein écran + envoi DMA vers le
  GC9A01 → rendu fluide, pochette affichée d'un coup.
- **Pochette** : lue via SMTC dans un thread WinRT persistant, ré-encodée en JPEG
  sous un budget (~12 Ko) pour un temps d'envoi constant, décodée par LVGL
  (`LV_USE_TJPGD` + `LV_USE_FS_MEMFS`). Cache par titre.
- **Réactivité** : le compagnon est piloté par les événements SMTC
  (changement de piste / play-pause), avec un *heartbeat* 1 s en filet.
- **Protocole série** : `ST {json}` (état) et `ART:<len>` + octets JPEG
  (PC → micro) ; `CMD:*` (micro → PC, pour l'encodeur à venir).

## Limitations connues

- **Compagnon = Windows uniquement** (SMTC + pycaw).
- **Deezer ne fournit pas sa file d'attente** → impossible de précharger les
  pochettes suivantes.
- Le **volume** lu/piloté est celui **par-application de Deezer** dans le
  mélangeur Windows (indépendant du curseur *interne* de l'appli Deezer).
- L'exe n'étant pas signé, **SmartScreen** peut avertir au 1er lancement.
