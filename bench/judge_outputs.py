#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Judge already-routed bench outputs (salvage path for runs whose judging phase died).

For every routed board in the given run dirs: KiCad DRC of the fixture input and of
the run's output board (bench.run.drc, cached), drc_judge added errors between them,
the style counts of the output, and completion from the board's .route.json. Writes
<run>/judged.json and prints one row per board. Needs kicad-cli on PATH (scripts/).

  bench/judge_outputs.py RUN [RUN ...] --fixtures DIR [--jobs 6]
"""
import argparse, concurrent.futures as cf, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import run as bench  # noqa: E402
import drc_judge  # noqa: E402

def one(args):
    run_dir, board, fixtures = args
    out_pcb = run_dir / "boards" / f"{board}.kicad_pcb"
    route_json = run_dir / "boards" / f"{board}.kicad_pcb.route.json"
    if not out_pcb.exists():
        return {"board": board, "missing": True}
    before = bench.drc(fixtures / board / "unrouted.kicad_pcb")
    after = bench.drc(out_pcb)
    if before is None or after is None:
        return {"board": board, "drc_failed": True}
    result = drc_judge.added_errors(before, after)
    style = bench.style_of(out_pcb, run_dir / "boards" / f"{board}.style.json")
    rj = json.loads(route_json.read_text()) if route_json.exists() else {}
    summary = rj.get("summary", rj)
    return {"board": board, "vias": style["vias"], "segments": style["segments"],
            "added_errors": result["added_errors"], "added_total": sum(result["added_errors"].values()),
            "error_gate": result["error_gate"], "clean": drc_judge.clean(result, after["unconnected"]),
            "routed": summary.get("routed"), "connections": summary.get("connections"),
            "optimize_copper": summary.get("optimize_copper")}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    fixtures = pathlib.Path(a.fixtures)
    for run in a.runs:
        run_dir = pathlib.Path("bench/results") / run
        boards = sorted(p.name[:-len(".kicad_pcb")] for p in (run_dir / "boards").glob("*.kicad_pcb"))
        with cf.ThreadPoolExecutor(a.jobs) as ex:
            rows = list(ex.map(one, [(run_dir, b, fixtures) for b in boards]))
        (run_dir / "judged.json").write_text(json.dumps(rows, indent=1))
        for r in rows:
            if "missing" in r or "drc_failed" in r:
                print(run, r)
            else:
                print(f"{run} {r['board'][:44]:44} vias={r['vias']:4} compl={r['routed']}/{r['connections']} clean={r['clean']} added={r['added_total']} gate={r['error_gate']} opt={r['optimize_copper']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
