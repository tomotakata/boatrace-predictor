import importlib.util
import itertools
import json
import sys
from copy import deepcopy
from pathlib import Path
from urllib.request import urlopen


ROOT = Path("/Users/tomo/Downloads/https-::infinix-holdings.goleadgrid.com/Ema/boatrace-predictor")
ENGINE_PATH = ROOT / "backend/app/prediction/engine.py"
REFERENCE_PATH = Path("/tmp/pdf_claude_reference_biwako_20260612.json")
RACE_IDS = [1195, 1197, 1190, 1193, 1200, 1198, 1199, 1196, 1189, 1191, 1192, 1194]
API_BASE = "https://boatrace-predictor-ten.vercel.app/api/races/{}"


def load_engine():
    spec = importlib.util.spec_from_file_location("pdf_engine", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fetch_race(race_id):
    with urlopen(API_BASE.format(race_id), timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_head(heads):
    return list(dict.fromkeys(int(h) for h in heads if h))


def evaluate(module, races, refs, params):
    predictor = module.BoatracePredictor()
    details = []
    format_hits = head_hits = honsen_hits = 0
    for race in races:
        race_copy = deepcopy(race)
        race_copy["engine_params"] = params
        race_input = module.race_dict_to_input(race_copy)
        out = predictor.predict(race_input)
        ref = refs[race_copy["race_no"]]
        got_honsen = [p.combo for p in out.honsen if p.grade in ("勝負", "通常", "見送り")]
        format_ok = out.fmt == ref["format"]
        head_ok = normalize_head(out.head_boats) == normalize_head(ref["head"])
        honsen_ok = set(got_honsen) == set(ref["honsen"])
        format_hits += int(format_ok)
        head_hits += int(head_ok)
        honsen_hits += int(honsen_ok)
        details.append({
            "race_no": race_copy["race_no"],
            "race_id": race_copy["id"],
            "expected": {
                "format": ref["format"],
                "head": ref["head"],
                "honsen": ref["honsen"],
            },
            "actual": {
                "format": out.fmt,
                "head": normalize_head(out.head_boats),
                "honsen": got_honsen,
                "reasoning": out.reasoning,
            },
            "match": {
                "format": format_ok,
                "head": head_ok,
                "honsen": honsen_ok,
            },
        })
    score = format_hits * 100 + head_hits * 10 + honsen_hits
    return {
        "score": score,
        "format_hits": format_hits,
        "head_hits": head_hits,
        "honsen_hits": honsen_hits,
        "details": details,
    }


def main():
    module = load_engine()
    refs = {row["race_no"]: row for row in json.loads(REFERENCE_PATH.read_text())}
    races = [fetch_race(race_id) for race_id in RACE_IDS]
    field_presence = {}
    required_fields = [
        "motor_eval", "motor_place2_rate", "st_advantage_rank", "avg_st",
        "today_st", "standard_st", "rank", "gen_rate", "hit_rate",
    ]
    for field in required_fields:
        field_presence[field] = sum(
            1 for race in races for boat in race.get("boats", []) if boat.get(field) not in (None, "")
        )
    kimarite_presence = {}
    for course in range(2, 7):
        for suffix in ("makuri", "makurizashi"):
            key = f"c{course}_{suffix}"
            kimarite_presence[key] = sum(
                1 for race in races for boat in race.get("boats", []) if boat.get(key) not in (None, "")
            )

    grid = {
        "dec1": [0.80, 0.85, 0.90],
        "dec2": [0.60, 0.70, 0.80],
        "n_cal": [12, 18, 24],
        "gap_threshold": [1.4, 1.5, 1.6],
        "escape_outstanding_threshold": [0.54, 0.58, 0.62],
        "gen_rate_mode": ["existing_or_kimarite", "kimarite"],
        "gen_rate_threshold": [0.05, 0.08],
        "revision67_lane1_unreliable_threshold": [0.42, 0.45],
    }
    best = None
    for values in itertools.product(*grid.values()):
        params = dict(zip(grid.keys(), values))
        result = evaluate(module, races, refs, params)
        if best is None or result["score"] > best["score"]:
            best = {"params": params, **result}

    output = {
        "field_presence": field_presence,
        "kimarite_presence": kimarite_presence,
        "best_params": best["params"],
        "metrics": {
            "format_hits": best["format_hits"],
            "head_hits": best["head_hits"],
            "honsen_hits": best["honsen_hits"],
            "total": len(races),
        },
        "details": best["details"],
    }
    out_path = Path("/tmp/pdf_calibration_results_biwako_20260612.json")
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(out_path)


if __name__ == "__main__":
    main()