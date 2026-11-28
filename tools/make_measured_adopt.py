"""List of buildings whose re-registered DSM height (data/manual/measured_heights_v2.json) goes into the game.

Source: the "实测核对" column of docs/building-audit.csv (tools/building_check.py): rows starting with "可采用" are the
ones where the new DSM height agrees with the old one or the 本机素材 main roof (2.5 m). Hand exclusions / additions below
(decided by the main session with the user, 2026-11-27). build_campus.py apply_measured reads the result; every other
building keeps data/manual/measured_heights.json.

Usage: .venv/Scripts/python.exe -I -X utf8 tools/make_measured_adopt.py
Output: data/manual/measured_adopt.json
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE = {   # name -> why it stays on the old measurement
    "尚贤楼": "翻新楼，人工核",
    "沁园22栋": "新实测比旧的差",
}
# 东苑食堂 / 晖园11-13 were excluded while their DSM heights came out low; that was the ground model of the DSM
# (tools/dsm_register.py --east-only measures 东苑 with a local ground), and they now agree with the local model and
# the official floor counts, so they go by the audit verdict like every other building.
ADD = {       # name -> why it is adopted although the audit did not say "可采用"
    "基嘉楼": "用户确认：约 3 层（新实测 10.3 m，本机素材 10.1 m）",
    "明德楼": "用户确认：6 层（采用新实测 26.3 m）",
}


def main():
    rows = list(csv.DictReader(open(ROOT / "docs" / "building-audit.csv", encoding="utf-8-sig")))
    v2 = json.loads((ROOT / "data" / "manual" / "measured_heights_v2.json").read_text(encoding="utf-8"))["buildings"]
    adopt, skipped = {}, []
    for r in rows:
        bid, name, verdict = r["楼号"], r["显示名"], r["实测核对"]
        if name in ADD:
            why = ADD[name]
        elif verdict.startswith("可采用"):
            why = verdict
        else:
            continue
        if name in EXCLUDE:
            skipped.append(f"{name}（{EXCLUDE[name]}）")
            continue
        if bid not in v2:
            skipped.append(f"{name or bid}（v2 里没有）")
            continue
        adopt[bid] = {"name": name, "h": v2[bid]["h"], "why": why}
    out = {"note": "Buildings whose height comes from measured_heights_v2.json (tools/make_measured_adopt.py); "
                   "the rest keep measured_heights.json.",
           "exclude": EXCLUDE, "add": ADD, "buildings": adopt}
    (ROOT / "data" / "manual" / "measured_adopt.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"adopted {len(adopt)}; skipped {skipped}")


if __name__ == "__main__":
    main()
