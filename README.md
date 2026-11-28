# TraceMaker

**A deterministic, DRC-verified PCB autorouter and component placer for KiCad 9 & 10.**

Give TraceMaker an unrouted or partially routed `.kicad_pcb` and it routes tracks, differential pairs, vias, and buses under your board's design rules — writing back **only** the copper it created while leaving every existing component, zone, lock, and property byte-for-byte untouched.

> [!NOTE]
> **About this repository:** Maintained by **SiliconBrane Inc.** ([`kaushikray2/TraceMaker`](https://github.com/kaushikray2/TraceMaker)) as the core C++20 routing engine powering **[KiCad AI Router](https://github.com/kaushikray2/kicad-ai-router)**. Forked from [`DingoOz/TraceMaker`](https://github.com/DingoOz/TraceMaker) at `v0.12.1` (`d34cbd0`) under `GPL-3.0-or-later`.

---

## Executive Summary

TraceMaker solves full-board and incremental PCB routing on commercial-grade multi-layer designs without inventing its own grading curve: **every routed board is judged by KiCad's own DRC (`kicad-cli pcb drc`)**, with zero added DRC violations tolerated.

Since forking from upstream `v0.12.1` (`d34cbd0`), this repository has landed **113 engineering commits across Phases 1–3**, transforming TraceMaker from an interactive standalone prototype into a **reproducible, memory-bounded, engineered-net-capable routing engine** focused on **x86_64 CPU execution**:

- **Higher Routing Completion & Walled-Pin Rescue:**
  - PCBench 120 s clean-pass rates improved on every non-trivial tier under bare routing (**Tier B `72.5% -> 77.5%`**, **Tier C `50.0% -> 56.7%`** [`66.7%` fully routed with zero added errors], **Tier D `54.5% -> 59.1%`** fully routed with zero added errors) with **0 added DRC errors across all 132 Tier A–D boards**.
  - Opt-in escape and finish engines cut stubborn open connections on dense BGA/fine-pitch boards: **EtherCAT `-39%`** (`18 -> 11` via `--escape-stubs`), **CoreOne `-23%`** (`22 -> 17` via `--escape-plan`), **d20 `-7%`** (`41 -> 38` via `--escape-plan` or `--finish-rip-walls`), **oskirby `-33%` walled pins** (`77 -> 52`), and **sizif `too_deep` deadlocks `1 -> 0`** (`11 -> 4` on `sizif-base`) via a bounded local conflict-clique solver.
- **Native Inner-Layer Rules & Negotiated Differential Pairs:**
  - Per-layer track widths (`track_width_on`) and coupled differential-pair widths/gaps (`diff_pair_width_on`, `diff_pair_gap_on`) flow end-to-end through `crules`, PathFinder search, and `RuleEngine` DRC — unlocking narrow inner stripline layers and tight BGA escape channels that previously collapsed to outer-layer scalars.
  - Differential pairs now support **atomic PathFinder rip-up negotiation (`--pair-negotiate`)**, **blind/buried and micro-vias**, and **reference-plane void penalties** (`usb-hub` weakest pair coupling `0.000 -> 0.897`, all pairs `>= 0.85`, zero added DRC errors).
- **50% Lower Peak RAM & Faster CPU Search:**
  - Tiled `16x16` `NodeStore` pages and paged legality caches cut peak memory in half (**`10.66 GB -> 5.29 GB`** on `mini_mass` 2-variant; 8-variant runs that previously OOM'd above `23 GB` now complete cleanly at **`17.0 GB`**).
  - A 2-word radix open list (`~2x` faster heap operations), flat open-addressing PathFinder history/block tables, spatial keepout/mask grids, sibling early-stop (**`-41.5%` wall time** on `usb-hub`), and single-pool `route-batch` (**`~2.0x` batch throughput**) accelerate CPU routing without altering search trajectories.
- **Bit-Exact Determinism & Safe Plugin Controls:**
  - `--deterministic` guarantees **byte-identical `.kicad_pcb` output across `--threads 1`, `4`, or `8`**, backed by hard RAII OS thread caps, build-commit provenance (`0.12.1+<sha>`), `--heartbeat` live telemetry, structured exit codes (`0/1/2/3`) + `exit_reason`, incremental `--route-open-only`, and bystander-safe `--reroute-window` / `--reroute-net`.

### Headline Scorecard

| Metric | Upstream `v0.12.1` | SiliconBrane Fork (Phase 3) | Freerouting `2.5` |
| :--- | ---: | ---: | ---: |
| **PCBench Tier A** (40 routine boards, 120 s) | 100.0% | **100.0%** | 100.0% |
| **PCBench Tier B** (40 medium boards, 120 s) | 72.5% | **77.5%** (`79.5%` feasible) | 50.0% |
| **PCBench Tier C** (30 dense boards, 120 s) | 50.0% (`60.0%` routed-0-err) | **56.7%** (`66.7%` routed-0-err) | 46.7% |
| **PCBench Tier D** (22 hardest boards, 120 s) | 40.9% (`54.5%` routed-0-err) | **59.1% routed-0-err**¹ | 36.4% |
| **Boards with Added KiCad DRC Errors** (Tiers A–D) | 0 | **0** | — |
| **Peak RAM — `mini_mass` (2 variants / 8 variants)** | 10.66 GB / OOM (`>23 GB`) | **5.29 GB / 17.02 GB** | — |
| **Cross-Thread Byte-Identical Replay (`1/4/8` threads)** | Partial (`--work` search only) | **Whole-job (`--deterministic`)** | No |
| **Automated Test Suite (`ctest`, `TM_WERROR=ON`)** | 428 tests | **532 tests** | — |

*¹ Three Tier C boards and three+ Tier D boards are routed 100% connected with zero added errors, but stock KiCad 10.0.x truncates pre-existing footprint violations (e.g. 199 solder-mask bridges on the unrouted input) so the strict differential DRC judge marks them `unknown` rather than `clean`.*

---

## Platform & Architecture Focus

- **Primary target:** **Linux x86_64 (CPU-only, C++20)** — Ubuntu 24.04+ / 26.04, Debian 13+, or current Fedora (`glibc >= 2.38` for prebuilt binaries; GCC 13–15 for source builds). Windows 10/11 users can run Linux builds inside WSL2 (Ubuntu 24.04+).
- **Why CPU-only:** Autorouting runtime is dominated by sequential A\* graph expansion, exact geometric clearance checks, and PathFinder negotiation rather than dense SIMD field sweeps. GPU (CUDA) and Apple Silicon (Metal) sources remain dormant in `src/gpu/` (`TM_ENABLE_CUDA=OFF` in the `cpu-only` preset) and are not part of active development.

---

## Quick Start

### 1. Build from Source (CPU-Only Preset)

**Dependencies (Ubuntu 24.04+ / 26.04):** CMake `>= 3.28`, Ninja, GCC `13–15`, Boost, Eigen3, oneTBB, `fmt`, `spdlog`, FlatBuffers, SQLite3, `zstd`, Catch2, `pybind11` (Clipper2 is fetched automatically if not installed).

```bash
cmake --preset cpu-only && cmake --build --preset cpu-only
```

The router binary is built at `build/cpu-only/src/app/tracemaker` (and the component placer at `build/cpu-only/src/place/tracemaker-place`).

### 2. Route a Board

```bash
# Standard portfolio route (120 s budget; automatically runs --relax rescue if opens remain)
build/cpu-only/src/app/tracemaker route board.kicad_pcb -o routed.kicad_pcb --time 120 --threads 8

# Bit-reproducible route (identical output on 1, 4, or 8 threads)
build/cpu-only/src/app/tracemaker route board.kicad_pcb -o routed.kicad_pcb \
  --deterministic --work 50000000 --threads 8 --json route.json
```

### 3. Verify with KiCad DRC

```bash
kicad-cli pcb drc --format json --severity-all --all-track-errors -o drc.json routed.kicad_pcb
```

*(If KiCad is not installed locally, `scripts/kicad-cli` runs the official `kicad/kicad:10.0.6` Docker image.)*

### 4. Watch Live in the Browser (Optional)

```bash
cd viewer && npm install && npm run build && cd ..
build/cpu-only/src/app/tracemaker route board.kicad_pcb -o routed.kicad_pcb --view --hold
```

Open `http://localhost:8766/` to inspect live search frontiers, stuck nets, and DRC rejection overlays.

---

## Everyday CLI Workflows

All commands below invoke `build/cpu-only/src/app/tracemaker` unless noted otherwise. Run `tracemaker tui board.kicad_pcb -o out.kicad_pcb` for an interactive terminal UI over every option.

### Core & Deterministic Routing

| Goal | Command |
| :--- | :--- |
| Route with a wall-clock limit | `route board.kicad_pcb -o out.kicad_pcb --time 120 --threads 8` |
| Route deterministically (reproducible across thread counts) | `route board.kicad_pcb -o out.kicad_pcb --deterministic --work 50000000` |
| Route many boards in one process under one global thread cap | `route-batch manifest.json --threads 16 --json batch_summary.json` |
| Stream live progress to a JSON heartbeat file | `route board.kicad_pcb -o out.kicad_pcb --heartbeat progress.json` |
| Re-route from scratch (strip existing unlocked tracks/vias first) | `route board.kicad_pcb -o out.kicad_pcb --reroute` |

### Hard-Board Completion, Escape & Scoped Rerouting

| Goal | Command |
| :--- | :--- |
| Finish only remaining open connections (keep all existing routes intact) | `route partial.kicad_pcb -o out.kicad_pcb --route-open-only --finish` |
| Re-route only inside a bounding box (`x1,y1,x2,y2` mm; bystanders untouched) | `route routed.kicad_pcb -o out.kicad_pcb --reroute-window 10,15,35,40` |
| Re-route specific nets without splitting bystander nets | `route routed.kicad_pcb -o out.kicad_pcb --reroute-net 'SPI_*,CLK'` |
| Reserve BGA/QFN escape corridors and release unused ones for stubborn opens | `route board.kicad_pcb -o out.kicad_pcb --escape-plan --escape-release-open` |
| Pre-place fine-pitch BGA/EtherCAT escape stubs | `route board.kicad_pcb -o out.kicad_pcb --escape-stubs` |
| Run full finish ladder + targeted rip-and-heal of routed copper walling pins | `route board.kicad_pcb -o out.kicad_pcb --finish --finish-rip-walls` |

### Engineered Nets, Per-Layer Rules & Signal Integrity

| Goal | Command |
| :--- | :--- |
| Route coupled differential pairs with atomic PathFinder victim negotiation | `route board.kicad_pcb -o out.kicad_pcb --diff-pairs --pair-negotiate` |
| Synthesize per-layer impedance/current widths & layout keepouts from parts | `route board.kicad_pcb -o out.kicad_pcb --component-rules on` |
| Inspect detected component rules before routing | `rules board.kicad_pcb --mode on` |
| Prioritize critical nets, penalize vias, and avoid reference-plane splits | `route board.kicad_pcb -o out.kicad_pcb --si-rules` |
| Audit high-speed return-path continuity across reference planes | `return-paths board.kicad_pcb --nets 'DDR*,*CLK*'` |
| Route byte/data buses lane-by-lane with skew length-matching | `route board.kicad_pcb -o out.kicad_pcb --bus 'DATA=/D[0-7]' --bus-skew-mm 0.5` |

### Diagnostics, Placement & Agent Control

| Goal | Command |
| :--- | :--- |
| Prove which pins are physically walled in by fixed pads/holes/edges | `walled board.kicad_pcb` |
| Check dense packages for un-escapable pins under board rules | `escape board.kicad_pcb` |
| Run TraceMaker's internal DRC (optionally refilling zones in memory) | `drc board.kicad_pcb --refill-zones --json drc_report.json` |
| Optimize or repair component placement (`tracemaker-place`) | `tracemaker-place in.kicad_pcb -o placed.kicad_pcb --mode auto --route-check 3000000` |
| Drive the router transactionally from an AI agent over JSONL / MCP | `session board.kicad_pcb --out routed.kicad_pcb` |

---

## Exit Codes & JSON Contract

Downstream tools (such as `kicad-ai-router` and CI pipelines) can rely on deterministic process exit codes and `route --json` fields:

| Exit Code | Meaning | `summary.exit_reason` (when applicable) |
| :---: | :--- | :--- |
| `0` | Board is **100% connected** (and stays connected after zone refill when `--soft-zones` is active) | `"complete"` |
| `1` | Runtime / I/O / parse / internal error | — (`error` object populated) |
| `2` | CLI usage, configuration, or manifest validation error | — |
| `3` | Routing completed cleanly, **but open connections remain** | `"open_connections"` or `"unconnected_after_refill"` |

Every `route --json` output also stamps `version` (`0.12.1+<git-sha>[-dirty]`), `work_accounting_version` (`2`), `deterministic`, `kb_used`, `stopped_by`, `threads_effective`, per-stage timings (`stages`), and `peak_rss_mb`.

---

## Running Tests & Benchmarks

### Test Suite (`532` Tests)

```bash
# Optional one-time download of external board fixtures (~2.4 GB into git-ignored bench/data/)
scripts/fetch_fixtures.sh

# Run full unit + integration test suite
ctest --preset cpu-only --output-on-failure
```

Tests requiring external fixtures or `kicad-cli` skip cleanly when those optional dependencies are absent. Sanitiser presets (`asan`, `tsan`) are also configured in `CMakePresets.json`.

### PCBench Evaluation

```bash
python3 bench/run.py --tier B --limit 40 --time 120 --jobs 2 --threads 8
```

Each benchmark run snapshots the binary and writes per-board JSONL metrics, routed `.kicad_pcb` outputs, and KiCad DRC comparisons into `bench/results/<run>/`.

---

## Known Limitations

- **Via count:** TraceMaker currently places more vias than human reference layouts and Freerouting (post-route `--optimize` via reduction and jog cleanup are scheduled for Phase 4).
- **Peak memory on giant 8-variant boards:** While 2-variant peak RSS dropped `50%` (`5.29 GB`), running all 8 portfolio variants simultaneously on the largest Tier-D boards peaks near `~17 GB`; machines with `<= 24 GB` RAM should run Tier-D benchmarks at `--jobs 1`.
- **KiCad DRC report caps:** Stock `kicad-cli` 10.0.x caps individual DRC violation lists at `199` (or `499` for clearance/unconnected). On boards whose *unrouted* input already saturates a cap, `bench/drc_judge.py` conservatively reports `error_gate: "unknown"` rather than `clean`.
- **Post-tuning skew edge case:** On one delay-tuning fixture (`RoyalBlue54L-Feather`), a post-tuning stage shortens a meandered USB net slightly past its `0.5 ps` skew budget (tracked since upstream `#60` and flagged by TraceMaker's DRC).

---

## Repository Layout

| Path | Contents |
| :--- | :--- |
| `src/app/` | `tracemaker` CLI entry points, `route_job` orchestration, finish ladder, `route-batch` |
| `src/route/` | PathFinder/A\* router, differential pairs, escape planning, chains, repair & legalisation |
| `src/crules/` | Component-aware rule synthesis, stackup impedance solver, per-layer netclass builder |
| `src/drc/` | Exact geometric clearance & design-rule engine (`RuleEngine`) |
| `src/analysis/` | Walled-pin escape proofs (`EscapeAnalyser`), return-path & SI audits |
| `src/io/kicad/` | Lossless round-trip KiCad `.kicad_pcb` / `.kicad_pro` / `.kicad_dru` reader & writer |
| `src/place/` | `tracemaker-place` simulated-annealing & routability-driven component placer |
| `src/core/`, `src/geom/`, `src/model/` | Tiled `NodeStore`, radix heap, flat hash maps, spatial grids, geometry & board model |
| `src/server/`, `viewer/` | Embedded WebSocket stream server and browser-based live routing viewer |
| `kicad_plugin/`, `skills/` | Standalone KiCad 10 PCM plugin and coding-agent skills |
| `bench/`, `tests/`, `docs/` | PCBench harness & KiCad DRC judge, Catch2 + Python integration tests, design docs & CLI reference |

---

## Further Reading

- **[CLI Reference (`docs/reference/cli.md`)](docs/reference/cli.md):** Auto-generated flag-by-flag reference verified in CI (`gen_reference --check`).
- **[Design Documents (`docs/`)](docs/index.md) & [Architecture Decisions (`docs/12-decisions.md`)](docs/12-decisions.md):** Deep-dive algorithmic notes and decision records (`docs/decisions/`).
- **[KiCad AI Router (`kaushikray2/kicad-ai-router`)](https://github.com/kaushikray2/kicad-ai-router):** Full AI-assisted KiCad plugin integrating TraceMaker's deterministic engine, portfolio racing, and engineered-net workflows.
- **[Contributing (`CONTRIBUTING.md`)](CONTRIBUTING.md):** Bug reporting and patch guidelines.

---

## Licence & Attribution

Licensed under the **GNU General Public License v3.0 or later (`GPL-3.0-or-later`)** — see [LICENSE](LICENSE).

- Original work Copyright (C) the [`DingoOz/TraceMaker`](https://github.com/DingoOz/TraceMaker) authors; fork modifications Copyright (C) 2026 **SiliconBrane Inc.** under the same `GPL-3.0-or-later` terms.
- [NOTICE](NOTICE) sets out the linking permission for NVIDIA's CUDA runtime, credits third-party open-source libraries and KiCad demo fixtures (`tests/truth/`), and documents benchmark board licensing (benchmark boards are fetched on demand into `bench/data/` and are never redistributed in this repository).
