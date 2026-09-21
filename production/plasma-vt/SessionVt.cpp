// SPDX-License-Identifier: GPL-2.0-or-later
// Local downstream policy; no changes to PAM, getty, logind or VT takeover.
#include "SessionVt.h"
#include "vt-policy.h"
#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusObjectPath>
#include <QDBusReply>
#include <QDBusVariant>
#include <QDebug>
#include <fcntl.h>
#include <linux/vt.h>
#include <sys/ioctl.h>
#include <unistd.h>

namespace PLASMALOGIN {
namespace {
QDBusMessage call(const QString &service, const QString &path,
                  const QString &interface, const QString &method,
                  const QList<QVariant> &args)
{
    auto request = QDBusMessage::createMethodCall(service, path, interface, method);
    request.setArguments(args);
    return QDBusConnection::systemBus().call(request, QDBus::Block, 1000);
}

// -1: unknown/error, 0: busy, 1: no unit/job can already be claiming this VT.
int gettyIdle(int vt)
{
    for (const auto &kind : {"getty", "autovt", "kmsconvt"}) {
        auto name = QStringLiteral("%1@tty%2.service").arg(QLatin1String(kind)).arg(vt);
        auto reply = call(QStringLiteral("org.freedesktop.systemd1"),
                          QStringLiteral("/org/freedesktop/systemd1"),
                          QStringLiteral("org.freedesktop.systemd1.Manager"),
                          QStringLiteral("GetUnit"), {name});
        if (reply.type() == QDBusMessage::ErrorMessage) {
            if (reply.errorName() == QLatin1String("org.freedesktop.systemd1.NoSuchUnit")) continue;
            return -1;
        }
        QDBusReply<QDBusObjectPath> unit(reply);
        if (!unit.isValid()) return -1;
        QDBusReply<QVariantMap> props(call(QStringLiteral("org.freedesktop.systemd1"),
            unit.value().path(), QStringLiteral("org.freedesktop.DBus.Properties"),
            QStringLiteral("GetAll"), {QStringLiteral("org.freedesktop.systemd1.Unit")}));
        if (!props.isValid()) return -1;
        const auto values = props.value();
        if (values.value(QStringLiteral("ActiveState")).toString() != QLatin1String("inactive")) return 0;
        const auto job = qvariant_cast<QDBusArgument>(values.value(QStringLiteral("Job")));
        if (job.currentSignature() != QLatin1String("(uo)")) return -1;
        uint id = 1; QDBusObjectPath path;
        job.beginStructure(); job >> id >> path; job.endStructure();
        if (id != 0) return 0;
    }
    return 1;
}
}

SessionVt::~SessionVt() { release(); }
void SessionVt::release()
{
    if (m_fd >= 0) { close(m_fd); m_fd = -1; }
}

int SessionVt::reserve()
{
    release();
    QDBusReply<QDBusVariant> config(call(QStringLiteral("org.freedesktop.login1"),
        QStringLiteral("/org/freedesktop/login1"), QStringLiteral("org.freedesktop.DBus.Properties"),
        QStringLiteral("Get"), {QStringLiteral("org.freedesktop.login1.Manager"), QStringLiteral("NAutoVTs")}));
    if (!config.isValid() || config.value().variant().metaType().id() != QMetaType::UInt
        || config.value().variant().toUInt() != 6) {
        qCritical("SESSION_VT=STOP reason=logind_contract");
        return -1;
    }
    const unsigned autoVts = config.value().variant().toUInt();
    int master = open("/dev/tty0", O_RDWR | O_NOCTTY | O_CLOEXEC);
    if (master < 0) { qCritical("SESSION_VT=STOP reason=console_open"); return -1; }
    int selected = -1;
    for (int previous = 0; previous < 15;) {
        vt_stat state{};
        if (ioctl(master, VT_GETSTATE, &state) < 0) break;
        int vt = nextSessionVt(state.v_state, autoVts, previous);
        if (vt < 0) break;
        previous = vt;
        int idle = gettyIdle(vt);
        if (idle < 0) break;
        if (idle == 0) continue;
        // Outside the automatic/reserved range: no queued automatic getty can
        // acquire the tty during PAM. Holding this fd also excludes it from
        // VT_OPENQRY until the helper has completed its session handoff.
        auto path = QStringLiteral("/dev/tty%1").arg(vt).toLocal8Bit();
        int fd = open(path.constData(), O_RDWR | O_NOCTTY | O_CLOEXEC);
        if (fd < 0) break;
        idle = gettyIdle(vt);
        if (idle != 1) { close(fd); if (idle < 0) break; continue; }
        m_fd = fd; selected = vt;
        qInfo("SELECTED_SESSION_VT=%d GETTY_STATE_FOR_SELECTED_VT=inactive_or_unloaded_no_job NAutoVTs=%u VT_RESERVATION=held", vt, autoVts);
        break;
    }
    close(master);
    if (selected < 0) qCritical("SESSION_VT=STOP reason=no_qualified_vt");
    return selected;
}
}
