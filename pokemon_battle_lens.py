"""
Pokemon Battle Lens

Screen-capture based Pokemon battle helper with OCR and type-effectiveness UI.

Install optional runtime packages:
    pip install mss opencv-python pillow pytesseract pygetwindow

Tesseract OCR engine is also required for OCR:
    Windows: https://github.com/UB-Mannheim/tesseract/wiki
    macOS:   brew install tesseract
    Linux:   sudo apt install tesseract-ocr

This is intentionally a single-file app. Extend the embedded DATA dictionary,
or export it to JSON with the "Export JSON" button and load the modified JSON
back with "Load JSON".
"""

from __future__ import annotations

import concurrent.futures
import ctypes
import ctypes.wintypes
import difflib
import json
import math
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    import mss  # type: ignore
except Exception:
    mss = None

try:
    import cv2  # type: ignore
except Exception:
    cv2 = None

try:
    import numpy as np  # type: ignore
except Exception:
    np = None

try:
    from PIL import Image  # type: ignore
    from PIL import ImageDraw  # type: ignore
    from PIL import ImageTk  # type: ignore
except Exception:
    Image = None
    ImageDraw = None
    ImageTk = None

try:
    import pytesseract  # type: ignore
except Exception:
    pytesseract = None

try:
    import pygetwindow as gw  # type: ignore
except Exception:
    gw = None


APP_NAME = "Pokemon Battle Lens"
APP_VERSION = "v1.1.0"
SCAN_INTERVAL_MS = 900
PREFERRED_WINDOW_KEYWORDS = ("melonds", "azahar")
# PyInstaller one-file builds extract bundled data to sys._MEIPASS.
# User settings must stay beside the EXE so they persist after restart.
APP_ROOT = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
BASE_DIR = getattr(sys, "_MEIPASS", APP_ROOT)
DATA_DIR = os.path.join(BASE_DIR, "data")
USER_SETTINGS_PATH = os.path.join(APP_ROOT, "config", "user_settings.json")
SETTINGS_SNAPSHOT_PATH = os.path.join(APP_ROOT, "config", "settings_snapshot.json")
OCR_ALIASES_PATH = os.path.join(APP_ROOT, "config", "ocr_aliases.json")
VISUAL_SAMPLES_PATH = os.path.join(APP_ROOT, "config", "visual_samples.json")
LOCAL_TESSDATA_DIR = os.path.join(APP_ROOT, "tessdata")
BUNDLED_TESSDATA_DIR = os.path.join(BASE_DIR, "tessdata")
SYSTEM_TESSDATA_DIRS = (
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Tesseract-OCR", "tessdata"),
    os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Tesseract-OCR", "tessdata"),
)
TESSDATA_DIR = LOCAL_TESSDATA_DIR
TESSERACT_CANDIDATES = [
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Tesseract-OCR", "tesseract.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Tesseract-OCR", "tesseract.exe"),
]
OCR_FILTER_KEYS = ("threshold", "white_min_value", "white_max_saturation", "white_channel_delta")

UI = {
    "bg": "#1c1e21",
    "bg2": "#24282c",
    "panel": "#292e33",
    "panel2": "#262a2f",
    "field": "#33383e",
    "line": "#454b53",
    "text": "#f1f3f5",
    "muted": "#b6bdc5",
    "blue": "#285f96",
    "blue2": "#1f4f7e",
    "green": "#35d064",
    "yellow": "#ffd02e",
    "red": "#ff625f",
    "orange": "#ff8a28",
}

TYPE_COLORS = {
    "Normal": "#8b9096",
    "Fire": "#f47a2a",
    "Water": "#3f86d8",
    "Electric": "#f5c72b",
    "Grass": "#54b957",
    "Ice": "#64c7d8",
    "Fighting": "#c95642",
    "Poison": "#9a5bc8",
    "Ground": "#c5944a",
    "Flying": "#789bd8",
    "Psychic": "#ea5f8e",
    "Bug": "#8aaa35",
    "Rock": "#aa9553",
    "Ghost": "#6f61ad",
    "Dragon": "#5d73d6",
    "Dark": "#5b5360",
    "Steel": "#7e9aa7",
    "Fairy": "#e279b5",
    "?": UI["field"],
}

TYPES = [
    "Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting",
    "Poison", "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost",
    "Dragon", "Dark", "Steel", "Fairy",
]

TYPE_KO = {
    "Normal": "노말",
    "Fire": "불꽃",
    "Water": "물",
    "Electric": "전기",
    "Grass": "풀",
    "Ice": "얼음",
    "Fighting": "격투",
    "Poison": "독",
    "Ground": "땅",
    "Flying": "비행",
    "Psychic": "에스퍼",
    "Bug": "벌레",
    "Rock": "바위",
    "Ghost": "고스트",
    "Dragon": "드래곤",
    "Dark": "악",
    "Steel": "강철",
    "Fairy": "페어리",
}

CATEGORY_KO = {
    "Physical": "물리",
    "Special": "특수",
    "Status": "변화",
    "Unknown": "분류 불명",
}

CATEGORY_LABELS = {
    "ko": CATEGORY_KO,
    "en": {
        "Physical": "Physical",
        "Special": "Special",
        "Status": "Status",
        "Unknown": "Unknown category",
    },
    "ja": {
        "Physical": "物理",
        "Special": "特殊",
        "Status": "変化",
        "Unknown": "分類不明",
    },
}

SPEED_PROFILE_LABELS = {
    "npc_basic": "NPC 기본",
    "npc_trained": "NPC 강화",
    "full_range": "전체 가능 범위",
}

SPEED_PROFILE_LABELS_BY_LANG = {
    "ko": SPEED_PROFILE_LABELS,
    "en": {
        "npc_basic": "NPC Normal",
        "npc_trained": "NPC Trained",
        "full_range": "Full Range",
    },
    "ja": {
        "npc_basic": "NPC 通常",
        "npc_trained": "NPC 強化",
        "full_range": "全範囲",
    },
}

SPEED_PROFILE_BY_LABEL = {
    label: key
    for labels in SPEED_PROFILE_LABELS_BY_LANG.values()
    for key, label in labels.items()
}


def speed_profile_label(profile_key: str, lang: str) -> str:
    labels = SPEED_PROFILE_LABELS_BY_LANG.get(lang, SPEED_PROFILE_LABELS_BY_LANG["ko"])
    return labels.get(profile_key, labels["npc_basic"])


def speed_profile_values(lang: str) -> List[str]:
    return list(SPEED_PROFILE_LABELS_BY_LANG.get(lang, SPEED_PROFILE_LABELS_BY_LANG["ko"]).values())


def speed_profile_key_from_label(label: str) -> str:
    return SPEED_PROFILE_BY_LABEL.get(label, "npc_basic")

SPEED_PROFILES = {
    # Typical in-game trainers: no speed EV investment, neutral nature, imperfect to perfect IV.
    "npc_basic": {"min_iv": 15, "max_iv": 31, "min_ev": 0, "max_ev": 0, "min_nature": 1.0, "max_nature": 1.0},
    # Boss/rival/post-game style approximation: some speed investment, neutral to positive nature.
    "npc_trained": {"min_iv": 20, "max_iv": 31, "min_ev": 0, "max_ev": 84, "min_nature": 1.0, "max_nature": 1.1},
    # Conservative full legal range except temporary modifiers/items.
    "full_range": {"min_iv": 0, "max_iv": 31, "min_ev": 0, "max_ev": 252, "min_nature": 0.9, "max_nature": 1.1},
}

OCR_PRESETS = {
    "한국어 게임 화면": "kor",
    "영어 게임 화면": "eng",
    "일본어 게임 화면": "jpn",
}

OCR_LABEL_BY_CODE = {code: label for label, code in OCR_PRESETS.items()}

SYSTEM_LANGUAGES = {
    "ko": "한국어",
    "en": "English",
    "ja": "日本語",
}

UI_TEXT = {
    "ko": {
        "subtitle": "실시간 타입 상성 오버레이",
        "always_top": "항상 위",
        "settings": "설정",
        "scan_start": "스캔 시작",
        "scan_stop": "스캔 중지",
        "idle": "대기 중",
        "scanning": "스캔 중",
        "manual_title": "수동 입력 / OCR 보정",
        "opponent": "상대 포켓몬",
        "apply_search": "검색 적용",
        "opponent_lv": "상대 Lv",
        "my_speed": "내 스피드",
        "move": "기술",
        "effects": "효과 표시",
        "unknown": "판별 불가",
        "log": "로그",
        "settings_title": "Pokemon Battle Lens 설정",
        "general": "일반",
        "system_language": "시스템 언어",
        "generation": "세대",
        "speed_profile": "스피드 기준",
        "scan_interval": "캡처 주기(ms)",
        "save_gen_profile": "\ud604\uc7ac \uac8c\uc784 ROI/OCR \uc800\uc7a5",
        "load_gen_profile": "\ud604\uc7ac \uac8c\uc784 \ubd88\ub7ec\uc624\uae30",
        "capture": "캡처",
        "capture_help": "모니터 또는 실행 중인 게임/에뮬레이터 창을 선택하세요.",
        "capture_target": "캡처 대상",
        "refresh_list": "목록 새로고침",
        "roi_preview": "ROI 미리보기",
        "roi_auto": "ROI 자동 보정",
        "data_language": "데이터 / 언어",
        "data_help": "데이터 JSON은 포켓몬/기술 이름을 맞추는 기준입니다. 게임 언어와 같은 데이터를 선택하세요.",
        "data_json": "데이터 JSON",
        "apply_language": "언어 적용",
        "game_language": "게임 언어",
        "apply": "적용",
        "white_brightness": "흰 글씨 밝기",
        "sat_limit": "채도 상한",
        "rgb_delta": "RGB 차이 허용",
        "base_threshold": "기본 threshold",
        "preprocess_preview": "전처리 미리보기",
        "roi_coords": "ROI 좌표",
        "roi_help": "ROI는 OCR이 읽을 화면 사각형 영역입니다. x/y는 왼쪽 위 좌표, w/h는 너비와 높이입니다.",
        "area": "영역",
        "apply_roi": "ROI 적용",
        "load_json": "JSON 불러오기",
        "export_data": "데이터 Export",
        "install_help": "설치 안내",
        "snapshot_save": "현재 설정 스냅샷",
        "snapshot_restore": "스냅샷 복원",
        "footer_generation": "현재 세대",
        "footer_data": "데이터",
        "footer_ocr": "OCR",
        "type_unknown": "타입 불명",
        "speed_unknown": "스피드: 상대 포켓몬을 선택하면 표시",
        "warning": "주의",
    },
    "en": {
        "subtitle": "Realtime type-effectiveness overlay",
        "always_top": "Always on top",
        "settings": "Settings",
        "scan_start": "Start Scan",
        "scan_stop": "Stop Scan",
        "idle": "Idle",
        "scanning": "Scanning",
        "manual_title": "Manual Input / OCR Correction",
        "opponent": "Opponent Pokemon",
        "apply_search": "Apply Search",
        "opponent_lv": "Opponent Lv",
        "my_speed": "My Speed",
        "move": "Move",
        "effects": "Effectiveness",
        "unknown": "Unknown",
        "log": "Log",
        "settings_title": "Pokemon Battle Lens Settings",
        "general": "General",
        "system_language": "System Language",
        "generation": "Generation",
        "game_profile": "Game/UI Profile",
        "speed_profile": "Speed Profile",
        "scan_interval": "Capture Interval (ms)",
        "save_gen_profile": "Save Game ROI/OCR",
        "load_gen_profile": "Load Current Game",
        "capture": "Capture",
        "capture_help": "Select a monitor or running game/emulator window.",
        "capture_target": "Capture Target",
        "refresh_list": "Refresh List",
        "roi_preview": "ROI Preview",
        "roi_auto": "Auto Calibrate ROI",
        "data_language": "Data / Language",
        "data_help": "The data JSON is used to match Pokemon and move names. Select data matching the game language.",
        "data_json": "Data JSON",
        "apply_language": "Apply Language",
        "game_language": "Game Language",
        "apply": "Apply",
        "white_brightness": "White Min Value",
        "sat_limit": "Saturation Max",
        "rgb_delta": "RGB Delta",
        "base_threshold": "Base Threshold",
        "preprocess_preview": "Preprocess Preview",
        "roi_coords": "ROI Coordinates",
        "roi_help": "ROI is the screen rectangle OCR reads. x/y are top-left, w/h are width and height.",
        "area": "Area",
        "apply_roi": "Apply ROI",
        "load_json": "Load JSON",
        "export_data": "Export Data",
        "install_help": "Install Help",
        "snapshot_save": "Save Snapshot",
        "snapshot_restore": "Restore Snapshot",
        "footer_generation": "Generation",
        "footer_data": "Data",
        "footer_ocr": "OCR",
        "type_unknown": "type unknown",
        "speed_unknown": "Speed: select an opponent Pokemon",
        "warning": "Warning",
    },
    "ja": {
        "subtitle": "リアルタイム タイプ相性オーバーレイ",
        "always_top": "常に前面",
        "settings": "設定",
        "scan_start": "スキャン開始",
        "scan_stop": "スキャン停止",
        "idle": "待機中",
        "scanning": "スキャン中",
        "manual_title": "手動入力 / OCR補正",
        "opponent": "相手ポケモン",
        "apply_search": "検索を適用",
        "opponent_lv": "相手 Lv",
        "my_speed": "自分の素早さ",
        "move": "技",
        "effects": "効果表示",
        "unknown": "判定不可",
        "log": "ログ",
        "settings_title": "Pokemon Battle Lens 設定",
        "general": "一般",
        "system_language": "システム言語",
        "generation": "世代",
        "speed_profile": "素早さ基準",
        "scan_interval": "キャプチャ間隔(ms)",
        "save_gen_profile": "\u73fe\u5728\u306e\u30b2\u30fc\u30e0ROI/OCR\u4fdd\u5b58",
        "load_gen_profile": "\u73fe\u5728\u306e\u30b2\u30fc\u30e0\u8aad\u307f\u8fbc\u307f",
        "capture": "キャプチャ",
        "capture_help": "モニターまたは実行中のゲーム/エミュレーターを選択してください。",
        "capture_target": "キャプチャ対象",
        "refresh_list": "一覧更新",
        "roi_preview": "ROIプレビュー",
        "roi_auto": "ROI自動補正",
        "data_language": "データ / 言語",
        "data_help": "データJSONはポケモン/技名の照合基準です。ゲーム言語と同じデータを選択してください。",
        "data_json": "データJSON",
        "apply_language": "言語を適用",
        "game_language": "ゲーム言語",
        "apply": "適用",
        "white_brightness": "白文字の明度",
        "sat_limit": "彩度上限",
        "rgb_delta": "RGB差分許容",
        "base_threshold": "基本しきい値",
        "preprocess_preview": "前処理プレビュー",
        "roi_coords": "ROI座標",
        "roi_help": "ROIはOCRが読む画面領域です。x/yは左上座標、w/hは幅と高さです。",
        "area": "領域",
        "apply_roi": "ROI適用",
        "load_json": "JSON読込",
        "export_data": "データ出力",
        "install_help": "インストール案内",
        "snapshot_save": "設定スナップショット保存",
        "snapshot_restore": "スナップショット復元",
        "footer_generation": "現在世代",
        "footer_data": "データ",
        "footer_ocr": "OCR",
        "type_unknown": "タイプ不明",
        "speed_unknown": "素早さ: 相手ポケモン選択で表示",
        "warning": "注意",
    },
}

DEFAULT_OCR_ALIASES = {
    "pokemon": {},
    "moves": {},
}

ABILITY_WARNINGS = {
    "levitate": "땅 타입 기술은 실제 전투에서 무효일 수 있습니다.",
    "earth-eater": "땅 타입 기술은 실제 전투에서 무효/회복이 될 수 있습니다.",
    "water-absorb": "물 타입 기술은 실제 전투에서 무효/회복이 될 수 있습니다.",
    "dry-skin": "물 타입 기술은 실제 전투에서 회복이 될 수 있습니다.",
    "storm-drain": "물 타입 기술은 실제 전투에서 무효가 될 수 있습니다.",
    "volt-absorb": "전기 타입 기술은 실제 전투에서 무효/회복이 될 수 있습니다.",
    "lightning-rod": "전기 타입 기술은 실제 전투에서 무효가 될 수 있습니다.",
    "motor-drive": "전기 타입 기술은 실제 전투에서 무효가 될 수 있습니다.",
    "flash-fire": "불꽃 타입 기술은 실제 전투에서 무효가 될 수 있습니다.",
    "sap-sipper": "풀 타입 기술은 실제 전투에서 무효가 될 수 있습니다.",
    "well-baked-body": "불꽃 타입 기술은 실제 전투에서 무효가 될 수 있습니다.",
    "wind-rider": "바람 계열 기술은 실제 전투에서 무효가 될 수 있습니다.",
    "soundproof": "소리 계열 기술은 실제 전투에서 무효가 될 수 있습니다.",
    "bulletproof": "탄/폭탄 계열 기술은 실제 전투에서 무효가 될 수 있습니다.",
}


def neutral_chart() -> Dict[str, Dict[str, float]]:
    return {attack: {defense: 1.0 for defense in TYPES} for attack in TYPES}


def set_effect(chart: Dict[str, Dict[str, float]], attack: str, defenses: Iterable[str], value: float) -> None:
    for defense in defenses:
        chart.setdefault(attack, {})[defense] = value


def make_gen2_to_5_chart() -> Dict[str, Dict[str, float]]:
    chart = neutral_chart()
    set_effect(chart, "Normal", ["Rock", "Steel"], 0.5)
    set_effect(chart, "Normal", ["Ghost"], 0.0)
    set_effect(chart, "Fire", ["Fire", "Water", "Rock", "Dragon"], 0.5)
    set_effect(chart, "Fire", ["Grass", "Ice", "Bug", "Steel"], 2.0)
    set_effect(chart, "Water", ["Water", "Grass", "Dragon"], 0.5)
    set_effect(chart, "Water", ["Fire", "Ground", "Rock"], 2.0)
    set_effect(chart, "Electric", ["Electric", "Grass", "Dragon"], 0.5)
    set_effect(chart, "Electric", ["Water", "Flying"], 2.0)
    set_effect(chart, "Electric", ["Ground"], 0.0)
    set_effect(chart, "Grass", ["Fire", "Grass", "Poison", "Flying", "Bug", "Dragon", "Steel"], 0.5)
    set_effect(chart, "Grass", ["Water", "Ground", "Rock"], 2.0)
    set_effect(chart, "Ice", ["Fire", "Water", "Ice", "Steel"], 0.5)
    set_effect(chart, "Ice", ["Grass", "Ground", "Flying", "Dragon"], 2.0)
    set_effect(chart, "Fighting", ["Poison", "Flying", "Psychic", "Bug"], 0.5)
    set_effect(chart, "Fighting", ["Normal", "Ice", "Rock", "Dark", "Steel"], 2.0)
    set_effect(chart, "Fighting", ["Ghost"], 0.0)
    set_effect(chart, "Poison", ["Poison", "Ground", "Rock", "Ghost"], 0.5)
    set_effect(chart, "Poison", ["Grass"], 2.0)
    set_effect(chart, "Poison", ["Steel"], 0.0)
    set_effect(chart, "Ground", ["Grass", "Bug"], 0.5)
    set_effect(chart, "Ground", ["Fire", "Electric", "Poison", "Rock", "Steel"], 2.0)
    set_effect(chart, "Ground", ["Flying"], 0.0)
    set_effect(chart, "Flying", ["Electric", "Rock", "Steel"], 0.5)
    set_effect(chart, "Flying", ["Grass", "Fighting", "Bug"], 2.0)
    set_effect(chart, "Psychic", ["Psychic", "Steel"], 0.5)
    set_effect(chart, "Psychic", ["Fighting", "Poison"], 2.0)
    set_effect(chart, "Psychic", ["Dark"], 0.0)
    set_effect(chart, "Bug", ["Fire", "Fighting", "Poison", "Flying", "Ghost", "Steel"], 0.5)
    set_effect(chart, "Bug", ["Grass", "Psychic", "Dark"], 2.0)
    set_effect(chart, "Rock", ["Fighting", "Ground", "Steel"], 0.5)
    set_effect(chart, "Rock", ["Fire", "Ice", "Flying", "Bug"], 2.0)
    set_effect(chart, "Ghost", ["Dark", "Steel"], 0.5)
    set_effect(chart, "Ghost", ["Psychic", "Ghost"], 2.0)
    set_effect(chart, "Ghost", ["Normal"], 0.0)
    set_effect(chart, "Dragon", ["Steel"], 0.5)
    set_effect(chart, "Dragon", ["Dragon"], 2.0)
    set_effect(chart, "Dark", ["Fighting", "Dark", "Steel"], 0.5)
    set_effect(chart, "Dark", ["Psychic", "Ghost"], 2.0)
    set_effect(chart, "Steel", ["Fire", "Water", "Electric", "Steel"], 0.5)
    set_effect(chart, "Steel", ["Ice", "Rock"], 2.0)
    return chart


def make_gen6_plus_chart() -> Dict[str, Dict[str, float]]:
    chart = make_gen2_to_5_chart()
    set_effect(chart, "Fire", ["Fire", "Water", "Rock", "Dragon"], 0.5)
    set_effect(chart, "Fire", ["Grass", "Ice", "Bug", "Steel"], 2.0)
    set_effect(chart, "Fighting", ["Poison", "Flying", "Psychic", "Bug", "Fairy"], 0.5)
    set_effect(chart, "Poison", ["Grass", "Fairy"], 2.0)
    set_effect(chart, "Bug", ["Fire", "Fighting", "Poison", "Flying", "Ghost", "Steel", "Fairy"], 0.5)
    set_effect(chart, "Ghost", ["Dark"], 0.5)
    set_effect(chart, "Ghost", ["Steel"], 1.0)
    set_effect(chart, "Dragon", ["Steel"], 0.5)
    set_effect(chart, "Dragon", ["Fairy"], 0.0)
    set_effect(chart, "Dark", ["Fighting", "Dark", "Fairy"], 0.5)
    set_effect(chart, "Dark", ["Steel"], 1.0)
    set_effect(chart, "Steel", ["Fire", "Water", "Electric", "Steel"], 0.5)
    set_effect(chart, "Steel", ["Ice", "Rock", "Fairy"], 2.0)
    set_effect(chart, "Fairy", ["Fire", "Poison", "Steel"], 0.5)
    set_effect(chart, "Fairy", ["Fighting", "Dragon", "Dark"], 2.0)
    return chart


def make_gen1_chart() -> Dict[str, Dict[str, float]]:
    chart = make_gen2_to_5_chart()
    for attack in chart:
        chart[attack]["Dark"] = 1.0
        chart[attack]["Steel"] = 1.0
        chart[attack]["Fairy"] = 1.0
    for attack in ["Dark", "Steel", "Fairy"]:
        chart[attack] = {defense: 1.0 for defense in TYPES}
    set_effect(chart, "Normal", ["Rock"], 0.5)
    set_effect(chart, "Fire", ["Fire", "Water", "Rock", "Dragon"], 0.5)
    set_effect(chart, "Fire", ["Grass", "Ice", "Bug"], 2.0)
    set_effect(chart, "Ice", ["Water", "Ice"], 0.5)
    set_effect(chart, "Poison", ["Bug", "Grass"], 2.0)
    set_effect(chart, "Bug", ["Poison", "Grass", "Psychic"], 2.0)
    set_effect(chart, "Ghost", ["Psychic"], 0.0)  # Gen 1 game behavior.
    set_effect(chart, "Ghost", ["Ghost"], 2.0)
    return chart


DATA: Dict[str, Any] = {
    "type_charts": {
        "1": make_gen1_chart(),
        "2": make_gen2_to_5_chart(),
        "3": make_gen2_to_5_chart(),
        "4": make_gen2_to_5_chart(),
        "5": make_gen2_to_5_chart(),
        "6": make_gen6_plus_chart(),
        "7": make_gen6_plus_chart(),
        "8": make_gen6_plus_chart(),
        "9": make_gen6_plus_chart(),
    },
    "pokemon_types": {
        # Extend freely. Keys are normalized internally, so English/Korean names can coexist.
        "피카츄": {"default": ["Electric"]},
        "라이츄": {"default": ["Electric"]},
        "리자몽": {"default": ["Fire", "Flying"]},
        "이상해꽃": {"default": ["Grass", "Poison"]},
        "거북왕": {"default": ["Water"]},
        "뮤츠": {"default": ["Psychic"]},
        "팬텀": {"default": ["Ghost", "Poison"]},
        "갸라도스": {"default": ["Water", "Flying"]},
        "망나뇽": {"default": ["Dragon", "Flying"]},
        "마기라스": {"default": ["Rock", "Dark"]},
        "핫삼": {"default": ["Bug", "Steel"]},
        "가디안": {"default": ["Psychic"], "6": ["Psychic", "Fairy"]},
        "입치트": {"default": ["Steel"], "6": ["Steel", "Fairy"]},
        "토게키스": {"default": ["Normal", "Flying"], "6": ["Fairy", "Flying"]},
        "한카리아스": {"default": ["Dragon", "Ground"]},
        "루카리오": {"default": ["Fighting", "Steel"]},
        "로토무": {"default": ["Electric", "Ghost"]},
        "개굴닌자": {"default": ["Water", "Dark"]},
        "따라큐": {"default": ["Ghost", "Fairy"]},
        "드래펄트": {"default": ["Dragon", "Ghost"]},
        "마스카나": {"default": ["Grass", "Dark"]},
        "라우드본": {"default": ["Fire", "Ghost"]},
        "웨이니발": {"default": ["Water", "Fighting"]},
        "Charizard": {"default": ["Fire", "Flying"]},
        "Venusaur": {"default": ["Grass", "Poison"]},
        "Blastoise": {"default": ["Water"]},
        "Pikachu": {"default": ["Electric"]},
        "Mewtwo": {"default": ["Psychic"]},
        "Gengar": {"default": ["Ghost", "Poison"]},
        "Gyarados": {"default": ["Water", "Flying"]},
        "Dragonite": {"default": ["Dragon", "Flying"]},
        "Tyranitar": {"default": ["Rock", "Dark"]},
        "Scizor": {"default": ["Bug", "Steel"]},
        "Gardevoir": {"default": ["Psychic"], "6": ["Psychic", "Fairy"]},
        "Mawile": {"default": ["Steel"], "6": ["Steel", "Fairy"]},
        "Togekiss": {"default": ["Normal", "Flying"], "6": ["Fairy", "Flying"]},
        "Garchomp": {"default": ["Dragon", "Ground"]},
        "Lucario": {"default": ["Fighting", "Steel"]},
        "Rotom": {"default": ["Electric", "Ghost"]},
        "Greninja": {"default": ["Water", "Dark"]},
        "Mimikyu": {"default": ["Ghost", "Fairy"]},
        "Dragapult": {"default": ["Dragon", "Ghost"]},
        "Meowscarada": {"default": ["Grass", "Dark"]},
        "Skeledirge": {"default": ["Fire", "Ghost"]},
        "Quaquaval": {"default": ["Water", "Fighting"]},
    },
    "moves": {
        "몸통박치기": "Normal",
        "전광석화": "Normal",
        "화염방사": "Fire",
        "불대문자": "Fire",
        "하이드로펌프": "Water",
        "파도타기": "Water",
        "번개": "Electric",
        "10만볼트": "Electric",
        "솔라빔": "Grass",
        "기가드레인": "Grass",
        "얼음빔": "Ice",
        "냉동펀치": "Ice",
        "인파이트": "Fighting",
        "독찌르기": "Poison",
        "지진": "Ground",
        "공중날기": "Flying",
        "사이코키네시스": "Psychic",
        "시저크로스": "Bug",
        "스톤샤워": "Rock",
        "섀도볼": "Ghost",
        "용성군": "Dragon",
        "악의파동": "Dark",
        "아이언헤드": "Steel",
        "문포스": "Fairy",
        "Tackle": "Normal",
        "Quick Attack": "Normal",
        "Flamethrower": "Fire",
        "Fire Blast": "Fire",
        "Hydro Pump": "Water",
        "Surf": "Water",
        "Thunder": "Electric",
        "Thunderbolt": "Electric",
        "Solar Beam": "Grass",
        "Giga Drain": "Grass",
        "Ice Beam": "Ice",
        "Ice Punch": "Ice",
        "Close Combat": "Fighting",
        "Poison Jab": "Poison",
        "Earthquake": "Ground",
        "Fly": "Flying",
        "Psychic": "Psychic",
        "X-Scissor": "Bug",
        "Rock Slide": "Rock",
        "Shadow Ball": "Ghost",
        "Draco Meteor": "Dragon",
        "Dark Pulse": "Dark",
        "Iron Head": "Steel",
        "Moonblast": "Fairy",
    },
}

DEFAULT_SETTINGS = {
    "generation": 9,
    "game_profile": "gen9_sv",
    "capture": {"source": "monitor", "monitor_index": 1, "window_title": ""},
    "scan_interval_ms": SCAN_INTERVAL_MS,
    "speed_profile": "npc_basic",
    "ocr": {
        "lang": "kor",
        "psm": 6,
        "threshold": 150,
        "white_min_value": 140,
        "white_max_saturation": 105,
        "white_channel_delta": 85,
    },
    "roi": {
        "opponent_name": {"x": 980, "y": 70, "w": 280, "h": 80},
        "opponent_level_status": {"x": 1140, "y": 130, "w": 220, "h": 60},
        "move_1": {"x": 820, "y": 690, "w": 260, "h": 70},
        "move_2": {"x": 1090, "y": 690, "w": 260, "h": 70},
        "move_3": {"x": 820, "y": 765, "w": 260, "h": 70},
        "move_4": {"x": 1090, "y": 765, "w": 260, "h": 70},
    },
}


GAME_UI_PROFILES: Tuple[Tuple[str, str, int], ...] = (
    ("gen1_rby", "Gen 1 - R/B/Y", 1),
    ("gen2_gsc", "Gen 2 - G/S/C", 2),
    ("gen3_rse", "Gen 3 - R/S/E", 3),
    ("gen3_frlg", "Gen 3 - FR/LG", 3),
    ("gen4_dppt", "Gen 4 - D/P/Pt", 4),
    ("gen4_hgss", "Gen 4 - HG/SS", 4),
    ("gen5_bw", "Gen 5 - B/W", 5),
    ("gen5_b2w2", "Gen 5 - B2/W2", 5),
    ("gen6_xy", "Gen 6 - X/Y", 6),
    ("gen6_oras", "Gen 6 - OR/AS", 6),
    ("gen7_sm", "Gen 7 - S/M", 7),
    ("gen7_usum", "Gen 7 - US/UM", 7),
    ("gen8_swsh", "Gen 8 - Sw/Sh", 8),
    ("gen8_bdsp", "Gen 8 - BD/SP", 8),
    ("gen8_pla", "Gen 8 - Legends: Arceus", 8),
    ("gen9_sv", "Gen 9 - S/V", 9),
)
GAME_UI_PROFILE_BY_KEY = {key: {"label": label, "generation": generation} for key, label, generation in GAME_UI_PROFILES}
GAME_UI_PROFILE_KEY_BY_LABEL = {label: key for key, label, _generation in GAME_UI_PROFILES}


def default_game_profile_for_generation(generation: int) -> str:
    for key, _label, profile_generation in GAME_UI_PROFILES:
        if profile_generation == generation:
            return key
    return "gen9_sv"


def game_profile_label(profile_key: str) -> str:
    return GAME_UI_PROFILE_BY_KEY.get(profile_key, GAME_UI_PROFILE_BY_KEY["gen9_sv"])["label"]


def game_profile_values() -> List[str]:
    return [label for _key, label, _generation in GAME_UI_PROFILES]


def game_profile_key_from_label(label: str) -> str:
    return GAME_UI_PROFILE_KEY_BY_LABEL.get(label, "gen9_sv")


def game_profile_generation(profile_key: str) -> int:
    return int(GAME_UI_PROFILE_BY_KEY.get(profile_key, GAME_UI_PROFILE_BY_KEY["gen9_sv"])["generation"])


@dataclass
class DetectionResult:
    opponent_text: str = ""
    level_status_text: str = ""
    moves_text: Tuple[str, str, str, str] = ("", "", "", "")
    opponent_match: Optional[str] = None
    opponent_candidates: Tuple[str, ...] = ()
    move_matches: Tuple[Optional[str], Optional[str], Optional[str], Optional[str]] = (None, None, None, None)
    timestamp: float = 0.0


@dataclass
class RoiCandidate:
    x: int
    y: int
    w: int
    h: int
    score: float
    kind: str = "unknown"


def normalize_name(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣ぁ-ゖァ-ヺー一-龯々]", "", text).lower()


def clean_ocr_text(text: str) -> str:
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -_:;|[](){}")


def clean_label_ocr_text(text: str, lang: str) -> str:
    """Keep only name-like characters for Pokemon/move OCR.

    Level OCR uses a separate numeric-only path. For labels, digits and
    punctuation create many false fuzzy matches on dot-font game screens.
    """
    text = clean_ocr_text(text)
    if "kor" in lang:
        text = re.sub(r"[^가-힣\s]", " ", text)
        text = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", text)
    elif "jpn" in lang or "jpn_vert" in lang:
        text = re.sub(r"[^ぁ-ゖァ-ヺー一-龯々\s]", " ", text)
        text = re.sub(r"(?<=[ぁ-ゖァ-ヺー一-龯々])\s+(?=[ぁ-ゖァ-ヺー一-龯々])", "", text)
    elif "eng" in lang:
        text = re.sub(r"[^A-Za-z\s]", " ", text)
    else:
        text = re.sub(r"[^A-Za-z가-힣ぁ-ゖァ-ヺー一-龯々\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def coerce_ocr_digits(text: str) -> str:
    table = str.maketrans({
        "O": "0", "o": "0", "D": "0", "Q": "0",
        "I": "1", "l": "1", "|": "1", "!": "1",
        "Z": "2", "z": "2",
        "S": "5", "s": "5",
        "G": "6",
        "B": "8",
        "g": "9", "q": "9",
    })
    return text.translate(table)


def normalize_ocr_lang(saved_lang: str, data: Dict[str, Any]) -> str:
    data_lang = str(data.get("ocr_lang", DEFAULT_SETTINGS["ocr"]["lang"]))
    if saved_lang == "kor+eng":
        return data_lang
    if saved_lang in OCR_LABEL_BY_CODE:
        return saved_lang
    return data_lang


def best_matches(query: str, choices: Iterable[str], limit: int = 5, cutoff: float = 0.35) -> List[str]:
    query_norm = normalize_name(query)
    if not query_norm:
        return []
    indexed = {normalize_name(choice): choice for choice in choices}
    direct = [choice for norm, choice in indexed.items() if query_norm in norm or norm in query_norm]
    fuzzy_norms = difflib.get_close_matches(query_norm, indexed.keys(), n=limit, cutoff=cutoff)
    merged = direct + [indexed[norm] for norm in fuzzy_norms]
    seen = set()
    return [x for x in merged if not (x in seen or seen.add(x))][:limit]


def decompose_hangul(char: str) -> Optional[Tuple[int, int, int]]:
    code = ord(char)
    if not 0xAC00 <= code <= 0xD7A3:
        return None
    syllable = code - 0xAC00
    initial = syllable // 588
    vowel = (syllable % 588) // 28
    final = syllable % 28
    return initial, vowel, final


def char_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    left_h = decompose_hangul(left)
    right_h = decompose_hangul(right)
    if left_h and right_h:
        score = 0.0
        if left_h[0] == right_h[0]:
            score += 0.40
        if left_h[1] == right_h[1]:
            score += 0.38
        if left_h[2] == right_h[2]:
            score += 0.22
        return score
    return 0.0


def hangul_aware_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    rows = len(left) + 1
    cols = len(right) + 1
    dp = [[0.0] * cols for _ in range(rows)]
    for i in range(1, rows):
        dp[i][0] = float(i)
    for j in range(1, cols):
        dp[0][j] = float(j)
    for i in range(1, rows):
        for j in range(1, cols):
            substitution_cost = 1.0 - char_similarity(left[i - 1], right[j - 1])
            dp[i][j] = min(
                dp[i - 1][j] + 1.0,
                dp[i][j - 1] + 1.0,
                dp[i - 1][j - 1] + substitution_cost,
            )
    max_len = max(len(left), len(right))
    return max(0.0, 1.0 - dp[-1][-1] / max_len)


def best_match_with_score(query: str, choices: Iterable[str], cutoff: float = 0.35) -> Tuple[Optional[str], float]:
    query_norm = normalize_name(query)
    if not query_norm:
        return None, 0.0
    best_choice = None
    best_score = 0.0
    for choice in choices:
        choice_norm = normalize_name(choice)
        if not choice_norm:
            continue
        ratio = max(
            difflib.SequenceMatcher(None, query_norm, choice_norm).ratio(),
            hangul_aware_similarity(query_norm, choice_norm),
        )
        if query_norm in choice_norm or choice_norm in query_norm:
            ratio = max(ratio, 0.82)
        if ratio > best_score:
            best_choice = choice
            best_score = ratio
    if best_score < cutoff:
        return None, best_score
    return best_choice, best_score


def best_alias_match(variants: Iterable[str], aliases: Dict[str, str], choices: Iterable[str]) -> Tuple[Optional[str], float]:
    valid_choices = set(choices)
    normalized_aliases = [(normalize_name(alias), target) for alias, target in aliases.items() if target in valid_choices]
    best_target = None
    best_score = 0.0
    for text in variants:
        norm = normalize_name(text)
        if not norm:
            continue
        for alias_norm, target in normalized_aliases:
            if not alias_norm:
                continue
            if norm == alias_norm:
                return target, 1.0
            if alias_norm in norm or norm in alias_norm:
                score = min(0.96, 0.78 + min(len(norm), len(alias_norm)) / max(len(norm), len(alias_norm)) * 0.18)
            else:
                score = difflib.SequenceMatcher(None, norm, alias_norm).ratio() * 0.92
            if score > best_score:
                best_target = target
                best_score = score
    if best_score >= 0.84:
        return best_target, best_score
    return None, best_score


def deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value))


def merge_language_pack(base_data: Dict[str, Any], pack: Dict[str, Any]) -> Dict[str, Any]:
    data = deep_copy(base_data)
    data.setdefault("pokemon_types", {}).update(pack.get("pokemon_types", {}))
    data.setdefault("moves", {}).update(pack.get("moves", {}))
    data["meta"] = pack.get("meta", {})
    data["ocr_lang"] = pack.get("ocr_lang", data.get("ocr_lang", "kor"))
    return data


def find_language_packs() -> Dict[str, str]:
    packs: Dict[str, str] = {}
    if not os.path.isdir(DATA_DIR):
        return packs
    for filename in sorted(os.listdir(DATA_DIR)):
        if filename.lower().endswith(".json"):
            path = os.path.join(DATA_DIR, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if "pokemon_types" not in payload and "moves" not in payload:
                    continue
                label = payload.get("meta", {}).get("label") or os.path.splitext(filename)[0]
                packs[label] = path
            except Exception:
                continue
    return packs


def load_pack_from_path(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_user_settings() -> Dict[str, Any]:
    if not os.path.exists(USER_SETTINGS_PATH):
        return {}
    try:
        with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_user_settings(settings: Dict[str, Any], language_label: str = "") -> None:
    try:
        os.makedirs(os.path.dirname(USER_SETTINGS_PATH), exist_ok=True)
        existing = load_user_settings()
        payload = {"settings": settings, "language_label": language_label}
        if "roi_by_source" in existing:
            payload["roi_by_source"] = existing["roi_by_source"]
        if "profiles_by_game" in existing:
            payload["profiles_by_game"] = existing["profiles_by_game"]
        if "profiles_by_generation" in existing:
            payload["profiles_by_generation"] = existing["profiles_by_generation"]
        with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def generation_profile_from_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    ocr = settings.get("ocr", {})
    return {
        "roi": deep_copy(settings.get("roi", {})),
        "ocr": {key: ocr.get(key, DEFAULT_SETTINGS["ocr"].get(key)) for key in OCR_FILTER_KEYS},
    }


def apply_generation_profile_to_settings(settings: Dict[str, Any], profile: Dict[str, Any]) -> None:
    if isinstance(profile.get("roi"), dict):
        settings["roi"] = deep_update(DEFAULT_SETTINGS["roi"], profile["roi"])
    if isinstance(profile.get("ocr"), dict):
        settings.setdefault("ocr", {})
        for key in OCR_FILTER_KEYS:
            if key in profile["ocr"]:
                settings["ocr"][key] = profile["ocr"][key]


def load_ocr_aliases() -> Dict[str, Dict[str, str]]:
    aliases = deep_copy(DEFAULT_OCR_ALIASES)
    if os.path.exists(OCR_ALIASES_PATH):
        try:
            with open(OCR_ALIASES_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            for category in ("pokemon", "moves"):
                if isinstance(payload.get(category), dict):
                    aliases.setdefault(category, {}).update({str(k): str(v) for k, v in payload[category].items()})
        except Exception:
            pass
    else:
        save_ocr_aliases(aliases)
    return aliases


def save_ocr_aliases(aliases: Dict[str, Dict[str, str]]) -> None:
    try:
        os.makedirs(os.path.dirname(OCR_ALIASES_PATH), exist_ok=True)
        with open(OCR_ALIASES_PATH, "w", encoding="utf-8") as f:
            json.dump(aliases, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_visual_samples() -> Dict[str, List[Dict[str, Any]]]:
    empty = {"pokemon": [], "moves": []}
    if not os.path.exists(VISUAL_SAMPLES_PATH):
        return empty
    try:
        with open(VISUAL_SAMPLES_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return {
            "pokemon": list(payload.get("pokemon", [])) if isinstance(payload.get("pokemon", []), list) else [],
            "moves": list(payload.get("moves", [])) if isinstance(payload.get("moves", []), list) else [],
        }
    except Exception:
        return empty


def save_visual_samples(samples: Dict[str, List[Dict[str, Any]]]) -> None:
    try:
        os.makedirs(os.path.dirname(VISUAL_SAMPLES_PATH), exist_ok=True)
        with open(VISUAL_SAMPLES_PATH, "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def deep_update(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    result = deep_copy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_update(result[key], value)
        else:
            result[key] = value
    return result


def configure_tesseract() -> Optional[str]:
    if pytesseract is None:
        return None
    for path in TESSERACT_CANDIDATES:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            tessdata_dir = find_tessdata_dir()
            if tessdata_dir:
                os.environ["TESSDATA_PREFIX"] = tessdata_dir
            return path
    return None


def tessdata_dirs() -> List[str]:
    seen = set()
    dirs: List[str] = []
    for path in (LOCAL_TESSDATA_DIR, BUNDLED_TESSDATA_DIR, *SYSTEM_TESSDATA_DIRS):
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized not in seen:
            seen.add(normalized)
            dirs.append(path)
    return dirs


def find_tessdata_dir() -> Optional[str]:
    for path in tessdata_dirs():
        if os.path.isdir(path) and any(name.endswith(".traineddata") for name in os.listdir(path)):
            return path
    return None


def available_tesseract_languages() -> set:
    languages = set()
    for path in tessdata_dirs():
        if not os.path.isdir(path):
            continue
        for name in os.listdir(path):
            if name.endswith(".traineddata"):
                languages.add(os.path.splitext(name)[0])
    return languages


def missing_tesseract_languages(lang: str) -> List[str]:
    available = available_tesseract_languages()
    requested = [part.strip() for part in lang.split("+") if part.strip()]
    return [part for part in requested if part not in available]


def get_generation_key(gen: int) -> str:
    return str(max(1, min(9, gen)))


def get_pokemon_types(name: str, gen: int, data: Dict[str, Any]) -> Optional[List[str]]:
    entry = data["pokemon_types"].get(name)
    if not entry:
        return None
    for key in range(gen, 0, -1):
        if str(key) in entry:
            return list(entry[str(key)])
    return list(entry.get("default", []))


def get_pokemon_sprite(name: str, data: Dict[str, Any]) -> Optional[str]:
    entry = data["pokemon_types"].get(name)
    if not isinstance(entry, dict):
        return None
    sprite = entry.get("sprite")
    if sprite:
        return str(sprite)
    number = entry.get("national_number")
    if number:
        return os.path.join("assets", "sprites", f"{int(number):04d}.png")
    return None


def get_pokemon_entry(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    entry = data.get("pokemon_types", {}).get(name)
    return entry if isinstance(entry, dict) else {}


def get_pokemon_speed_base(name: str, data: Dict[str, Any]) -> Optional[int]:
    entry = get_pokemon_entry(name, data)
    stats = entry.get("base_stats", {})
    speed = stats.get("speed") if isinstance(stats, dict) else None
    return int(speed) if speed is not None else None


def get_ability_warning_lines(name: str, data: Dict[str, Any]) -> List[str]:
    entry = get_pokemon_entry(name, data)
    lines: List[str] = []
    for ability in entry.get("abilities", []):
        ability_id = ""
        ability_name = ""
        if isinstance(ability, dict):
            ability_id = str(ability.get("id", "")).lower()
            ability_name = str(ability.get("name", ""))
        else:
            ability_id = str(ability).lower()
            ability_name = str(ability)
        warning = ABILITY_WARNINGS.get(ability_id)
        if warning:
            prefix = f"{ability_name}: " if ability_name else ""
            lines.append(prefix + warning)
    return lines


def resolve_project_path(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if os.path.isabs(path):
        return path
    bundled_path = os.path.join(BASE_DIR, path)
    if os.path.exists(bundled_path):
        return bundled_path
    # Frozen builds should also be able to use optional local files placed
    # next to the EXE, such as git-ignored sprites downloaded by the user.
    return os.path.join(APP_ROOT, path)


def clamp_roi(roi: Dict[str, int], width: int, height: int) -> Dict[str, int]:
    x = max(0, min(int(roi["x"]), max(0, width - 1)))
    y = max(0, min(int(roi["y"]), max(0, height - 1)))
    w = max(1, min(int(roi["w"]), width - x))
    h = max(1, min(int(roi["h"]), height - y))
    return {"x": x, "y": y, "w": w, "h": h}


def inflate_roi(roi: Dict[str, int], pad_x: int, pad_y: int, width: int, height: int) -> Dict[str, int]:
    return clamp_roi(
        {
            "x": int(roi["x"]) - pad_x,
            "y": int(roi["y"]) - pad_y,
            "w": int(roi["w"]) + pad_x * 2,
            "h": int(roi["h"]) + pad_y * 2,
        },
        width,
        height,
    )


def candidate_to_roi(candidate: RoiCandidate) -> Dict[str, int]:
    return {"x": candidate.x, "y": candidate.y, "w": candidate.w, "h": candidate.h}


def scaled_default_rois(width: int, height: int) -> Dict[str, Dict[str, int]]:
    rois = DEFAULT_SETTINGS["roi"]
    base_width = max(item["x"] + item["w"] for item in rois.values())
    base_height = max(item["y"] + item["h"] for item in rois.values())
    sx = width / base_width
    sy = height / base_height
    scaled = {}
    for name, roi in rois.items():
        scaled[name] = clamp_roi(
            {
                "x": round(roi["x"] * sx),
                "y": round(roi["y"] * sy),
                "w": round(roi["w"] * sx),
                "h": round(roi["h"] * sy),
            },
            width,
            height,
        )
    return scaled


def detect_ui_box_candidates(frame: Any) -> List[RoiCandidate]:
    if cv2 is None or np is None:
        return []
    try:
        image = frame
        if image.shape[-1] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(gray, 50, 140)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 5))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        height, width = gray.shape[:2]
        candidates: List[RoiCandidate] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < max(70, width * 0.04) or h < max(22, height * 0.025):
                continue
            if w > width * 0.8 or h > height * 0.35:
                continue
            aspect = w / max(1, h)
            if aspect < 1.4 or aspect > 12:
                continue
            area = cv2.contourArea(contour)
            rect_area = max(1, w * h)
            rectangularity = min(1.0, area / rect_area)
            position_bonus = 0.25 if y > height * 0.45 else 0.1
            score = rectangularity + position_bonus + min(0.4, rect_area / (width * height) * 8)
            candidates.append(RoiCandidate(x, y, w, h, score))
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:40]
    except Exception:
        return []


def infer_battle_rois_from_candidates(candidates: List[RoiCandidate], width: int, height: int) -> Optional[Dict[str, Dict[str, int]]]:
    if len(candidates) < 4:
        return None
    lower = [
        item for item in candidates
        if item.y > height * 0.42 and item.w > width * 0.12 and item.h < height * 0.18
    ]
    lower.sort(key=lambda item: item.w * item.h, reverse=True)
    moves = lower[:4]
    if len(moves) < 4:
        return None
    moves = sorted(moves, key=lambda item: (item.y, item.x))
    top = [
        item for item in candidates
        if item.y < height * 0.45 and item.w > width * 0.12 and item.h < height * 0.16
    ]
    top.sort(key=lambda item: (item.y, -item.x, -item.score))
    opponent = top[0] if top else None
    rois: Dict[str, Dict[str, int]] = {}
    for idx, candidate in enumerate(moves, start=1):
        rois[f"move_{idx}"] = inflate_roi(candidate_to_roi(candidate), -4, -3, width, height)
    if opponent:
        rois["opponent_name"] = inflate_roi(candidate_to_roi(opponent), -2, -2, width, height)
        level_roi = {
            "x": opponent.x + max(0, opponent.w - int(opponent.w * 0.35)),
            "y": opponent.y + int(opponent.h * 0.45),
            "w": int(opponent.w * 0.35),
            "h": int(opponent.h * 0.55),
        }
        rois["opponent_level_status"] = clamp_roi(level_roi, width, height)
    else:
        fallback = scaled_default_rois(width, height)
        rois["opponent_name"] = fallback["opponent_name"]
        rois["opponent_level_status"] = fallback["opponent_level_status"]
    return rois


def image_hash_from_roi(frame: Any, roi: Dict[str, int]) -> Optional[str]:
    if cv2 is None or np is None:
        return None
    try:
        x, y, w, h = [int(roi[k]) for k in ("x", "y", "w", "h")]
        if w <= 0 or h <= 0:
            return None
        height, width = frame.shape[:2]
        x, y = max(0, x), max(0, y)
        crop = frame[y:min(y + h, height), x:min(x + w, width)]
        if crop.size == 0:
            return None
        if crop.shape[-1] == 4:
            crop = cv2.cvtColor(crop, cv2.COLOR_BGRA2BGR)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (64, 24), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if binary.mean() > 127:
            binary = 255 - binary
        small = cv2.resize(binary, (32, 12), interpolation=cv2.INTER_AREA)
        mean = float(small.mean())
        return "".join("1" if value > mean else "0" for value in small.flatten())
    except Exception:
        return None


def hash_similarity(left: str, right: str) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    distance = sum(1 for a, b in zip(left, right) if a != b)
    return 1.0 - distance / len(left)


def visual_match_from_roi(
    frame: Any,
    roi: Dict[str, int],
    samples: Dict[str, List[Dict[str, Any]]],
    category: str,
    choices: Iterable[str],
    cutoff: float = 0.88,
) -> Tuple[Optional[str], float]:
    current_hash = image_hash_from_roi(frame, roi)
    if not current_hash:
        return None, 0.0
    valid_choices = set(choices)
    best_label = None
    best_score = 0.0
    for sample in samples.get(category, []):
        label = str(sample.get("label", ""))
        sample_hash = str(sample.get("hash", ""))
        if label not in valid_choices or not sample_hash:
            continue
        score = hash_similarity(current_hash, sample_hash)
        if score > best_score:
            best_label = label
            best_score = score
    if best_label and best_score >= cutoff:
        return best_label, best_score
    return None, best_score


def get_move_type(name: str, data: Dict[str, Any]) -> Optional[str]:
    if name in data["moves"]:
        value = data["moves"][name]
        if isinstance(value, dict):
            return value.get("type")
        return value
    candidates = best_matches(name, data["moves"].keys(), limit=1, cutoff=0.48)
    if candidates:
        value = data["moves"][candidates[0]]
        if isinstance(value, dict):
            return value.get("type")
        return value
    return None


def get_move_category(name: str, data: Dict[str, Any]) -> str:
    value = data.get("moves", {}).get(name)
    if isinstance(value, dict):
        return str(value.get("category", "Unknown")).title()
    candidates = best_matches(name, data.get("moves", {}).keys(), limit=1, cutoff=0.48)
    if candidates:
        value = data["moves"][candidates[0]]
        if isinstance(value, dict):
            return str(value.get("category", "Unknown")).title()
    return "Unknown"


def calc_speed(base_speed: int, level: int, iv: int, ev: int, nature: float) -> int:
    raw = math.floor(((2 * base_speed + iv + ev / 4) * level) / 100) + 5
    return math.floor(raw * nature)


def estimate_speed_range(base_speed: int, level: int, profile_key: str) -> Tuple[int, int]:
    level = max(1, min(100, int(level)))
    profile = SPEED_PROFILES.get(profile_key, SPEED_PROFILES["npc_basic"])
    min_speed = calc_speed(base_speed, level, profile["min_iv"], profile["min_ev"], profile["min_nature"])
    max_speed = calc_speed(base_speed, level, profile["max_iv"], profile["max_ev"], profile["max_nature"])
    return min_speed, max_speed


def speed_summary(my_speed_text: str, opponent_name: str, level_text: str, profile_key: str, data: Dict[str, Any], lang: str = "ko") -> str:
    base_speed = get_pokemon_speed_base(opponent_name, data)
    if base_speed is None:
        return {"ko": "스피드: 상대 종족값 정보 없음", "en": "Speed: no base stat data", "ja": "素早さ: 種族値データなし"}.get(lang, "스피드: 상대 종족값 정보 없음")
    try:
        level = int(level_text)
    except ValueError:
        level = 50
    min_speed, max_speed = estimate_speed_range(base_speed, level, profile_key)
    profile_label = speed_profile_label(profile_key, lang)
    if lang == "en":
        base = f"Speed: {profile_label}, {opponent_name} base {base_speed}, Lv.{level} estimate {min_speed}-{max_speed}"
    elif lang == "ja":
        base = f"素早さ: {profile_label}基準 {opponent_name} 種族値 {base_speed}, Lv.{level} 予想 {min_speed}-{max_speed}"
    else:
        base = f"스피드: {profile_label} 기준 {opponent_name} 종족값 {base_speed}, Lv.{level} 예상 {min_speed}-{max_speed}"
    try:
        my_speed = int(my_speed_text)
    except ValueError:
        return base + {"ko": " / 내 스피드 입력 시 선공 추정", "en": " / enter my speed to estimate turn order", "ja": " / 自分の素早さ入力で先攻推定"}.get(lang, " / 내 스피드 입력 시 선공 추정")
    if my_speed > max_speed:
        return base + (f" / My {my_speed}: likely faster" if lang == "en" else f" / 自分 {my_speed}: だいたい先攻" if lang == "ja" else f" / 내 {my_speed}: 대체로 선공")
    if my_speed < min_speed:
        return base + (f" / My {my_speed}: likely slower" if lang == "en" else f" / 自分 {my_speed}: だいたい後攻" if lang == "ja" else f" / 내 {my_speed}: 대체로 후공")
    return base + (f" / My {my_speed}: uncertain" if lang == "en" else f" / 自分 {my_speed}: 不確実" if lang == "ja" else f" / 내 {my_speed}: 불확실")


def effectiveness(move_type: str, defender_types: List[str], gen: int, data: Dict[str, Any]) -> float:
    chart = data["type_charts"][get_generation_key(gen)]
    multiplier = 1.0
    for defender in defender_types:
        multiplier *= chart.get(move_type, {}).get(defender, 1.0)
    return multiplier


def format_effect(multiplier: Optional[float]) -> str:
    if multiplier is None:
        return "판별 불가"
    if multiplier == 0:
        return "효과 없음"
    if multiplier == 1:
        return "보통"
    if multiplier == int(multiplier):
        return f"{int(multiplier)}배 효과"
    return f"{multiplier:g}배"


def format_effect_for_language(multiplier: Optional[float], lang: str) -> str:
    if lang == "en":
        if multiplier is None:
            return "Unknown"
        if multiplier == 0:
            return "No effect"
        if multiplier == 1:
            return "Normal"
        return f"{multiplier:g}x effective"
    if lang == "ja":
        if multiplier is None:
            return "判定不可"
        if multiplier == 0:
            return "効果なし"
        if multiplier == 1:
            return "通常"
        return f"{multiplier:g}倍効果"
    return format_effect(multiplier)


def category_label_for_language(category: str, lang: str) -> str:
    return CATEGORY_LABELS.get(lang, CATEGORY_LABELS["ko"]).get(category, category)


def effect_style(multiplier: Optional[float]) -> Tuple[str, str]:
    if multiplier is None:
        return (UI["panel2"], UI["muted"])
    if multiplier == 0:
        return (UI["panel2"], UI["red"])
    if multiplier > 1:
        return (UI["panel2"], UI["green"])
    if multiplier < 1:
        return (UI["panel2"], UI["yellow"])
    return (UI["panel2"], UI["text"])


def language_display(label: str) -> str:
    if "Korean" in label or "한국어" in label:
        return "Korean / 한국어"
    if "Japanese" in label or "日本語" in label:
        return "Japanese / 日本語"
    if "English" in label:
        return "English"
    return label


def available_sources() -> List[str]:
    sources = ["monitor"]
    if gw is not None:
        try:
            titles = [title for title in gw.getAllTitles() if title.strip()]
            sources.extend(sorted(set(titles))[:80])
        except Exception:
            pass
    return sources


def preferred_start_source(saved_source: str = "monitor") -> str:
    sources = available_sources()
    for keyword in PREFERRED_WINDOW_KEYWORDS:
        for source in sources:
            if keyword in source.lower():
                return source
    return saved_source if saved_source in sources or saved_source == "monitor" else "monitor"


def display_source(source: str) -> str:
    if source == "monitor":
        return "전체 화면 / 모니터 1"
    return source


def source_from_display(value: str) -> str:
    if value.startswith("전체 화면"):
        return "monitor"
    return value


def available_source_labels() -> List[str]:
    return [display_source(source) for source in available_sources()]


def choose_ui_font() -> str:
    available = set(tkfont.families())
    for family in ("맑은 고딕", "Malgun Gothic", "Noto Sans CJK KR", "Pretendard", "Segoe UI Variable", "Segoe UI"):
        if family in available:
            return family
    return "Arial"


class ScreenCapture:
    def __init__(self, log: Callable[[str], None]) -> None:
        self.log = log

    def _capture_window_printwindow(self, hwnd: int) -> Optional[Any]:
        if np is None:
            return None
        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            rect = ctypes.wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width <= 0 or height <= 0:
                return None
            hwnd_dc = user32.GetWindowDC(hwnd)
            mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
            old_obj = gdi32.SelectObject(mem_dc, bitmap)
            # PW_RENDERFULLCONTENT works for many modern Windows windows; fallback value is harmless if ignored.
            ok = user32.PrintWindow(hwnd, mem_dc, 0x00000002)
            if not ok:
                ok = user32.PrintWindow(hwnd, mem_dc, 0)
            bmp_info = ctypes.create_string_buffer(40)
            ctypes.memset(bmp_info, 0, 40)
            ctypes.cast(bmp_info, ctypes.POINTER(ctypes.c_uint32))[0] = 40
            ctypes.cast(bmp_info, ctypes.POINTER(ctypes.c_int32))[1] = width
            ctypes.cast(bmp_info, ctypes.POINTER(ctypes.c_int32))[2] = -height
            ctypes.cast(bmp_info, ctypes.POINTER(ctypes.c_uint16))[6] = 1
            ctypes.cast(bmp_info, ctypes.POINTER(ctypes.c_uint16))[7] = 32
            buffer = ctypes.create_string_buffer(width * height * 4)
            gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, bmp_info, 0)
            gdi32.SelectObject(mem_dc, old_obj)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, hwnd_dc)
            if not ok:
                return None
            arr = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 4))
            if arr[..., :3].max() == 0:
                return None
            return arr.copy()
        except Exception as exc:
            self.log(f"PrintWindow 캡처 실패: {exc}")
            return None

    def capture(self, settings: Dict[str, Any]) -> Any:
        if mss is None or np is None:
            raise RuntimeError("mss/numpy가 설치되어 있지 않아 화면 캡처를 사용할 수 없습니다.")
        cap = settings["capture"]
        with mss.mss() as sct:
            if cap.get("source") == "window" and cap.get("window_title") and gw is not None:
                wins = gw.getWindowsWithTitle(cap["window_title"])
                if wins:
                    win = wins[0]
                    hwnd = getattr(win, "_hWnd", None)
                    if hwnd:
                        frame = self._capture_window_printwindow(int(hwnd))
                        if frame is not None:
                            return frame
                    box = {"left": win.left, "top": win.top, "width": win.width, "height": win.height}
                    return np.array(sct.grab(box))
            idx = int(cap.get("monitor_index", 1))
            monitors = sct.monitors
            idx = min(max(1, idx), len(monitors) - 1)
            return np.array(sct.grab(monitors[idx]))


class OcrEngine:
    def __init__(self, log: Callable[[str], None]) -> None:
        self.log = log

    def available(self) -> bool:
        return pytesseract is not None and Image is not None and cv2 is not None and np is not None

    def text_from_roi(self, frame: Any, roi: Dict[str, int], settings: Dict[str, Any]) -> str:
        results = self.text_variants_from_roi(frame, roi, settings)
        return results[0] if results else ""

    def _crop_roi(self, frame: Any, roi: Dict[str, int]) -> Optional[Any]:
        x, y, w, h = [int(roi[k]) for k in ("x", "y", "w", "h")]
        if w <= 0 or h <= 0:
            return None
        height, width = frame.shape[:2]
        x, y = max(0, x), max(0, y)
        roi_img = frame[y:min(y + h, height), x:min(x + w, width)]
        if roi_img.size == 0:
            return None
        if roi_img.shape[-1] == 4:
            roi_img = cv2.cvtColor(roi_img, cv2.COLOR_BGRA2BGR)
        return roi_img

    def _white_text_ocr_images(self, roi_img: Any, ocr_settings: Dict[str, Any], scale: int = 3) -> List[Any]:
        """Create OCR-friendly images by isolating bright white UI text.

        Pokemon DS/GBA/Switch UI often draws white glyphs with dark shadows or
        colored panels. These masks keep the bright low-saturation glyph pixels
        and flatten everything else to a clean white background.
        """
        bgr = roi_img
        threshold = int(ocr_settings.get("threshold", 150))
        white_min_value = int(ocr_settings.get("white_min_value", max(135, threshold - 10)))
        white_max_saturation = int(ocr_settings.get("white_max_saturation", 105))
        white_channel_delta = int(ocr_settings.get("white_channel_delta", 85))
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h_chan, s_chan, v_chan = cv2.split(hsv)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        bright = max(0, min(255, white_min_value))
        sat_max = max(0, min(255, white_max_saturation))
        delta_max = max(0, min(255, white_channel_delta))
        white_mask = cv2.inRange(hsv, (0, 0, bright), (179, sat_max, 255))
        channel_min = np.min(bgr, axis=2)
        channel_max = np.max(bgr, axis=2)
        balanced_bright = ((channel_min >= bright) & ((channel_max - channel_min) <= delta_max)).astype(np.uint8) * 255
        value_mask = cv2.inRange(v_chan, max(145, bright - 20), 255)
        low_sat_mask = cv2.inRange(s_chan, 0, min(255, sat_max + 15))
        mask = cv2.bitwise_or(white_mask, balanced_bright)
        mask = cv2.bitwise_or(mask, cv2.bitwise_and(value_mask, low_sat_mask))

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=1)

        text_black = np.full(mask.shape, 255, dtype=np.uint8)
        text_black[mask > 0] = 0
        text_black = cv2.resize(text_black, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)

        text_white = 255 - text_black
        gray_scaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        _, otsu = cv2.threshold(gray_scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if otsu.mean() < 127:
            otsu = 255 - otsu
        adaptive = cv2.adaptiveThreshold(gray_scaled, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9)

        return [text_black, text_white, otsu, adaptive]

    def text_variants_from_roi(self, frame: Any, roi: Dict[str, int], settings: Dict[str, Any], robust: bool = False) -> List[str]:
        if not self.available():
            return []
        roi_img = self._crop_roi(frame, roi)
        if roi_img is None:
            return []
        threshold = int(settings["ocr"].get("threshold", 150))
        lang = settings["ocr"].get("lang", "kor")
        psm = int(settings["ocr"].get("psm", 6))
        psm_values = [7, psm] if psm != 7 else [7]
        images = self._white_text_ocr_images(roi_img, settings.get("ocr", {}), scale=4)
        if robust:
            for candidate_psm in (8, 13):
                if candidate_psm not in psm_values:
                    psm_values.append(candidate_psm)
        else:
            images = images[:2]
        texts: List[str] = []
        seen = set()
        for img in images:
            pil = Image.fromarray(img)
            for psm_value in psm_values:
                try:
                    config = f"--oem 1 --psm {psm_value} -c preserve_interword_spaces=0"
                    text = clean_label_ocr_text(pytesseract.image_to_string(pil, lang=lang, config=config), lang)
                    if text and text not in seen:
                        texts.append(text)
                        seen.add(text)
                except Exception as exc:
                    self.log(f"OCR 오류: {exc}")
                    break
        return texts

    def best_text_for_choices(self, frame: Any, roi: Dict[str, int], settings: Dict[str, Any], choices: Iterable[str], cutoff: float, robust: bool = False) -> Tuple[str, Optional[str], float, List[str]]:
        variants = self.text_variants_from_roi(frame, roi, settings, robust=robust)
        best_text = variants[0] if variants else ""
        best_match = None
        best_score = 0.0
        for text in variants:
            match, score = best_match_with_score(text, choices, cutoff=cutoff)
            if score > best_score:
                best_text = text
                best_match = match
                best_score = score
        return best_text, best_match, best_score, variants

    def _segment_digit_images(self, image: Any) -> List[Any]:
        # image is white background / black glyphs.
        ink = image < 180
        if not np.any(ink):
            return []
        rows = np.where(np.any(ink, axis=1))[0]
        cols = np.where(np.any(ink, axis=0))[0]
        if len(rows) == 0 or len(cols) == 0:
            return []
        top, bottom = max(0, rows[0] - 4), min(image.shape[0] - 1, rows[-1] + 4)
        col_has_ink = np.any(ink[top:bottom + 1, :], axis=0)
        runs: List[Tuple[int, int]] = []
        start: Optional[int] = None
        for idx, has_ink in enumerate(col_has_ink):
            if has_ink and start is None:
                start = idx
            elif not has_ink and start is not None:
                runs.append((start, idx - 1))
                start = None
        if start is not None:
            runs.append((start, len(col_has_ink) - 1))

        merged: List[Tuple[int, int]] = []
        for run in runs:
            if not merged or run[0] - merged[-1][1] > 6:
                merged.append(run)
            else:
                merged[-1] = (merged[-1][0], run[1])

        digits = []
        min_width = max(8, image.shape[1] // 25)
        for left, right in merged:
            if right - left + 1 < min_width:
                continue
            crop = image[top:bottom + 1, max(0, left - 4):min(image.shape[1], right + 5)]
            digits.append(crop)
        if len(digits) == 1 and digits[0].shape[1] > digits[0].shape[0] * 0.75:
            wide = digits[0]
            wide_ink = wide < 180
            projection = wide_ink.sum(axis=0)
            lo = max(1, int(wide.shape[1] * 0.35))
            hi = min(wide.shape[1] - 2, int(wide.shape[1] * 0.65))
            if hi > lo:
                split = lo + int(np.argmin(projection[lo:hi + 1]))
                left_part = wide[:, :max(1, split)]
                right_part = wide[:, min(wide.shape[1] - 1, split + 1):]
                if left_part.shape[1] >= min_width and right_part.shape[1] >= min_width:
                    digits = [left_part, right_part]
        return digits[:3]

    def _shape_correct_digit(self, digit: str, image: Any) -> str:
        if digit != "8":
            return digit
        ink = image < 180
        if not np.any(ink):
            return digit
        h, w = ink.shape
        upper_right = ink[h // 5:h // 2, w // 2:w - max(1, w // 12)].mean()
        lower_right = ink[h // 2:4 * h // 5, w // 2:w - max(1, w // 12)].mean()
        center = ink[2 * h // 5:3 * h // 5, w // 4:3 * w // 4].mean()
        if lower_right > upper_right * 1.55 and center > upper_right * 1.2:
            return "6"
        return digit

    def _classify_digit_shape(self, image: Any) -> str:
        ink = image < 180
        if not np.any(ink):
            return ""
        rows = np.where(np.any(ink, axis=1))[0]
        cols = np.where(np.any(ink, axis=0))[0]
        crop = ink[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
        if crop.size == 0:
            return ""
        norm = cv2.resize(crop.astype(np.uint8) * 255, (28, 42), interpolation=cv2.INTER_NEAREST) > 0
        h, w = norm.shape

        def density(y1: float, y2: float, x1: float, x2: float) -> float:
            ys = slice(max(0, int(h * y1)), min(h, int(h * y2)))
            xs = slice(max(0, int(w * x1)), min(w, int(w * x2)))
            area = norm[ys, xs]
            return float(area.mean()) if area.size else 0.0

        segments = {
            "top": density(0.00, 0.20, 0.20, 0.80),
            "mid": density(0.40, 0.60, 0.20, 0.80),
            "bottom": density(0.80, 1.00, 0.20, 0.80),
            "ul": density(0.12, 0.48, 0.00, 0.34),
            "ur": density(0.12, 0.48, 0.66, 1.00),
            "ll": density(0.52, 0.88, 0.00, 0.34),
            "lr": density(0.52, 0.88, 0.66, 1.00),
        }
        on = {name: value > 0.18 for name, value in segments.items()}

        # Dot-font digits are close to seven-segment shapes after thresholding.
        patterns = {
            "0": {"top", "bottom", "ul", "ur", "ll", "lr"},
            "1": {"ur", "lr"},
            "2": {"top", "mid", "bottom", "ur", "ll"},
            "3": {"top", "mid", "bottom", "ur", "lr"},
            "4": {"mid", "ul", "ur", "lr"},
            "5": {"top", "mid", "bottom", "ul", "lr"},
            "6": {"top", "mid", "bottom", "ul", "ll", "lr"},
            "7": {"top", "ur", "lr"},
            "8": {"top", "mid", "bottom", "ul", "ur", "ll", "lr"},
            "9": {"top", "mid", "bottom", "ul", "ur", "lr"},
        }
        best_digit = ""
        best_score = -999.0
        active = {name for name, value in on.items() if value}
        for digit, expected in patterns.items():
            true_positive = len(active & expected)
            false_positive = len(active - expected)
            false_negative = len(expected - active)
            score = true_positive * 2.0 - false_positive * 1.4 - false_negative * 1.2
            if score > best_score:
                best_digit = digit
                best_score = score

        # Common DS level font case: 6 has strong lower-left ink, 5 does not.
        if on["top"] and on["mid"] and on["bottom"] and on["ul"] and on["lr"]:
            ll_upper = density(0.52, 0.70, 0.00, 0.34)
            if not on["ur"]:
                return "6" if ll_upper > 0.13 else "5"
            if segments["ll"] > max(0.16, segments["ur"] * 1.15):
                return "6"
            if segments["ll"] < 0.16:
                return "5"
        return best_digit

    def _segmented_digits_from_image(self, image: Any) -> str:
        parts = self._segment_digit_images(image)
        if not parts:
            return ""
        digits = []
        for part in parts:
            try:
                padded = cv2.copyMakeBorder(part, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
                text = pytesseract.image_to_string(
                    Image.fromarray(padded),
                    lang="eng",
                    config="--oem 1 --psm 10 -c tessedit_char_whitelist=0123456789",
                )
                found = "".join(re.findall(r"\d+", coerce_ocr_digits(text)))
                if found:
                    digits.append(self._shape_correct_digit(found[0], padded))
                else:
                    shape_digit = self._classify_digit_shape(padded)
                    if shape_digit:
                        digits.append(shape_digit)
            except Exception:
                shape_digit = self._classify_digit_shape(part)
                if shape_digit:
                    digits.append(shape_digit)
        return "".join(digits)

    def digits_from_roi(self, frame: Any, roi: Dict[str, int], settings: Dict[str, Any]) -> str:
        if not self.available():
            return ""
        roi_img = self._crop_roi(frame, roi)
        if roi_img is None:
            return ""
        images = self._white_text_ocr_images(roi_img, settings.get("ocr", {}), scale=5)
        psm_values = (7, 8, 13)
        candidates: List[Tuple[str, int]] = []
        segmented = self._segmented_digits_from_image(images[0]) if images else ""
        if segmented:
            try:
                value = int(segmented)
                if 1 <= value <= 100:
                    # A small left-side artifact in the level ROI is often
                    # classified as a leading 8, turning level 4/5 into 84/85.
                    if len(segmented) == 2 and segmented.startswith("8") and segmented[1] != "0":
                        candidates.append((segmented[1], 45))
                        candidates.append((segmented, 10))
                    else:
                        return str(value)
            except ValueError:
                pass
        for img in images:
            for psm in psm_values:
                try:
                    for config in (
                        f"--oem 1 --psm {psm} -c tessedit_char_whitelist=0123456789",
                        f"--oem 1 --psm {psm}",
                    ):
                        text = pytesseract.image_to_string(Image.fromarray(img), lang="eng", config=config)
                        digits = "".join(re.findall(r"\d+", coerce_ocr_digits(text)))
                        if digits:
                            candidates.append((digits, 0))
                            if len(digits) > 2:
                                candidates.append((digits[-2:], 0))
                            if len(digits) > 3:
                                candidates.append((digits[-3:].lstrip("0") or "0", 0))
                except Exception as exc:
                    self.log(f"레벨 OCR 오류: {exc}")
                    break
        scored: List[Tuple[int, str]] = []
        flat_candidates = [digits for digits, _bonus in candidates]
        for digits, bonus in candidates:
            if not digits:
                continue
            try:
                value = int(digits)
            except ValueError:
                continue
            if not 1 <= value <= 100:
                continue
            score = bonus
            score += 8 if len(digits) <= 2 else 4
            score += flat_candidates.count(digits) * 3
            if value >= 5:
                score += 1
            scored.append((score, str(value)))
        if scored:
            scored.sort(key=lambda item: (item[0], int(item[1])), reverse=True)
            return scored[0][1]
        return candidates[0][0] if candidates else ""


def move_match_accept_threshold(text: str) -> float:
    norm_len = len(normalize_name(text))
    if norm_len <= 1:
        return 0.90
    if norm_len <= 2:
        return 0.82
    if norm_len <= 4:
        return 0.78
    return 0.62


class PokemonBattleLens(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("620x760")
        self.minsize(540, 640)
        self.configure(bg=UI["bg"])

        self.tesseract_path = configure_tesseract()
        self.language_packs = find_language_packs()
        self.user_settings = load_user_settings()
        default_language = next((label for label in self.language_packs if "Korean" in label or "한국어" in label), None)
        saved_language = self.user_settings.get("language_label")
        if saved_language not in self.language_packs:
            saved_language = default_language or next(iter(self.language_packs), "Embedded Korean/English")
        self.language_var = tk.StringVar(value=saved_language)
        self.data = self._load_selected_language_data()
        self.ocr_aliases = load_ocr_aliases()
        self.visual_samples = load_visual_samples()
        self.settings = deep_update(DEFAULT_SETTINGS, self.user_settings.get("settings", {}))
        saved_capture = self.settings.get("capture", {})
        saved_source = saved_capture.get("window_title") if saved_capture.get("source") == "window" else "monitor"
        start_source = preferred_start_source(saved_source or "monitor")
        if start_source == "monitor":
            self.settings["capture"]["source"] = "monitor"
            self.settings["capture"]["window_title"] = ""
        else:
            self.settings["capture"]["source"] = "window"
            self.settings["capture"]["window_title"] = start_source
            roi_profiles = self.user_settings.get("roi_by_source", {})
            if start_source in roi_profiles:
                self.settings["roi"] = deep_update(DEFAULT_SETTINGS["roi"], roi_profiles[start_source])
        self.settings["ocr"]["lang"] = normalize_ocr_lang(self.settings.get("ocr", {}).get("lang", ""), self.data)
        self.capture = ScreenCapture(self.log)
        self.ocr = OcrEngine(self.log)
        self.queue: queue.Queue[DetectionResult] = queue.Queue()
        self.scanning = False
        self.worker: Optional[threading.Thread] = None
        self.current_detection = DetectionResult()
        self.last_move_matches: List[Optional[str]] = [None, None, None, None]
        self.last_level_text = ""
        self.not_battle_frames = 0
        self.battle_pause_logged = False
        self.settings_window: Optional[tk.Toplevel] = None
        self.logo_image: Optional[tk.PhotoImage] = None
        self.app_icon_image: Optional[tk.PhotoImage] = None
        self.sprite_cache: Dict[str, Any] = {}
        self.current_sprite_image: Optional[Any] = None

        self.gen_var = tk.IntVar(value=int(self.settings.get("generation", 9)))
        self.active_generation = int(self.gen_var.get())
        saved_game_profile = str(self.settings.get("game_profile") or default_game_profile_for_generation(self.active_generation))
        if saved_game_profile not in GAME_UI_PROFILE_BY_KEY:
            saved_game_profile = default_game_profile_for_generation(self.active_generation)
        self.settings["game_profile"] = saved_game_profile
        self.active_game_profile = saved_game_profile
        game_profiles = self.user_settings.get("profiles_by_game", {})
        gen_profiles = self.user_settings.get("profiles_by_generation", {})
        profile = game_profiles.get(saved_game_profile) or gen_profiles.get(str(self.active_generation))
        if profile:
            apply_generation_profile_to_settings(self.settings, profile)
        self.always_top_var = tk.BooleanVar(value=True)
        self.game_profile_var = tk.StringVar(value=game_profile_label(saved_game_profile))
        self.source_var = tk.StringVar(value=start_source)
        self.source_display_var = tk.StringVar(value=display_source(self.source_var.get()))
        self.ocr_lang_var = tk.StringVar(value=self.settings["ocr"].get("lang", "kor"))
        self.ocr_preset_var = tk.StringVar(value=OCR_LABEL_BY_CODE.get(self.ocr_lang_var.get(), "한국어 게임 화면"))
        self.ocr_lang_var.set(OCR_PRESETS.get(self.ocr_preset_var.get(), self.ocr_lang_var.get()))
        self.settings["ocr"]["lang"] = self.ocr_lang_var.get()
        self.ocr_threshold_var = tk.IntVar(value=int(self.settings["ocr"].get("threshold", 150)))
        self.ocr_white_min_var = tk.IntVar(value=int(self.settings["ocr"].get("white_min_value", 140)))
        self.ocr_sat_max_var = tk.IntVar(value=int(self.settings["ocr"].get("white_max_saturation", 105)))
        self.ocr_delta_var = tk.IntVar(value=int(self.settings["ocr"].get("white_channel_delta", 85)))
        self.scan_interval_var = tk.IntVar(value=int(self.settings.get("scan_interval_ms", SCAN_INTERVAL_MS)))
        self.manual_opponent_var = tk.StringVar()
        self.my_speed_var = tk.StringVar()
        self.opponent_level_var = tk.StringVar(value="50")
        self.move_vars = [tk.StringVar() for _ in range(4)]
        self.system_language_var = tk.StringVar(value=SYSTEM_LANGUAGES.get(self.settings.get("system_language", "ko"), SYSTEM_LANGUAGES["ko"]))
        speed_profile = self.settings.get("speed_profile", "npc_basic")
        self.speed_profile_var = tk.StringVar(value=speed_profile_label(speed_profile, self._system_language_code()))
        self.status_var = tk.StringVar(value=self.tr("idle"))
        self.footer_var = tk.StringVar()

        self._build_ui()
        self._apply_window_icon()
        self.attributes("-topmost", True)
        self._updating_profile_vars = False
        self.gen_var.trace_add("write", lambda *_: self._on_generation_changed())
        self.game_profile_var.trace_add("write", lambda *_: self._on_game_profile_changed())
        self.after(200, self._poll_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._initial_log()

    def tr(self, key: str) -> str:
        code = {label: code for code, label in SYSTEM_LANGUAGES.items()}.get(
            getattr(self, "system_language_var", tk.StringVar(value=SYSTEM_LANGUAGES["ko"])).get(),
            self.settings.get("system_language", "ko") if hasattr(self, "settings") else "ko",
        )
        return UI_TEXT.get(code, UI_TEXT["ko"]).get(key, UI_TEXT["en"].get(key, UI_TEXT["ko"].get(key, key)))

    def _system_language_code(self) -> str:
        return {label: code for code, label in SYSTEM_LANGUAGES.items()}.get(self.system_language_var.get(), "ko")

    def _load_selected_language_data(self) -> Dict[str, Any]:
        label = self.language_var.get()
        path = self.language_packs.get(label)
        if not path:
            return deep_copy(DATA)
        try:
            return merge_language_pack(DATA, load_pack_from_path(path))
        except Exception as exc:
            self.log(f"Language JSON load failed: {exc}")
            return deep_copy(DATA)

    def _change_language_pack(self) -> None:
        self.data = self._load_selected_language_data()
        self.settings["ocr"]["lang"] = self.data.get("ocr_lang", self.settings["ocr"].get("lang", "kor"))
        if hasattr(self, "ocr_lang_var"):
            self.ocr_lang_var.set(self.settings["ocr"]["lang"])
        if hasattr(self, "ocr_preset_var"):
            self.ocr_preset_var.set(OCR_LABEL_BY_CODE.get(self.settings["ocr"]["lang"], self.ocr_preset_var.get()))
        self.manual_opponent_var.set("")
        for var in self.move_vars:
            var.set("")
        self._refresh_effects()
        self._update_footer()
        self.log(f"Language data selected: {self.language_var.get()} / OCR={self.settings['ocr']['lang']}")

    def _build_ui(self) -> None:
        font_family = choose_ui_font()
        self.option_add("*Font", (font_family, 10))
        self.option_add("*TCombobox*Listbox.Font", (font_family, 10))
        style = ttk.Style(self)
        style.theme_use("clam")
        self.configure(bg=UI["bg"])
        self.geometry("760x840")
        self.minsize(620, 700)

        style.configure("App.TFrame", background=UI["bg"])
        style.configure("Panel.TFrame", background=UI["panel"])
        style.configure("TLabel", background=UI["bg"], foreground=UI["text"], font=(font_family, 10))
        style.configure("Muted.TLabel", background=UI["bg"], foreground=UI["muted"], font=(font_family, 9))
        style.configure("Title.TLabel", background=UI["bg"], foreground=UI["text"], font=(font_family, 18, "bold"))
        style.configure("SubTitle.TLabel", background=UI["bg"], foreground=UI["muted"], font=(font_family, 9))
        style.configure("Panel.TLabel", background=UI["panel"], foreground=UI["text"], font=(font_family, 10))
        style.configure("PanelMuted.TLabel", background=UI["panel"], foreground=UI["muted"], font=(font_family, 9))
        style.configure("PanelTitle.TLabel", background=UI["panel"], foreground=UI["text"], font=(font_family, 12, "bold"))
        style.configure("TCheckbutton", background=UI["bg"], foreground=UI["text"], font=(font_family, 9))
        style.map("TCheckbutton", background=[("active", UI["bg"])], foreground=[("active", UI["text"])])
        style.configure("TButton", padding=(12, 7), font=(font_family, 10), background=UI["field"], foreground=UI["text"], bordercolor=UI["line"], lightcolor=UI["field"], darkcolor=UI["field"])
        style.map("TButton", background=[("active", "#3b4148"), ("pressed", "#20242a")], foreground=[("active", UI["text"])])
        style.configure("Accent.TButton", padding=(14, 8), font=(font_family, 10, "bold"), background=UI["blue"], foreground="#ffffff", bordercolor=UI["blue"])
        style.map("Accent.TButton", background=[("active", "#3d8fe6"), ("pressed", UI["blue2"])])
        style.configure("TEntry", fieldbackground=UI["field"], foreground=UI["text"], insertcolor=UI["text"], bordercolor=UI["line"], lightcolor=UI["field"], darkcolor=UI["field"], padding=6)
        style.configure("TCombobox", fieldbackground=UI["field"], background=UI["field"], foreground=UI["text"], arrowcolor=UI["text"], bordercolor=UI["line"], padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", UI["field"])], foreground=[("readonly", UI["text"])], background=[("readonly", UI["field"])])
        style.configure("TSpinbox", fieldbackground=UI["field"], foreground=UI["text"], bordercolor=UI["line"], arrowsize=12, padding=5)

        root = ttk.Frame(self, padding=14, style="App.TFrame")
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        root.rowconfigure(3, weight=0)

        header = ttk.Frame(root, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        self.logo_image = self._load_logo_image()
        if self.logo_image is not None:
            tk.Label(header, image=self.logo_image, bg=UI["bg"]).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 12))
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(header, text=self.tr("subtitle"), style="SubTitle.TLabel").grid(row=1, column=1, sticky="w", pady=(1, 0))
        top_actions = ttk.Frame(header, style="App.TFrame")
        top_actions.grid(row=0, column=2, rowspan=2, sticky="e")
        ttk.Checkbutton(top_actions, text=self.tr("always_top"), variable=self.always_top_var, command=self._toggle_topmost).pack(side="left", padx=(0, 8))
        ttk.Button(top_actions, text=self.tr("settings"), command=self._open_settings).pack(side="left", padx=(0, 6))
        self.scan_button = ttk.Button(top_actions, text=self.tr("scan_start"), style="Accent.TButton", command=self._toggle_scan)
        self.scan_button.pack(side="left")

        manual = ttk.Frame(root, padding=12, style="Panel.TFrame")
        manual.grid(row=1, column=0, sticky="ew", pady=(14, 10))
        manual.columnconfigure(1, weight=1)
        manual.columnconfigure(3, weight=1)
        ttk.Label(manual, text=self.tr("manual_title"), style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 9))
        ttk.Label(manual, text=self.tr("opponent"), style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8))
        entry = ttk.Entry(manual, textvariable=self.manual_opponent_var)
        entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 8))
        entry.bind("<KeyRelease>", lambda _event: self._refresh_effects())
        ttk.Button(manual, text=self.tr("apply_search"), command=self._refresh_effects).grid(row=1, column=3, sticky="ew")
        ttk.Label(manual, text=self.tr("opponent_lv"), style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        level_entry = ttk.Entry(manual, textvariable=self.opponent_level_var, width=8)
        level_entry.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
        level_entry.bind("<KeyRelease>", lambda _event: self._refresh_effects())
        ttk.Label(manual, text=self.tr("my_speed"), style="Panel.TLabel").grid(row=2, column=2, sticky="w", padx=(0, 8), pady=(8, 0))
        speed_entry = ttk.Entry(manual, textvariable=self.my_speed_var, width=8)
        speed_entry.grid(row=2, column=3, sticky="ew", pady=(8, 0))
        speed_entry.bind("<KeyRelease>", lambda _event: self._refresh_effects())
        for idx, var in enumerate(self.move_vars):
            row_index = 3 + idx
            ttk.Label(manual, text=f"{self.tr('move')} {idx + 1}", style="Panel.TLabel").grid(row=row_index, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
            ent = ttk.Entry(manual, textvariable=var, width=20)
            ent.grid(row=row_index, column=1, columnspan=3, sticky="ew", pady=(8, 0))
            ent.bind("<KeyRelease>", lambda _event: self._refresh_effects())

        content = ttk.Frame(root, style="App.TFrame")
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=0)
        content.rowconfigure(1, weight=1)

        result = ttk.Frame(content, padding=12, style="Panel.TFrame")
        result.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        result.columnconfigure(0, weight=1)
        ttk.Label(result, text=self.tr("effects"), style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        opponent_row = ttk.Frame(result, style="Panel.TFrame")
        opponent_row.grid(row=1, column=0, sticky="ew", pady=(8, 7))
        opponent_row.columnconfigure(1, weight=1)
        sprite_box = tk.Frame(opponent_row, width=88, height=88, bg=UI["panel"], highlightbackground=UI["line"], highlightthickness=1)
        sprite_box.grid(row=0, column=0, sticky="nw", padx=(0, 12))
        sprite_box.grid_propagate(False)
        self.sprite_label = tk.Label(sprite_box, text="?", bg=UI["panel"], fg=UI["muted"], font=(font_family, 20, "bold"))
        self.sprite_label.place(relx=0.5, rely=0.5, anchor="center")
        self.opponent_label = tk.Label(
            opponent_row,
            text="상대 포켓몬: -",
            anchor="w",
            justify="left",
            bg=UI["panel"],
            fg=UI["text"],
            font=(font_family, 17, "bold"),
            wraplength=600,
        )
        self.opponent_label.grid(row=0, column=1, sticky="ew")
        self.ability_warning_label = tk.Label(
            result,
            text="",
            anchor="w",
            justify="left",
            padx=10,
            pady=6,
            bg="#3a3218",
            fg=UI["yellow"],
            font=(font_family, 9, "bold"),
        )
        self.ability_warning_label.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.speed_label = ttk.Label(result, text="스피드: -", style="Panel.TLabel")
        self.speed_label.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.effect_labels: List[tk.Label] = []
        self.move_name_labels: List[tk.Label] = []
        self.type_badge_labels: List[tk.Label] = []
        self.effect_result_labels: List[tk.Label] = []
        for idx in range(4):
            row = idx + 4
            row_bg = UI["panel2"]
            move_row = tk.Frame(result, bg=row_bg, highlightbackground=UI["line"], highlightthickness=1)
            move_row.grid(row=row, column=0, sticky="ew", pady=5)
            move_row.columnconfigure(1, weight=1)
            num = tk.Label(move_row, text=str(idx + 1), width=3, anchor="center", padx=8, pady=12, bg=UI["field"], fg=UI["muted"], font=(font_family, 12, "bold"))
            num.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 12))
            move_label = tk.Label(move_row, text=f"{self.tr('move')} {idx + 1}", anchor="w", padx=14, pady=8, bg=row_bg, fg=UI["text"], font=(font_family, 17, "bold"))
            move_label.grid(row=0, column=1, sticky="ew")
            type_badge = tk.Label(move_row, text="?", width=8, anchor="center", padx=12, pady=7, bg=UI["field"], fg="#ffffff", font=(font_family, 12, "bold"))
            type_badge.grid(row=0, column=2, sticky="e", padx=(10, 14), pady=(8, 0))
            effect_label = tk.Label(move_row, text=self.tr("unknown"), anchor="w", padx=14, pady=8, bg=row_bg, fg=UI["muted"], font=(font_family, 15, "bold"))
            effect_label.grid(row=1, column=1, columnspan=2, sticky="ew")
            self.effect_labels.append(move_label)
            self.move_name_labels.append(move_label)
            self.type_badge_labels.append(type_badge)
            self.effect_result_labels.append(effect_label)

        log_frame = ttk.Frame(content, padding=12, style="Panel.TFrame")
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        log_head = ttk.Frame(log_frame, style="Panel.TFrame")
        log_head.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        log_head.columnconfigure(1, weight=1)
        ttk.Label(log_head, text=self.tr("log"), style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(log_head, textvariable=self.status_var, style="Panel.TLabel").grid(row=0, column=1, sticky="e")
        self.log_text = tk.Text(log_frame, height=8, wrap="word", bg="#181b1f", fg="#dce3ec", insertbackground="#ffffff", relief="flat", padx=10, pady=10, font=(font_family, 10))
        self.log_text.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        footer = ttk.Frame(root, padding=(0, 8, 0, 0), style="App.TFrame")
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.footer_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer, text=APP_VERSION, style="Muted.TLabel").grid(row=0, column=1, sticky="e", padx=(10, 0))
        tk.Label(footer, text="●", bg=UI["bg"], fg=UI["green"], font=(font_family, 10, "bold")).grid(row=0, column=2, sticky="e", padx=(8, 0))
        self._update_footer()

    def _load_logo_image(self) -> Optional[tk.PhotoImage]:
        path = os.path.join(BASE_DIR, "assets", "app_icon_v2.png")
        if not os.path.exists(path):
            return None
        try:
            image = tk.PhotoImage(file=path)
            scale = max(1, math.ceil(max(image.width(), image.height()) / 44))
            return image.subsample(scale, scale)
        except Exception:
            return None

    def _apply_window_icon(self) -> None:
        ico_path = os.path.join(BASE_DIR, "assets", "app_icon.ico")
        png_path = os.path.join(BASE_DIR, "assets", "app_icon_v2.png")
        try:
            if os.path.exists(ico_path):
                self.iconbitmap(ico_path)
            if os.path.exists(png_path):
                icon = tk.PhotoImage(file=png_path)
                scale = max(1, math.ceil(max(icon.width(), icon.height()) / 256))
                self.app_icon_image = icon.subsample(scale, scale)
                self.iconphoto(True, self.app_icon_image)
        except Exception:
            pass

    def _load_sprite_image(self, sprite_path: Optional[str]) -> Optional[Any]:
        if not sprite_path:
            return None
        path = resolve_project_path(sprite_path)
        if path in self.sprite_cache:
            return self.sprite_cache[path]
        if path.startswith("http://") or path.startswith("https://") or not os.path.exists(path):
            return None
        try:
            if Image is not None and ImageTk is not None:
                image = Image.open(path).convert("RGBA")
                resample = getattr(Image, "Resampling", Image).NEAREST
                image.thumbnail((80, 80), resample)
                photo = ImageTk.PhotoImage(image)
            else:
                photo = tk.PhotoImage(file=path)
            self.sprite_cache[path] = photo
            return photo
        except Exception:
            return None

    def _set_opponent_sprite(self, opponent_name: str) -> None:
        image = self._load_sprite_image(get_pokemon_sprite(opponent_name, self.data))
        self.current_sprite_image = image
        if image is not None:
            self.sprite_label.configure(image=image, text="", bg=UI["panel"])
        else:
            self.sprite_label.configure(image="", text="?", bg=UI["panel"], fg=UI["muted"])

    def _initial_log(self) -> None:
        missing = []
        for name, mod in [("mss", mss), ("opencv-python", cv2), ("numpy", np), ("Pillow", Image), ("pytesseract", pytesseract)]:
            if mod is None:
                missing.append(name)
        if missing:
            self.log("누락 패키지: " + ", ".join(missing))
            self.log("설치: pip install mss opencv-python pillow pytesseract pygetwindow")
        if self.tesseract_path:
            self.log(f"Tesseract OCR: {self.tesseract_path}")
            tessdata_dir = find_tessdata_dir()
            if tessdata_dir:
                self.log(f"Tesseract tessdata: {tessdata_dir}")
            langs = ", ".join(sorted(available_tesseract_languages()))
            if langs:
                self.log(f"Tesseract languages: {langs}")
        else:
            self.log("Tesseract OCR 엔진을 찾지 못했습니다.")
        self.log("기본 데이터는 샘플입니다. 모든 포켓몬/기술을 쓰려면 JSON으로 확장하세요.")

    def _update_footer(self) -> None:
        if not hasattr(self, "footer_var"):
            return
        self.footer_var.set(
            f"{self.tr('footer_generation')}: {self.gen_var.get()}    "
            f"{self.tr('game_profile')}: {self.game_profile_var.get()}    "
            f"{self.tr('footer_data')}: {language_display(self.language_var.get())}    "
            f"{self.tr('footer_ocr')}: {self.ocr_preset_var.get()}"
        )

    def log(self, msg: str) -> None:
        def append() -> None:
            stamp = time.strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{stamp}] {msg}\n")
            self.log_text.see("end")
        if hasattr(self, "log_text"):
            self.after(0, append)

    def _toggle_topmost(self) -> None:
        self.attributes("-topmost", bool(self.always_top_var.get()))

    def _sync_ocr_vars_from_settings(self) -> None:
        if not hasattr(self, "ocr_threshold_var"):
            return
        ocr = self.settings.get("ocr", {})
        self.ocr_threshold_var.set(int(ocr.get("threshold", DEFAULT_SETTINGS["ocr"]["threshold"])))
        self.ocr_white_min_var.set(int(ocr.get("white_min_value", DEFAULT_SETTINGS["ocr"]["white_min_value"])))
        self.ocr_sat_max_var.set(int(ocr.get("white_max_saturation", DEFAULT_SETTINGS["ocr"]["white_max_saturation"])))
        self.ocr_delta_var.set(int(ocr.get("white_channel_delta", DEFAULT_SETTINGS["ocr"]["white_channel_delta"])))

    def _save_game_profile(self, profile_key: Optional[str] = None) -> None:
        self._sync_ocr_filter_settings()
        key = profile_key or game_profile_key_from_label(self.game_profile_var.get())
        profiles = self.user_settings.setdefault("profiles_by_game", {})
        profiles[key] = generation_profile_from_settings(self.settings)

    def _load_game_profile(self, profile_key: str) -> bool:
        generation = game_profile_generation(profile_key)
        profile = self.user_settings.get("profiles_by_game", {}).get(profile_key)
        if not profile:
            profile = self.user_settings.get("profiles_by_generation", {}).get(str(generation))
        if not profile:
            return False
        apply_generation_profile_to_settings(self.settings, profile)
        self._sync_ocr_vars_from_settings()
        self._load_roi_to_vars()
        self.log(f"{game_profile_label(profile_key)} ROI/OCR profile loaded")
        return True

    def _on_generation_changed(self) -> None:
        if getattr(self, "_updating_profile_vars", False):
            self._update_footer()
            return
        try:
            new_generation = int(self.gen_var.get())
        except Exception:
            return
        if new_generation == getattr(self, "active_generation", new_generation):
            self._update_footer()
            return
        self._save_game_profile(self.active_game_profile)
        self.active_generation = new_generation
        next_profile = default_game_profile_for_generation(new_generation)
        self.active_game_profile = next_profile
        self.settings["game_profile"] = next_profile
        self._updating_profile_vars = True
        self.game_profile_var.set(game_profile_label(next_profile))
        self._updating_profile_vars = False
        loaded = self._load_game_profile(next_profile)
        if not loaded:
            self.log(f"{game_profile_label(next_profile)} saved ROI/OCR profile not found; keeping current settings")
        self.settings["generation"] = new_generation
        self._refresh_effects()
        self._update_footer()

    def _on_game_profile_changed(self) -> None:
        if getattr(self, "_updating_profile_vars", False):
            self._update_footer()
            return
        new_profile = game_profile_key_from_label(self.game_profile_var.get())
        if new_profile == getattr(self, "active_game_profile", new_profile):
            self._update_footer()
            return
        self._save_game_profile(self.active_game_profile)
        self.active_game_profile = new_profile
        new_generation = game_profile_generation(new_profile)
        self.settings["game_profile"] = new_profile
        self.settings["generation"] = new_generation
        self.active_generation = new_generation
        self._updating_profile_vars = True
        self.gen_var.set(new_generation)
        self._updating_profile_vars = False
        loaded = self._load_game_profile(new_profile)
        if not loaded:
            self.log(f"{game_profile_label(new_profile)} saved ROI/OCR profile not found; keeping current settings")
        self._refresh_effects()
        self._update_footer()

    def _save_current_generation_profile_ui(self) -> None:
        self._save_game_profile(game_profile_key_from_label(self.game_profile_var.get()))
        self._persist_settings()
        self.log(f"{self.game_profile_var.get()} ROI/OCR profile saved")

    def _load_current_generation_profile_ui(self) -> None:
        profile_key = game_profile_key_from_label(self.game_profile_var.get())
        if self._load_game_profile(profile_key):
            self._refresh_effects()
            self._update_footer()
        else:
            messagebox.showinfo(APP_NAME, f"No saved ROI/OCR profile for {self.game_profile_var.get()}.")

    def _persist_settings(self) -> None:
        self._apply_source_setting()
        self.settings["generation"] = int(self.gen_var.get())
        self.settings["game_profile"] = game_profile_key_from_label(self.game_profile_var.get())
        self.settings["scan_interval_ms"] = max(100, int(self.scan_interval_var.get()))
        self.settings["speed_profile"] = speed_profile_key_from_label(self.speed_profile_var.get())
        self.settings["ocr"]["lang"] = self.ocr_lang_var.get()
        self.settings["system_language"] = self._system_language_code()
        self._sync_ocr_filter_settings()
        self._save_game_profile(self.settings["game_profile"])
        roi_by_source = self.user_settings.get("roi_by_source", {})
        roi_by_source[self.source_var.get()] = deep_copy(self.settings["roi"])
        self.user_settings["roi_by_source"] = roi_by_source
        save_user_settings(self.settings, self.language_var.get())
        try:
            with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            payload["roi_by_source"] = roi_by_source
            payload["profiles_by_game"] = self.user_settings.get("profiles_by_game", {})
            payload["profiles_by_generation"] = self.user_settings.get("profiles_by_generation", {})
            with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_close(self) -> None:
        self._persist_settings()
        self.destroy()

    def _save_settings_snapshot(self) -> None:
        self._persist_settings()
        try:
            os.makedirs(os.path.dirname(SETTINGS_SNAPSHOT_PATH), exist_ok=True)
            payload = load_user_settings()
            payload["snapshot_saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(SETTINGS_SNAPSHOT_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.log(f"설정 스냅샷 저장: {SETTINGS_SNAPSHOT_PATH}")
            messagebox.showinfo(APP_NAME, f"설정 스냅샷을 저장했습니다.\n{SETTINGS_SNAPSHOT_PATH}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"설정 스냅샷 저장 실패:\n{exc}")

    def _restore_settings_snapshot(self) -> None:
        if not os.path.exists(SETTINGS_SNAPSHOT_PATH):
            messagebox.showinfo(APP_NAME, "저장된 설정 스냅샷이 없습니다.")
            return
        try:
            with open(SETTINGS_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            os.makedirs(os.path.dirname(USER_SETTINGS_PATH), exist_ok=True)
            payload.pop("snapshot_saved_at", None)
            with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.log("설정 스냅샷 복원 완료. 앱을 다시 시작하면 완전히 적용됩니다.")
            messagebox.showinfo(APP_NAME, "설정 스냅샷을 복원했습니다.\n앱을 다시 시작하면 완전히 적용됩니다.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"설정 스냅샷 복원 실패:\n{exc}")

    def _change_system_language(self) -> None:
        current_profile = speed_profile_key_from_label(self.speed_profile_var.get())
        self.settings["system_language"] = self._system_language_code()
        self.speed_profile_var.set(speed_profile_label(current_profile, self._system_language_code()))
        self._persist_settings()
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.destroy()
            self.settings_window = None
        self._rebuild_main_ui()

    def _rebuild_main_ui(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._build_ui()
        self._refresh_effects()

    def _open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        win = tk.Toplevel(self)
        self.settings_window = win
        win.title(self.tr("settings_title"))
        win.geometry("720x640")
        win.minsize(560, 420)
        win.configure(bg=UI["bg"])
        win.transient(self)
        win.attributes("-topmost", bool(self.always_top_var.get()))
        win.protocol("WM_DELETE_WINDOW", lambda: self._close_settings(win))

        body = ttk.Frame(win, padding=12, style="App.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        canvas = tk.Canvas(body, bg=UI["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, style="App.TFrame")
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(content_window, width=event.width))
        canvas.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(-1 * (event.delta // 120), "units")))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))
        content.columnconfigure(0, weight=1)

        general = ttk.Frame(content, padding=14, style="Panel.TFrame")
        general.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        general.columnconfigure(1, weight=1)
        general.columnconfigure(3, weight=1)
        ttk.Label(general, text=self.tr("general"), style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        ttk.Label(general, text=self.tr("system_language"), style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(general, textvariable=self.system_language_var, values=list(SYSTEM_LANGUAGES.values()), state="readonly").grid(row=1, column=1, sticky="ew")
        ttk.Button(general, text=self.tr("apply"), command=self._change_system_language).grid(row=1, column=2, sticky="ew", padx=(12, 6))
        ttk.Label(general, text=self.tr("generation"), style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Combobox(general, textvariable=self.gen_var, values=list(range(1, 10)), width=8, state="readonly").grid(row=2, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(general, text=self.tr("speed_profile"), style="Panel.TLabel").grid(row=2, column=2, sticky="e", padx=(12, 8), pady=(8, 0))
        ttk.Combobox(general, textvariable=self.speed_profile_var, values=speed_profile_values(self._system_language_code()), state="readonly").grid(row=2, column=3, sticky="ew", pady=(8, 0))
        ttk.Label(general, text=self.tr("game_profile"), style="Panel.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Combobox(general, textvariable=self.game_profile_var, values=game_profile_values(), state="readonly").grid(row=3, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Label(general, text=self.tr("scan_interval"), style="Panel.TLabel").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Spinbox(general, from_=100, to=5000, increment=100, textvariable=self.scan_interval_var, width=8).grid(row=4, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(general, text=self.tr("save_gen_profile"), command=self._save_current_generation_profile_ui).grid(row=4, column=2, sticky="ew", padx=(12, 6), pady=(8, 0))
        ttk.Button(general, text=self.tr("load_gen_profile"), command=self._load_current_generation_profile_ui).grid(row=4, column=3, sticky="ew", pady=(8, 0))
        """
        ttk.Label(general, text="세대", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(general, textvariable=self.gen_var, values=list(range(1, 10)), width=8, state="readonly").grid(row=1, column=1, sticky="ew")
        ttk.Label(general, text="스피드 기준", style="Panel.TLabel").grid(row=1, column=2, sticky="e", padx=(12, 8))
        ttk.Combobox(general, textvariable=self.speed_profile_var, values=speed_profile_values(self._system_language_code()), state="readonly").grid(row=1, column=3, sticky="ew")
        ttk.Label(general, text="캡처 주기(ms)", style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Spinbox(general, from_=100, to=5000, increment=100, textvariable=self.scan_interval_var, width=8).grid(row=2, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(general, text="현재 세대 ROI/OCR 저장", command=self._save_current_generation_profile_ui).grid(row=2, column=2, sticky="ew", padx=(12, 6), pady=(8, 0))
        ttk.Button(general, text="현재 세대 불러오기", command=self._load_current_generation_profile_ui).grid(row=2, column=3, sticky="ew", pady=(8, 0))
        """

        capture_box = ttk.Frame(content, padding=14, style="Panel.TFrame")
        capture_box.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        capture_box.columnconfigure(1, weight=1)
        ttk.Label(capture_box, text=self.tr("capture"), style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        ttk.Label(capture_box, text=self.tr("capture_help"), style="PanelMuted.TLabel").grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        ttk.Label(capture_box, text=self.tr("capture_target"), style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8))
        self.source_display_var.set(display_source(self.source_var.get()))
        self.source_combo = ttk.Combobox(capture_box, textvariable=self.source_display_var, values=available_source_labels(), state="readonly")
        self.source_combo.grid(row=2, column=1, sticky="ew")
        ttk.Button(capture_box, text=self.tr("refresh_list"), command=self._refresh_sources).grid(row=2, column=2, sticky="ew", padx=(8, 0))
        ttk.Button(capture_box, text=self.tr("roi_preview"), command=self._show_roi_preview).grid(row=2, column=3, sticky="ew", padx=(8, 0))
        ttk.Button(capture_box, text=self.tr("roi_auto"), command=self._auto_calibrate_roi).grid(row=3, column=3, sticky="ew", padx=(8, 0), pady=(8, 0))

        language = ttk.Frame(content, padding=14, style="Panel.TFrame")
        language.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        language.columnconfigure(1, weight=1)
        ttk.Label(language, text=self.tr("data_language"), style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        ttk.Label(
            language,
            text=self.tr("data_help"),
            style="PanelMuted.TLabel",
            wraplength=500,
            justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        ttk.Label(language, text=self.tr("data_json"), style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8))
        self.language_combo = ttk.Combobox(
            language,
            textvariable=self.language_var,
            values=list(self.language_packs.keys()) or ["Embedded Korean/English"],
            state="readonly",
        )
        self.language_combo.grid(row=2, column=1, sticky="ew")
        ttk.Button(language, text=self.tr("apply_language"), command=self._change_language_pack).grid(row=2, column=2, sticky="ew", padx=(8, 0))

        ocr_box = ttk.Frame(content, padding=14, style="Panel.TFrame")
        ocr_box.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ocr_box.columnconfigure(1, weight=1)
        ttk.Label(ocr_box, text="OCR", style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        ttk.Label(ocr_box, text=self.tr("game_language"), style="PanelMuted.TLabel", wraplength=500, justify="left").grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        ttk.Label(ocr_box, text=self.tr("game_language"), style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(ocr_box, textvariable=self.ocr_preset_var, values=list(OCR_PRESETS.keys()), state="readonly").grid(row=2, column=1, sticky="ew")
        ttk.Button(ocr_box, text=self.tr("apply"), command=self._apply_ocr_lang).grid(row=2, column=2, sticky="ew", padx=(8, 0))
        ttk.Label(ocr_box, text=self.tr("white_brightness"), style="Panel.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Spinbox(ocr_box, from_=0, to=255, textvariable=self.ocr_white_min_var, width=8, command=self._sync_ocr_filter_settings).grid(row=3, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(ocr_box, text=self.tr("sat_limit"), style="Panel.TLabel").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Spinbox(ocr_box, from_=0, to=255, textvariable=self.ocr_sat_max_var, width=8, command=self._sync_ocr_filter_settings).grid(row=4, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(ocr_box, text=self.tr("rgb_delta"), style="Panel.TLabel").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Spinbox(ocr_box, from_=0, to=255, textvariable=self.ocr_delta_var, width=8, command=self._sync_ocr_filter_settings).grid(row=5, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(ocr_box, text=self.tr("base_threshold"), style="Panel.TLabel").grid(row=6, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Spinbox(ocr_box, from_=0, to=255, textvariable=self.ocr_threshold_var, width=8, command=self._sync_ocr_filter_settings).grid(row=6, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(ocr_box, text=self.tr("preprocess_preview"), command=self._show_roi_preview).grid(row=6, column=2, sticky="ew", padx=(8, 0), pady=(8, 0))

        roi = ttk.Frame(content, padding=14, style="Panel.TFrame")
        roi.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        roi.columnconfigure(1, weight=1)
        ttk.Label(roi, text=self.tr("roi_coords"), style="PanelTitle.TLabel").grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 8))
        ttk.Label(
            roi,
            text=self.tr("roi_help"),
            style="Panel.TLabel",
            wraplength=500,
            justify="left",
        ).grid(row=1, column=0, columnspan=6, sticky="ew", pady=(0, 8))
        self.roi_name_var = tk.StringVar(value="opponent_name")
        self.roi_vars = {key: tk.IntVar(value=self.settings["roi"]["opponent_name"][key]) for key in ("x", "y", "w", "h")}
        ttk.Label(roi, text=self.tr("area"), style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(roi, textvariable=self.roi_name_var, values=list(self.settings["roi"].keys()), state="readonly").grid(row=2, column=1, columnspan=5, sticky="ew")
        for col, key in enumerate(("x", "y", "w", "h")):
            ttk.Label(roi, text=key, style="Panel.TLabel").grid(row=3, column=col, sticky="w", pady=(8, 0), padx=(0, 4))
            ttk.Spinbox(roi, from_=0, to=9999, textvariable=self.roi_vars[key], width=8, command=self._save_roi_from_vars).grid(row=4, column=col, sticky="ew", padx=(0, 8))
        ttk.Button(roi, text=self.tr("apply_roi"), command=self._save_roi_from_vars).grid(row=4, column=4, columnspan=2, sticky="ew")
        self.roi_name_var.trace_add("write", lambda *_: self._load_roi_to_vars())

        files = ttk.Frame(content, padding=14, style="Panel.TFrame")
        files.grid(row=5, column=0, sticky="ew")
        for col in range(5):
            files.columnconfigure(col, weight=1)
        ttk.Button(files, text=self.tr("load_json"), command=self._load_json).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(files, text=self.tr("export_data"), command=self._export_json).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(files, text=self.tr("snapshot_save"), command=self._save_settings_snapshot).grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(files, text=self.tr("snapshot_restore"), command=self._restore_settings_snapshot).grid(row=0, column=3, sticky="ew", padx=6)
        ttk.Button(files, text=self.tr("install_help"), command=self._show_install_help).grid(row=0, column=4, sticky="ew", padx=(6, 0))

    def _close_settings(self, win: tk.Toplevel) -> None:
        self._apply_source_setting()
        self._apply_ocr_lang()
        self.settings["scan_interval_ms"] = max(100, int(self.scan_interval_var.get()))
        self.settings["speed_profile"] = speed_profile_key_from_label(self.speed_profile_var.get())
        self._refresh_effects()
        self._update_footer()
        self._persist_settings()
        win.destroy()
        self.settings_window = None

    def _apply_ocr_lang(self) -> None:
        selected = self.ocr_preset_var.get().strip()
        value = OCR_PRESETS.get(selected, self.ocr_lang_var.get().strip() or self.data.get("ocr_lang", "kor"))
        self.settings["ocr"]["lang"] = value
        self.ocr_lang_var.set(value)
        self._sync_ocr_filter_settings()
        self._update_footer()
        self.log(f"OCR language set: {value}")

    def _sync_ocr_filter_settings(self) -> None:
        self.settings.setdefault("ocr", {})
        if hasattr(self, "ocr_threshold_var"):
            self.settings["ocr"]["threshold"] = max(0, min(255, int(self.ocr_threshold_var.get())))
        if hasattr(self, "ocr_white_min_var"):
            self.settings["ocr"]["white_min_value"] = max(0, min(255, int(self.ocr_white_min_var.get())))
        if hasattr(self, "ocr_sat_max_var"):
            self.settings["ocr"]["white_max_saturation"] = max(0, min(255, int(self.ocr_sat_max_var.get())))
        if hasattr(self, "ocr_delta_var"):
            self.settings["ocr"]["white_channel_delta"] = max(0, min(255, int(self.ocr_delta_var.get())))

    def _refresh_sources(self) -> None:
        if hasattr(self, "source_combo") and self.source_combo.winfo_exists():
            self.source_combo.configure(values=available_source_labels())
        self.log("캡처 소스 목록을 새로고침했습니다.")

    def _capture_dependencies_ready(self) -> bool:
        missing = []
        if mss is None:
            missing.append("mss")
        if np is None:
            missing.append("numpy")
        if pytesseract is None or not self.tesseract_path:
            missing.append("Tesseract OCR")
        if missing:
            msg = "화면 캡처 패키지가 없어 스캔을 시작할 수 없습니다: " + ", ".join(missing)
            self.status_var.set("스캔 실패: 캡처 패키지 없음")
            self.log(msg)
            messagebox.showerror(APP_NAME, msg + "\n\n설치:\npip install mss numpy")
            return False
        self.settings["ocr"]["lang"] = self.ocr_lang_var.get().strip() or self.settings["ocr"].get("lang", "kor")
        missing_langs = missing_tesseract_languages(self.settings["ocr"]["lang"])
        if missing_langs:
            searched = "\n".join(tessdata_dirs())
            msg = (
                "Tesseract OCR language data is missing: "
                + ", ".join(missing_langs)
                + "\n\nPut .traineddata files in one of these folders:\n"
                + searched
            )
            self.status_var.set("OCR language data missing")
            self.log(msg.replace("\n", " / "))
            messagebox.showerror(APP_NAME, msg)
            return False
        return True

    def _canonical_pokemon_name(self, text: str) -> Optional[str]:
        if text in self.data["pokemon_types"]:
            return text
        matches = best_matches(text, self.data["pokemon_types"].keys(), limit=1, cutoff=0.75)
        return matches[0] if matches else None

    def _canonical_move_name(self, text: str) -> Optional[str]:
        if text in self.data["moves"]:
            return text
        match, score = best_match_with_score(text, self.data["moves"].keys(), cutoff=0.78)
        return match if match and score >= 0.78 else None

    def _add_visual_sample(self, category: str, label: str, roi_hash: str) -> bool:
        items = self.visual_samples.setdefault(category, [])
        for item in items:
            if item.get("label") == label and hash_similarity(str(item.get("hash", "")), roi_hash) >= 0.97:
                return False
        items.append({"label": label, "hash": roi_hash, "source": self.source_var.get(), "created": time.time()})
        if len(items) > 300:
            del items[:-300]
        return True

    def _learn_visual_samples(self) -> None:
        if not self._capture_dependencies_ready():
            return
        try:
            frame = self.capture.capture(self.settings)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"현재 화면 캡처 실패:\n{exc}")
            return
        learned = []
        opponent = self._canonical_pokemon_name(self.manual_opponent_var.get().strip())
        if opponent:
            roi_hash = image_hash_from_roi(frame, self.settings["roi"]["opponent_name"])
            if roi_hash and self._add_visual_sample("pokemon", opponent, roi_hash):
                learned.append(f"상대={opponent}")
        for idx, var in enumerate(self.move_vars, start=1):
            move = self._canonical_move_name(var.get().strip())
            if not move:
                continue
            roi_hash = image_hash_from_roi(frame, self.settings["roi"][f"move_{idx}"])
            if roi_hash and self._add_visual_sample("moves", move, roi_hash):
                learned.append(f"기술{idx}={move}")
        if learned:
            save_visual_samples(self.visual_samples)
            self.log("시각 샘플 저장: " + ", ".join(learned))
            self.status_var.set("현재 화면 기억 완료")
        else:
            self.log("시각 샘플 저장 안 됨: 수동 입력값이 비었거나 이미 같은 샘플이 있습니다.")
            messagebox.showinfo(APP_NAME, "상대 포켓몬/기술명을 먼저 정확히 입력한 뒤 다시 눌러주세요.")

    def _frame_to_preview_image(self, frame: Any) -> Optional[Any]:
        if Image is None or ImageDraw is None or np is None:
            return None
        if frame is None:
            return None
        try:
            arr = frame
            if arr.shape[-1] == 4:
                arr = arr[:, :, [2, 1, 0, 3]]
                image = Image.fromarray(arr, "RGBA")
            else:
                arr = arr[:, :, [2, 1, 0]]
                image = Image.fromarray(arr, "RGB")
            draw = ImageDraw.Draw(image, "RGBA")
            colors = {
                "opponent_name": (53, 208, 100, 230),
                "opponent_level_status": (94, 200, 232, 230),
                "move_1": (255, 208, 46, 230),
                "move_2": (255, 138, 40, 230),
                "move_3": (255, 98, 95, 230),
                "move_4": (176, 111, 255, 230),
            }
            for name, roi in self.settings["roi"].items():
                x, y, w, h = [int(roi[k]) for k in ("x", "y", "w", "h")]
                color = colors.get(name, (255, 255, 255, 220))
                draw.rectangle((x, y, x + w, y + h), outline=color, width=4)
                draw.rectangle((x, max(0, y - 22), x + 210, y), fill=(0, 0, 0, 160))
                draw.text((x + 5, max(0, y - 19)), name, fill=color)
            image.thumbnail((980, 620), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image) if ImageTk is not None else None
        except Exception as exc:
            self.log(f"ROI 미리보기 생성 실패: {exc}")
            return None

    def _roi_crop_preview_image(self, frame: Any, roi_name: str, processed: bool = False) -> Optional[Any]:
        if Image is None or ImageTk is None or cv2 is None or np is None:
            return None
        roi = self.settings["roi"].get(roi_name)
        if not roi:
            return None
        crop = self.ocr._crop_roi(frame, roi)
        if crop is None:
            return None
        try:
            if processed:
                self._sync_ocr_filter_settings()
                images = self.ocr._white_text_ocr_images(crop, self.settings.get("ocr", {}), scale=5)
                if not images:
                    return None
                image = Image.fromarray(images[0]).convert("RGB")
            else:
                image = Image.fromarray(crop[:, :, [2, 1, 0]], "RGB")
                if image.width < 240:
                    scale = max(1, 240 // max(1, image.width))
                    image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
            image.thumbnail((520, 180), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)
        except Exception as exc:
            self.log(f"OCR 전처리 미리보기 실패: {exc}")
            return None

    def _show_roi_preview(self) -> None:
        self._apply_source_setting()
        self._sync_ocr_filter_settings()
        try:
            frame = self.capture.capture(self.settings)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"캡처 실패:\n{exc}")
            return
        preview = self._frame_to_preview_image(frame)
        if preview is None:
            messagebox.showerror(APP_NAME, "ROI 미리보기를 표시하려면 pillow/numpy가 필요합니다.")
            return
        win = tk.Toplevel(self)
        win.title("ROI 미리보기")
        win.configure(bg=UI["bg"])
        win.attributes("-topmost", bool(self.always_top_var.get()))
        label = tk.Label(win, image=preview, bg=UI["bg"])
        label.image = preview
        label.pack(padx=12, pady=12)
        ttk.Label(
            win,
            text="색상 박스가 OCR 대상 영역입니다. 아래 전처리 결과는 OCR에 실제로 들어가는 흰 글씨 분리 이미지입니다.",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        tool = ttk.Frame(win, padding=12, style="Panel.TFrame")
        tool.pack(fill="x", padx=12, pady=(0, 12))
        tool.columnconfigure(1, weight=1)
        tool.columnconfigure(3, weight=1)
        selected_roi = tk.StringVar(value=getattr(self, "roi_name_var", tk.StringVar(value="move_1")).get() if hasattr(self, "roi_name_var") else "move_1")
        if selected_roi.get() not in self.settings["roi"]:
            selected_roi.set("move_1")
        ttk.Label(tool, text="전처리 ROI", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(tool, textvariable=selected_roi, values=list(self.settings["roi"].keys()), state="readonly").grid(row=0, column=1, sticky="ew", padx=(0, 12))
        ttk.Label(tool, text="밝기", style="Panel.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Spinbox(tool, from_=0, to=255, textvariable=self.ocr_white_min_var, width=7).grid(row=0, column=3, sticky="ew")
        ttk.Label(tool, text="채도 상한", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Spinbox(tool, from_=0, to=255, textvariable=self.ocr_sat_max_var, width=7).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(8, 0))
        ttk.Label(tool, text="RGB 차이", style="Panel.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 8), pady=(8, 0))
        ttk.Spinbox(tool, from_=0, to=255, textvariable=self.ocr_delta_var, width=7).grid(row=1, column=3, sticky="ew", pady=(8, 0))

        compare = ttk.Frame(win, padding=(12, 0, 12, 8), style="App.TFrame")
        compare.pack(fill="x")
        compare.columnconfigure(0, weight=1)
        compare.columnconfigure(1, weight=1)
        ttk.Label(compare, text="원본 ROI", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(compare, text="흰 글씨 분리 결과", style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=(10, 0))
        original_label = tk.Label(compare, bg=UI["bg"])
        original_label.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(4, 0))
        processed_label = tk.Label(compare, bg=UI["bg"])
        processed_label.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(4, 0))
        ocr_text_var = tk.StringVar(value="")
        ttk.Label(win, textvariable=ocr_text_var, style="Muted.TLabel", wraplength=900).pack(anchor="w", padx=12, pady=(0, 8))

        def refresh_processed() -> None:
            self._sync_ocr_filter_settings()
            roi_name = selected_roi.get()
            original = self._roi_crop_preview_image(frame, roi_name, processed=False)
            processed = self._roi_crop_preview_image(frame, roi_name, processed=True)
            if original is not None:
                original_label.configure(image=original)
                original_label.image = original
            if processed is not None:
                processed_label.configure(image=processed)
                processed_label.image = processed
            if roi_name == "opponent_level_status":
                level = self.ocr.digits_from_roi(frame, self.settings["roi"][roi_name], self.settings)
                ocr_text_var.set("숫자 OCR 결과: " + (level or "-"))
            else:
                variants = self.ocr.text_variants_from_roi(frame, self.settings["roi"][roi_name], self.settings)[:5]
                ocr_text_var.set("OCR 후보: " + (" / ".join(variants) if variants else "-"))

        actions = ttk.Frame(win, style="App.TFrame")
        actions.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(actions, text="전처리 갱신", command=refresh_processed).pack(side="left")
        ttk.Button(actions, text="설정 저장", command=lambda: (self._sync_ocr_filter_settings(), self._persist_settings(), self.log("OCR 전처리 설정 저장"))).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="닫기", command=win.destroy).pack(side="right")
        selected_roi.trace_add("write", lambda *_: refresh_processed())
        refresh_processed()

    def _frame_to_calibration_image(self, frame: Any, candidates: List[RoiCandidate], proposed_rois: Dict[str, Dict[str, int]]) -> Optional[Any]:
        if Image is None or ImageDraw is None or np is None:
            return None
        try:
            arr = frame
            if arr.shape[-1] == 4:
                arr = arr[:, :, [2, 1, 0, 3]]
                image = Image.fromarray(arr, "RGBA")
            else:
                arr = arr[:, :, [2, 1, 0]]
                image = Image.fromarray(arr, "RGB")
            draw = ImageDraw.Draw(image, "RGBA")
            for candidate in candidates[:20]:
                draw.rectangle(
                    (candidate.x, candidate.y, candidate.x + candidate.w, candidate.y + candidate.h),
                    outline=(255, 255, 255, 80),
                    width=1,
                )
            colors = {
                "opponent_name": (53, 208, 100, 240),
                "opponent_level_status": (94, 200, 232, 240),
                "move_1": (255, 208, 46, 240),
                "move_2": (255, 138, 40, 240),
                "move_3": (255, 98, 95, 240),
                "move_4": (176, 111, 255, 240),
            }
            for name, roi in proposed_rois.items():
                x, y, w, h = [int(roi[k]) for k in ("x", "y", "w", "h")]
                color = colors.get(name, (53, 208, 100, 240))
                draw.rectangle((x, y, x + w, y + h), outline=color, width=5)
                draw.rectangle((x, max(0, y - 24), x + 220, y), fill=(0, 0, 0, 170))
                draw.text((x + 5, max(0, y - 20)), name, fill=color)
            image.thumbnail((980, 620), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image) if ImageTk is not None else None
        except Exception as exc:
            self.log(f"자동 보정 미리보기 실패: {exc}")
            return None

    def _frame_to_editor_base_image(self, frame: Any, max_width: int = 980, max_height: int = 620) -> Optional[Tuple[Any, float]]:
        if Image is None or ImageTk is None or np is None:
            return None
        try:
            arr = frame
            if arr.shape[-1] == 4:
                arr = arr[:, :, [2, 1, 0, 3]]
                image = Image.fromarray(arr, "RGBA")
            else:
                arr = arr[:, :, [2, 1, 0]]
                image = Image.fromarray(arr, "RGB")
            scale = min(max_width / image.width, max_height / image.height, 1.0)
            if scale < 1.0:
                image = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image), scale
        except Exception as exc:
            self.log(f"ROI 편집 이미지 생성 실패: {exc}")
            return None

    def _auto_calibrate_roi(self) -> None:
        if not self._capture_dependencies_ready():
            return
        self._apply_source_setting()
        try:
            frame = self.capture.capture(self.settings)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"캡처 실패:\n{exc}")
            return
        height, width = frame.shape[:2]
        candidates = detect_ui_box_candidates(frame)
        proposals: List[Tuple[str, Dict[str, Dict[str, int]]]] = []
        detected = infer_battle_rois_from_candidates(candidates, width, height)
        if detected is not None:
            proposals.append(("OpenCV 후보 탐지", detected))
        proposals.append(("기본 좌표 스케일링", scaled_default_rois(width, height)))
        proposals.append(("현재 ROI", {name: clamp_roi(roi, width, height) for name, roi in self.settings["roi"].items()}))
        method, proposed, score, details = self._select_best_roi_proposal(frame, proposals)
        preview = self._frame_to_calibration_image(frame, candidates, proposed)
        if preview is None:
            messagebox.showerror(APP_NAME, "자동 보정 미리보기를 만들 수 없습니다.")
            return
        win = tk.Toplevel(self)
        win.title("ROI 자동 보정")
        win.configure(bg=UI["bg"])
        win.attributes("-topmost", bool(self.always_top_var.get()))
        label = tk.Label(win, image=preview, bg=UI["bg"])
        label.image = preview
        label.pack(padx=12, pady=12)
        detail_text = " / ".join(details[:5]) if details else "OCR 매칭 없음"
        ttk.Label(
            win,
            text=f"방식: {method} / OCR 점수: {score:.1f} / {detail_text}\n박스가 맞으면 적용하세요. 틀리면 다시 캡처하거나 수동 좌표를 조정하세요.",
            style="Muted.TLabel",
            wraplength=900,
        ).pack(anchor="w", padx=12, pady=(0, 10))
        actions = ttk.Frame(win, style="App.TFrame")
        actions.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(actions, text="다시 캡처", command=lambda: (win.destroy(), self._auto_calibrate_roi())).pack(side="left")
        ttk.Button(actions, text="박스 직접 수정", command=lambda: (win.destroy(), self._open_roi_editor(frame, proposed))).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="적용", style="Accent.TButton", command=lambda: self._apply_auto_calibrated_rois(proposed, win)).pack(side="right")

    def _open_roi_editor(self, frame: Any, rois: Dict[str, Dict[str, int]]) -> None:
        base = self._frame_to_editor_base_image(frame)
        if base is None:
            messagebox.showerror(APP_NAME, "ROI 편집 화면을 만들 수 없습니다.")
            return
        image, scale = base
        editable = deep_copy(rois)
        win = tk.Toplevel(self)
        win.title("ROI 박스 직접 수정")
        win.configure(bg=UI["bg"])
        win.attributes("-topmost", bool(self.always_top_var.get()))
        canvas = tk.Canvas(win, width=image.width(), height=image.height(), bg=UI["bg"], highlightthickness=0)
        canvas.image = image
        canvas.pack(padx=12, pady=12)
        canvas.create_image(0, 0, image=image, anchor="nw")
        colors = {
            "opponent_name": "#35d064",
            "opponent_level_status": "#5ec8e8",
            "move_1": "#ffd02e",
            "move_2": "#ff8a28",
            "move_3": "#ff625f",
            "move_4": "#b06fff",
        }
        rect_items: Dict[int, str] = {}
        text_items: Dict[int, str] = {}
        drag_state = {"item": None, "name": None, "mode": "move", "x": 0, "y": 0}

        def redraw() -> None:
            canvas.delete("roi")
            rect_items.clear()
            text_items.clear()
            for name, roi in editable.items():
                x1 = int(roi["x"] * scale)
                y1 = int(roi["y"] * scale)
                x2 = int((roi["x"] + roi["w"]) * scale)
                y2 = int((roi["y"] + roi["h"]) * scale)
                color = colors.get(name, "#ffffff")
                rect = canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=3, tags=("roi",))
                text = canvas.create_text(x1 + 5, max(10, y1 - 10), text=name, anchor="w", fill=color, tags=("roi",), font=(choose_ui_font(), 10, "bold"))
                rect_items[rect] = name
                text_items[text] = name

        def find_roi_at(x: int, y: int) -> Optional[Tuple[str, str]]:
            for name, roi in reversed(list(editable.items())):
                x1 = int(roi["x"] * scale)
                y1 = int(roi["y"] * scale)
                x2 = int((roi["x"] + roi["w"]) * scale)
                y2 = int((roi["y"] + roi["h"]) * scale)
                if x1 <= x <= x2 and y1 <= y <= y2:
                    near_corner = abs(x - x2) <= 12 and abs(y - y2) <= 12
                    return name, "resize" if near_corner else "move"
            return None

        def on_down(event: Any) -> None:
            found = find_roi_at(event.x, event.y)
            if not found:
                return
            name, mode = found
            drag_state.update({"name": name, "mode": mode, "x": event.x, "y": event.y})

        def on_drag(event: Any) -> None:
            name = drag_state.get("name")
            if not name:
                return
            dx = int((event.x - drag_state["x"]) / max(scale, 0.001))
            dy = int((event.y - drag_state["y"]) / max(scale, 0.001))
            if dx == 0 and dy == 0:
                return
            roi = editable[str(name)]
            frame_h, frame_w = frame.shape[:2]
            if drag_state["mode"] == "resize":
                roi["w"] = max(10, roi["w"] + dx)
                roi["h"] = max(10, roi["h"] + dy)
            else:
                roi["x"] += dx
                roi["y"] += dy
            editable[str(name)] = clamp_roi(roi, frame_w, frame_h)
            drag_state["x"] = event.x
            drag_state["y"] = event.y
            redraw()

        def on_up(_event: Any) -> None:
            drag_state.update({"name": None, "mode": "move"})

        canvas.bind("<ButtonPress-1>", on_down)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_up)
        redraw()
        ttk.Label(win, text="박스를 드래그해서 이동하세요. 오른쪽 아래 모서리를 드래그하면 크기가 바뀝니다.", style="Muted.TLabel").pack(anchor="w", padx=12, pady=(0, 8))
        actions = ttk.Frame(win, style="App.TFrame")
        actions.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(actions, text="취소", command=win.destroy).pack(side="left")
        ttk.Button(actions, text="적용", style="Accent.TButton", command=lambda: self._apply_auto_calibrated_rois(editable, win)).pack(side="right")

    def _select_best_roi_proposal(self, frame: Any, proposals: List[Tuple[str, Dict[str, Dict[str, int]]]]) -> Tuple[str, Dict[str, Dict[str, int]], float, List[str]]:
        best_method = proposals[0][0]
        best_rois = proposals[0][1]
        best_score = -1.0
        best_details: List[str] = []
        for method, rois in proposals:
            score, details = self._score_roi_proposal_with_ocr(frame, rois)
            if score > best_score:
                best_method = method
                best_rois = rois
                best_score = score
                best_details = details
        return best_method, best_rois, best_score, best_details

    def _score_roi_proposal_with_ocr(self, frame: Any, rois: Dict[str, Dict[str, int]]) -> Tuple[float, List[str]]:
        if not self.ocr.available():
            return (0.0, ["OCR 패키지 없음"])
        score = 0.0
        details: List[str] = []
        opponent_text = self.ocr.text_from_roi(frame, rois.get("opponent_name", {"x": 0, "y": 0, "w": 1, "h": 1}), self.settings)
        opponent_matches = best_matches(opponent_text, self.data["pokemon_types"].keys(), limit=1, cutoff=0.42)
        if opponent_text:
            score += 0.2
            details.append(f"상대 OCR='{opponent_text}'")
        if opponent_matches:
            score += 3.0
            details.append(f"상대 후보={opponent_matches[0]}")
        for idx in range(1, 5):
            key = f"move_{idx}"
            move_text = self.ocr.text_from_roi(frame, rois.get(key, {"x": 0, "y": 0, "w": 1, "h": 1}), self.settings)
            move_matches = best_matches(move_text, self.data["moves"].keys(), limit=1, cutoff=0.45)
            if move_text:
                score += 0.15
            if move_matches:
                score += 2.0
                details.append(f"기술{idx}={move_matches[0]}")
            elif move_text:
                details.append(f"기술{idx} OCR='{move_text}'")
        return score, details

    def _apply_auto_calibrated_rois(self, rois: Dict[str, Dict[str, int]], win: tk.Toplevel) -> None:
        self.settings["roi"].update(rois)
        self._load_roi_to_vars()
        self.log("ROI 자동 보정 적용: " + json.dumps(rois, ensure_ascii=False))
        self._persist_settings()
        win.destroy()

    def _toggle_scan(self) -> None:
        self.scanning = not self.scanning
        if self.scanning:
            if not self._capture_dependencies_ready():
                self.scanning = False
                if hasattr(self, "scan_button"):
                    self.scan_button.configure(text=self.tr("scan_start"))
                return
            self._apply_source_setting()
            self.settings["scan_interval_ms"] = max(100, int(self.scan_interval_var.get()))
            self.status_var.set(self.tr("scanning"))
            if hasattr(self, "scan_button"):
                self.scan_button.configure(text=self.tr("scan_stop"))
            self.worker = threading.Thread(target=self._scan_loop, daemon=True)
            self.worker.start()
        else:
            self.status_var.set(self.tr("idle"))
            if hasattr(self, "scan_button"):
                self.scan_button.configure(text=self.tr("scan_start"))

    def _apply_source_setting(self) -> None:
        previous_source = self.source_var.get()
        if hasattr(self, "source_display_var"):
            self.source_var.set(source_from_display(self.source_display_var.get().strip()))
        source = self.source_var.get().strip()
        if previous_source and previous_source != source:
            roi_by_source = self.user_settings.get("roi_by_source", {})
            roi_by_source[previous_source] = deep_copy(self.settings["roi"])
            if source in roi_by_source:
                self.settings["roi"] = deep_update(DEFAULT_SETTINGS["roi"], roi_by_source[source])
                self._load_roi_to_vars()
        if source == "monitor" or not source:
            self.settings["capture"]["source"] = "monitor"
            self.settings["capture"]["window_title"] = ""
        else:
            self.settings["capture"]["source"] = "window"
            self.settings["capture"]["window_title"] = source

    def _scan_loop(self) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="ocr") as executor:
            while self.scanning:
                started = time.time()
                try:
                    frame = self.capture.capture(self.settings)
                    settings_snapshot = deep_copy(self.settings)
                    roi = settings_snapshot["roi"]
                    pokemon_choices = tuple(self.data["pokemon_types"].keys())
                    move_choices = tuple(self.data["moves"].keys())

                    opponent_future = executor.submit(
                        self.ocr.best_text_for_choices,
                        frame,
                        roi["opponent_name"],
                        settings_snapshot,
                        pokemon_choices,
                        0.50,
                    )
                    level_future = executor.submit(
                        self.ocr.digits_from_roi,
                        frame,
                        roi["opponent_level_status"],
                        settings_snapshot,
                    )
                    move_futures = [
                        executor.submit(
                            self.ocr.best_text_for_choices,
                            frame,
                            roi[f"move_{i}"],
                            settings_snapshot,
                            move_choices,
                            0.45,
                        )
                        for i in range(1, 5)
                    ]

                    opponent, opponent_match, opponent_score, opponent_variants = opponent_future.result()
                    alias_opponent, alias_opponent_score = best_alias_match(
                        opponent_variants, self.ocr_aliases.get("pokemon", {}), pokemon_choices
                    )
                    if alias_opponent:
                        opponent_match = alias_opponent
                        opponent_score = alias_opponent_score

                    current_opponent = self.current_detection.opponent_match
                    opponent_changed = bool(opponent_match and current_opponent and opponent_match != current_opponent)
                    if opponent_changed:
                        self.last_level_text = ""
                    level_status = level_future.result()
                    if level_status:
                        self.last_level_text = level_status
                    elif self.last_level_text and not opponent_changed:
                        level_status = self.last_level_text
                    self.log(f"OCR 레벨: accepted={level_status or '-'}")

                    move_results = [future.result() for future in move_futures]
                    robust_futures: Dict[int, concurrent.futures.Future[Any]] = {}
                    prepared_moves: List[Tuple[str, Optional[str], float, List[str], Optional[str]]] = []
                    for idx, (text, match, score, variants) in enumerate(move_results):
                        alias_move, alias_score = best_alias_match(variants, self.ocr_aliases.get("moves", {}), move_choices)
                        if alias_move:
                            match = alias_move
                            score = alias_score
                        accepted = match if match and score >= move_match_accept_threshold(text) else None
                        prepared_moves.append((text, match, score, variants, accepted))
                        if accepted is None or len(normalize_name(text)) <= 1:
                            robust_futures[idx] = executor.submit(
                                self.ocr.best_text_for_choices,
                                frame,
                                roi[f"move_{idx + 1}"],
                                settings_snapshot,
                                move_choices,
                                0.45,
                                True,
                            )

                    moves_list = []
                    move_matches = []
                    for idx, (text, match, score, variants, accepted) in enumerate(prepared_moves):
                        if idx in robust_futures:
                            robust_text, robust_match, robust_score, robust_variants = robust_futures[idx].result()
                            if robust_score > score:
                                text, match, score = robust_text, robust_match, robust_score
                            variants = variants + [item for item in robust_variants if item not in variants]
                            accepted = match if match and score >= move_match_accept_threshold(text) else None
                        previous = self.last_move_matches[idx]
                        if accepted is None and previous and normalize_name(text) and normalize_name(text) in normalize_name(previous):
                            accepted = previous
                            match = previous
                            score = max(score, 0.91)
                        if accepted:
                            self.last_move_matches[idx] = accepted
                        moves_list.append(text)
                        move_matches.append(accepted)
                        self.log(f"OCR 기술{idx + 1}: variants={variants[:3]} match={match} score={score:.2f} accepted={accepted}")

                    move_text_count = sum(1 for item in moves_list if normalize_name(item))
                    accepted_move_count = sum(1 for item in move_matches if item)
                    if move_text_count == 0 and accepted_move_count == 0:
                        self.not_battle_frames += 1
                    else:
                        if self.battle_pause_logged:
                            self.log("Battle UI detected again; OCR resume")
                        self.not_battle_frames = 0
                        self.battle_pause_logged = False

                    if self.not_battle_frames >= 4:
                        if not self.battle_pause_logged:
                            self.log("Move UI not detected; waiting for battle screen")
                            self.battle_pause_logged = True
                        self.status_var.set("전투 대기 중")
                        continue

                    result = self._build_detection(opponent, level_status, tuple(moves_list), opponent_match, tuple(move_matches))
                    self.queue.put(result)
                except Exception as exc:
                    self.log(str(exc))
                    self.status_var.set(f"{self.tr('scan_stop')}: " + str(exc)[:80])
                    self.scanning = False
                    self.queue.put(DetectionResult(timestamp=time.time()))
                elapsed = time.time() - started
                interval = max(100, int(self.settings.get("scan_interval_ms", SCAN_INTERVAL_MS))) / 1000
                time.sleep(max(0.1, interval - elapsed))

    def _build_detection(
        self,
        opponent: str,
        level_status: str,
        moves: Tuple[str, str, str, str],
        opponent_match: Optional[str] = None,
        move_matches_override: Optional[Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]] = None,
    ) -> DetectionResult:
        pokemon_candidates = best_matches(opponent, self.data["pokemon_types"].keys(), limit=5)
        if opponent_match and opponent_match not in pokemon_candidates:
            pokemon_candidates = [opponent_match] + pokemon_candidates
        move_matches: List[Optional[str]] = []
        if move_matches_override is not None:
            move_matches = list(move_matches_override)
        else:
            for move in moves:
                match, score = best_match_with_score(move, self.data["moves"].keys(), cutoff=move_match_accept_threshold(move))
                move_matches.append(match if match and score >= move_match_accept_threshold(move) else None)
        return DetectionResult(
            opponent_text=opponent,
            level_status_text=level_status,
            moves_text=moves,
            opponent_match=pokemon_candidates[0] if pokemon_candidates else None,
            opponent_candidates=tuple(pokemon_candidates),
            move_matches=tuple(move_matches),  # type: ignore[arg-type]
            timestamp=time.time(),
        )

    def _poll_queue(self) -> None:
        while True:
            try:
                self.current_detection = self.queue.get_nowait()
            except queue.Empty:
                break
            self._apply_detection_to_inputs(self.current_detection)
            self._refresh_effects()
            self._log_detection(self.current_detection)
            if not self.scanning and hasattr(self, "scan_button"):
                self.scan_button.configure(text=self.tr("scan_start"))
        self.after(200, self._poll_queue)

    def _apply_detection_to_inputs(self, detection: DetectionResult) -> None:
        if self.scanning:
            if detection.opponent_match:
                current = self.manual_opponent_var.get().strip()
                if current != detection.opponent_match:
                    self.manual_opponent_var.set(detection.opponent_match)
        elif detection.opponent_match and not self.manual_opponent_var.get().strip():
            self.manual_opponent_var.set(detection.opponent_match)

        if detection.level_status_text:
            digits = re.findall(r"\d+", detection.level_status_text)
            if digits:
                level = int(digits[0])
                if 1 <= level <= 100:
                    self.opponent_level_var.set(str(level))
        elif self.scanning and self.opponent_level_var.get().strip() == "50":
            self.opponent_level_var.set("")

        for idx, match in enumerate(detection.move_matches):
            if self.scanning:
                if match:
                    if self.move_vars[idx].get().strip() != match:
                        self.move_vars[idx].set(match)
            elif match and not self.move_vars[idx].get().strip():
                self.move_vars[idx].set(match)

    def _log_detection(self, detection: DetectionResult) -> None:
        if detection.timestamp == 0:
            return
        cand = ", ".join(detection.opponent_candidates) or "-"
        moves = " / ".join(detection.moves_text)
        self.log(f"OCR 상대='{detection.opponent_text}' 후보=[{cand}] 레벨/상태='{detection.level_status_text}' 기술='{moves}'")

    def _refresh_effects(self) -> None:
        gen = int(self.gen_var.get())
        opponent_input = self.manual_opponent_var.get().strip()
        opponent_candidates = best_matches(opponent_input, self.data["pokemon_types"].keys(), limit=5)
        opponent_name = opponent_candidates[0] if opponent_candidates else opponent_input
        defender_types = get_pokemon_types(opponent_name, gen, self.data) if opponent_name else None

        if defender_types:
            type_text = "/".join(TYPE_KO.get(t, t) for t in defender_types)
            self.opponent_label.configure(text=f"{self.tr('opponent')}: {opponent_name} ({type_text})")
            self._set_opponent_sprite(opponent_name)
            warning_lines = get_ability_warning_lines(opponent_name, self.data)
            if warning_lines:
                self.ability_warning_label.configure(text=f"{self.tr('warning')}: " + " / ".join(warning_lines))
                self.ability_warning_label.grid()
            else:
                self.ability_warning_label.configure(text="")
                self.ability_warning_label.grid_remove()
            profile_key = speed_profile_key_from_label(self.speed_profile_var.get())
            self.speed_label.configure(text=speed_summary(self.my_speed_var.get(), opponent_name, self.opponent_level_var.get(), profile_key, self.data, self._system_language_code()))
        else:
            self.opponent_label.configure(text=f"{self.tr('opponent')}: {opponent_input or '-'} ({self.tr('type_unknown')})")
            self._set_opponent_sprite("")
            self.ability_warning_label.configure(text="")
            self.ability_warning_label.grid_remove()
            self.speed_label.configure(text=self.tr("speed_unknown"))

        for idx, var in enumerate(self.move_vars):
            raw_move = var.get().strip()
            move_candidates = best_matches(raw_move, self.data["moves"].keys(), limit=1, cutoff=0.48)
            move_name = move_candidates[0] if move_candidates else raw_move
            move_type = get_move_type(move_name, self.data) if move_name else None
            mult = effectiveness(move_type, defender_types, gen, self.data) if move_type and defender_types else None
            bg, fg = effect_style(mult)
            type_label = TYPE_KO.get(move_type, move_type or "?")
            category = get_move_category(move_name, self.data) if move_name else "Unknown"
            category_label = category_label_for_language(category, self._system_language_code())
            display_name = move_name or f"{self.tr('move')} {idx + 1}"
            self.move_name_labels[idx].configure(text=display_name, bg=bg, fg=UI["text"] if mult is not None else UI["muted"])
            self.type_badge_labels[idx].configure(
                text=type_label,
                bg=TYPE_COLORS.get(move_type or "?", UI["field"]),
                fg="#ffffff" if move_type != "Electric" else "#1d1d1d",
            )
            effect_text = format_effect_for_language(mult, self._system_language_code())
            self.effect_result_labels[idx].configure(text=f"{effect_text}  ·  {category_label}", bg=bg, fg=fg)

        if opponent_candidates and opponent_input and opponent_name != opponent_input:
            prefix = {"ko": "상대 후보", "en": "Opponent candidates", "ja": "相手候補"}.get(self._system_language_code(), "상대 후보")
            self.status_var.set(prefix + ": " + ", ".join(opponent_candidates))
        else:
            self.status_var.set(self.tr("scanning") if self.scanning else self.tr("idle"))
        self._update_footer()

    def _load_roi_to_vars(self) -> None:
        if not hasattr(self, "roi_name_var") or not hasattr(self, "roi_vars"):
            return
        selected = self.roi_name_var.get()
        values = self.settings["roi"].get(selected, {})
        for key, var in self.roi_vars.items():
            var.set(int(values.get(key, 0)))

    def _save_roi_from_vars(self) -> None:
        if not hasattr(self, "roi_name_var") or not hasattr(self, "roi_vars"):
            return
        selected = self.roi_name_var.get()
        self.settings["roi"][selected] = {key: int(var.get()) for key, var in self.roi_vars.items()}
        self.log(f"ROI 적용: {selected} = {self.settings['roi'][selected]}")
        self._persist_settings()

    def _load_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if "pokemon_types" in payload or "moves" in payload:
                self.data = merge_language_pack(DATA, payload)
                self.settings["ocr"]["lang"] = self.data.get("ocr_lang", self.settings["ocr"].get("lang", "kor"))
                if hasattr(self, "ocr_lang_var"):
                    self.ocr_lang_var.set(self.settings["ocr"]["lang"])
            if "data" in payload:
                self.data = payload["data"]
            if "settings" in payload:
                self.settings.update(payload["settings"])
                loaded_generation = int(self.settings.get("generation", self.gen_var.get()))
                loaded_profile = str(self.settings.get("game_profile") or default_game_profile_for_generation(loaded_generation))
                if loaded_profile not in GAME_UI_PROFILE_BY_KEY:
                    loaded_profile = default_game_profile_for_generation(loaded_generation)
                self.active_generation = loaded_generation
                self.active_game_profile = loaded_profile
                self._updating_profile_vars = True
                self.gen_var.set(loaded_generation)
                self.game_profile_var.set(game_profile_label(loaded_profile))
                self._updating_profile_vars = False
                self.scan_interval_var.set(int(self.settings.get("scan_interval_ms", SCAN_INTERVAL_MS)))
                speed_profile = self.settings.get("speed_profile", "npc_basic")
                self.speed_profile_var.set(speed_profile_label(speed_profile, self._system_language_code()))
                self.ocr_preset_var.set(OCR_LABEL_BY_CODE.get(self.settings.get("ocr", {}).get("lang", "kor"), self.ocr_preset_var.get()))
            self.log(f"JSON 불러오기 완료: {path}")
            self._load_roi_to_vars()
            self._refresh_effects()
            self._update_footer()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"JSON 불러오기 실패:\n{exc}")

    def _export_json(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        payload = {"data": self.data, "settings": self.settings}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.log(f"JSON 저장 완료: {path}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"JSON 저장 실패:\n{exc}")

    def _show_install_help(self) -> None:
        messagebox.showinfo(
            APP_NAME,
            "필요 패키지:\n"
            "pip install mss opencv-python pillow pytesseract pygetwindow\n\n"
            "OCR 엔진 Tesseract도 별도 설치해야 합니다.\n"
            "Windows는 UB-Mannheim Tesseract 빌드를 권장합니다.\n\n"
            "ROI는 현재 화면 해상도 기준 좌표입니다. DS/GBA/Switch/에뮬레이터마다 "
            "상대 이름, 레벨/상태, 기술 1~4 좌표를 조정하세요.",
        )


def main() -> None:
    app = PokemonBattleLens()
    app.mainloop()


if __name__ == "__main__":
    main()
