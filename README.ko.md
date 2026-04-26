# Pokemon Battle Lens

[English](README.md) | [日本語](README.ja.md)

Pokemon Battle Lens는 화면 캡처 기반 포켓몬 배틀 보조 프로그램입니다. 게임 화면을 OCR로 읽어서 상대 포켓몬과 내 기술 4개를 판독하고, 타입 상성, 기술 분류, 특성 주의 문구, 대략적인 스피드 예상치를 표시합니다.

이 프로젝트는 비공식 팬 제작 도구입니다. 포켓몬 이름과 기술 데이터는 PokeAPI 데이터를 기반으로 생성됩니다. 포켓몬 스프라이트 이미지는 이 저장소에 포함하지 않으며, 필요할 때 사용자가 로컬에서 선택적으로 받을 수 있습니다.

## 주요 기능

- 모니터 또는 선택한 게임/에뮬레이터 창 실시간 캡처
- 한국어, 영어, 일본어 게임 화면 OCR
- 한국어, 영어, 일본어 포켓몬/기술 JSON 데이터
- 세대별 타입 상성 차이를 위한 세대 선택
- 색상으로 구분되는 기술별 타입 효과 표시
- 기술 분류 표시: 물리 / 특수 / 변화
- 부유처럼 타입 무효 가능성이 있는 특성 주의 문구
- 상대 포켓몬의 대략적인 스피드 범위 계산
- 항상 위에 표시되는 보조 창
- 에뮬레이터/창 배치에 맞게 수정 가능한 ROI 영역
- 세대별 ROI/OCR 설정 저장
- 테스트용 설정 스냅샷 저장/복원
- Windows EXE 빌드 지원

## 현재 범위

현재 앱은 싱글 배틀을 기준으로 만들어져 있습니다.

더블 배틀은 UI 배치와 OCR 영역이 달라서 아직 활성화하지 않았습니다. 제대로 지원하려면 별도 배틀 모드와 별도 ROI 프로필로 분리하는 것이 맞습니다.

## 요구 사항

### Python

Python 3.10 이상을 권장합니다. 현재 개발 환경은 Python 3.12입니다.

Python 패키지 설치:

```powershell
pip install -r requirements.txt
```

### Tesseract OCR

`pytesseract`는 Python 래퍼일 뿐입니다. 실제 OCR 엔진인 Tesseract OCR도 시스템에 설치되어 있어야 합니다.

Windows 설치 예시:

```powershell
winget install --id UB-Mannheim.TesseractOCR --source winget
```

앱은 아래 위치에서 Tesseract를 찾습니다.

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
C:\Program Files (x86)\Tesseract-OCR\tesseract.exe
```

### OCR 언어 데이터

필요한 언어팩을 Tesseract의 `tessdata` 폴더에 넣어야 합니다.

- `eng.traineddata`: 영어
- `kor.traineddata`: 한국어
- `jpn.traineddata`: 일본어

일반적인 Windows 경로:

```text
C:\Program Files\Tesseract-OCR\tessdata
```

한국어/일본어 OCR 프리셋은 기본적으로 영어 OCR을 섞지 않습니다. 포켓몬 게임 폰트에서 잘못된 영어 판독이 섞이는 문제를 줄이기 위한 설정입니다.

## 실행

```powershell
python pokemon_battle_lens.py
```

EXE를 빌드했다면 아래 파일을 실행합니다.

```powershell
PokemonBattleLens.exe
```

## 기본 사용법

1. 포켓몬 게임 또는 에뮬레이터를 실행합니다.
2. `python pokemon_battle_lens.py`를 실행합니다.
3. `설정`을 엽니다.
4. 캡처 대상을 선택합니다: 모니터 또는 게임/에뮬레이터 창.
5. 세대와 게임 화면 언어를 선택합니다.
6. `ROI 미리보기`를 엽니다.
7. 상대 이름, 레벨, 기술 4개가 잘 들어오도록 ROI 박스를 조정합니다.
8. 스캔을 시작합니다.

## OCR과 ROI

OCR은 캡처 이미지에서 글자를 읽는 기능입니다.

ROI는 OCR에 넘길 화면 사각형 영역입니다.

게임, 에뮬레이터, 화면 배율, 창 크기, UI 배치에 따라 필요한 ROI 좌표가 달라집니다. 앱은 ROI와 OCR 전처리 설정을 세대별로 저장합니다. 크게 실험하기 전에는 설정 스냅샷을 저장해 두는 것을 권장합니다.

## 설정 스냅샷

OCR/ROI 설정을 많이 바꾸기 전에는 스냅샷 버튼을 사용하세요.

- 현재 설정 스냅샷
- 스냅샷 복원

스냅샷 파일은 로컬 전용이며 git에는 올라가지 않습니다.

```text
config/settings_snapshot.json
```

## 데이터 파일

포함된 생성 데이터:

```text
data/pokemon_ko.json
data/pokemon_en.json
data/pokemon_ja.json
```

JSON 데이터에는 아래 정보가 포함됩니다.

- 포켓몬 현지화 이름
- 타입 데이터
- 종족값
- 가능한 특성
- 스프라이트 경로
- 기술 현지화 이름
- 기술 타입
- 기술 분류

데이터는 아래 명령으로 다시 생성할 수 있습니다.

```powershell
python scripts/fetch_pokeapi_data.py
```

PokeAPI를 사용하므로 시간이 걸릴 수 있습니다.

선택적 로컬 스프라이트는 아래 명령으로 받을 수 있습니다.

```powershell
python scripts/fetch_pokeapi_data.py --download-sprites
```

받은 스프라이트는 `assets/sprites/`에 저장되며 git에는 올라가지 않습니다.

## Windows EXE 빌드

PyInstaller 설치:

```powershell
pip install pyinstaller
```

빌드:

```powershell
python -m PyInstaller --noconsole --onefile --name PokemonBattleLens --icon assets\app_icon.ico --add-data "data;data" --add-data "assets\app_icon.ico;assets" --add-data "assets\app_icon_v2.png;assets" pokemon_battle_lens.py
```

결과물:

```text
dist/PokemonBattleLens.exe
```

주의:

- EXE도 실행 PC에 Tesseract OCR이 설치되어 있어야 합니다.
- 로컬 설정은 EXE 옆의 `config/` 폴더에 저장됩니다.
- 생성된 EXE와 빌드 폴더는 git에 커밋하지 마세요.
- 다운로드한 포켓몬 스프라이트는 원본 권리를 확인하기 전에는 EXE에 포함하거나 재배포하지 마세요.

## 저장소 구조

```text
pokemon_battle_lens.py        메인 앱
requirements.txt              Python 의존성
assets/                       앱 아이콘
assets/sprites/               선택적 로컬 스프라이트, git 제외
data/                         생성된 포켓몬/기술 JSON 데이터
config/roi_profiles.json      예시 ROI 프로필
config/ocr_aliases.json       선택적 OCR 보정 별칭
scripts/fetch_pokeapi_data.py 데이터 생성 스크립트
LICENSE                       앱 소스코드 MIT 라이선스
NOTICE.md                     서드파티 고지와 IP 주의사항
```

## 알려진 한계

- OCR 품질은 에뮬레이터 배율, 게임 폰트, 배경, ROI 위치에 크게 영향을 받습니다.
- 다른 창에 가려진 창 캡처는 가능한 경우 Windows `PrintWindow`를 사용하지만, 일부 하드웨어 가속 게임/에뮬레이터에서는 지원되지 않을 수 있습니다.
- 특성 효과는 주의 문구로만 표시됩니다. 타입 효과 계산을 자동으로 바꾸지는 않습니다.
- 스피드 계산은 트레이너의 IV, EV, 성격, 아이템, 랭크 변화 등을 정확히 알 수 없으므로 근사치입니다.
- 더블 배틀은 아직 지원하지 않습니다.

## 법적 고지

이 프로젝트는 비공식 도구이며 Nintendo, Game Freak, Creatures, The Pokemon Company와 관련이 없습니다.

포켓몬/기술 데이터는 PokeAPI 리소스를 기반으로 생성됩니다. 포켓몬 스프라이트 이미지는 이 저장소에 포함하지 않습니다. 큰 패키지 형태로 재배포하기 전에는 [NOTICE.md](NOTICE.md), PokeAPI, 원본 에셋의 라이선스를 확인하세요.
