"""
Build Pokemon Battle Lens JSON data from PokeAPI.

Outputs:
  data/pokemon_ko.json
  data/pokemon_en.json
  data/pokemon_ja.json
  assets/sprites/0001.png ...

Run:
  python scripts/fetch_pokeapi_data.py
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional


BASE_URL = "https://pokeapi.co/api/v2"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
SPRITE_DIR = os.path.join(ROOT, "assets", "sprites")
CACHE_DIR = os.path.join(ROOT, ".cache", "pokeapi")

LANGS = {
    "ko": {"label": "Korean / 한국어", "ocr_lang": "kor", "name_langs": ["ko", "en"]},
    "en": {"label": "English", "ocr_lang": "eng", "name_langs": ["en"]},
    "ja": {"label": "Japanese / 日本語", "ocr_lang": "jpn", "name_langs": ["ja-Hrkt", "ja", "en"]},
}

GENERATION_NUMBER = {
    "generation-i": "1",
    "generation-ii": "2",
    "generation-iii": "3",
    "generation-iv": "4",
    "generation-v": "5",
    "generation-vi": "6",
    "generation-vii": "7",
    "generation-viii": "8",
    "generation-ix": "9",
}


def ensure_dirs() -> None:
    for path in (DATA_DIR, SPRITE_DIR, CACHE_DIR):
        os.makedirs(path, exist_ok=True)


def fetch_json(endpoint_or_url: str) -> Dict[str, Any]:
    if endpoint_or_url.startswith("http"):
        url = endpoint_or_url
        cache_name = endpoint_or_url.replace("https://", "").replace("http://", "")
    else:
        endpoint = endpoint_or_url.strip("/")
        if "?" in endpoint:
            url = f"{BASE_URL}/{endpoint}"
        else:
            url = f"{BASE_URL}/{endpoint}/"
        cache_name = endpoint_or_url.strip("/")
    safe_cache_name = re.sub(r"[^0-9A-Za-z_.-]+", "__", cache_name)
    cache_path = os.path.join(CACHE_DIR, safe_cache_name + ".json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            os.remove(cache_path)

    last_error: Optional[Exception] = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "PokemonBattleLens/1.0 data generator",
                    "Accept": "application/json,image/png,*/*",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            time.sleep(0.08)
            return payload
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def download_file(url: Optional[str], path: str) -> bool:
    if not url:
        return False
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    for attempt in range(4):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "PokemonBattleLens/1.0 data generator"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            with open(path, "wb") as f:
                f.write(data)
            time.sleep(0.04)
            return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1 + attempt)
    return False


def localized_name(names: Iterable[Dict[str, Any]], lang_codes: List[str], fallback: str) -> str:
    by_lang = {item.get("language", {}).get("name"): item.get("name") for item in names}
    for lang in lang_codes:
        value = by_lang.get(lang)
        if value:
            return value
    return fallback


def type_names(type_slots: Iterable[Dict[str, Any]]) -> List[str]:
    ordered = sorted(type_slots, key=lambda item: item.get("slot", 0))
    return [item["type"]["name"].title() for item in ordered]


def base_stats(stats: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    return {
        item.get("stat", {}).get("name", ""): int(item.get("base_stat", 0))
        for item in stats
        if item.get("stat", {}).get("name")
    }


def localized_ability(ability_url: str, lang_codes: List[str], fallback: str) -> str:
    try:
        ability = fetch_json(ability_url)
        return localized_name(ability.get("names", []), lang_codes, fallback)
    except Exception:
        return fallback


def generation_from_url(url: str) -> Optional[str]:
    name = url.rstrip("/").split("/")[-1]
    return GENERATION_NUMBER.get(name)


def pokemon_type_entry(number: int, species: Dict[str, Any], pokemon: Dict[str, Any], lang_codes: List[str]) -> Dict[str, Any]:
    abilities = []
    for item in sorted(pokemon.get("abilities", []), key=lambda value: value.get("slot", 0)):
        ability = item.get("ability", {})
        ability_id = ability.get("name", "")
        abilities.append({
            "id": ability_id,
            "name": localized_ability(ability.get("url", ""), lang_codes, ability_id),
            "hidden": bool(item.get("is_hidden", False)),
        })
    entry: Dict[str, Any] = {
        "national_number": number,
        "default": type_names(pokemon.get("types", [])),
        "sprite": os.path.join("assets", "sprites", f"{number:04d}.png").replace("\\", "/"),
        "base_stats": base_stats(pokemon.get("stats", [])),
        "abilities": abilities,
    }
    for past in pokemon.get("past_types", []):
        generation = generation_from_url(past.get("generation", {}).get("url", ""))
        if generation:
            entry[generation] = type_names(past.get("types", []))
    return entry


def build_pokemon_data() -> Dict[str, Dict[str, Any]]:
    species_index = fetch_json("pokemon-species?limit=2000")
    rows = species_index.get("results", [])
    output = {code: {} for code in LANGS}
    for idx, row in enumerate(rows, start=1):
        species = fetch_json(row["url"])
        number = int(species["id"])
        if number < 1:
            continue
        pokemon = fetch_json(f"pokemon/{number}")
        sprite_url = pokemon.get("sprites", {}).get("front_default")
        download_file(sprite_url, os.path.join(SPRITE_DIR, f"{number:04d}.png"))
        fallback = species.get("name", f"pokemon-{number}")
        for code, spec in LANGS.items():
            name = localized_name(species.get("names", []), spec["name_langs"], fallback)
            output[code][name] = pokemon_type_entry(number, species, pokemon, spec["name_langs"])
        if idx % 50 == 0:
            print(f"pokemon {idx}/{len(rows)}")
    return output


def build_move_data() -> Dict[str, Dict[str, Dict[str, str]]]:
    move_index = fetch_json("move?limit=2000")
    rows = move_index.get("results", [])
    output = {code: {} for code in LANGS}
    for idx, row in enumerate(rows, start=1):
        move = fetch_json(row["url"])
        move_type = move.get("type", {}).get("name", "").title()
        category = move.get("damage_class", {}).get("name", "unknown").title()
        if not move_type:
            continue
        fallback = move.get("name", "")
        for code, spec in LANGS.items():
            name = localized_name(move.get("names", []), spec["name_langs"], fallback)
            output[code][name] = {"type": move_type, "category": category}
        if idx % 100 == 0:
            print(f"moves {idx}/{len(rows)}")
    return output


def write_language_files(pokemon: Dict[str, Dict[str, Any]], moves: Dict[str, Dict[str, Dict[str, str]]]) -> None:
    for code, spec in LANGS.items():
        payload = {
            "meta": {
                "language": code,
                "label": spec["label"],
                "description": "Generated from PokeAPI for Pokemon Battle Lens.",
                "source": "https://pokeapi.co/",
            },
            "ocr_lang": spec["ocr_lang"],
            "pokemon_types": pokemon[code],
            "moves": moves[code],
        }
        path = os.path.join(DATA_DIR, f"pokemon_{code}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"wrote {path}: {len(pokemon[code])} pokemon, {len(moves[code])} moves")


def main() -> None:
    ensure_dirs()
    pokemon = build_pokemon_data()
    moves = build_move_data()
    write_language_files(pokemon, moves)


if __name__ == "__main__":
    main()
