// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

namespace PLASMALOGIN {
class SessionVt {
public:
    SessionVt() = default;
    ~SessionVt();
    SessionVt(const SessionVt &) = delete;
    SessionVt &operator=(const SessionVt &) = delete;
    int reserve();
    void release();
private:
    int m_fd = -1;
};
}
