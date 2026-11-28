// SPDX-License-Identifier: GPL-3.0-or-later
// Modifications Copyright (C) 2026 SiliconBrane Inc.
// Modified 2026 as part of the SiliconBrane fork of TraceMaker:
// the version stamp is computed at build time (cmake/GitVersion.cmake), and dirtiness ignores untracked files.
// The modifications are licensed under GPL-3.0-or-later, the same
// terms as the original work. The original copyright notice above
// remains in force for the original portions of this file.
#include "core/version.hpp"
#include "tm_version.hpp"  // generated at build time (cmake/GitVersion.cmake): TM_VERSION with the commit identity

namespace tmk {
std::string_view version() { return TM_VERSION; }
}  // namespace tmk
