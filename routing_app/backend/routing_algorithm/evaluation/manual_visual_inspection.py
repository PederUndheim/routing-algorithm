from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "evaluation" / "evaluation_results"
FIGURE_DIR = PROJECT_ROOT / "figures" / "evaluation"

MPL_CONFIG_DIR = Path("/private/tmp/routing_algorithm_mpl")
XDG_CACHE_DIR = Path("/private/tmp/routing_algorithm_xdg_cache")
MPL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
XDG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CONFIG_DIR))
os.environ.setdefault("XDG_CACHE_HOME", str(XDG_CACHE_DIR))


SIMILARITY_LABELS = {
    "excellent": "Very high similarity",
    "usable": "High similarity",
    "inspect": "Moderate similarity",
    "likely_bad_failure": "Low similarity",
}
SIMILARITY_ORDER = [
    "Very high similarity",
    "High similarity",
    "Moderate similarity",
    "Low similarity",
]
INSPECTION_ORDER = [
    "Good route",
    "Acceptable route",
    "Problematic route",
    "Clear route failure",
]
MODE_ORDER = ["off", "balanced"]
MODE_LABELS = {"off": "Off", "balanced": "Balanced"}
INSPECTION_COLORS = {
    "Good route": "#2a9d8f",
    "Acceptable route": "#8ab17d",
    "Problematic route": "#f4a261",
    "Clear route failure": "#c44536",
}
PUBLICATION_TEXT = {
    "title": 15,
    "axis_label": 18,
    "tick_label": 16,
    "legend": 15,
    "annotation": 14,
}
SIMILARITY_HEATMAP_TEXT = {
    "title": 23,
    "axis_label": 22,
    "tick_label": 21,
    "annotation": 26,
}
SIMILARITY_SHORT_LABELS = {
    "Very high similarity": "Very high",
    "High similarity": "High",
    "Moderate similarity": "Moderate",
    "Low similarity": "Low",
}
INSPECTION_SHORT_LABELS = {
    "Good route": "Good",
    "Acceptable route": "Acceptable",
    "Problematic route": "Problematic",
    "Clear route failure": "Failure",
}


MANUAL_ROUTE_REVIEWS: list[dict[str, Any]] = [
    {
        "area_name": "hemsedal",
        "area_display": "Hemsedal",
        "route_id": "1609_fortopp",
        "manual_route_name": "1609 (fortopp)",
        "reviews": {
            "off": ("Moderate similarity", "Good route", "Alternative line through easy terrain at the start."),
            "balanced": ("High similarity", "Good route", "Starts closer to the reference route."),
        },
    },
    {
        "area_name": "hemsedal",
        "area_display": "Hemsedal",
        "route_id": "storeskardnoese",
        "manual_route_name": "Storeskardnøse",
        "reviews": {
            "off": (
                "Very high similarity",
                "Good route",
                "Easy terrain. Could possibly round the small steep sections more widely.",
            ),
            "balanced": ("Very high similarity", "Good route", "Good route through easy terrain."),
        },
    },
    {
        "area_name": "hemsedal",
        "area_display": "Hemsedal",
        "route_id": "1740",
        "manual_route_name": "1740",
        "reviews": {
            "off": ("Moderate similarity", "Acceptable route", "Should preferably take the outer left line towards the end."),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route well towards the end."),
        },
    },
    {
        "area_name": "hemsedal",
        "area_display": "Hemsedal",
        "route_id": "leinenoese",
        "manual_route_name": "Leinenøse",
        "reviews": {
            "off": (
                "Low similarity",
                "Problematic route",
                "Follows another trail at the start and enters unnecessary runout terrain.",
            ),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route well."),
        },
    },
    {
        "area_name": "hemsedal",
        "area_display": "Hemsedal",
        "route_id": "skogshorn",
        "manual_route_name": "Skogshorn",
        "reviews": {
            "off": (
                "Low similarity",
                "Good route",
                "Safe and efficient, but could follow a wider curve like the reference route.",
            ),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route well."),
        },
    },
    {
        "area_name": "hemsedal",
        "area_display": "Hemsedal",
        "route_id": "skurvefjellet",
        "manual_route_name": "Skurvefjellet",
        "reviews": {
            "off": ("Low similarity", "Good route", "Different trail choices, but still a safe route."),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route well."),
        },
    },
    {
        "area_name": "isfjorden",
        "area_display": "Isfjorden",
        "route_id": "galtatind",
        "manual_route_name": "Galtåtind",
        "reviews": {
            "off": (
                "Very high similarity",
                "Good route",
                "Good route, possibly better than the reference around the steepest section.",
            ),
            "balanced": ("High similarity", "Good route", "Same, but shorter route choice in forest due to track data."),
        },
    },
    {
        "area_name": "isfjorden",
        "area_display": "Isfjorden",
        "route_id": "kjovskarstinden",
        "manual_route_name": "Kjøvskarstinden",
        "reviews": {
            "off": (
                "Low similarity",
                "Good route",
                "Alternative summit approach. The reference route is still clearly within the corridor.",
            ),
            "balanced": ("Very high similarity", "Good route", "Good route, and more precise than the reference in places."),
        },
    },
    {
        "area_name": "isfjorden",
        "area_display": "Isfjorden",
        "route_id": "kyrkjetaket",
        "manual_route_name": "Kyrkjetaket",
        "reviews": {
            "off": ("Very high similarity", "Good route", "Good route."),
            "balanced": ("Very high similarity", "Good route", "Same, but shorter route choice in forest due to track data."),
        },
    },
    {
        "area_name": "isfjorden",
        "area_display": "Isfjorden",
        "route_id": "loftskarstinden",
        "manual_route_name": "Loftskarstinden",
        "reviews": {
            "off": (
                "Low similarity",
                "Good route",
                "Alternative route via Galtåtind. The reference route is partly covered by the corridor.",
            ),
            "balanced": (
                "Low similarity",
                "Good route",
                "Same, but shorter route choice in forest due to track data.",
            ),
        },
    },
    {
        "area_name": "isfjorden",
        "area_display": "Isfjorden",
        "route_id": "sore_klauva",
        "manual_route_name": "Søre Klauvå",
        "reviews": {
            "off": ("High similarity", "Good route", "Good route."),
            "balanced": ("High similarity", "Good route", "Same, but shorter route choice in forest due to track data."),
        },
    },
    {
        "area_name": "jotunheimen",
        "area_display": "Jotunheimen",
        "route_id": "kyrkja",
        "manual_route_name": "Kyrkja",
        "reviews": {
            "off": ("Low similarity", "Good route", "Alternative line through easy terrain and across the lake."),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route well."),
        },
    },
    {
        "area_name": "jotunheimen",
        "area_display": "Jotunheimen",
        "route_id": "midtre_hoegvagltind",
        "manual_route_name": "Midtre Høgvagltind",
        "reviews": {
            "off": ("Low similarity", "Good route", "Alternative, but safe, route over the ridge."),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route well."),
        },
    },
    {
        "area_name": "jotunheimen",
        "area_display": "Jotunheimen",
        "route_id": "semelholstinden",
        "manual_route_name": "Semelholstinden",
        "reviews": {
            "off": ("Moderate similarity", "Good route", "Some alternative, but safe, route choices."),
            "balanced": ("Low similarity", "Good route", "Some alternative, but safe, route choices."),
        },
    },
    {
        "area_name": "jotunheimen",
        "area_display": "Jotunheimen",
        "route_id": "store_smoerstabbtinden",
        "manual_route_name": "Store Smørstabbtinden",
        "reviews": {
            "off": (
                "Moderate similarity",
                "Good route",
                "Good route, with minor alternatives in easy start terrain.",
            ),
            "balanced": ("Very high similarity", "Good route", "Good route following the reference."),
        },
    },
    {
        "area_name": "jotunheimen",
        "area_display": "Jotunheimen",
        "route_id": "storebjoern",
        "manual_route_name": "Storebjørn",
        "reviews": {
            "off": ("High similarity", "Good route", "Follows the reference route."),
            "balanced": ("High similarity", "Good route", "Follows the reference route."),
        },
    },
    {
        "area_name": "jotunheimen",
        "area_display": "Jotunheimen",
        "route_id": "galdhoepiggen_juvasshytta",
        "manual_route_name": "Galdhøpiggen (Juvasshytta)",
        "reviews": {
            "off": ("High similarity", "Good route", "Mostly follows the reference route."),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route."),
        },
    },
    {
        "area_name": "jotunheimen",
        "area_display": "Jotunheimen",
        "route_id": "galdhoepiggen_spiterstulen",
        "manual_route_name": "Galdhøpiggen Spiterstulen",
        "reviews": {
            "off": (
                "High similarity",
                "Good route",
                "Mostly follows the reference route, with minor local alternatives.",
            ),
            "balanced": (
                "High similarity",
                "Good route",
                "Mostly follows the reference route, with minor local alternatives.",
            ),
        },
    },
    {
        "area_name": "jotunheimen",
        "area_display": "Jotunheimen",
        "route_id": "uranostinden",
        "manual_route_name": "Uranostinden",
        "reviews": {
            "off": (
                "Low similarity",
                "Acceptable route",
                "Completely alternative route. Suitable overall, but should take a wider turn before the summit approach.",
            ),
            "balanced": (
                "Low similarity",
                "Acceptable route",
                "Completely alternative route. Suitable overall, but should take a wider turn before the summit approach.",
            ),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "884",
        "manual_route_name": "884",
        "reviews": {
            "off": (
                "Very high similarity",
                "Acceptable route",
                "Follows the reference, but should take a wider eastern curve near the summit to avoid terrain above 35 degrees.",
            ),
            "balanced": ("Very high similarity", "Acceptable route", "Same issue near the summit."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "botnfjellet",
        "manual_route_name": "Botnfjellet",
        "reviews": {
            "off": ("High similarity", "Good route", "Follows the reference route, with small local variations."),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route well."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "breitinden",
        "manual_route_name": "Breitinden",
        "reviews": {
            "off": ("Moderate similarity", "Acceptable route", "Should take a longer eastern detour like the reference route."),
            "balanced": ("Moderate similarity", "Acceptable route", "Same issue as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "buren",
        "manual_route_name": "Buren",
        "reviews": {
            "off": (
                "High similarity",
                "Good route",
                "Mostly follows the reference, with both better and worse local variations.",
            ),
            "balanced": (
                "High similarity",
                "Good route",
                "Mostly follows the reference, with both better and worse local variations.",
            ),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "djeveltanna",
        "manual_route_name": "Djeveltanna",
        "reviews": {
            "off": (
                "Moderate similarity",
                "Acceptable route",
                "Alternative variant. Longer exposure to steep terrain, but avoids the steepest reference section.",
            ),
            "balanced": ("Moderate similarity", "Acceptable route", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "durmaalstinden",
        "manual_route_name": "Durmålstinden",
        "reviews": {
            "off": ("Moderate similarity", "Good route", "Mostly follows the reference, with some variation at the start."),
            "balanced": ("Moderate similarity", "Good route", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "graatinden_1",
        "manual_route_name": "Gråtinden 1",
        "reviews": {
            "off": ("Very high similarity", "Good route", "Similar to the reference, with variations in easy terrain."),
            "balanced": ("Very high similarity", "Good route", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "graatinden_2",
        "manual_route_name": "Gråtinden 2",
        "reviews": {
            "off": ("Moderate similarity", "Good route", "Similar to the reference, with variations in easy terrain."),
            "balanced": ("High similarity", "Good route", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "hatten",
        "manual_route_name": "Hatten",
        "reviews": {
            "off": ("High similarity", "Good route", "Some local alternatives, but overall follows the reference."),
            "balanced": ("High similarity", "Good route", "Some local alternatives, but overall follows the reference."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "kinnbeinet",
        "manual_route_name": "Kinnbeinet",
        "reviews": {
            "off": ("Moderate similarity", "Good route", "Follows the reference, with small local variations."),
            "balanced": ("High similarity", "Good route", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "kvitbergfjellet",
        "manual_route_name": "Kvitbergfjellet",
        "reviews": {
            "off": ("Low similarity", "Good route", "Deviates from the reference, but remains a good route."),
            "balanced": ("Low similarity", "Good route", "Deviates from the reference, but remains a good route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "middagstinden_anmarsj",
        "manual_route_name": "Middagstinden anmarsj",
        "reviews": {
            "off": (
                "Moderate similarity",
                "Acceptable route",
                "Alternative route over a broad ridge instead of across the lake.",
            ),
            "balanced": ("Moderate similarity", "Acceptable route", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "middagstinden",
        "manual_route_name": "Middagstinden",
        "reviews": {
            "off": (
                "High similarity",
                "Acceptable route",
                "Different choices in exposed terrain. Suitability depends strongly on snow conditions.",
            ),
            "balanced": (
                "High similarity",
                "Acceptable route",
                "Different choices in exposed terrain and near the summit. Suitability depends on snow conditions.",
            ),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "nordfjordtinden_1",
        "manual_route_name": "Nordfjordtinden 1",
        "reviews": {
            "off": (
                "Moderate similarity",
                "Acceptable route",
                "Alternative approach with less travel on the lake, but probably less efficient.",
            ),
            "balanced": ("Low similarity", "Acceptable route", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "nordfjordtinden_2",
        "manual_route_name": "Nordfjordtinden 2",
        "reviews": {
            "off": (
                "Low similarity",
                "Clear route failure",
                "Completely different route choice, with unnecessary travel through very steep terrain.",
            ),
            "balanced": ("Low similarity", "Clear route failure", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "revbergtinden",
        "manual_route_name": "Revbergtinden",
        "reviews": {
            "off": ("Very high similarity", "Good route", "Follows the reference route."),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "skittentinden",
        "manual_route_name": "Skittentinden",
        "reviews": {
            "off": (
                "Very high similarity",
                "Good route",
                "Handles exposed terrain similarly to the reference, but the final steep section could be improved.",
            ),
            "balanced": ("Moderate similarity", "Good route", "Same issue near the final steep section."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "steinskarstinden",
        "manual_route_name": "Steinskarstinden",
        "reviews": {
            "off": ("High similarity", "Good route", "Similar to the reference overall, with some local variations."),
            "balanced": (
                "Very high similarity",
                "Good route",
                "Hybrid between the track-off route and the reference route.",
            ),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "storsteinnestinden_1",
        "manual_route_name": "Storsteinnestinden 1",
        "reviews": {
            "off": (
                "Low similarity",
                "Problematic route",
                "Completely different route. Possible, but less intuitive for this summit.",
            ),
            "balanced": (
                "Very high similarity",
                "Acceptable route",
                "Mostly follows the reference, but is steeper than necessary in places.",
            ),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "storsteinnestinden_2",
        "manual_route_name": "Storsteinnestinden 2",
        "reviews": {
            "off": (
                "Low similarity",
                "Acceptable route",
                "Very different route over 884 and along the ridge. Possibly safer, but less ideal for skiing.",
            ),
            "balanced": ("Low similarity", "Acceptable route", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "straumsaksla_1",
        "manual_route_name": "Straumsaksla 1",
        "reviews": {
            "off": ("Moderate similarity", "Good route", "Deviates from the reference, but may be safer."),
            "balanced": ("Moderate similarity", "Good route", "Deviates from the reference, but may be safer."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "straumsaksla_2",
        "manual_route_name": "Straumsaksla 2",
        "reviews": {
            "off": ("High similarity", "Good route", "Appears safer than the reference route."),
            "balanced": ("High similarity", "Good route", "Appears safer than the reference route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "styrmannen",
        "manual_route_name": "Styrmannen",
        "reviews": {
            "off": ("High similarity", "Good route", "Mostly follows the reference, with some local variations."),
            "balanced": ("High similarity", "Good route", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "tverrfjellet",
        "manual_route_name": "Tverrfjellet",
        "reviews": {
            "off": (
                "Low similarity",
                "Acceptable route",
                "Deviates substantially in easy terrain. The longer reference detour near the summit would be preferable.",
            ),
            "balanced": (
                "High similarity",
                "Acceptable route",
                "Mostly follows the reference, but should also follow it more closely near the end.",
            ),
        },
    },
    {
        "area_name": "kattfjordeidet",
        "area_display": "Kattfjordeidet",
        "route_id": "vasstinden",
        "manual_route_name": "Vasstinden",
        "reviews": {
            "off": ("High similarity", "Good route", "Follows the reference route well."),
            "balanced": ("High similarity", "Good route", "Follows the reference route well."),
        },
    },
    {
        "area_name": "sogndal",
        "area_display": "Sogndal",
        "route_id": "graanipa",
        "manual_route_name": "Grånipa",
        "reviews": {
            "off": ("High similarity", "Good route", "Alternative, but good, final route choice."),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route."),
        },
    },
    {
        "area_name": "sogndal",
        "area_display": "Sogndal",
        "route_id": "sogndalseggi",
        "manual_route_name": "Sogndalseggi",
        "reviews": {
            "off": ("High similarity", "Problematic route", "Mostly good, but crosses an unnecessary steep slope."),
            "balanced": ("Very high similarity", "Good route", "Mostly follows the reference, and is often better."),
        },
    },
    {
        "area_name": "sogndal",
        "area_display": "Sogndal",
        "route_id": "togga",
        "manual_route_name": "Togga",
        "reviews": {
            "off": ("Very high similarity", "Good route", "Mostly follows the reference route."),
            "balanced": ("Very high similarity", "Good route", "Mostly follows the reference route."),
        },
    },
    {
        "area_name": "svolvaer",
        "area_display": "Svolvær",
        "route_id": "blaatinden",
        "manual_route_name": "Blåtinden",
        "reviews": {
            "off": ("Moderate similarity", "Acceptable route", "Shorter, but more exposed, route variant."),
            "balanced": ("Moderate similarity", "Acceptable route", "Shorter, but more exposed, route variant."),
        },
    },
    {
        "area_name": "svolvaer",
        "area_display": "Svolvær",
        "route_id": "dronningtinden",
        "manual_route_name": "Dronningtinden",
        "reviews": {
            "off": (
                "Low similarity",
                "Acceptable route",
                "Reference route appears safer, and the lake should possibly be avoided.",
            ),
            "balanced": (
                "Moderate similarity",
                "Acceptable route",
                "Should follow the reference more closely for a slightly safer route choice.",
            ),
        },
    },
    {
        "area_name": "svolvaer",
        "area_display": "Svolvær",
        "route_id": "noekksaetra",
        "manual_route_name": "Nøkksætra",
        "reviews": {
            "off": ("Low similarity", "Acceptable route", "Shorter, but more exposed, route variant."),
            "balanced": ("Low similarity", "Good route", "Good alternative to the reference route."),
        },
    },
    {
        "area_name": "svolvaer",
        "area_display": "Svolvær",
        "route_id": "smaatindan_1",
        "manual_route_name": "Småtindan (Softbakken)",
        "reviews": {
            "off": (
                "Low similarity",
                "Acceptable route",
                "Different upper route choice. Similar quality, but the reference detour is safer at the start.",
            ),
            "balanced": ("Low similarity", "Acceptable route", "Same as for the track-off route."),
        },
    },
    {
        "area_name": "svolvaer",
        "area_display": "Svolvær",
        "route_id": "smaatindan_2",
        "manual_route_name": "Småtindan (Litlhaugen)",
        "reviews": {
            "off": ("High similarity", "Good route", "Very similar to the reference route."),
            "balanced": ("High similarity", "Good route", "Very similar to the reference route."),
        },
    },
    {
        "area_name": "svolvaer",
        "area_display": "Svolvær",
        "route_id": "suolovarri",
        "manual_route_name": "Suolovarri",
        "reviews": {
            "off": ("Low similarity", "Good route", "Completely different, but still good, route variant."),
            "balanced": ("Low similarity", "Good route", "Completely different, but still good, route variant."),
        },
    },
    {
        "area_name": "svolvaer",
        "area_display": "Svolvær",
        "route_id": "sydalsfjellet",
        "manual_route_name": "Sydalsfjellet",
        "reviews": {
            "off": ("High similarity", "Good route", "Overall very similar to the reference, with a different start."),
            "balanced": ("High similarity", "Good route", "Overall very similar to the reference, with a different start."),
        },
    },
    {
        "area_name": "svolvaer",
        "area_display": "Svolvær",
        "route_id": "tuva",
        "manual_route_name": "Tuva",
        "reviews": {
            "off": ("Very high similarity", "Good route", "Follows the reference route."),
            "balanced": ("Very high similarity", "Good route", "Follows the reference route."),
        },
    },
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def manual_review_rows() -> list[dict[str, str]]:
    rows = []
    for route in MANUAL_ROUTE_REVIEWS:
        for mode in MODE_ORDER:
            similarity_label, inspection_label, note = route["reviews"][mode]
            rows.append(
                {
                    "area_name": route["area_name"],
                    "area_display": route["area_display"],
                    "route_id": route["route_id"],
                    "manual_route_name": route["manual_route_name"],
                    "track_influence_mode": mode,
                    "manual_similarity_label": similarity_label,
                    "manual_inspection_label": inspection_label,
                    "inspection_note": note,
                }
            )
    return rows


def _metric_rows_by_key() -> dict[tuple[str, str, str], dict[str, str]]:
    rows = _read_csv(DATA_DIR / "all_areas_eval_metrics.csv")
    return {
        (row["area_name"], row["route_id"], row["track_influence_mode"]): row
        for row in rows
        if row.get("status") == "ok" and row.get("track_influence_mode") in MODE_ORDER
    }


def joined_manual_review_rows() -> list[dict[str, Any]]:
    metrics_by_key = _metric_rows_by_key()
    joined = []
    for review in manual_review_rows():
        key = (review["area_name"], review["route_id"], review["track_influence_mode"])
        metric_row = metrics_by_key.get(key)
        if metric_row is None:
            raise KeyError(f"No metric row found for manual review key: {key}")

        automatic_similarity_label = SIMILARITY_LABELS.get(metric_row["quality_label"], metric_row["quality_label"])
        reference_ates = metric_row.get("reference_ates") or "Unknown"
        row = {
            "area_name": metric_row.get("area_name", ""),
            "area_display": review["area_display"],
            "area_id": metric_row.get("area_id", ""),
            "route_id": metric_row.get("route_id", ""),
            "route_name": metric_row.get("route_name", ""),
            "manual_route_name": review["manual_route_name"],
            "reference_ates": reference_ates,
            "track_influence_mode": metric_row.get("track_influence_mode", ""),
            "automatic_quality_label": metric_row.get("quality_label", ""),
            "automatic_similarity_label": automatic_similarity_label,
            "manual_similarity_label": review["manual_similarity_label"],
            "similarity_label_matches_metrics": automatic_similarity_label == review["manual_similarity_label"],
            "manual_inspection_label": review["manual_inspection_label"],
            "inspection_note": review["inspection_note"],
            "distance_symmetric_median_m": metric_row.get("distance_symmetric_median_m", ""),
            "distance_symmetric_p95_m": metric_row.get("distance_symmetric_p95_m", ""),
            "reference_in_generated_buffer_50m_pct": metric_row.get("reference_in_generated_buffer_50m_pct", ""),
            "reference_in_generated_buffer_100m_pct": metric_row.get("reference_in_generated_buffer_100m_pct", ""),
            "corridor_balanced_coverage_pct": metric_row.get("corridor_balanced_coverage_pct", ""),
            "length_ratio_generated_to_reference": metric_row.get("length_ratio_generated_to_reference", ""),
            "reference_path": metric_row.get("reference_path", ""),
            "generated_path": metric_row.get("generated_path", ""),
            "plot_path": metric_row.get("plot_path", ""),
        }
        joined.append(row)
    return joined


def _float_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values = []
    for row in rows:
        try:
            value = float(row.get(key, "nan"))
        except (TypeError, ValueError):
            continue
        if value == value:
            values.append(value)
    return values


def _summarize_groups(rows: list[dict[str, Any]], group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(str(row.get(field, "")) or "Unknown" for field in group_fields)].append(row)

    summaries = []
    for key, group_rows in sorted(grouped.items()):
        summary = {field: value for field, value in zip(group_fields, key)}
        n = len(group_rows)
        summary["n"] = n
        counts = Counter(str(row["manual_inspection_label"]) for row in group_rows)
        for label in INSPECTION_ORDER:
            prefix = label.lower().replace(" ", "_")
            count = counts[label]
            summary[f"{prefix}_count"] = count
            summary[f"{prefix}_pct"] = 100.0 * count / n if n else 0.0
        for key_name, out_name in [
            ("distance_symmetric_median_m", "median_symmetric_deviation_median_m"),
            ("distance_symmetric_p95_m", "median_symmetric_p95_m"),
            ("reference_in_generated_buffer_50m_pct", "median_reference_50m_coverage_pct"),
            ("reference_in_generated_buffer_100m_pct", "median_reference_100m_coverage_pct"),
            ("corridor_balanced_coverage_pct", "median_balanced_corridor_coverage_pct"),
            ("length_ratio_generated_to_reference", "median_length_ratio_generated_to_reference"),
        ]:
            values = _float_values(group_rows, key_name)
            summary[out_name] = median(values) if values else ""
        summaries.append(summary)
    return summaries


def _similarity_vs_inspection_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for mode in MODE_ORDER:
        mode_rows = [row for row in rows if row["track_influence_mode"] == mode]
        total = len(mode_rows)
        for similarity_label in SIMILARITY_ORDER:
            similarity_rows = [row for row in mode_rows if row["manual_similarity_label"] == similarity_label]
            counts = Counter(str(row["manual_inspection_label"]) for row in similarity_rows)
            for inspection_label in INSPECTION_ORDER:
                count = counts[inspection_label]
                out.append(
                    {
                        "track_influence_mode": mode,
                        "similarity_label": similarity_label,
                        "manual_inspection_label": inspection_label,
                        "count": count,
                        "share_within_similarity_pct": 100.0 * count / len(similarity_rows) if similarity_rows else 0.0,
                        "share_within_mode_pct": 100.0 * count / total if total else 0.0,
                    }
                )
    return out


def _plot_similarity_vs_manual_inspection(rows: list[dict[str, Any]]) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    max_count = 1
    matrices: dict[str, list[list[int]]] = {}
    for mode in MODE_ORDER:
        mode_rows = [row for row in rows if row["track_influence_mode"] == mode]
        matrix = []
        for similarity_label in SIMILARITY_ORDER:
            row_values = []
            for inspection_label in INSPECTION_ORDER:
                count = sum(
                    1
                    for row in mode_rows
                    if row["manual_similarity_label"] == similarity_label
                    and row["manual_inspection_label"] == inspection_label
                )
                row_values.append(count)
                max_count = max(max_count, count)
            matrix.append(row_values)
        matrices[mode] = matrix

    fig, axes = plt.subplots(1, 2, figsize=(14.0, 10.4), constrained_layout=False)
    fig.subplots_adjust(left=0.15, right=0.99, bottom=0.33, top=0.84, wspace=0.08)
    mode_titles = {
        "off": "Without track cost reduction",
        "balanced": "With track cost reduction",
    }
    for index, (ax, mode) in enumerate(zip(axes, MODE_ORDER)):
        matrix = matrices[mode]
        ax.imshow(matrix, cmap="Blues", vmin=0, vmax=max_count, aspect="equal")
        ax.set_title(mode_titles[mode], fontsize=SIMILARITY_HEATMAP_TEXT["title"], fontweight="bold", pad=14)
        ax.set_xticks(
            range(len(INSPECTION_ORDER)),
            [INSPECTION_SHORT_LABELS[label] for label in INSPECTION_ORDER],
        )
        ax.set_yticks(
            range(len(SIMILARITY_ORDER)),
            [SIMILARITY_SHORT_LABELS[label] for label in SIMILARITY_ORDER] if index == 0 else [],
        )
        ax.tick_params(axis="x", rotation=35, labelsize=SIMILARITY_HEATMAP_TEXT["tick_label"])
        ax.tick_params(axis="y", labelsize=SIMILARITY_HEATMAP_TEXT["tick_label"], pad=10)
        ax.set_xticks([x - 0.5 for x in range(1, len(INSPECTION_ORDER))], minor=True)
        ax.set_yticks([y - 0.5 for y in range(1, len(SIMILARITY_ORDER))], minor=True)
        ax.grid(which="minor", color="white", linewidth=2)
        ax.tick_params(which="minor", bottom=False, left=False)
        ax.set_xlabel("Route quality", fontsize=SIMILARITY_HEATMAP_TEXT["axis_label"], labelpad=10)
        if index == 0:
            ax.set_ylabel("Geometric similarity", fontsize=SIMILARITY_HEATMAP_TEXT["axis_label"], labelpad=10)
        for y, row_values in enumerate(matrix):
            for x, count in enumerate(row_values):
                color = "white" if count > max_count * 0.55 else "#243447"
                ax.text(
                    x,
                    y,
                    str(count),
                    ha="center",
                    va="center",
                    fontsize=SIMILARITY_HEATMAP_TEXT["annotation"],
                    color=color,
                )

    out = FIGURE_DIR / "similarity_vs_manual_inspection.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


def _plot_manual_label_distribution(rows: list[dict[str, Any]]) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    xs = list(range(len(MODE_ORDER)))
    bottoms = [0] * len(MODE_ORDER)

    fig, ax = plt.subplots(figsize=(7.6, 6.5), constrained_layout=False)
    fig.subplots_adjust(left=0.12, right=0.72, bottom=0.12, top=0.88)
    for label in INSPECTION_ORDER:
        values = [
            sum(1 for row in rows if row["track_influence_mode"] == mode and row["manual_inspection_label"] == label)
            for mode in MODE_ORDER
        ]
        bars = ax.bar(xs, values, bottom=bottoms, label=label, color=INSPECTION_COLORS[label], width=0.58)
        for bar, value, bottom in zip(bars, values, bottoms):
            if value:
                is_clear_route_failure = label == "Clear route failure"
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bottom + value + 0.35 if is_clear_route_failure else bottom + value / 2,
                    str(value),
                    ha="center",
                    va="bottom" if is_clear_route_failure else "center",
                    fontsize=PUBLICATION_TEXT["annotation"],
                    color="#243447" if is_clear_route_failure else "white",
                )
        bottoms = [bottom + value for bottom, value in zip(bottoms, values)]

    ax.set_xticks(xs, [MODE_LABELS[mode] for mode in MODE_ORDER])
    ax.set_ylabel("Number of routes", fontsize=PUBLICATION_TEXT["axis_label"])
    ax.set_ylim(0, max(bottoms) + 4)
    ax.grid(axis="y", color="#d7dde2", linewidth=0.8, alpha=0.75)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#8d99a6")
    ax.spines["bottom"].set_color("#8d99a6")
    ax.tick_params(colors="#243447", labelsize=PUBLICATION_TEXT["tick_label"])
    ax.legend(
        frameon=False,
        fontsize=PUBLICATION_TEXT["legend"],
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        ncol=1,
    )

    out = FIGURE_DIR / "manual_inspection_label_distribution.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


def _plot_manual_inspection_by_area_and_mode(rows: list[dict[str, Any]]) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    area_order = []
    area_labels = {}
    for row in rows:
        area_name = str(row["area_name"])
        if area_name not in area_order:
            area_order.append(area_name)
            area_labels[area_name] = str(row["area_display"])

    bar_width = 0.34
    offsets = {"off": -bar_width / 1.6, "balanced": bar_width / 1.6}
    xs = list(range(len(area_order)))
    area_totals = [
        len({row["route_id"] for row in rows if row["area_name"] == area})
        for area in area_order
    ]

    fig, ax = plt.subplots(figsize=(13.0, 8.0), constrained_layout=False)
    fig.subplots_adjust(left=0.11, right=0.985, bottom=0.18, top=0.80)
    for mode in MODE_ORDER:
        bottoms = [0.0] * len(area_order)
        mode_positions = [x + offsets[mode] for x in xs]
        mode_totals = [
            sum(1 for row in rows if row["area_name"] == area and row["track_influence_mode"] == mode)
            for area in area_order
        ]
        for label in INSPECTION_ORDER:
            values = []
            for area, total in zip(area_order, mode_totals):
                count = sum(
                    1
                    for row in rows
                    if row["area_name"] == area
                    and row["track_influence_mode"] == mode
                    and row["manual_inspection_label"] == label
                )
                values.append(100.0 * count / total if total else 0.0)
            ax.bar(
                mode_positions,
                values,
                bottom=bottoms,
                color=INSPECTION_COLORS[label],
                edgecolor="white",
                linewidth=0.7,
                width=bar_width,
                label=label if mode == "off" else None,
            )
            bottoms = [bottom + value for bottom, value in zip(bottoms, values)]

        for position in mode_positions:
            ax.text(
                position,
                -6.5,
                MODE_LABELS[mode],
                ha="center",
                va="top",
                fontsize=PUBLICATION_TEXT["annotation"],
                color="#4a5563",
            )

    for x, total in zip(xs, area_totals):
        ax.text(
            x,
            103,
            f"n={total}",
            ha="center",
            va="bottom",
            fontsize=PUBLICATION_TEXT["annotation"],
            color="#243447",
        )

    ax.set_xticks(xs, [area_labels[area] for area in area_order])
    ax.tick_params(axis="x", labelsize=PUBLICATION_TEXT["tick_label"], pad=10, colors="#243447")
    ax.tick_params(axis="y", labelsize=PUBLICATION_TEXT["tick_label"], colors="#243447")
    ax.set_ylabel("Routes (%)", fontsize=PUBLICATION_TEXT["axis_label"])
    ax.set_ylim(-12, 112)
    # for x in [value + 0.5 for value in xs[:-1]]:
    #     ax.axvline(x, color="#edf0f2", linewidth=1.0, zorder=0)
    ax.grid(axis="y", color="#d7dde2", linewidth=0.8, alpha=0.75)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#8d99a6")
    ax.spines["bottom"].set_color("#8d99a6")
    ax.legend(
        frameon=False,
        fontsize=PUBLICATION_TEXT["legend"],
        ncol=4,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.1),
    )

    out = FIGURE_DIR / "manual_inspection_by_area_track_mode.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out


def write_manual_visual_inspection_outputs() -> list[Path]:
    manual_rows = manual_review_rows()
    joined_rows = joined_manual_review_rows()

    manual_fieldnames = [
        "area_name",
        "area_display",
        "route_id",
        "manual_route_name",
        "track_influence_mode",
        "manual_similarity_label",
        "manual_inspection_label",
        "inspection_note",
    ]
    joined_fieldnames = [
        "area_name",
        "area_display",
        "area_id",
        "route_id",
        "route_name",
        "manual_route_name",
        "reference_ates",
        "track_influence_mode",
        "automatic_quality_label",
        "automatic_similarity_label",
        "manual_similarity_label",
        "similarity_label_matches_metrics",
        "manual_inspection_label",
        "inspection_note",
        "distance_symmetric_median_m",
        "distance_symmetric_p95_m",
        "reference_in_generated_buffer_50m_pct",
        "reference_in_generated_buffer_100m_pct",
        "corridor_balanced_coverage_pct",
        "length_ratio_generated_to_reference",
        "reference_path",
        "generated_path",
        "plot_path",
    ]
    summary_value_fieldnames = [
        "n",
        "good_route_count",
        "good_route_pct",
        "acceptable_route_count",
        "acceptable_route_pct",
        "problematic_route_count",
        "problematic_route_pct",
        "clear_route_failure_count",
        "clear_route_failure_pct",
        "median_symmetric_deviation_median_m",
        "median_symmetric_p95_m",
        "median_reference_50m_coverage_pct",
        "median_reference_100m_coverage_pct",
        "median_balanced_corridor_coverage_pct",
        "median_length_ratio_generated_to_reference",
    ]
    cross_tab_fieldnames = [
        "track_influence_mode",
        "similarity_label",
        "manual_inspection_label",
        "count",
        "share_within_similarity_pct",
        "share_within_mode_pct",
    ]

    outputs = [
        _write_csv(DATA_DIR / "manual_visual_inspection_off_balanced.csv", manual_rows, manual_fieldnames),
        _write_csv(DATA_DIR / "manual_visual_inspection_metrics_joined.csv", joined_rows, joined_fieldnames),
        _write_csv(
            DATA_DIR / "manual_inspection_summary_by_mode.csv",
            _summarize_groups(joined_rows, ("track_influence_mode",)),
            ["track_influence_mode", *summary_value_fieldnames],
        ),
        _write_csv(
            DATA_DIR / "manual_inspection_summary_by_mode_and_area.csv",
            _summarize_groups(joined_rows, ("track_influence_mode", "area_name")),
            ["track_influence_mode", "area_name", *summary_value_fieldnames],
        ),
        _write_csv(
            DATA_DIR / "manual_inspection_summary_by_mode_and_ates.csv",
            _summarize_groups(joined_rows, ("track_influence_mode", "reference_ates")),
            ["track_influence_mode", "reference_ates", *summary_value_fieldnames],
        ),
        _write_csv(
            DATA_DIR / "manual_inspection_metric_summary_by_label.csv",
            _summarize_groups(joined_rows, ("track_influence_mode", "manual_inspection_label")),
            ["track_influence_mode", "manual_inspection_label", *summary_value_fieldnames],
        ),
        _write_csv(
            DATA_DIR / "manual_similarity_vs_inspection_counts.csv",
            _similarity_vs_inspection_rows(joined_rows),
            cross_tab_fieldnames,
        ),
        _plot_similarity_vs_manual_inspection(joined_rows),
        _plot_manual_label_distribution(joined_rows),
        _plot_manual_inspection_by_area_and_mode(joined_rows),
    ]

    mismatches = [row for row in joined_rows if not row["similarity_label_matches_metrics"]]
    if mismatches:
        mismatch_path = DATA_DIR / "manual_similarity_label_mismatches.csv"
        outputs.append(_write_csv(mismatch_path, mismatches, joined_fieldnames))
    return outputs
