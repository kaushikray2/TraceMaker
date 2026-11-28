// Copyright (C) 2026 SiliconBrane Inc.
//
// This file is part of TraceMaker (SiliconBrane fork).
//
// TraceMaker is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// TraceMaker is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with TraceMaker. If not, see <https://www.gnu.org/licenses/>.
//
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
// Post-route copper optimisation (issue #67, Phase 4A; design in bench/records/phase4a-optimize-design.md).
// Two transforms over a run's new copper, both connectivity-preserving by construction:
//
//   A. Collinear merge: two tracks of one net, same layer and width, meeting straight-on at a vertex where
//      the copper graph has degree exactly two become one track. The union of the two capsules is the merged
//      capsule, so the copper shape is identical and no legality check is needed.
//   B. Via-jog collapse: track(L) - via - short track(M) - via - track(L) becomes a single track on L,
//      removing two vias. A collapse is applied only when the router's exact check
//      (route::Obstacles::segment_state, the check octilinear trusts) proves the replacement segment legal
//      against the whole board, and only under the degree discipline of the design note (nothing else may
//      touch the two via positions: no other track end or interior, no arc, no pad).
//
// Like the other after-route passes (doc 05 §39) this works on the new copper of one run against the board
// as the router saw it; the caller judges the result by unconnected items per net and drops it if any net
// is worse. Input copper is never modified. Everything is integer geometry visited in a fixed order, so
// the result is deterministic.
#include <vector>

#include "model/board.hpp"
#include "model/rules.hpp"

namespace tmk::passes {

struct OptimizeOptions {
  Coord max_jog = 5'000'000;    // longest middle segment a via jog may have, nm
  long work_limit = 2'000'000;  // exact checks (rule 5); when it runs out the remaining jogs stay as they are
  bool soft_zones = false;      // as RouterOptions::soft_zones
};

struct OptimizeResult {
  int merged = 0;     // stage A: track pairs merged (copper-identical)
  int jogs = 0;       // stage B: patterns that passed every guard and reached the exact check
  int collapsed = 0;  // stage B: jogs collapsed (two vias removed each)
  int no_room = 0;    // stage B: the exact check refused the replacement segment
  long checks = 0;
  bool out_of_work = false;
};

// `board` is the board as the router saw it (without the new copper); `tracks` and `vias` are the run's new
// copper and are rewritten in place (collapsed jogs removed, replacement and merged tracks in their place).
OptimizeResult optimize_copper(const model::Board& board, const model::DesignRules& rules, std::vector<model::Track>& tracks,
                               std::vector<model::Via>& vias, const OptimizeOptions& opt);

}  // namespace tmk::passes
