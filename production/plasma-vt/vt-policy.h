// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

namespace PLASMALOGIN {
// VT_GETSTATE exposes only bits 1..15. Never infer freedom beyond that mask.
// This delivery qualifies Fedora logind's NAutoVTs=ReserveVT=6 contract.
constexpr int nextSessionVt(unsigned occupied, unsigned autoVts, int after = 0)
{
    if (autoVts != 6) return -1;
    for (int vt = after + 1; vt < 16; ++vt)
        if (unsigned(vt) > autoVts && !(occupied & (1U << vt))) return vt;
    return -1;
}
}
