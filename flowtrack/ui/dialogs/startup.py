"""Small startup dialogs; all lease interpretation remains outside the UI."""

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from flowtrack.application.startup import StartupChoice
from flowtrack.infrastructure.lease import LeaseState


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
