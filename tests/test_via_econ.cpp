// SPDX-License-Identifier: GPL-3.0-or-later
// Issue 67 (Phase 4A slice 2): search-side via economics (RouterOptions::via_search_mult).
// The multiplier prices every layer change the detailed search commits (the A* via step, the
// cost-to-go field, via drops, via-in-pad endpoints). At its default of 1.0 a run must be
// byte-identical to the run before the option existed; raised, it must steer a connection away
// from a layer dip whose same-layer detour is cheaper than the dearer vias; and with it on, the
// result must not depend on the thread count.
#include <catch2/catch_test_macros.hpp>

#include <unistd.h>

#include <filesystem>
#include <fstream>
#include <nlohmann/json.hpp>
#include <string>

#include "drc/drc.hpp"
#include "io/kicad/board_reader.hpp"
#include "io/kicad/project_reader.hpp"
#include "io/srj/srj.hpp"
#include "route/router.hpp"

namespace fs = std::filesystem;
using nlohmann::json;
using namespace tmk;

namespace {

// The test_redecomp ball-grid breakout (many crossings, negotiation has to rip): a proven,
// stable routing problem for the inertness and thread-invariance checks.
std::string breakout_problem() {
  json p;
  p["layerCount"] = 2;
  p["minTraceWidth"] = 0.12;
  p["bounds"] = {{"minX", -10.0}, {"maxX", 10.0}, {"minY", -7.0}, {"maxY", 7.0}};
  json obstacles = json::array(), connections = json::array();
  std::vector<std::pair<double, double>> ring;
  for (int i = 0; i < 8; ++i) ring.push_back({-4.2 + 1.2 * i, 5.2});
  for (int i = 0; i < 8; ++i) ring.push_back({-4.2 + 1.2 * i, -5.2});
  for (int i = 0; i < 4; ++i) ring.push_back({-5.2, -1.8 + 1.2 * i});
  for (int i = 0; i < 4; ++i) ring.push_back({5.2, -1.8 + 1.2 * i});
  int n = 0;
  for (int gy = -2; gy <= 2; ++gy)
    for (int gx = -2; gx <= 2; ++gx) {
      const double x = 0.8 * gx, y = 0.8 * gy;
      const bool ball_in_use = !(gx == 0 && gy == 0);
      const std::string id = "b" + std::to_string(n), tp = "t" + std::to_string(n);
      obstacles.push_back({{"type", "rect"}, {"layers", {"bottom"}}, {"center", {{"x", x}, {"y", y}}}, {"width", 0.36}, {"height", 0.36},
                           {"connectedTo", {id}}, {"obstacleId", "pad_" + id}, {"componentId", "bga"}});
      if (ball_in_use) {
        const auto [tx, ty] = ring[static_cast<std::size_t>((n * 5) % 24)];
        obstacles.push_back({{"type", "rect"}, {"layers", {"top"}}, {"center", {{"x", tx}, {"y", ty}}}, {"width", 0.6}, {"height", 0.5},
                             {"connectedTo", {tp}}, {"obstacleId", "pad_" + tp}, {"componentId", "T" + std::to_string(n)}});
        connections.push_back({{"name", "c" + std::to_string(n)},
                               {"pointsToConnect",
                                {{{"x", x}, {"y", y}, {"layer", "bottom"}, {"pointId", id}}, {{"x", tx}, {"y", ty}, {"layer", "top"}, {"pointId", tp}}}},
                               {"rootConnectionName", "c" + std::to_string(n)}});
      }
      ++n;
    }
  p["obstacles"] = obstacles;
  p["connections"] = connections;
  return p.dump();
}

// One connection between two top-layer pads, split by two offset top-layer keep-out walls
// (a chicane). The straight line is 8 mm; dipping under the walls costs the track plus two
// vias, weaving around the wall ends on layer costs about 17 mm of track and no vias, and the
// weave stays inside the first search window (chord box + 2 mm + length/4 = 4 mm margin).
// At the default via price (3 mm) the dip is cheaper (8 + 2*3 = 14 < 17); at
// via_search_mult 8 a via costs 24 mm and the weave wins.
std::string wall_problem() {
  json p;
  p["layerCount"] = 2;
  p["minTraceWidth"] = 0.12;
  p["bounds"] = {{"minX", -6.0}, {"maxX", 6.0}, {"minY", -7.0}, {"maxY", 7.0}};
  json obstacles = json::array(), connections = json::array();
  obstacles.push_back({{"type", "rect"}, {"layers", {"top"}}, {"center", {{"x", -4.0}, {"y", 0.0}}}, {"width", 0.6}, {"height", 0.5},
                       {"connectedTo", {"a"}}, {"obstacleId", "pad_a"}, {"componentId", "A"}});
  obstacles.push_back({{"type", "rect"}, {"layers", {"top"}}, {"center", {{"x", 4.0}, {"y", 0.0}}}, {"width", 0.6}, {"height", 0.5},
                       {"connectedTo", {"b"}}, {"obstacleId", "pad_b"}, {"componentId", "B"}});
  obstacles.push_back({{"type", "rect"}, {"layers", {"top"}}, {"center", {{"x", -1.1}, {"y", 1.5}}}, {"width", 0.8}, {"height", 9.0},
                       {"obstacleId", "wall1"}, {"componentId", "WALL"}});
  obstacles.push_back({{"type", "rect"}, {"layers", {"top"}}, {"center", {{"x", 1.1}, {"y", -1.5}}}, {"width", 0.8}, {"height", 9.0},
                       {"obstacleId", "wall2"}, {"componentId", "WALL"}});
  connections.push_back({{"name", "c0"},
                         {"pointsToConnect",
                          {{{"x", -4.0}, {"y", 0.0}, {"layer", "top"}, {"pointId", "a"}}, {{"x", 4.0}, {"y", 0.0}, {"layer", "top"}, {"pointId", "b"}}}}});
  p["obstacles"] = obstacles;
  p["connections"] = connections;
  return p.dump();
}

struct Loaded {
  model::Board board;
  model::DesignRules rules;
};

Loaded load_problem(const std::string& problem, const char* tag) {
  const auto files = io::srj_to_kicad(io::read_srj(problem));
  const fs::path dir = fs::temp_directory_path() / (std::string("tm_via_econ_test_") + tag + "_" + std::to_string(::getpid()));
  fs::create_directories(dir);
  const fs::path pcb = dir / "b.kicad_pcb";
  std::ofstream(pcb) << files.pcb;
  std::ofstream(dir / "b.kicad_pro") << files.pro;
  if (!files.dru.empty()) std::ofstream(dir / "b.kicad_dru") << files.dru;
  Loaded l{io::read_board_file(pcb.string()).board, io::read_design_rules(pcb.string())};
  fs::remove_all(dir);
  return l;
}

int errors(model::Board b, const model::DesignRules& r, const route::RouteResult& res) {
  for (const auto& t : res.tracks) b.tracks.push_back(t);
  for (const auto& v : res.vias) b.vias.push_back(v);
  int n = 0;
  for (const auto& v : drc::run_drc(b, r).violations)
    if (v.severity == "error" && v.type != "unconnected_items") ++n;
  return n;
}

route::RouterOptions options() {
  route::RouterOptions o;
  o.work_budget = 4000000;
  o.time_limit_s = 3600;  // the work budget decides, also in a slow sanitizer build
  o.gpu_device = -1;
  o.txn = 0;
  return o;
}

}  // namespace

TEST_CASE("via economics: the multiplier defaults to 1 and is inert at 1", "[route][via_econ]") {
  CHECK(route::RouterOptions{}.via_search_mult == 1.0);
  const auto l = load_problem(breakout_problem(), "inert");
  const auto base = route::route_portfolio(l.board, l.rules, options(), 1, {}, 2);
  route::RouterOptions explicit_one = options();
  explicit_one.via_search_mult = 1.0;
  const auto same = route::route_portfolio(l.board, l.rules, explicit_one, 1, {}, 2);
  CHECK(base.best.routed == same.best.routed);
  CHECK(base.best.tracks.size() == same.best.tracks.size());
  CHECK(base.best.vias.size() == same.best.vias.size());
  CHECK(base.best.expansions == same.best.expansions);
  CHECK(errors(l.board, l.rules, base.best) == 0);
}

TEST_CASE("via economics: a dearer via steers the search around a wall", "[route][via_econ]") {
  const auto l = load_problem(wall_problem(), "wall");
  route::RouterOptions cheap = options();
  cheap.optimize = false;  // isolate the search price: the clean-up has its own absolute via price and judge
  const auto dip = route::route_portfolio(l.board, l.rules, cheap, 1, {}, 1);
  CHECK(dip.best.routed == 1);
  CHECK(dip.best.vias.size() >= 2);  // down and back up: the dip the default price prefers
  CHECK(errors(l.board, l.rules, dip.best) == 0);
  route::RouterOptions dear = options();
  dear.optimize = false;
  dear.via_search_mult = 8.0;
  const auto around = route::route_portfolio(l.board, l.rules, dear, 1, {}, 1);
  CHECK(around.best.routed == 1);
  CHECK(around.best.vias.empty());  // the same-layer detour is cheaper than two 24 mm vias
  CHECK(errors(l.board, l.rules, around.best) == 0);
}

TEST_CASE("via economics: identical at any thread count with the multiplier on", "[route][via_econ]") {
  const auto l = load_problem(breakout_problem(), "threads");
  route::RouterOptions on = options();
  on.via_search_mult = 3.0;
  const auto one = route::route_portfolio(l.board, l.rules, on, 1, {}, 1);
  const auto four = route::route_portfolio(l.board, l.rules, on, 1, {}, 4);
  CHECK(one.best.routed == four.best.routed);
  CHECK(one.best.tracks.size() == four.best.tracks.size());
  CHECK(one.best.vias.size() == four.best.vias.size());
  CHECK(one.best.expansions == four.best.expansions);
  CHECK(errors(l.board, l.rules, one.best) == 0);
}
