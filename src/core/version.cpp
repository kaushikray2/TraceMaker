// SPDX-License-Identifier: GPL-3.0-or-later
#include "core/version.hpp"
#include "tm_version.hpp"  // generated at build time (cmake/GitVersion.cmake): TM_VERSION with the commit identity

namespace tmk {
std::string_view version() { return TM_VERSION; }
}  // namespace tmk
