# Pokemon Battle Lens

[한국어](README.ko.md) | [日本語](README.ja.md)

Pokemon Battle Lens is a screen-capture based Pokemon battle assistant. It reads the game screen with OCR, detects the opponent Pokemon and your four moves, then shows type effectiveness, move category, ability warnings, and rough speed estimates.

This is an unofficial fan-made tool. Pokemon names, move data, and sprites are generated from PokeAPI data.

## Features

- Real-time screen capture from a monitor or selected game/emulator window
- OCR for Korean, English, and Japanese game screens
- Localized Pokemon/move JSON data for Korean, English, and Japanese
- Generation selector for type chart differences
- Move effectiveness display with color coding
- Move category display: Physical / Special / Status
- Opponent ability warning notes, such as Levitate-style immunity risks
- Rough opponent speed range estimation
- Always-on-top helper window
- Editable ROI boxes for different emulator/window layouts
- ROI/OCR settings saved per generation
- Settings snapshot save/restore for safe testing
- Optional PyInstaller build for a Windows EXE

## Current Scope

The app is currently focused on single battles.

Double battles are intentionally not enabled yet because their UI layout and OCR regions are different. Supporting them cleanly should be done as a separate battle mode with separate ROI profiles.

## Requirements

### Python

Python 3.10 or newer is recommended. The app is currently developed on Python 3.12.

Install Python packages:

```powershell
pip install -r requirements.txt
```

### Tesseract OCR

`pytesseract` is only a Python wrapper. You also need the Tesseract OCR engine installed on your system.

Windows install option:

```powershell
winget install --id UB-Mannheim.TesseractOCR --source winget
```

The app looks for Tesseract in:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
C:\Program Files (x86)\Tesseract-OCR\tesseract.exe
```

### OCR Language Data

Install the language packs you need into Tesseract's `tessdata` folder:

- `eng.traineddata` for English
- `kor.traineddata` for Korean
- `jpn.traineddata` for Japanese

Typical Windows path:

```text
C:\Program Files\Tesseract-OCR\tessdata
```

Korean and Japanese OCR presets intentionally do not mix English OCR by default. This reduces false matches on Pokemon game fonts.

## Run

```powershell
python pokemon_battle_lens.py
```

If you build an EXE, run:

```powershell
PokemonBattleLens.exe
```

## Basic Usage

1. Start your Pokemon game or emulator.
2. Run `python pokemon_battle_lens.py`.
3. Open `Settings`.
4. Select the capture target: monitor or game/emulator window.
5. Select generation and game screen language.
6. Open `ROI Preview`.
7. Adjust ROI boxes until opponent name, level, and all four moves are covered.
8. Start scanning.

## OCR and ROI

OCR means reading text from a captured image.

ROI means the rectangular screen region passed into OCR.

Different games, emulators, scaling settings, and layouts need different ROI coordinates. The app stores ROI and OCR preprocessing settings per generation. Use the settings snapshot feature before experimenting.

## Settings Snapshot

Use the settings snapshot buttons before changing OCR/ROI heavily:

- Save Snapshot
- Restore Snapshot

Snapshot files are local-only and are ignored by git:

```text
config/settings_snapshot.json
```

## Data Files

Included generated data:

```text
data/pokemon_ko.json
data/pokemon_en.json
data/pokemon_ja.json
assets/sprites/
```

The JSON data includes:

- Pokemon localized names
- Type data
- Base stats
- Possible abilities
- Sprite paths
- Move localized names
- Move type
- Move category

The data can be regenerated with:

```powershell
python scripts/fetch_pokeapi_data.py
```

This uses PokeAPI and may take time.

## Build Windows EXE

Install PyInstaller:

```powershell
pip install pyinstaller
```

Build:

```powershell
python -m PyInstaller --noconsole --onefile --name PokemonBattleLens --icon assets\app_icon.ico --add-data "data;data" --add-data "assets;assets" pokemon_battle_lens.py
```

Output:

```text
dist/PokemonBattleLens.exe
```

Notes:

- The EXE still expects Tesseract OCR to be installed on the computer.
- Local settings are written next to the EXE under `config/`.
- Do not commit generated EXE/build folders to git.

## Repository Layout

```text
pokemon_battle_lens.py       Main app
requirements.txt             Python dependencies
assets/                      Icons, UI images, Pokemon sprites
data/                        Generated Pokemon/move JSON data
config/roi_profiles.json     Example ROI profiles
config/ocr_aliases.json      Optional OCR correction aliases
scripts/fetch_pokeapi_data.py Data generation script
```

## Known Limitations

- OCR quality depends heavily on emulator scaling, game font, background, and ROI placement.
- Covered-window capture uses Windows `PrintWindow` when possible, but some hardware-accelerated games/emulators may not support it.
- Ability effects are warning-only. They do not automatically change type effectiveness.
- Speed estimates are approximate because trainer IVs, EVs, natures, items, and boosts are not fully known.
- Double battles are not yet supported.

## Legal

This project is unofficial and not affiliated with Nintendo, Game Freak, Creatures, or The Pokemon Company.

Pokemon data and sprites are generated from PokeAPI resources. Check PokeAPI and upstream asset licensing before redistributing large packaged builds.
