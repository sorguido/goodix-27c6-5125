// SPDX-License-Identifier: GPL-2.0-or-later
import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    objectName: "diagnosticPage"
    required property var managerWindow
    readonly property QtObject scrollViewport: flickable
    property var diagnostic: backend.diagnostics
    property string screen: "dashboard"
    property string profile: "install"
    property string prepareOrigin: "choose"
    property bool awaitingReport: false
    property bool privacySubmitted: false
    property string exportNotice: ""
    readonly property bool available: !diagnostic.busy && !backend.view.busy
    readonly property var profileNames: ({system: "System status", install: "Installation or update failed", login: "Fingerprint sign-in problem", recognition: "Fingerprint recognition problem", other: "Other problem"})
    readonly property var timeChoices: ["During the current startup", "During the previous startup", "Within the last 30 minutes", "Earlier today", "Choose a date and time range", "Most recent installation attempt"]
    readonly property var timeValues: ["current", "previous", "last30", "today", "custom", "installation"]
    readonly property var checkDescriptions: ({driver: "Installation and file integrity", components: "Fedora libfprint, fprintd, dependencies and library files", service: "Service configuration, overrides and D-Bus", auth: "Fedora Plasma, PAM and authentication", security: "SELinux, file permissions and required labels", reader: "Is the Goodix USB device detected?"})
    readonly property var checkGlyphs: ({driver: "◉", components: "▤", service: "⚙", auth: "▣", security: "♢", reader: "♧"})
    readonly property color ink: managerWindow.inkColor
    readonly property color surface: managerWindow.surfaceColor
    readonly property color card: managerWindow.cardColor
    readonly property color line: managerWindow.lineColor
    title: screen === "dashboard" ? "Diagnostic Center" : "Diagnostic Center / " + ({checks: "System checks", choose: "Find a problem", prepare: "Prepare report", preview: "Review report", test: "Test the reader"})[screen]
    Kirigami.Theme.inherit: false
    Kirigami.Theme.backgroundColor: surface
    Kirigami.Theme.textColor: ink
    background: Rectangle { color: page.surface }
    Component.onDestruction: if (backend) backend.cancel_diagnostics()
    onVisibleChanged: if (!visible && diagnostic.busy) backend.cancel_diagnostics()

    function showScreen(next) {
        screen = next
        Qt.callLater(function() { if (page.flickable) page.flickable.contentY = 0 })
    }
    function invalidateReport() {
        awaitingReport = false
        exportNotice = ""
        backend.invalidate_diagnostic_report()
    }
    function prepareReport(selected, origin) {
        invalidateReport()
        profile = selected
        prepareOrigin = origin
        timeSelection.currentIndex = selected === "install" ? 5 : 0
        extendedDetails.checked = false
        showScreen("prepare")
    }
    function goBack() {
        if (screen === "dashboard") {
            managerWindow.pageStack.pop()
        } else if (screen === "prepare") {
            invalidateReport()
            showScreen(prepareOrigin)
        } else if (screen === "preview") {
            invalidateReport()
            showScreen("prepare")
        } else {
            if (screen === "test") backend.cancel_reader_test()
            showScreen("dashboard")
        }
    }
    function statusFor(id) {
        for (let check of diagnostic.checks) if (check.id === id) return check.summary
        return "Not checked"
    }
    function statusColor(outcome) {
        return outcome === "pass" ? "#27ae60" : outcome === "anomaly" ? "#d69c4c" : page.line
    }
    Connections {
        target: backend
        function onChanged() {
            if (page.awaitingReport && !page.diagnostic.collecting) {
                page.awaitingReport = false
                if (page.diagnostic.reportReady) page.showScreen("preview")
            }
        }
    }

    component ActionButton: Controls.Button { implicitHeight: 38 }

    component HeadingBlock: RowLayout {
        property string symbol
        property string heading
        property string description
        Layout.fillWidth: true
        spacing: 15
        Rectangle {
            Layout.preferredWidth: 49; Layout.preferredHeight: 49
            radius: 12
            color: "#086da2"
            Controls.Label { anchors.centerIn: parent; text: parent.parent.symbol; color: "white"; font.pixelSize: 27; Accessible.ignored: true }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 5
            Kirigami.Heading { text: parent.parent.heading; color: page.ink; level: 1; font.pixelSize: 27; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Controls.Label { text: parent.parent.description; wrapMode: Text.WordWrap; opacity: .78; Layout.fillWidth: true }
        }
    }
    component Panel: Controls.Frame {
        Layout.fillWidth: true
        padding: 22
        background: Rectangle { color: page.card; radius: 15; border.color: page.line }
    }
    component Notice: Controls.Frame {
        property string message
        Layout.fillWidth: true
        padding: 13
        background: Rectangle { color: page.card; radius: 9; border.color: page.line }
        contentItem: Controls.Label { text: parent.message; wrapMode: Text.WordWrap; color: page.ink; opacity: .85 }
    }
    component ChoiceCard: Controls.Button {
        property string symbol
        property string heading
        property string description
        Layout.fillWidth: true
        Layout.preferredHeight: page.width > 760 ? 154 : 120
        padding: 18
        enabled: page.available
        Accessible.name: heading
        background: Rectangle { color: parent.hovered ? Qt.lighter(managerWindow.palette.button, 1.12) : managerWindow.palette.button; radius: 12; border.color: parent.activeFocus || parent.hovered ? managerWindow.palette.highlight : page.line }
        contentItem: ColumnLayout {
            spacing: 8
            Controls.Label { text: parent.parent.symbol; color: managerWindow.palette.highlight; font.pixelSize: 27; Accessible.ignored: true }
            Controls.Label { text: parent.parent.heading; font.pixelSize: 17; font.weight: Font.DemiBold; color: page.ink; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Controls.Label { text: parent.parent.description; color: page.ink; opacity: .78; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
    }
    component IssueCard: Controls.Button {
        property string symbol
        property string heading
        property string description
        Layout.fillWidth: true
        Layout.preferredHeight: 112
        padding: 18
        enabled: page.available
        Accessible.name: heading
        background: Rectangle { color: parent.hovered ? Qt.lighter(managerWindow.palette.button, 1.12) : managerWindow.palette.button; radius: 12; border.color: parent.activeFocus || parent.hovered ? managerWindow.palette.highlight : page.line }
        contentItem: RowLayout {
            spacing: 13
            Controls.Label { text: parent.parent.symbol; color: managerWindow.palette.highlight; font.pixelSize: 27; Accessible.ignored: true }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8
                Controls.Label { text: parent.parent.parent.heading; font.pixelSize: 16; font.weight: Font.DemiBold; color: page.ink; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Controls.Label { text: parent.parent.parent.description; color: page.ink; opacity: .78; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
        }
    }
    component StepBar: RowLayout {
        Layout.fillWidth: true
        spacing: 7
        Repeater {
            model: ["Choose problem", "Prepare report", "Review & save"]
            RowLayout {
                required property string modelData
                required property int index
                Layout.fillWidth: true
                spacing: 7
                Rectangle {
                    Layout.preferredWidth: 28; Layout.preferredHeight: 28; radius: 14
                    color: index < 2 || page.screen === "preview" ? "#285d78" : "transparent"
                    border.color: index < 2 || page.screen === "preview" ? managerWindow.palette.highlight : page.line
                    Controls.Label { anchors.centerIn: parent; text: index + 1; color: index < 2 || page.screen === "preview" ? "white" : page.ink; font.pixelSize: 12 }
                }
                Controls.Label { text: modelData; font.pixelSize: 12; opacity: .75; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Rectangle { visible: index < 2; Layout.preferredWidth: page.width > 760 ? 30 : 10; height: 1; color: page.line }
            }
        }
    }

    ColumnLayout {
        width: page.width - Kirigami.Units.largeSpacing * 4
        spacing: 20
        RowLayout {
            Layout.fillWidth: true
            ActionButton {
                objectName: "diagnosticBack"
                flat: true
                text: page.screen === "dashboard" ? "Back to Manager" : page.screen === "prepare" ? (page.prepareOrigin === "checks" ? "System checks" : "Change problem") : page.screen === "preview" ? "Report options" : "Diagnostic Center"
                icon.name: "go-previous"
                enabled: page.available
                onClicked: page.goBack()
            }
            Controls.Label { text: "/ " + ({dashboard: "Diagnostic Center", checks: "Check my system", choose: "I have a problem", prepare: "Prepare report", preview: "Report ready", test: "Test the reader"})[page.screen]; opacity: .66; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        ColumnLayout {
            visible: page.screen === "dashboard"
            Layout.fillWidth: true
            spacing: 21
            HeadingBlock { objectName: "diagnosticHero"; symbol: "⌁"; heading: "Diagnostic Center"; description: "Check your system, understand problems, and prepare reports for support." }
            Panel {
                contentItem: ColumnLayout {
                    spacing: 16
                    RowLayout {
                        Layout.fillWidth: true
                        Kirigami.Heading { text: "System overview"; color: page.ink; font.pixelSize: 21; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        ActionButton { objectName: "overviewRunChecks"; text: "Run system checks"; icon.name: "view-refresh"; enabled: page.available; onClicked: backend.run_diagnostics() }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 14
                        Rectangle {
                            Layout.preferredWidth: 39; Layout.preferredHeight: 39; radius: 20
                            color: page.diagnostic.checks.some(function(check) { return check.outcome === "anomaly" }) ? "#493827" : "#283a45"
                            Controls.Label { anchors.centerIn: parent; text: page.diagnostic.checks.some(function(check) { return check.outcome === "anomaly" }) ? "!" : "i"; color: "#91cfee"; font.pixelSize: 23; Accessible.ignored: true }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Controls.Label { objectName: "overviewFinding"; text: page.diagnostic.overview; font.weight: Font.DemiBold; font.pixelSize: 16; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Controls.Label { text: "Only completed checks support a conclusion. Current configuration does not guarantee a future fingerprint attempt or login."; opacity: .78; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: page.line }
                    GridLayout {
                        columns: page.width > 760 ? 4 : 2
                        Layout.fillWidth: true
                        columnSpacing: 15; rowSpacing: 15
                        Repeater {
                            model: [{key: "driver", title: "Driver", glyph: "◉"}, {key: "service", title: "Services", glyph: "⚙"}, {key: "auth", title: "Sign-in", glyph: "▤"}, {key: "reader", title: "Reader", glyph: "♧"}]
                            ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.minimumWidth: 100
                                spacing: 7
                                Controls.Label { text: modelData.glyph; color: managerWindow.palette.highlight; font.pixelSize: 25; Layout.alignment: Qt.AlignHCenter; Accessible.ignored: true }
                                Controls.Label { text: modelData.title; font.weight: Font.DemiBold; Layout.alignment: Qt.AlignHCenter }
                                Controls.Label { text: page.statusFor(modelData.key); opacity: .75; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; Layout.fillWidth: true }
                            }
                        }
                    }
                }
            }
            Kirigami.Heading { text: "What would you like to do?"; color: page.ink; level: 2; font.pixelSize: 20; font.weight: Font.DemiBold }
            GridLayout {
                columns: page.width > 760 ? 3 : 1
                Layout.fillWidth: true
                columnSpacing: 13; rowSpacing: 13
                ChoiceCard { objectName: "chooseChecks"; symbol: "◫"; heading: "Check my system"; description: "Check the main components and find configuration problems."; onClicked: page.showScreen("checks") }
                ChoiceCard { objectName: "chooseProblem"; symbol: "☷"; heading: "I have a problem"; description: "Tell us what happened. We'll help you collect the right information."; onClicked: page.showScreen("choose") }
                ChoiceCard { objectName: "chooseReader"; symbol: "◉"; heading: "Test the reader"; description: "Check the fingerprint reader on request, using the normal driver path."; onClicked: page.showScreen("test") }
            }
            Notice { message: "Checks never change Fedora settings or repair your system automatically. Reports stay on your computer until you choose to share them." }
        }
        ColumnLayout {
            visible: page.screen === "checks"
            Layout.fillWidth: true
            spacing: 18
            HeadingBlock { symbol: "◫"; heading: "System checks"; description: "Check the components required for fingerprint authentication." }
            Notice { message: page.diagnostic.generatedAt ? "Checked: " + page.diagnostic.generatedAt + ". " + page.diagnostic.overview : "No checks have been run yet. Choose Run checks to inspect current system evidence without opening the reader." }
            Panel {
                padding: 0
                contentItem: ColumnLayout {
                    spacing: 0
                    Repeater {
                        model: page.diagnostic.checks.length ? page.diagnostic.checks : [
                            {id: "driver", title: "Goodix driver", summary: "Not checked", outcome: "not_checked", detail: "Installation and file integrity"},
                            {id: "components", title: "Fingerprint components", summary: "Not checked", outcome: "not_checked", detail: "Fedora libfprint, fprintd, dependencies and library files"},
                            {id: "service", title: "Fingerprint service", summary: "Not checked", outcome: "not_checked", detail: "Service configuration, overrides and D-Bus"},
                            {id: "auth", title: "Sign-in integration", summary: "Not checked", outcome: "not_checked", detail: "Fedora Plasma, PAM and authentication"},
                            {id: "security", title: "Security settings", summary: "Not checked", outcome: "not_checked", detail: "SELinux, file permissions and required labels"},
                            {id: "reader", title: "Fingerprint reader", summary: "Not checked", outcome: "not_checked", detail: "Is the Goodix USB device detected?"}]
                        ColumnLayout {
                            id: checkDelegate
                            required property var modelData
                            property bool expanded: false
                            Layout.fillWidth: true
                            spacing: 0
                            Controls.AbstractButton {
                                objectName: "check-" + checkDelegate.modelData.id
                                Layout.fillWidth: true
                                padding: 18
                                Accessible.name: checkDelegate.modelData.title + ": " + checkDelegate.modelData.summary
                                onClicked: checkDelegate.expanded = !checkDelegate.expanded
                                contentItem: RowLayout {
                                    spacing: 14
                                    Controls.Label { text: page.checkGlyphs[checkDelegate.modelData.id]; color: managerWindow.palette.highlight; font.pixelSize: 22; Accessible.ignored: true }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Controls.Label { text: checkDelegate.modelData.title; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                        Controls.Label { text: page.checkDescriptions[checkDelegate.modelData.id]; opacity: .75; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                    }
                                    Rectangle {
                                        Layout.preferredWidth: Math.min(160, statusLabel.implicitWidth + 20)
                                        Layout.preferredHeight: Math.max(30, statusLabel.implicitHeight + 12)
                                        color: managerWindow.palette.button; radius: 6
                                        border.color: page.statusColor(checkDelegate.modelData.outcome)
                                        Controls.Label { id: statusLabel; anchors.centerIn: parent; width: Math.min(140, implicitWidth); text: checkDelegate.modelData.summary; color: page.ink; font.pixelSize: 12; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter }
                                    }
                                    Controls.Label { text: checkDelegate.expanded ? "⌃" : "⌄"; color: page.statusColor(checkDelegate.modelData.outcome); Accessible.ignored: true }
                                }
                            }
                            Controls.Label { objectName: "detail-" + checkDelegate.modelData.id; visible: checkDelegate.expanded; text: checkDelegate.modelData.detail; wrapMode: Text.WordWrap; Layout.fillWidth: true; Layout.margins: 18; opacity: .8 }
                            Rectangle { Layout.fillWidth: true; height: 1; color: page.line }
                        }
                    }
                }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: page.width > 760 ? 3 : 1
                columnSpacing: 12; rowSpacing: 12
                ActionButton { objectName: "runChecks"; text: "Run checks"; icon.name: "view-refresh"; enabled: page.available; onClicked: backend.run_diagnostics() }
                Item { visible: page.width > 760; Layout.fillWidth: true }
                ActionButton { objectName: "prepareSystemReport"; text: "Prepare system report"; highlighted: true; enabled: page.available; onClicked: page.prepareReport("system", "checks") }
            }
        }
        ColumnLayout {
            visible: page.screen === "choose"
            Layout.fillWidth: true
            spacing: 20
            HeadingBlock { symbol: "☷"; heading: "What isn't working?"; description: "Choose the option closest to your problem. No technical knowledge needed." }
            GridLayout {
                columns: page.width > 760 ? 2 : 1
                Layout.fillWidth: true
                columnSpacing: 12; rowSpacing: 12
                IssueCard { objectName: "problemInstall"; symbol: "↓"; heading: "Installation or update failed"; description: "Driver couldn't be installed, updated or removed."; onClicked: page.prepareReport("install", "choose") }
                IssueCard { objectName: "problemLogin"; symbol: "▣"; heading: "I can't sign in with a fingerprint"; description: "Problems at the login screen, when unlocking, with sudo or with polkit."; onClicked: page.prepareReport("login", "choose") }
                IssueCard { objectName: "problemRecognition"; symbol: "◉"; heading: "Fingerprint isn't recognized"; description: "Finger not detected, no match, interrupted scan or retry issue."; onClicked: page.prepareReport("recognition", "choose") }
                IssueCard { objectName: "problemOther"; symbol: "⋯"; heading: "Something else"; description: "Collect a broad system report when none of the above applies."; onClicked: page.prepareReport("other", "choose") }
            }
            Notice { message: "The report type is chosen automatically from your answer. Extended details can be included only if you request them." }
        }
        ColumnLayout {
            visible: page.screen === "prepare"
            Layout.fillWidth: true
            spacing: 18
            StepBar {}
            HeadingBlock { symbol: "▤"; heading: "Prepare a diagnostic report"; description: "Selected problem: " + page.profileNames[page.profile] + ". We'll prepare the most relevant information." }
            Panel {
                contentItem: ColumnLayout {
                    spacing: 12
                    Controls.Label { text: "When did it happen?"; font.weight: Font.DemiBold }
                    Controls.ComboBox { objectName: "reportTime"; id: timeSelection; implicitHeight: 41; model: page.timeChoices; Layout.fillWidth: true; enabled: page.available; onCurrentIndexChanged: page.invalidateReport(); Accessible.name: "When did it happen?" }
                    Controls.Label { text: "If older events were not preserved by Fedora, the report will say so."; opacity: .72; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Controls.Label { visible: timeSelection.currentIndex === 4; text: "Enter start and end timestamps including the timezone (maximum 24 hours)."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Controls.TextField { objectName: "reportSince"; id: reportSince; visible: timeSelection.currentIndex === 4; placeholderText: "Start: 2026-11-08T09:00:00+01:00"; Layout.fillWidth: true; enabled: page.available; onTextChanged: page.invalidateReport(); Accessible.name: "Start date and time with timezone" }
                    Controls.TextField { objectName: "reportUntil"; id: reportUntil; visible: timeSelection.currentIndex === 4; placeholderText: "End: 2026-11-08T10:00:00+01:00"; Layout.fillWidth: true; enabled: page.available; onTextChanged: page.invalidateReport(); Accessible.name: "End date and time with timezone" }
                }
            }
            Panel {
                contentItem: ColumnLayout {
                    spacing: 10
                    Controls.Label { text: "What should be included?"; font.weight: Font.DemiBold }
                    Controls.CheckBox { text: "Essential diagnostic information"; checked: true; enabled: false }
                    Controls.Label { text: "Relevant component state, fixed error codes and event timestamps."; opacity: .75; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Controls.CheckBox { objectName: "extendedDetails"; id: extendedDetails; text: "Include extended technical details"; enabled: page.available; onCheckedChanged: page.invalidateReport() }
                    Controls.Label { text: "Reports may include event times, system paths or other personal details. Raw messages, pairing data, credentials and fingerprints are always excluded."; opacity: .75; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
            }
            Notice { message: "A report based on system events may contain personal details. You'll see a privacy notice before collection and can review everything before sharing." }
            RowLayout {
                Layout.fillWidth: true
                ActionButton { text: "Back"; enabled: page.available; onClicked: page.goBack() }
                Item { Layout.fillWidth: true }
                ActionButton { objectName: "continueReport"; text: "Continue to report"; icon.name: "go-next"; highlighted: true; enabled: page.available; onClicked: { page.invalidateReport(); page.privacySubmitted = false; consentCheck.checked = false; privacyDialog.open() } }
            }
        }
        ColumnLayout {
            visible: page.screen === "preview" && page.diagnostic.reportReady
            Layout.fillWidth: true
            spacing: 18
            StepBar {}
            HeadingBlock { symbol: "▤"; heading: "Review your report"; description: "Read the summary before deciding whether to save or share the details." }
            Panel {
                contentItem: ColumnLayout {
                    spacing: 12
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 14
                        Rectangle {
                            Layout.preferredWidth: 39; Layout.preferredHeight: 39; radius: 20
                            color: "#493827"
                            Controls.Label { anchors.centerIn: parent; text: "!"; color: "#f2c077"; font.pixelSize: 23; Accessible.ignored: true }
                        }
                        Kirigami.Heading { text: page.diagnostic.reportTitle; color: page.ink; font.pixelSize: 21; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                    Controls.Label { text: page.diagnostic.reportSummary; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Repeater {
                        model: page.diagnostic.checks.filter(function(check) { return check.outcome === "anomaly" })
                        ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 5
                            Controls.Label { objectName: "finding-title-" + modelData.id; text: modelData.title + ": " + modelData.summary; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            Controls.Label { objectName: "finding-detail-" + modelData.id; text: modelData.detail; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        }
                    }
                    Rectangle { height: 1; Layout.fillWidth: true; color: page.line }
                    Controls.Label { text: "Problem type: " + page.profileNames[page.profile]; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Controls.Label { text: "Time range: " + page.timeChoices[timeSelection.currentIndex]; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Controls.Label { text: "Data included: Essential information" + (extendedDetails.checked ? " + extended details" : ""); wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
            }
            Controls.Label { text: "Technical report preview"; font.weight: Font.DemiBold }
            Controls.ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: 260
                Controls.TextArea { objectName: "reportPreview"; text: page.diagnostic.reportText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; font.family: "monospace"; Accessible.name: "Technical report preview" }
            }
            Notice { message: "Reports are saved locally. Nothing is uploaded or sent to the maintainer automatically. Always review personal information before attaching a report to an issue." }
            GridLayout {
                Layout.fillWidth: true
                columns: page.width > 760 ? 3 : 1
                columnSpacing: 12; rowSpacing: 12
                ActionButton { objectName: "previewBack"; text: "Report options"; icon.name: "go-previous"; onClicked: page.goBack() }
                Item { visible: page.width > 760; Layout.fillWidth: true }
                RowLayout {
                    spacing: 12
                    ActionButton { objectName: "copyReport"; text: "Copy report"; icon.name: "edit-copy"; enabled: page.available && page.diagnostic.reportReady; onClicked: { backend.copy_diagnostic_report(); page.exportNotice = "Report copied. Review personal information before sharing." } }
                    ActionButton { objectName: "saveReport"; text: "Save report .txt"; icon.name: "document-save"; highlighted: true; enabled: page.available && page.diagnostic.reportReady; onClicked: backend.save_diagnostic_report() }
                }
            }
            Controls.Label { text: page.exportNotice; visible: text.length > 0; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        ColumnLayout {
            visible: page.screen === "test"
            Layout.fillWidth: true
            spacing: 20
            HeadingBlock { symbol: "◉"; heading: "Test the fingerprint reader"; description: "A guided check using the normal fingerprint verification path." }
            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 185; Layout.preferredHeight: 185
                color: "transparent"; radius: 93; border.width: 3; border.color: page.line
                Image { anchors.centerIn: parent; source: "io.github.sorguido.GoodixManager.svg"; sourceSize.width: 100; sourceSize.height: 100; Accessible.ignored: true }
            }
            Kirigami.Heading { objectName: "readerHeading"; text: page.diagnostic.readerBusy ? "Reader test in progress" : page.diagnostic.readerState === "match" ? "Fingerprint matched" : !page.diagnostic.readerCanStart ? "Reader test stopped" : "Ready to check the reader"; color: page.ink; font.pixelSize: 24; Layout.alignment: Qt.AlignHCenter; wrapMode: Text.WordWrap }
            Controls.Label { objectName: "readerMessage"; text: page.diagnostic.readerMessage; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Notice { message: "This requests ordinary fingerprint verification. A first biometric action may activate the driver's qualified Linux pairing. No new fingerprint is enrolled. Keep your password available. At most three physical attempts; stop on the first match." }
            Controls.CheckBox { objectName: "readerConsent"; id: readerConsent; text: "I understand and want to test the reader"; enabled: !page.diagnostic.readerBusy && page.diagnostic.readerCanStart }
            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                ActionButton { objectName: "readerStart"; text: "Start reader test"; highlighted: true; enabled: page.available && page.diagnostic.readerCanStart && readerConsent.checked; onClicked: backend.start_reader_test(readerConsent.checked) }
                ActionButton { objectName: "readerCancel"; text: "Cancel test"; enabled: page.diagnostic.readerBusy; onClicked: backend.cancel_reader_test() }
            }
            Controls.Label { text: "Physical attempts started: " + page.diagnostic.readerAttempts + " / 3. A successful test does not guarantee a future login."; opacity: .75; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        RowLayout {
            visible: page.diagnostic.collecting
            Layout.fillWidth: true
            Controls.BusyIndicator { running: parent.visible; Layout.preferredWidth: 32; Layout.preferredHeight: 32 }
            Controls.Label { text: "Collecting a bounded, read-only diagnostic snapshot…"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            ActionButton { objectName: "cancelCollection"; text: "Cancel"; onClicked: backend.cancel_diagnostics() }
        }
        Notice { visible: page.diagnostic.reportError.length > 0; message: page.diagnostic.reportError }
    }
    Controls.Dialog {
        id: privacyDialog
        objectName: "privacyDialog"
        anchors.centerIn: parent
        width: Math.min(page.width - 32, 535)
        modal: true
        title: "Before collecting this report"
        closePolicy: Controls.Popup.CloseOnEscape
        contentItem: ColumnLayout {
            spacing: 14
            Controls.Label { text: "Diagnostic logs can include information about your computer and activity:"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Controls.Label { text: "• Event timestamps and selected system paths\n• Configuration findings and fixed error categories\n• Fingerprint-related event metadata"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Notice { message: "Pairing secrets, passwords, fingerprint images, biometric templates and raw messages are never included. Nothing is uploaded automatically." }
            Controls.CheckBox { objectName: "reportConsent"; id: consentCheck; text: "I will review the report before sharing it"; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                ActionButton { objectName: "cancelConsent"; text: "Cancel"; onClicked: privacyDialog.close() }
                Item { Layout.fillWidth: true }
                ActionButton {
                    objectName: "createReport"
                    text: "Create report"
                    highlighted: true
                    enabled: consentCheck.checked && page.available
                    onClicked: {
                        page.privacySubmitted = true
                        backend.create_diagnostic_report(page.profile, page.timeValues[timeSelection.currentIndex], extendedDetails.checked, consentCheck.checked, reportSince.text, reportUntil.text)
                        page.awaitingReport = page.diagnostic.collecting
                        privacyDialog.close()
                    }
                }
            }
        }
        onClosed: if (!page.privacySubmitted) page.invalidateReport()
    }
}
