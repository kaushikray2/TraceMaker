# Phase 4A slice 2 A/B - --via-search-mult 3 (issue #67)

Design: bench/records/phase4a-via-econ-design.md. Inventory:
bench/records/phase4a-via-econ-inventory.md. Judged rows:
phase4a-via-econ-ab-judged-{off,on}.json (bench/judge_outputs.py output).

## Protocol (seeded; stated deviation from the gate protocol)

Per issue #68, unseeded wall-clock comparisons are not measurements (the
rescue stage races outside the deterministic contract), so both arms ran:

  tracemaker route <fixture>/unrouted.kicad_pcb --seed 1 --variants 1
    --threads 4 --no-gpu --work 60000000 --time 3600 (safety net only)

fixtures ~/tm-gate3/fix, binary at 09af519e (this branch). The only
difference between arms is --via-search-mult 3 in the ON arm (a via costs
9 mm of track in the detailed searches instead of 3 mm). Every route
summary in both arms: deterministic true, time_limited false, kb_used
false. DRC judged with bench/judge_outputs.py (kicad-cli 10.0.6 through
scripts/, drc_judge added_errors against each fixture own input).

Deviation, stated: the Phase 3 gate protocol is the full portfolio at
120 s wall. This A/B runs a single variant at a fixed 60M-expansion
budget per stage so the comparison is deterministic and
machine-independent. Absolute completions are therefore lower than the
gate on the big boards (LeeChee 1103/1160 here vs fully routed at the
gate), and via ratios are quoted at each arm own completion.

Boards: the five worst via-excess boards of the committed baseline
(bench/records/phase4a-via-baseline-gate3.json) plus two modest-excess
controls. All five worst boards are 2-layer; PocketBone is 4-layer,
PSLab 4-layer (F.Cu-L1..B.Cu-L4).

## Results

| board | ref vias | OFF routed/open | OFF vias (ratio) | ON routed/open | ON vias (ratio) | d vias | d routed | added err OFF/ON | clean OFF/ON | wall s OFF/ON |
|---|---|---|---|---|---|---|---|---|---|---|
| LeeChee_1800 (D) | 94 | 1103/57 | 266 (2.83) | 1090/70 | 211 (2.24) | -55 (-20.7%) | -13 | 0 / 0 (gate unknown*) | F / F | 247 / 236 |
| MonApollo_analog-board (D) | 225 | 1088/102 | 431 (1.92) | 1076/114 | 374 (1.66) | -57 (-13.2%) | -12 | 0 / 0 | F / F | 245 / 244 |
| tiny-8088_Computer (C) | 47 | 255/29 | 85 (1.81) | 243/41 | 34 (0.72) | -51 (-60.0%) | -12 | 0 / 0 | F / F | 206 / 193 |
| mechkeys_MF68+10 (C) | 97 | 375/40 | 108 (1.11) | 369/46 | 68 (0.70) | -40 (-37.0%) | -6 | 0 / 0 | F / F | 190 / 186 |
| rvi_v2x_hardware_V2X (C) | 205 | 457/22 | 302 (1.47) | 458/21 | 288 (1.40) | -14 (-4.6%) | +1 | 0 / 0 | F / F | 184 / 172 |
| kitspace_PSLab (C, control) | 174 | 339/0 | 201 (1.16) | 339/0 | 188 (1.08) | -13 (-6.5%) | 0 | 0 / 0 | T / T | 54 / 53 |
| jadonk_PocketBone (C, control) | 78 | 201/1 | 101 (1.29) | 201/1 | 100 (1.28) | -1 (-1.0%) | 0 | 0 / 0 | F / F | 208 / 208 |
| **total / median** | 920 | 4318/283 | **1494 (median 1.47)** | 4276/325 | **1263 (median 1.28)** | **-231 (-15.5%)** | **-42** | **0 / 0** | | 1334 / 1292 |

*LeeChee error_gate is "unknown" in BOTH arms: a KiCad DRC category
saturates its per-type cap on that board (the same masking recorded at
the Phase 3 gate); added_errors counts 0 and the state is the same in
both arms, so it carries no arm difference.

## Findings

1. The price works mechanically. Every board via count fell; the
   aggregate fell 15.5% and the median ratio on this set moved
   1.47 -> 1.28. Two boards went below their human reference
   (MF68+10 0.70, tiny-8088 0.72).
2. Completion fell on four of seven boards: -42 routed overall. The
   losses sit exactly where the via gains are largest (tiny-8088
   -51 vias / -12 routed; LeeChee -55 / -13; MonApollo -57 / -12;
   MF68+10 -40 / -6). Where completion held (PSLab, PocketBone,
   rvi_v2x +1), the via gains were small (-13, -1, -14).
3. Zero added DRC errors in both arms on all seven boards; per-board
   clean status unchanged (only PSLab is clean, in both arms).
4. Wall time did not move systematically (ON within +-6% per board;
   work-budgeted runs, wall is indicative only).

## Verdict: the slice FAILS the gate terms as configured

The Phase 4 exit gate demands equal-or-better completion at a lower
via ratio. This slice trades about 5.5 vias per lost connection
(231 vias for 42 connections). That is a completion-for-vias trade,
not a via reduction at equal completion, and by the slice guardrail
it is a failure, reported as such.

The mechanism is plain: at a fixed expansion budget, a 9 mm via
spends the budget differently - searches that would have dipped now
expand longer detours or hit their attempt caps, so the budget ends
with more connections open. The searches that do complete genuinely
use fewer vias; the price does what price theory says. The binding
constraint at 60M is search effort, not willingness to dip. A smaller
multiplier would shrink both sides of the trade; there is no evidence
of a free point on this curve, and per the one-setting rule none was
hunted.

The via-heavy tail is real in both arms: the gate portfolio routed
LeeChee fully with 673 vias; the OFF arm here has 266 vias at
1103/1160. The last ~5% of connections cost more vias than the first
95% - any future via work that does not protect tail completion will
repeat this trade.

## Recommended next lever (inventory-supported, not built)

Align the router own clean-up judge with its search price.
optimize_vias and lns_vias already re-route at via_cost_mult 10
(30 mm per via) but judge the trade at a hardcoded 2 mm per via, so
they reject most of the via removals their own searches find (a
re-route removing 2 vias is rejected if it adds more than 4 mm of
track). Raising the judge price toward the search price acts only on
already-routed connections under the restore-on-failure transaction,
so completion cannot drop by construction; the cost is track length,
which the judge still prices. The reach is bounded by the clean-up
budget share - smaller than the search-side prize, but it is the one
via lever in the inventory with zero completion risk. A second,
bigger candidate is budget-compensated pricing (dear vias only once
the board is nearly routed, with the tail protected by the
polish/endgame reserves); it needs its own stage-sequence inventory
before it is more than a sketch.

## Verification of the implementation (09af519e)

- New tests tests/test_via_econ.cpp [via_econ]: 3 cases, 17 assertions,
  all pass - default inertness (identical routed/tracks/vias/expansions
  at default vs explicit 1.0), steering on a synthetic chicane (dips at
  mult 1, zero vias at mult 8, DRC-clean both ways), thread invariance
  at mult 3 (1 vs 4 threads identical).
- Full ctest on the final build: 545 entries, 0 failed. The two
  determinism gates skipped on the first pass (their PCBench fixture
  lives in untracked bench/data, absent from a fresh worktree; linked
  in and re-run): seed_determinism PASSED (561.8 s),
  deterministic_mode PASSED (506.0 s) - both at the default, flag off.
  Flag-on determinism is covered by the thread-invariance unit test
  and by deterministic:true in all seven ON-arm summaries above.
- docs/reference/cli.md unchanged: --via-search-mult is registered in
  the hidden (empty) CLI11 group, like --redecompose / --pin-via-pen.
