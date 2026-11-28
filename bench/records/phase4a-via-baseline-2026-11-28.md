# Phase 4A gating measurement — via-ratio baseline (2026-11-28)

Issue #67. Measured on the Phase 3 gate corpus: the gate3-tierB/C/D bench runs
(main + solo merged, dedup by board) produced by the phase-tip binary at eb77606,
bare `route`, 120 s limit, 8 threads, no route args — the rel0120-style gate
protocol. Records: `~/tm-audit4-wt/bench/results/gate3-tier{B,C,D}{,-solo}/boards.jsonl`
on zorinbox-1; per-board data extracted to `bench/records/phase4a-via-baseline-gate3.json`
by `bench/via_baseline.py` (this commit).

## Where the human baseline lives

There is no standalone via-baseline table. The human reference is the fixture's own
designer routing: `bench/run.py` (line 272) measures each fixture's
`processed.kicad_pcb` with the same style counter as the router output and stores it
per board as `style_ref` (`style_ref.vias` = human via count). `bench/human_baseline.py`
judges the human boards' DRC cleanliness but does not count vias. So the baseline
exists, per board, inside the bench records — this measurement is derived from it.

## The distribution (per-board ratio = TraceMaker vias / human vias)

90 of 92 gate boards carry both counters; 83 have a non-zero human via count and
enter the ratio distribution (7 boards were routed by their designers with 0 vias;
TraceMaker used vias on 5 of those, up to 16).

| set | boards (ref>0) | median ratio | median, fully routed | total TM / human vias | above 1.0x |
|---|---|---|---|---|---|
| Tier B | 36 | 1.659 | 1.693 | 2254 / 1587 = 1.420 | 29 |
| Tier C | 28 | 1.396 | 1.245 | 3977 / 2543 = 1.564 | 21 |
| Tier D | 19 | 1.981 | 2.611 | 5839 / 3115 = 1.875 | 19 |
| **All** | **83** | **1.667** | **1.726** | **12070 / 7245 = 1.666** | **69 / 83** |

## Discrepancy with the workstream text — read this first

The Phase 4 text (and issue #67) states the current median via ratio as
**1.01–1.10x**. That figure does **not** reproduce on the gate corpus under the
harness's own counters, under any subset tried (all boards, fully routed only,
clean only, human vias >= 20): every median lands between 1.25 and 2.61. Either the
1.01–1.10x was measured on a different corpus/definition (e.g. the held-out quality
set against Freerouting, or the DAC2020 boards), or it is simply wrong. On the
corpus the exit gate is scored on, the gate target "median below 1.0x" means
cutting the median board's via count by ~40%, and the aggregate by ~4,800 vias —
a routing-behaviour problem (via cost / layer assignment), not a cleanup-pass
problem alone. The --optimize pass is still the right first slice (it is measurable
per board and cannot hurt completion), but nobody should expect it to close a
1.67x median by itself; later 4A slices must feed back into via cost during search.

## Where the excess concentrates

- A minority of boards carry most of the excess: the top 5 boards (LeeChee_1800
  +579, MonApollo +472, tiny-8088 +222, mechkeys_MF68+10 +208, rvi_v2x +206)
  account for ~1,700 of the ~4,825 total excess vias.
- The worst boards have very high `short_segments` counts in the router output
  (DSP-ADAU1452: 307 short segments / 220 vias; Hardware_Playground_sd_wav_pcm5100:
  683 / 72; EUC-VESC: 229 / 84) — vias cluster around short jogs and stair patterns,
  i.e. layer changes made for a few millimetres of travel and changed back. That is
  exactly the pattern a post-route pass can attack: via-pair jogs whose middle
  segment is short and whose removal is a local, verifiable transform.
- 14 of 83 boards are already at or below 1.0x; the median board is not close.

## Protocol for the A/B that follows

Same gate protocol (bare route, 120 s, threads 8) with `--optimize` added;
compare per-board vias, completion and drc_judge added errors against these
records board-for-board. Zero added errors is a hard requirement.
