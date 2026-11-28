#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 4A gating measurement: TraceMaker via counts vs the human reference routing.

Reads bench result runs (boards.jsonl) whose records carry `style` (TraceMaker output)
and `style_ref` (the fixture's own designer routing, processed.kicad_pcb, measured with
the same counter -- bench/run.py line 272). Emits the via-ratio distribution the Phase 4
exit gate is scored on: median ratio must go below 1.0x at equal or better completion.

  bench/via_baseline.py RUN_DIR [RUN_DIR ...] [--tier B]
"""
import argparse, json, pathlib, re, statistics, sys

def load(dirs):
    rows = []
    for d in dirs:
        for line in (pathlib.Path(d) / "boards.jsonl").read_text().splitlines():
            r = json.loads(line)
            if "style" in r and "style_ref" in r:
                if not r.get("tier"):
                    m = re.search(r"tier([BCD])", str(d))
                    r["tier"] = m.group(1) if m else None
                rows.append(r)
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--json-out")
    a = ap.parse_args()
    rows = load(a.runs)
    out = {"boards": []}
    for r in rows:
        tm, ref = r["style"]["vias"], r["style_ref"]["vias"]
        out["boards"].append({
            "board": r["board"], "tier": r.get("tier"), "tm_vias": tm, "ref_vias": ref,
            "ratio": (tm / ref) if ref else None, "excess": tm - ref,
            "completion": r.get("completion"), "clean": r.get("clean"),
            "tm_short_segments": r["style"].get("short_segments"), "tm_stair_steps": r["style"].get("stair_steps"),
            "tm_bends": r["style"].get("bends"), "tm_segments": r["style"].get("segments")})
    def stats(sel, label):
        ratios = [b["ratio"] for b in sel if b["ratio"] is not None]
        full = [b for b in sel if b["completion"] == 1.0]
        fr = [b["ratio"] for b in full if b["ratio"] is not None]
        zero_ref = [b for b in sel if b["ref_vias"] == 0]
        print(f"{label}: boards={len(sel)} with_ref={len(ratios)} ref0={len(zero_ref)} "
              f"median_ratio={statistics.median(ratios):.4f} median_ratio_fully_routed={statistics.median(fr):.4f} "
              f"total_ratio={sum(b['tm_vias'] for b in sel)}/{sum(b['ref_vias'] for b in sel)}="
              f"{sum(b['tm_vias'] for b in sel)/max(1,sum(b['ref_vias'] for b in sel)):.4f} "
              f"above_1x={sum(1 for x in ratios if x > 1.0)} at_or_below={sum(1 for x in ratios if x <= 1.0)}")
        return {"boards": len(sel), "median_ratio": statistics.median(ratios), "median_ratio_fully_routed": statistics.median(fr),
                "total_tm": sum(b["tm_vias"] for b in sel), "total_ref": sum(b["ref_vias"] for b in sel),
                "above_1x": sum(1 for x in ratios if x > 1.0)}
    out["summary"] = {}
    tiers = sorted({b["tier"] for b in out["boards"] if b["tier"]})
    # tier may be null in records; fall back to run order handled by caller passing one run per tier
    out["summary"]["all"] = stats(out["boards"], "ALL")
    for t in tiers:
        out["summary"][t] = stats([b for b in out["boards"] if b["tier"] == t], f"tier {t}")
    print("\nTop excess-via boards (tm - ref, fully routed first):")
    for b in sorted(out["boards"], key=lambda b: -b["excess"])[:20]:
        print(f"  {b['board'][:52]:52} tm={b['tm_vias']:4} ref={b['ref_vias']:4} excess={b['excess']:4} "
              f"ratio={b['ratio'] if b['ratio'] is None else round(b['ratio'],3)} compl={b['completion']} "
              f"short_seg={b['tm_short_segments']} stairs={b['tm_stair_steps']}")
    print("\nBoards where the human used 0 vias but TraceMaker used some:")
    for b in sorted([b for b in out["boards"] if b["ref_vias"] == 0 and b["tm_vias"] > 0], key=lambda b: -b["tm_vias"]):
        print(f"  {b['board'][:52]:52} tm={b['tm_vias']:4} compl={b['completion']}")
    if a.json_out:
        pathlib.Path(a.json_out).write_text(json.dumps(out, indent=1))
    return 0

if __name__ == "__main__":
    sys.exit(main())
