// SPDX-License-Identifier: GPL-3.0-or-later
// Issue 68 (Phase 4B): congestion-weighted re-decomposition of multi-pin nets during negotiation
// (RouterOptions::redecomp_every). On a generated breakout with one multi-pin bus net united across
// three connections: with the option on the result stays legal and does not depend on the thread
// count, and with the option off nothing changes. (That re-decomposition fires and re-pairs on real
// boards is bench evidence, not a unit assertion: bench/records/p4b-redecomp. A synthetic board that
// negotiates for many passes with a multi-pin net still open is not stable enough to assert on.)
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

// The test_txn ball-grid breakout (many crossings, negotiation has to rip), plus one multi-pin net:
// three pads on the left (bottom) and three on the right (top), united as one net through three
// connections that share a __netConnectionName, in crossing order, so the net spans the whole board
// and its spanning tree is decided again while the breakout traffic congests the middle.
std::string problem() {
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
  const double lys[3] = {-2.0, 0.0, 2.0};
  for (int i = 0; i < 3; ++i) {
    const std::string lid = "bl" + std::to_string(i), rid = "br" + std::to_string(i);
    obstacles.push_back({{"type", "rect"}, {"layers", {"bottom"}}, {"center", {{"x", -8.0}, {"y", lys[i]}}}, {"width", 0.6}, {"height", 0.5},
                         {"connectedTo", {lid}}, {"obstacleId", "pad_" + lid}, {"componentId", "BL"}});
    obstacles.push_back({{"type", "rect"}, {"layers", {"top"}}, {"center", {{"x", 8.0}, {"y", lys[2 - i]}}}, {"width", 0.6}, {"height", 0.5},
                         {"connectedTo", {rid}}, {"obstacleId", "pad_" + rid}, {"componentId", "BR"}});
    connections.push_back({{"name", "bus" + std::to_string(i)},
                           {"__netConnectionName", "BUS"},
                           {"pointsToConnect",
                            {{{"x", -8.0}, {"y", lys[i]}, {"layer", "bottom"}, {"pointId", lid}},
                             {{"x", 8.0}, {"y", lys[2 - i]}, {"layer", "top"}, {"pointId", rid}}}}});
  }
  p["obstacles"] = obstacles;
  p["connections"] = connections;
  return p.dump();
}

struct Loaded {
  model::Board board;
  model::DesignRules rules;
};

Loaded load_problem() {
  const auto files = io::srj_to_kicad(io::read_srj(problem()));
  const fs::path dir = fs::temp_directory_path() / ("tm_redecomp_test_" + std::to_string(::getpid()));
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

TEST_CASE("re-decomposition: legal result, identical at any thread count", "[route][redecomp]") {
  const auto l = load_problem();
  route::RouterOptions on = options();
  on.redecomp_every = 1;
  const auto one = route::route_portfolio(l.board, l.rules, on, 1, {}, 1);
  const auto four = route::route_portfolio(l.board, l.rules, on, 1, {}, 4);
  CHECK(one.best.routed == four.best.routed);
  CHECK(one.best.tracks.size() == four.best.tracks.size());
  CHECK(one.best.vias.size() == four.best.vias.size());
  CHECK(one.best.expansions == four.best.expansions);
  CHECK(one.best.redecomp_changed == four.best.redecomp_changed);
  CHECK(errors(l.board, l.rules, one.best) == 0);
}

TEST_CASE("re-decomposition: off by default and changes nothing when off", "[route][redecomp]") {
  const auto l = load_problem();
  const auto off = route::route_portfolio(l.board, l.rules, options(), 1, {}, 2);
  route::RouterOptions on = options();
  on.redecomp_every = 1;
  const auto with = route::route_portfolio(l.board, l.rules, on, 1, {}, 2);
  CHECK(off.best.redecomp_rounds == 0);
  CHECK(off.best.redecomp_changed == 0);
  CHECK(errors(l.board, l.rules, off.best) == 0);
  CHECK(with.best.routed >= off.best.routed);  // re-pairing may only help the bus net, never lose routes
}
