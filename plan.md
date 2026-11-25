# TraceMaker improvement programme — plan

Status tracker for the fork programme (kaushikray2/TraceMaker, forked from
DingoOz/TraceMaker; upstream main stays pinned at d34cbd0, the v0.12.1-era
base). **This file is updated in the same commit as any work that changes an
item's status** — a commit that moves an item without moving this file is
incomplete. Active track: x86 CPU only. All numbers below are measured on
the programme bench boards (PCBench fixture set) unless stated otherwise.

## Done

### Phase 1 — frozen at fe39106 on tm-phase1 (upstream: DingoOz/TraceMaker PR #96)
18 commits: paged NodeStore for search state behind --paged-nodes;
--finish-guard-walls rung pricing (DR-22 Tier 1), later corrected to price
each rung by a proof over its own output board; chains --causes and
--apply-sweeps with differential-pair-whole lifts and co-closed marking;
window/routed signatures (Zobrist); a hardening batch (2^31 state-index
guard, per-search --search-mem accounting counting touched blocks, the
--search-mem 0 hole closed); the tree builds clean under its own
TM_WERROR=ON default; CUDA field step 1 (persistent workspaces — parked
since, see Queued outside). Verification: ctest 494/494 three consecutive
runs; record/replay byte-match (131 tracks, 10 vias, 1390 messages);
oskirby finish ladder 137 open -> 112 with walled_in 23 from the final
board proof; guard-walls A/B on d20 measured-neutral (flag stays opt-in).
Fork issues #8, #11, #12, #13, #14, #15 closed with evidence.

### Stage 2A — determinism gate (tm-phase2-cpu, 732506d; follow-up 1cfc932)
Seeded, work-budgeted runs are reproducible: knowledge base suppressed
under --seed without an explicit --kb; wall-clock stops in the post-route
stages are aggregated into the route JSON (time_limited), which also
reports kb_used and deterministic. Gate test (seed_determinism): the AI
Router plugin exact flag mix on an unrouted and a partially routed board,
byte-identical .kicad_pcb across repeats and --threads 1/4/8. Build clean
(TM_WERROR=ON); ctest 495/495. Follow-up 1cfc932: post-chains wall proofs
price the board under the fitted rules that produced it.

### Stage 2B step 1 — tiled NodeStore (e140962)
The paged NodeStore is cut into 16x16-cell board tiles instead of 1 MB
flat strips. oskirby uncapped: outcome and expansions identical to the
flat store (137/1051, 22,432,211). oskirby --search-mem 64: 137/1051 —
the connection the flat store lost to strip waste (138/1050) is reclaimed
inside the true cap. mini_mass, 2 variants: peak RSS 10.66 -> 8.01 GB,
outcomes identical.

### Stage 2B step 2 — paged companions (2026-11-24)
The per-cell legality caches (cell state/history, via state) are tiled
like the NodeStore under --paged-nodes instead of allocating window-sized
dense arrays per variant thread; entry semantics (generation stamps,
recompute on miss) are unchanged, so trajectories are identical — only
where the bytes live changes. Verified: build clean; ctest 495/495;
oskirby expansions identical (22,432,211); mini_mass 2 variants identical
(987/995, 22,223,805 expansions), peak RSS 8.01 -> 5.87 GB; mini_mass
8 variants now COMPLETES at 17.02 GB peak (986/995, 5:11) where both
previous stores were OOM-killed at ~23 GB. The remaining 8-variant weight
sits in per-variant ClassCache and field state — addressed by the
field_cpu item below.

### Stage 2B step 3 — per-stage timing + peak RSS (2026-11-24, #18)
Every route job's JSON now carries a `stages` block (parse / search /
repair / refill / save / other — `other` is the residual, so the stages
sum to `seconds` by construction) and `peak_rss_mb` (getrusage).
Escape analysis and legalise are not job stages in this engine:
per-connection pad escape and the relax rounds' legalise step are
route_portfolio's work, so their time sits in `search`. Verified: build
clean; ctest 495/495; two seeded usb-hub runs produced byte-identical
boards (112/113, unchanged), stages summed to `seconds` exactly, peak
RSS 435–449 MB.

### Stage 2B step 4 — --threads as a hard global cap (2026-11-24, #19)
New `src/core/parallel.hpp`: a process-wide worker budget. A route job
sets the cap from its --threads; route_portfolio registers its variant
workers as primary, and zone refill's per-layer fan-out (the one stage
that ignored --threads, including when called inside a search) now
runs at most the allowance the cap leaves free — inline when the
portfolio holds the whole cap. The route JSON reports
`threads_effective`; --help documents the cap and the +2 allowance
(main thread + live-log writer). Verified: build clean; ctest 495/495;
OS thread peaks measured at 50 ms sampling on the seeded usb-hub run:
--threads 2 -> peak 4 (= cap + 2) on two runs, --threads 8 -> peak 10;
boards byte-identical between the two --threads 2 runs and the routed
count (112/113) unchanged at 2 and 8 threads.

### Stage 2B step 5 — sibling early-stop (2026-11-24, #20)
The portfolio's shared deadline (a completer sets it; siblings drain
against 2x its elapsed + 5 s) already existed for wall-clock runs; it
is now reported and controllable. `stopped_early`,
`early_stop_cancelled` and the cancelled variants' unspent budget
(`early_stop_saved_s` for wall-clock runs, `early_stop_saved_work`
for work-budget runs) are in the route JSON. Auto mode keeps the
deadline off under either work budget — the winner there must not
depend on thread timing; `--early-stop` forces it (a fired run
reports deterministic: false, via the new deadline_stopped result
flag, which also keeps such runs from being misreported as
time-limited), `--no-early-stop` disables it everywhere. Halving
keeps its own rung-level early exit. Verified: build clean; ctest
495/495 (seed gate unchanged); usb-hub minus its one hard net,
--time 180: wall 33.7 -> 19.7 s, 1 variant cancelled, board
byte-identical to the --no-early-stop run (same winner); forced
--work --early-stop: fired, saved_work 16.8M of 20M, deterministic
false, time_limited false.

## In progress

Nothing in flight at this commit; the next items are the data-structure changes (see Remaining).

## Remaining (in sequence)

### Stage 2B — CPU performance (rest)
- Radix heap for the open list; flat open-addressing hash maps; spatial
  keepouts / UniformGrid.
- field_cpu: change-tracking init, parallel layer sweeps, shared
  ClassCache pages (the mini_mass 8-variant RSS remainder).
- Bench: drc_judge.py KiCad DRC error-cap fix; causes wired into
  run_finish; DR-22 Tier 2-prime; bounded CPU local solver for too_deep
  cliques.
- Interim gate Fri 2026-11-27: defect register reconciled (fork issues
  #1-#25), shipped / measured-neutral / remaining report, cold-agent
  verification.

### Stage 2C — determinism cluster + plugin Tier 1
In dependency order:
- #16 Whole-job determinism: work-budget the post-route stages (repair,
  legalise, rescue, advisor, refill/thermal), not just the main route
  (~1.5-2.5 d incl. the byte-identity gate on an ordinary and a --relax
  board).
- #21 Deterministic round budget for --relax: --rounds/--round-work bind,
  --time demoted to a safety net, stopped_by reported (~0.5-1 d).
- #17 --deterministic mode flag: seed + work budgets + KB policy + JSON
  assertion in one switch (~0.5-1 d, on top of #16/#21).
- Plugin Tier 1 remainder: finish mode (--route-open-only), bystander-safe
  windowed re-route, trustworthy exit codes for the full outcome set,
  progress heartbeat.

### Stage 2D — batch mode
- #22 route-batch: many boards, one process, one global thread pool
  (~3-5 d). Gated on #19 (the global cap) and the 2C determinism cluster
  (its acceptance compares batch vs single-run results under work
  budgets).

## Queued outside

### GPU programme — PARKED (owner rulings 2026-11-23 and 2026-11-24)
Parked is sequencing, not descoping: prove each improvement on CPU,
measure and verify it, then port to the CUDA path in full — never both
variants at once. Unpark trigger: the CPU programme above is measured and
verified complete. Items: #23 (parity umbrella), #24 (deterministic GPU
routing), #25 (device-memory-bounded search state), the parked CUDA
defect fixes #9 and #10, and CUDA port steps 2-3. macOS / Metal is parked
the same way; the code stays in the tree.

### Held unless directed
- --escape-stubs (DR-21) measurement on sizif + EtherCAT boards.
- Downstream: the KiCad AI Router plugin stays on the pinned 0.12.1 engine
  release; its engine-adoption test is parked until Phase 2 finishes.

## How the next phase gets planned

From this phase measured results: the stage timings and RSS profile from
#18 decide where the remaining 2B effort goes; feature requests arrive as
fork issues and are placed into phases by owner ruling (as #16/#17 were
placed into 2C and #18-#22 into 2B/2C/2D on 2026-11-24); anything
GPU-shaped files under the parked umbrella until the unpark trigger fires.
