# Pokemon Battle Lens

[English](README.md) | [한국어](README.ko.md)

Pokemon Battle Lens は、画面キャプチャを利用するポケモンバトル支援ツールです。ゲーム画面を OCR で読み取り、相手のポケモンと自分の技 4 つを検出して、タイプ相性、技分類、特性に関する注意、素早さの概算を表示します。

このプロジェクトは非公式のファンメイドツールです。ポケモン名と技データは PokeAPI のデータから生成されています。ポケモンのスプライト画像はこのリポジトリには含めておらず、必要な場合はユーザーがローカルで任意にダウンロードできます。

## 機能

- モニターまたは選択したゲーム/エミュレーターウィンドウのリアルタイムキャプチャ
- 日本語、英語、韓国語のゲーム画面 OCR
- 日本語、英語、韓国語のポケモン/技 JSON データ
- 世代ごとのタイプ相性差に対応する世代選択
- 色分けされた技ごとのタイプ相性表示
- 技分類表示: 物理 / 特殊 / 変化
- ふゆう系の無効化リスクなど、相手特性の注意表示
- 相手ポケモンの素早さ範囲の概算
- 常に前面表示できる補助ウィンドウ
- エミュレーターやウィンドウ配置に合わせて編集できる ROI 領域
- 世代ごとの ROI/OCR 設定保存
- 安全に試すための設定スナップショット保存/復元
- Windows EXE ビルド対応

## 現在の対象範囲

現在のアプリはシングルバトルを対象にしています。

ダブルバトルは UI レイアウトと OCR 領域が異なるため、まだ有効化していません。きれいに対応するには、別のバトルモードと専用 ROI プロファイルとして実装するのが適切です。

## 必要なもの

### Python

Python 3.10 以上を推奨します。現在の開発環境は Python 3.12 です。

Python パッケージをインストールします。

```powershell
pip install -r requirements.txt
```

### Tesseract OCR

`pytesseract` は Python ラッパーです。実際の OCR エンジンである Tesseract OCR もシステムにインストールする必要があります。

Windows でのインストール例:

```powershell
winget install --id UB-Mannheim.TesseractOCR --source winget
```

アプリは以下の場所から Tesseract を探します。

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
C:\Program Files (x86)\Tesseract-OCR\tesseract.exe
```

### OCR 言語データ

必要な言語パックを Tesseract の `tessdata` フォルダーに入れてください。

- `eng.traineddata`: 英語
- `kor.traineddata`: 韓国語
- `jpn.traineddata`: 日本語

一般的な Windows パス:

```text
C:\Program Files\Tesseract-OCR\tessdata
```

`Program Files` に書き込む権限がない場合は、`pokemon_battle_lens.py` または
`PokemonBattleLens.exe` の隣に `tessdata/` フォルダーを作成し、`.traineddata`
ファイルを入れてください。

日本語/韓国語 OCR プリセットでは、初期設定で英語 OCR を混ぜないようにしています。ポケモンのゲームフォントで誤った英語認識が混ざる問題を減らすためです。

## 実行

```powershell
python pokemon_battle_lens.py
```

EXE をビルドした場合は以下を実行します。

```powershell
PokemonBattleLens.exe
```

## 基本的な使い方

1. ポケモンのゲームまたはエミュレーターを起動します。
2. `python pokemon_battle_lens.py` を実行します。
3. `Settings` を開きます。
4. キャプチャ対象を選択します: モニターまたはゲーム/エミュレーターウィンドウ。
5. 世代とゲーム画面の言語を選択します。
6. `ROI Preview` を開きます。
7. 相手名、レベル、4 つの技が入るように ROI ボックスを調整します。
8. スキャンを開始します。

## OCR と ROI

OCR は、キャプチャ画像から文字を読み取る処理です。

ROI は、OCR に渡す画面上の長方形領域です。

ゲーム、エミュレーター、画面倍率、ウィンドウサイズ、UI レイアウトによって必要な ROI 座標は変わります。アプリは ROI と OCR 前処理設定を世代ごとに保存します。大きく調整する前に、設定スナップショットを保存しておくことをおすすめします。

## 設定スナップショット

OCR/ROI を大きく変更する前に、スナップショットボタンを使ってください。

- Save Snapshot
- Restore Snapshot

スナップショットファイルはローカル専用で、git には含まれません。

```text
config/settings_snapshot.json
```

## データファイル

同梱されている生成データ:

```text
data/pokemon_ko.json
data/pokemon_en.json
data/pokemon_ja.json
```

JSON データには以下が含まれます。

- ポケモンのローカライズ名
- タイプデータ
- 種族値
- 可能性のある特性
- スプライトパス
- 技のローカライズ名
- 技タイプ
- 技分類

データは以下のコマンドで再生成できます。

```powershell
python scripts/fetch_pokeapi_data.py
```

PokeAPI を使用するため、時間がかかる場合があります。

任意のローカルスプライトは以下のコマンドでダウンロードできます。

```powershell
python scripts/fetch_pokeapi_data.py --download-sprites
```

ダウンロードされたスプライトは `assets/sprites/` に保存され、git では無視されます。

## Windows EXE ビルド

PyInstaller をインストールします。

```powershell
pip install pyinstaller
```

ビルド:

```powershell
python -m PyInstaller --noconsole --onefile --name PokemonBattleLens --icon assets\app_icon.ico --add-data "data;data" --add-data "assets\app_icon.ico;assets" --add-data "assets\app_icon_v2.png;assets" pokemon_battle_lens.py
```

出力:

```text
dist/PokemonBattleLens.exe
```

注意:

- EXE でも、実行する PC に Tesseract OCR がインストールされている必要があります。
- ローカル設定は EXE の隣の `config/` フォルダーに保存されます。
- 生成された EXE やビルドフォルダーは git にコミットしないでください。
- ダウンロードしたポケモンスプライトは、元の権利を確認するまで EXE に含めたり再配布したりしないでください。

## リポジトリ構成

```text
pokemon_battle_lens.py        メインアプリ
requirements.txt              Python 依存関係
assets/                       アプリアイコン
assets/sprites/               任意のローカルスプライト、git 対象外
data/                         生成されたポケモン/技 JSON データ
config/roi_profiles.json      サンプル ROI プロファイル
config/ocr_aliases.json       任意の OCR 補正エイリアス
scripts/fetch_pokeapi_data.py データ生成スクリプト
LICENSE                       アプリのソースコードの MIT ライセンス
NOTICE.md                     サードパーティ通知と IP 注意事項
```

## 既知の制限

- OCR 品質は、エミュレーター倍率、ゲームフォント、背景、ROI 位置に大きく依存します。
- 隠れたウィンドウのキャプチャには可能な場合 Windows `PrintWindow` を使いますが、一部のハードウェアアクセラレーションを使うゲーム/エミュレーターでは対応できない場合があります。
- 特性効果は注意表示のみです。タイプ相性の計算を自動で変更するものではありません。
- 素早さ計算は、トレーナーの IV、EV、性格、持ち物、ランク補正などが完全には分からないため概算です。
- ダブルバトルはまだサポートしていません。

## 法的表記

このプロジェクトは非公式であり、Nintendo、Game Freak、Creatures、The Pokemon Company とは関係ありません。

ポケモン/技データは PokeAPI リソースから生成されています。ポケモンのスプライト画像はこのリポジトリには含まれていません。大きなパッケージとして再配布する前に、[NOTICE.md](NOTICE.md)、PokeAPI、元アセットのライセンスを確認してください。
