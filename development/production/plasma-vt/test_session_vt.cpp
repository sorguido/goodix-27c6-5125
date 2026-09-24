// SPDX-License-Identifier: GPL-2.0-or-later
// Real SessionVt implementation, fake kernel calls, private synthetic D-Bus.
#include "SessionVt.h"
#include <QCoreApplication>
#include <cassert>
#include <cstdarg>
#include <cstdlib>
#include <linux/vt.h>
#include <fcntl.h>
#include <string>

static unsigned mask, initial;
static int held = 0;
extern "C" int __wrap_open(const char *path, int flags, ...)
{
    assert((flags & (O_NOCTTY | O_CLOEXEC)) == (O_NOCTTY | O_CLOEXEC));
    std::string p(path);
    assert(p.starts_with("/dev/tty"));
    int vt = std::stoi(p.substr(8));
    if (!vt) return 100;
    assert(vt > 6 && vt < 16 && !(mask & (1U << vt)));
    mask |= 1U << vt; ++held;
    return 100 + vt;
}
extern "C" int __wrap_close(int fd)
{
    assert(fd >= 100 && fd < 116);
    if (fd != 100) { mask &= ~(1U << (fd - 100)); --held; }
    return 0;
}
extern "C" int __wrap_ioctl(int fd, unsigned long request, ...)
{
    assert(fd == 100 && request == VT_GETSTATE);
    va_list args; va_start(args, request);
    auto state = va_arg(args, vt_stat *); va_end(args);
    state->v_state = mask; state->v_active = 1;
    return 0;
}
int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    assert(argc == 3);
    mask = initial = std::stoul(argv[1]);
    int expected = std::stoi(argv[2]);
    {
        PLASMALOGIN::SessionVt session;
        assert(session.reserve() == expected);
        assert(held == (expected > 0 ? 1 : 0));
        if (expected > 0) assert(mask & (1U << expected));
        // Auth cancellation and repeated release are symmetric.
        session.release(); session.release();
        assert(mask == initial && held == 0);
        assert(session.reserve() == expected);
    }
    // Session/helper failure and Display destruction release the reservation.
    assert(mask == initial && held == 0);
}
