// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: window
    title: "Goodix Manager"
    width: 840
    height: 780
    minimumWidth: 520
    minimumHeight: 560
    property var info: backend.view
    property string requestedAction: ""
    readonly property bool driverOperationActive: info.busy && ["install", "update", "remove"].indexOf(info.operation) !== -1
    // Bind all system groups at startup and on paletteChanged; no application theme override.
    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }
    SystemPalette { id: inactivePalette; colorGroup: SystemPalette.Inactive }
    SystemPalette { id: disabledPalette; colorGroup: SystemPalette.Disabled }
    palette.active {
        window: systemPalette.window
        windowText: systemPalette.windowText
        base: systemPalette.base
        alternateBase: systemPalette.alternateBase
        text: systemPalette.text
        button: systemPalette.button
        buttonText: systemPalette.buttonText
        light: systemPalette.light
        midlight: systemPalette.midlight
        dark: systemPalette.dark
        mid: systemPalette.mid
        shadow: systemPalette.shadow
        highlight: systemPalette.highlight
        highlightedText: systemPalette.highlightedText
        placeholderText: systemPalette.placeholderText
        accent: systemPalette.accent
    }
    palette.inactive {
        window: inactivePalette.window
        windowText: inactivePalette.windowText
        base: inactivePalette.base
        alternateBase: inactivePalette.alternateBase
        text: inactivePalette.text
        button: inactivePalette.button
        buttonText: inactivePalette.buttonText
        light: inactivePalette.light
        midlight: inactivePalette.midlight
        dark: inactivePalette.dark
        mid: inactivePalette.mid
        shadow: inactivePalette.shadow
        highlight: inactivePalette.highlight
        highlightedText: inactivePalette.highlightedText
        placeholderText: inactivePalette.placeholderText
        accent: inactivePalette.accent
    }
    palette.disabled {
        window: disabledPalette.window
        windowText: disabledPalette.windowText
        base: disabledPalette.base
        alternateBase: disabledPalette.alternateBase
        text: disabledPalette.text
        button: disabledPalette.button
        buttonText: disabledPalette.buttonText
        light: disabledPalette.light
        midlight: disabledPalette.midlight
        dark: disabledPalette.dark
        mid: disabledPalette.mid
        shadow: disabledPalette.shadow
        highlight: disabledPalette.highlight
        highlightedText: disabledPalette.highlightedText
        placeholderText: disabledPalette.placeholderText
        accent: disabledPalette.accent
    }
    readonly property color surfaceColor: systemPalette.window
    readonly property color cardColor: systemPalette.base
    readonly property color inkColor: systemPalette.text
    readonly property color lineColor: systemPalette.mid
    onClosing: function(close) {
        if (info.busy) {
            close.accepted = false
            busyDialog.open()
        }
    }
    pageStack.initialPage: Kirigami.ScrollablePage {
        id: page
        title: "Goodix Manager"
        Kirigami.Theme.inherit: false
        Kirigami.Theme.backgroundColor: window.surfaceColor
        Kirigami.Theme.textColor: window.inkColor
        background: Rectangle { color: window.surfaceColor }
        ColumnLayout {
            spacing: Kirigami.Units.largeSpacing * 2
            width: page.width - Kirigami.Units.largeSpacing * 4
            RowLayout {
                Layout.fillWidth: true
                Image {
                    source: "io.github.sorguido.GoodixManager.svg"
                    sourceSize.width: 76
                    sourceSize.height: 76
                    Layout.preferredWidth: 76
                    Layout.preferredHeight: 76
                    Accessible.ignored: true
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { color: window.inkColor; text: "Your fingerprint.\nYour device."; level: 1; font.pointSize: 22; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Controls.Label { text: "Goodix 27c6:5125 · Fedora KDE"; opacity: 0.72; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
            }
            Kirigami.AbstractCard {
                Layout.fillWidth: true
                padding: 22
                background: Rectangle { color: window.cardColor; radius: 16; border.color: window.lineColor; border.width: 1 }
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.largeSpacing
                    RowLayout {
                        Layout.fillWidth: true
                        Rectangle {
                            implicitWidth: 10
                            implicitHeight: 10
                            radius: 5
                            color: info.state === "blocked" ? "#e5a24b" : "#35b6ae"
                            Accessible.ignored: true
                        }
                        Kirigami.Heading { color: window.inkColor; text: info.busy ? "Working on your driver" : info.title; level: 2; font.pointSize: 17; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Controls.BusyIndicator {
                            objectName: "driverBusyIndicator"
                            running: info.busy
                            visible: running
                            implicitWidth: 44
                            implicitHeight: 44
                            Accessible.name: info.notice
                        }
                    }
                    Controls.Label { text: info.notice; wrapMode: Text.WordWrap; Layout.fillWidth: true; Accessible.role: Accessible.StaticText }
                    Controls.Label {
                        text: "Do not close Goodix Manager or interrupt the operation."
                        visible: window.driverOperationActive
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    GridLayout {
                        columns: 2
                        columnSpacing: 26
                        rowSpacing: 10
                        Layout.fillWidth: true
                        Controls.Label { text: "Installed driver"; opacity: 0.7 }
                        Controls.Label { text: info.runtime; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        Controls.Label { text: "This RPM"; opacity: 0.7 }
                        Controls.Label { text: info.payload }
                        Controls.Label { text: "Manager package"; opacity: 0.7 }
                        Controls.Label { text: info.package; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    }
                    Kirigami.InlineMessage {
                        objectName: "enrollmentRequiredNotice"
                        Layout.fillWidth: true
                        visible: info.enrollmentRequired
                        type: Kirigami.MessageType.Information
                        text: "New fingerprint enrollment is required. Earlier templates are preserved but cannot be used with this driver."
                    }
                    Kirigami.InlineMessage {
                        Layout.fillWidth: true
                        visible: info.rebootRequired
                        type: Kirigami.MessageType.Information
                        text: "Restart your computer before checking fingerprint login. Keep your password available."
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 10
                        Controls.Button { implicitHeight: 38;
                            text: info.upgradeLegacy ? "Upgrade to " + info.payload : info.action === "update" ? "Apply Update" : "Install"
                            icon.name: info.action === "update" ? "system-software-update" : "list-add"
                            highlighted: true
                            enabled: !info.busy && info.action !== ""
                            onClicked: { window.requestedAction = info.action; confirmDialog.open() }
                        }
                        Controls.Button { implicitHeight: 38;
                            text: "Verify status"
                            icon.name: "view-refresh"
                            enabled: !info.busy
                            onClicked: backend.refresh()
                        }
                        Controls.Button { implicitHeight: 38;
                            text: "Remove"
                            icon.name: "edit-delete"
                            enabled: !info.busy && info.canRemove
                            onClicked: { window.requestedAction = "remove"; confirmDialog.open() }
                        }
                    }
                }
            }
            Kirigami.AbstractCard {
                Layout.fillWidth: true
                padding: 22
                background: Rectangle { color: window.cardColor; radius: 16; border.color: window.lineColor; border.width: 1 }
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.largeSpacing
                    RowLayout {
                        Layout.fillWidth: true
                        Rectangle {
                            objectName: "softwareUpdatesIndicator"
                            implicitWidth: 10
                            implicitHeight: 10
                            radius: 5
                            color: info.remoteState === "current" ? "#27ae60" : info.remoteState === "available" ? "#e5a24b" : window.lineColor
                            Accessible.ignored: true
                        }
                        Kirigami.Heading { color: window.inkColor; text: "Software Updates"; level: 3; font.pointSize: 15; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Controls.BusyIndicator { running: info.remoteChecking; visible: info.remoteChecking; implicitWidth: 24; implicitHeight: 24 }
                    }
                    Controls.Label { text: info.remoteMessage; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Controls.Label {
                        visible: info.remoteAvailable
                        text: "Download the official RPM, verify its signature, open it in Discover, then reopen Goodix Manager to apply the local payload."
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 10
                        Controls.Button { implicitHeight: 38; text: "Download RPM"; icon.name: "download"; visible: info.remoteAvailable; onClicked: backend.open_release(true) }
                        Controls.Button { implicitHeight: 38; text: "Release notes"; icon.name: "document-open"; visible: info.remoteAvailable; onClicked: backend.open_release(false) }
                        Controls.Button { implicitHeight: 38; text: "Check again"; enabled: !info.remoteChecking; onClicked: backend.check_releases() }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Controls.Button { implicitHeight: 38; text: "Read Documents"; icon.name: "help-contents"; onClicked: backend.documents() }
                Controls.Button { implicitHeight: 38; text: "Report a bug"; icon.name: "tools-report-bug"; onClicked: backend.report_bug() }
                Item { Layout.fillWidth: true }
                Controls.Button { implicitHeight: 38;
                    text: "Copy diagnostics"
                    icon.name: "edit-copy"
                    onClicked: { backend.copy_diagnostics(); copiedLabel.text = "Diagnostics copied"; copiedTimer.restart() }
                }
            }
            Controls.Label { id: copiedLabel; Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; opacity: 0.7 }
            Controls.Label {
                text: "Installing the Manager package does not activate the driver. Removing the driver keeps this app available. Password login and recovery remain essential."
                wrapMode: Text.WordWrap
                opacity: 0.7
                Layout.fillWidth: true
            }
        }
    }
    Timer { id: copiedTimer; interval: 3000; onTriggered: copiedLabel.text = "" }
    Controls.Dialog {
        id: confirmDialog
        anchors.centerIn: parent
        width: Math.min(window.width - 48, 480)
        modal: true
        title: window.requestedAction === "remove" ? "Remove the fingerprint driver?" : window.requestedAction === "update" ? (info.upgradeLegacy ? "Upgrade to " + info.payload + "?" : "Apply the local update?") : "Install the fingerprint driver?"
        standardButtons: Controls.Dialog.Ok | Controls.Dialog.Cancel
        contentItem: Controls.Label {
            text: window.requestedAction === "remove"
                ? "This removes the installed driver using its ordinary integrity-checked uninstaller. Goodix Manager, pairing state and stored fingerprints are preserved. Keep your password available and restart afterwards."
                : info.upgradeLegacy ? "This upgrades the verified earlier driver directly to " + info.payload + ". The fingerprint format changes: enroll every finger again after the upgrade. Historical templates and pairing state are preserved. Keep your password available. No preliminary uninstall is required."
                : "The verified local payload will be applied with administrator authorization. New enrollment is required when moving from an earlier 2.x driver; historical templates are preserved. Keep your password available. This does not perform fingerprint enrollment or pair the reader."
            wrapMode: Text.WordWrap
        }
        onAccepted: backend.perform(window.requestedAction)
    }
    Controls.Dialog {
        id: busyDialog
        anchors.centerIn: parent
        width: Math.min(window.width - 48, 420)
        modal: true
        title: "Operation in progress"
        standardButtons: Controls.Dialog.Ok
        contentItem: Controls.Label { text: "Wait for the operation and its cleanup to finish before closing Goodix Manager."; wrapMode: Text.WordWrap }
    }
}
