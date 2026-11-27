// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <functional>
#include <string>

namespace tmk::app {

// route-batch (issue #22): route every board of a JSON manifest in this process, through
// one global thread pool bounded by one thread cap for the whole batch. The manifest:
//
//   {"threads": 16,                       // optional batch-wide defaults
//    "options": {"seed": 42, "work": 3000000},
//    "jobs": [{"input": "a.kicad_pcb", "output": "a_routed.kicad_pcb",
//              "json": "a.json",          // optional; default: the output with a .json extension
//              "options": {"seed": 7}},   // per-board overrides of the batch options
//             ...]}
//
// Paths are resolved against the manifest's directory. Each board writes the same result
// JSON a single `route --json` run writes; a board that fails (unreadable, bad option,
// route error) gets an error result JSON instead and never stops the batch. The return
// value is the batch exit code: 0 every board complete, 3 some board left connections
// open, 1 some board failed to run, 2 the manifest itself is unusable. Log lines are
// delivered through `log`, already prefixed per board.
int run_batch(const std::string& manifest_path, int threads_override, const std::string& summary_out,
              const std::function<void(const std::string&)>& log);

}  // namespace tmk::app
