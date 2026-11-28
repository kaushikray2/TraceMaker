// SPDX-License-Identifier: GPL-3.0-or-later
// Modifications Copyright (C) 2026 SiliconBrane Inc.
// Modified 2026 as part of the SiliconBrane fork of TraceMaker:
// work accounting is versioned, documented, and emitted in the route JSON.
// The modifications are licensed under GPL-3.0-or-later, the same
// terms as the original work. The original copyright notice above
// remains in force for the original portions of this file.
#pragma once
#include <string_view>

namespace tmk {
// TraceMaker version string, e.g. "0.1.0".
std::string_view version();

// What one --work expansion unit covers (issue 41). Version 1 is the upstream 0.12.1 accounting;
// version 2 folds the pair leg checks and the via-shove / pin-rescue / via-retry work into the
// expansion count, so a budget calibrated under version 1 buys measurably less search under
// version 2 (about half the reach on the Nomad reference fixture). Bump this whenever the
// accounting changes and say so at the --work entry of the CLI reference; it is emitted in the
// route JSON as work_accounting_version, next to the expansions count.
inline constexpr int kWorkAccountingVersion = 2;
}  // namespace tmk
