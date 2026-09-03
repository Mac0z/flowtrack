"""Small startup dialogs; all lease interpretation remains outside the UI."""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from flowtrack.application.startup import StartupChoice
from flowtrack.infrastructure.lease import LeaseState
from flowtrack.infrastructure.conflicts import ConflictScanResult


def decide_conflicts(result: ConflictScanResult, parent: QWidget | None = None) -> bool:
    """Require an explicit acknowledgement before suspicious data is opened writable."""
    while True:
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Possible database conflict detected")
        box.setText("FlowTrack found another file that may be a synchronisation conflict.")
        details = [f"Canonical: {result.canonical.name}", ""]
        details.extend(
            f"• {item.filename} — {item.modified_utc:%Y-%m-%d %H:%M} UTC — "
            f"{'valid SQLite' if item.sqlite_valid else 'invalid or unverified'}"
            for item in result.candidates
        )
        box.setInformativeText("\n".join(details) +
            "\n\nFlowTrack will not merge, rename, or delete either file automatically.")
        open_folder = box.addButton("Open Data Folder", QMessageBox.ButtonRole.ActionRole)
        proceed = box.addButton("Continue Carefully", QMessageBox.ButtonRole.DestructiveRole)
        exit_button = box.addButton("Exit", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(exit_button)
        box.exec()
        if box.clickedButton() is open_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(result.canonical.parent)))
            continue
        return box.clickedButton() is proceed


def choose_data_directory(parent: QWidget | None = None) -> Path | None:
    QMessageBox.information(
        parent, "Choose Data Location",
        "Choose where FlowTrack stores your data. This may be a local folder or a "
        "synchronised folder such as OneDrive.",
    )
    selected = QFileDialog.getExistingDirectory(parent, "Choose FlowTrack Data Directory")
    return Path(selected) if selected else None


def decide_startup(state: LeaseState, parent: QWidget | None = None) -> StartupChoice:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("FlowTrack Data Safety")
    readonly = box.addButton("Open Read-Only", QMessageBox.ButtonRole.AcceptRole)
    recover = None
    if state is LeaseState.ACTIVE_OTHER_INSTANCE:
        box.setText("This dataset appears to be open on another computer.")
        box.setInformativeText(
            "Synchronised folders such as OneDrive do not provide database-level locking."
        )
    elif state is LeaseState.STALE_OTHER_INSTANCE:
        box.setText("FlowTrack has not received a recent heartbeat for this dataset.")
        box.setInformativeText(
            "The previous session may have crashed or another computer may be offline. "
            "Recover only if FlowTrack is not open there."
        )
        recover = box.addButton("Recover Write Access", QMessageBox.ButtonRole.DestructiveRole)
    else:
        box.setText("The dataset session information is unreadable.")
        box.setInformativeText(
            "Recover only if you are certain FlowTrack is not open on another computer."
        )
        recover = box.addButton("Recover Write Access", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    if box.clickedButton() is readonly:
        return StartupChoice.READ_ONLY
    if recover is not None and box.clickedButton() is recover:
        return StartupChoice.WRITE
    return StartupChoice.CANCEL
