// SPDX-License-Identifier: GPL-3.0-or-later
#include "app/batch.hpp"

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

#include "app/route_job.hpp"
#include "core/parallel.hpp"
#include "core/version.hpp"
#include "route/router.hpp"

namespace tmk::app {
namespace {

using nlohmann::json;
namespace fs = std::filesystem;

std::string read_file(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::invalid_argument("cannot read " + path);
  return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}

std::string resolve(const fs::path& base, const std::string& p) {
  if (p.empty()) return p;
  const fs::path q(p);
  return q.is_absolute() ? p : (base / q).string();
}

// One manifest job, ready to run (or carrying the manifest error that stops it).
struct Spec {
  RouteJob job;
  std::string name;
  std::string json_path;
  int demand = 1;  // primary-worker tokens this job wants (its effective variant count)
  std::string error;
};

struct Record {
  int exit_code = 1;
  int routed = 0, connections = 0;
  double wall_s = 0;
  double peak_rss_mb = -1;
  std::string error;
};

void write_error_json(const Spec& sp, const std::string& error) {
  if (sp.json_path.empty()) return;
  const json j{{"board", sp.name}, {"input", sp.job.in}, {"output", sp.job.out}, {"error", error}, {"exit_code", 1}};
  std::ofstream(sp.json_path) << j.dump(1) << "\n";
}

// Applies one manifest option to a job; returns "" or the error to report for the board.
// A key's presence is its given-ness, exactly as a flag's presence is on the command line
// (seed_given / kb_given / time_given drive the determinism contract).
std::string apply_option(RouteJob& job, const std::string& key, const json& v, const fs::path& base) {
  auto bad = [&](const char* what) { return "option '" + key + "': expected " + what; };
  long lv = 0;
  double dv = 0;
  bool bv = false;
  std::string sv;
  std::vector<std::string> av;
  auto get_long = [&] {
    if (!v.is_number_integer() && !v.is_number_unsigned()) return false;
    lv = v.get<long>();
    return true;
  };
  auto get_double = [&] {
    if (!v.is_number()) return false;
    dv = v.get<double>();
    return true;
  };
  auto get_bool = [&] {
    if (!v.is_boolean()) return false;
    bv = v.get<bool>();
    return true;
  };
  auto get_string = [&] {
    if (!v.is_string()) return false;
    sv = v.get<std::string>();
    return true;
  };
  auto get_strings = [&] {
    if (!v.is_array()) return false;
    for (const auto& e : v) {
      if (!e.is_string()) return false;
      av.push_back(e.get<std::string>());
    }
    return true;
  };
  if (key == "seed") {
    if (!get_long()) return bad("an integer");
    job.opt.seed = static_cast<decltype(job.opt.seed)>(lv);
    job.seed_given = true;
  } else if (key == "work") {
    if (!get_long()) return bad("an integer");
    job.opt.work_budget = lv;
  } else if (key == "round_work") {
    if (!get_long()) return bad("an integer");
    job.opt.round_work = lv;
  } else if (key == "rounds") {
    if (!get_long()) return bad("an integer");
    job.opt.rounds = static_cast<int>(lv);
  } else if (key == "time") {
    if (!get_double()) return bad("a number");
    job.opt.time_limit_s = dv;
    job.time_given = true;
  } else if (key == "time_total") {
    if (!get_double()) return bad("a number");
    job.time_total_s = dv;
  } else if (key == "variants") {
    if (!get_long()) return bad("an integer");
    job.variants = static_cast<int>(lv);
  } else if (key == "repair") {
    if (!get_string()) return bad("a string");
    job.repair = sv;
  } else if (key == "relax") {
    if (!get_bool()) return bad("a boolean");
    job.opt.relax = bv;
  } else if (key == "halving") {
    if (!get_bool()) return bad("a boolean");
    job.opt.halving = bv;
  } else if (key == "deterministic") {
    if (!get_bool()) return bad("a boolean");
    job.deterministic_mode = bv;
  } else if (key == "early_stop") {
    if (!get_bool()) return bad("a boolean");
    if (bv) job.early_stop = true; else job.no_early_stop = true;
  } else if (key == "kb") {
    if (!get_string()) return bad("a string");
    job.kb_path = resolve(base, sv);
    job.kb_given = true;
  } else if (key == "only_nets") {
    if (!get_strings()) return bad("an array of strings");
    job.only_nets = av;
  } else if (key == "skip_nets") {
    if (!get_strings()) return bad("an array of strings");
    job.skip_nets = av;
  } else if (key == "reroute") {
    if (!get_bool()) return bad("a boolean");
    job.reroute = bv;
  } else if (key == "route_open_only") {
    if (!get_bool()) return bad("a boolean");
    job.route_open_only = bv;
  } else if (key == "reroute_nets") {
    if (!get_strings()) return bad("an array of strings");
    job.reroute_nets = av;
  } else if (key == "reroute_window") {
    if (!get_string()) return bad("a string");
    job.reroute_window = sv;
  } else if (key == "copper_layers") {
    if (!get_long()) return bad("an integer");
    job.copper_layers = static_cast<int>(lv);
  } else if (key == "warm_pcb") {
    if (!get_string()) return bad("a string");
    job.warm_pcb = resolve(base, sv);
  } else if (key == "heartbeat" || key == "heartbeat_s") {
    return "option '" + key + "': heartbeat is not available in batch mode (the live progress state is process-wide); route the board singly for a heartbeat";
  } else if (key == "threads") {
    return "option 'threads': the thread cap is set once for the whole batch (the manifest's \"threads\" or route-batch --threads), not per board";
  } else {
    return "unknown option '" + key + "'";
  }
  return "";
}

}  // namespace

int run_batch(const std::string& manifest_path, int threads_override, const std::string& summary_out,
              const std::function<void(const std::string&)>& log) {
  json m;
  try {
    m = json::parse(read_file(manifest_path));
  } catch (const std::exception& e) {
    log("route-batch: " + std::string(e.what()));
    return 2;
  }
  if (!m.is_object() || !m.contains("jobs") || !m["jobs"].is_array() || m["jobs"].empty()) {
    log("route-batch: the manifest must be a JSON object with a non-empty \"jobs\" array");
    return 2;
  }
  for (auto it = m.begin(); it != m.end(); ++it)
    if (it.key() != "jobs" && it.key() != "threads" && it.key() != "options") {
      log("route-batch: unknown manifest key '" + it.key() + "' (keys: jobs, threads, options)");
      return 2;
    }
  int threads = threads_override;
  if (threads <= 0 && m.contains("threads")) {
    if (!m["threads"].is_number_integer()) {
      log("route-batch: \"threads\" must be an integer");
      return 2;
    }
    threads = m["threads"].get<int>();
  }
  if (threads <= 0) threads = static_cast<int>(std::thread::hardware_concurrency());
  if (threads <= 0) threads = 8;
  json global_options = json::object();
  if (m.contains("options")) {
    if (!m["options"].is_object()) {
      log("route-batch: \"options\" must be an object");
      return 2;
    }
    global_options = m["options"];
  }
  const fs::path base = fs::absolute(fs::path(manifest_path)).parent_path();

  std::vector<Spec> specs;
  for (const auto& e : m["jobs"]) {
    Spec sp;
    if (!e.is_object()) {
      sp.name = "?";
      sp.error = "job entry is not an object";
      specs.push_back(std::move(sp));
      continue;
    }
    for (auto it = e.begin(); it != e.end() && sp.error.empty(); ++it)
      if (it.key() != "input" && it.key() != "output" && it.key() != "json" && it.key() != "options")
        sp.error = "unknown job key '" + it.key() + "' (keys: input, output, json, options)";
    std::string input, output, jsonp;
    if (sp.error.empty()) {
      if (!e.contains("input") || !e["input"].is_string() || !e.contains("output") || !e["output"].is_string()) {
        sp.error = "a job needs string \"input\" and \"output\" paths";
      } else {
        input = resolve(base, e["input"].get<std::string>());
        output = resolve(base, e["output"].get<std::string>());
        if (e.contains("json")) {
          if (!e["json"].is_string()) sp.error = "\"json\" must be a string path";
          else jsonp = resolve(base, e["json"].get<std::string>());
        }
      }
    }
    if (sp.error.empty() && e.contains("options") && !e["options"].is_object()) sp.error = "\"options\" must be an object";
    sp.name = input.empty() ? std::string("?") : fs::path(input).stem().string();
    if (jsonp.empty() && !output.empty()) {
      fs::path o(output);
      jsonp = o.replace_extension(".json").string();
    }
    sp.json_path = jsonp;
    sp.job.in = input;
    sp.job.out = output;
    sp.job.json_out = jsonp;
    sp.job.external_cap = true;  // the batch owns the process-wide cap (see the scheduler below)
    if (sp.error.empty())
      for (auto it = global_options.begin(); it != global_options.end() && sp.error.empty(); ++it)
        sp.error = apply_option(sp.job, it.key(), it.value(), base);
    if (sp.error.empty() && e.contains("options"))
      for (auto it = e["options"].begin(); it != e["options"].end() && sp.error.empty(); ++it)
        sp.error = apply_option(sp.job, it.key(), it.value(), base);
    // Primary-worker demand, mirroring run_route_job's effective-variant sizing (explicit
    // variants clamp at 64; automatic is the portfolio size). The job's granted tokens
    // become its thread count; work-budgeted results do not depend on it (issue #16).
    const int eff = sp.job.variants > 0 ? std::min(sp.job.variants, 64) : route::portfolio_size();
    sp.demand = std::clamp(std::min(eff, threads), 1, threads);
    specs.push_back(std::move(sp));
  }

  // Scheduler: one coordinator thread hands out primary-worker tokens from the batch cap.
  // A job runs with as many tokens as are free when it reaches the head of the queue (at
  // least one), so the sum of live jobs' thread counts never exceeds the cap; secondary
  // stages claim the remainder through the #19 budget the batch sets once, below. Waiting
  // jobs hold no thread: a thread is spawned per running job only.
  const auto batch_t0 = std::chrono::steady_clock::now();
  parallel::set_cap(threads);
  std::vector<Record> records(specs.size());
  std::mutex log_m;
  auto say = [&](const std::string& line) {
    std::lock_guard<std::mutex> g(log_m);
    log(line);
  };
  std::mutex sched_m;
  std::condition_variable sched_cv;
  int free_tokens = threads;
  int peak_granted = 0;
  int running = 0;
  std::size_t next = 0;
  std::vector<std::thread> live;
  while (true) {
    std::size_t idx = 0;
    int grant = 0;
    {
      std::unique_lock<std::mutex> lk(sched_m);
      sched_cv.wait(lk, [&] { return (next >= specs.size() && running == 0) || (next < specs.size() && free_tokens >= 1); });
      if (next >= specs.size() && running == 0) break;
      idx = next++;
      if (!specs[idx].error.empty()) {
        records[idx].exit_code = 1;
        records[idx].error = specs[idx].error;
        write_error_json(specs[idx], specs[idx].error);
        say("[" + specs[idx].name + "] not run: " + specs[idx].error);
        continue;
      }
      grant = std::min(specs[idx].demand, free_tokens);
      free_tokens -= grant;
      peak_granted = std::max(peak_granted, threads - free_tokens);
      ++running;
    }
    Spec& sp = specs[idx];
    sp.job.threads = grant;
    sp.job.log = [&log_m, &log, name = sp.name](const std::string& line) {
      std::lock_guard<std::mutex> g(log_m);
      log("[" + name + "] " + line);
    };
    live.emplace_back([&, idx, grant] {
      Record& rec = records[idx];
      const auto t0 = std::chrono::steady_clock::now();
      try {
        const RouteJobResult res = run_route_job(specs[idx].job);
        rec.exit_code = res.exit_code();
        rec.routed = res.result.routed;
        rec.connections = res.result.connections;
        if (res.summary.contains("peak_rss_mb") && res.summary["peak_rss_mb"].is_number()) rec.peak_rss_mb = res.summary["peak_rss_mb"].get<double>();
      } catch (const std::exception& e) {
        rec.exit_code = 1;
        rec.error = e.what();
        write_error_json(specs[idx], rec.error);
      }
      rec.wall_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
      {
        std::lock_guard<std::mutex> g(sched_m);
        free_tokens += grant;
        --running;
      }
      sched_cv.notify_all();
    });
  }
  for (auto& th : live) th.join();
  parallel::set_cap(0);

  const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - batch_t0).count();
  int completed = 0, partial = 0, failed = 0;
  json jobs = json::array();
  for (std::size_t i = 0; i < specs.size(); ++i) {
    const Record& rec = records[i];
    json j{{"name", specs[i].name}, {"input", specs[i].job.in}, {"output", specs[i].job.out}, {"json", specs[i].json_path},
           {"exit_code", rec.exit_code}, {"routed", rec.routed}, {"connections", rec.connections}, {"wall_s", rec.wall_s}};
    if (rec.peak_rss_mb >= 0) j["peak_rss_mb"] = rec.peak_rss_mb;
    if (!rec.error.empty()) j["error"] = rec.error;
    jobs.push_back(std::move(j));
    if (!rec.error.empty() || rec.exit_code == 1) ++failed;
    else if (rec.exit_code == 0) ++completed;
    else ++partial;
  }
  const json summary{{"batch", {{"version", std::string(version())}, {"manifest", manifest_path}, {"jobs", static_cast<int>(specs.size())},
                                {"threads", threads}, {"wall_s", wall}, {"boards_completed", completed}, {"boards_partial", partial},
                                {"boards_failed", failed}, {"peak_workers_granted", peak_granted}}},
                     {"jobs", std::move(jobs)}};
  if (!summary_out.empty()) {
    std::ofstream(summary_out) << summary.dump(1) << "\n";
  } else {
    std::printf("%s\n", summary.dump(1).c_str());
    std::fflush(stdout);
  }
  char line[256];
  std::snprintf(line, sizeof line, "route-batch: %zu boards, %d completed, %d partial, %d failed, %.1f s wall (peak workers granted %d of %d)",
                specs.size(), completed, partial, failed, wall, peak_granted, threads);
  say(line);
  return failed > 0 ? 1 : partial > 0 ? 3 : 0;
}

}  // namespace tmk::app
