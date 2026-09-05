# Compiler l'executable (Windows)

But : produire `DeezerCompanion.exe` autonome. L'utilisateur final n'installe
QUE Deezer + cet exe. Aucun Python requis chez lui.

## Compilation (une fois, sur une machine avec Python)

1. Ouvrir un terminal dans ce dossier `companion`.
2. Lancer :
   ```
   build.bat
   ```
   (double-clic possible aussi). Si `python` n'est pas reconnu, edite `build.bat`
   et remplace `python` par `python3.10`.
3. Resultat : **`dist\DeezerCompanion.exe`**.

Le build embarque winsdk (WinRT), pycaw/comtypes, pyserial, pystray, Pillow.
L'exe fait plusieurs dizaines de Mo (winsdk), c'est normal. Mode sans console
(tray uniquement), icone `app.ico`.

## Distribution / utilisation

- Copier `DeezerCompanion.exe` chez l'utilisateur, ou il veut.
- Double-clic -> icone dans la zone de notification (tray). Clic droit :
  etat, Pause, Quitter.
- Prerequis cote utilisateur : appli **Deezer** installee, et le gadget (Pico)
  branche en USB.

### Lancement automatique a l'ouverture de session
`Win + R` -> `shell:startup` -> y deposer un **raccourci** vers
`DeezerCompanion.exe`.

## Notes
- **SmartScreen** : l'exe n'etant pas signe numeriquement, Windows peut afficher
  un avertissement au 1er lancement -> "Informations complementaires" -> "Executer
  quand meme". (Une signature de code payante supprimerait l'avertissement.)
- Demarrage un peu plus lent qu'un script (l'exe onefile se decompresse en RAM au
  lancement) : ~1-2 s, sans impact ensuite.
- Pour debugger un souci de build, refaire un exe AVEC console : retirer
  `--noconsole` dans `build.bat` (les logs [serie]/[etat]/[pochette] s'affichent).
