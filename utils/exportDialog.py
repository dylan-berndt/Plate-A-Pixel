import os

from PySide6.QtWidgets import (
    QDialog, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLineEdit,
    QListWidget, QMessageBox, QFileDialog,
)

from .ui import *
from .data import *
from .meshElement import MeshElement

CELL_STEP = 1.0


class ExportDialog(QDialog):
    """File > Export's window: a live mesh preview (the same MeshElement
    the main 3D panel uses, just smaller - see the mesh settings panel
    for why cellWidth/cellHeight edits here go through the same
    CanvasController setters rather than owning a separate copy of those
    values), the destination the user names themselves (no project-name
    auto-wiring - see objExport.py's rework), and every check export
    actually needs: every color named, no two colors sharing a name
    (both would otherwise silently collide since export writes flat,
    one file per part, into one folder), and mesh.warnings surfaced so a
    disconnected or isolated part isn't discovered only after slicing."""

    def __init__(self, projectController, theme: Theme = None, parent=None):
        super().__init__(parent)
        self._pc = projectController
        self._theme = theme or Theme()
        self._cellWidth = projectController.project.viewSettings.cellWidth
        self._cellHeight = projectController.project.viewSettings.cellHeight
        self._parentDir = os.path.expanduser("~")

        self.setWindowTitle(f"Export - {projectController.project.name}")
        self.setStyleSheet(self._theme.stylesheet())
        self.resize(680, 440)

        layout = QHBoxLayout(self)

        self._preview = MeshElement(theme=self._theme)
        self._preview.setFixedSize(280, 280)
        self._preview.bindProject(projectController)
        layout.addWidget(self._preview)

        form = QVBoxLayout()
        layout.addLayout(form, 1)

        form.addWidget(SectionLabel("Destination", theme=self._theme))
        self._folderNameEdit = QLineEdit(projectController.project.name)
        self._folderNameEdit.textChanged.connect(self._refreshValidation)
        form.addWidget(self._folderNameEdit)
        destRow = QHBoxLayout()
        self._destPreview = MonoText("", theme=self._theme)
        destRow.addWidget(self._destPreview, 1)
        browseButton = QPushButton("Choose Location...")
        browseButton.clicked.connect(self._chooseParentDir)
        destRow.addWidget(browseButton)
        form.addLayout(destRow)

        form.addWidget(SectionLabel("Cell Size", theme=self._theme))
        sizeRow = QHBoxLayout()
        sizeRow.addWidget(SectionLabel("Width", theme=self._theme))
        self._widthStepper = Stepper(
            "", onIncrement=lambda: self._setCellWidth(self._cellWidth + CELL_STEP),
            onDecrement=lambda: self._setCellWidth(max(CELL_STEP, self._cellWidth - CELL_STEP)),
            theme=self._theme,
        )
        sizeRow.addWidget(self._widthStepper)
        sizeRow.addWidget(SectionLabel("Height", theme=self._theme))
        self._heightStepper = Stepper(
            "", onIncrement=lambda: self._setCellHeight(self._cellHeight + CELL_STEP),
            onDecrement=lambda: self._setCellHeight(max(CELL_STEP, self._cellHeight - CELL_STEP)),
            theme=self._theme,
        )
        sizeRow.addWidget(self._heightStepper)
        form.addLayout(sizeRow)

        self._validationLabel = Text("")
        self._validationLabel.setStyleSheet("color: #a33; font-size: 11px;")
        self._validationLabel.setWordWrap(True)
        form.addWidget(self._validationLabel)

        form.addWidget(SectionLabel("Warnings", theme=self._theme))
        self._warningsList = QListWidget()
        self._warningsList.setMaximumHeight(90)
        form.addWidget(self._warningsList)

        form.addStretch(1)

        buttonRow = QHBoxLayout()
        buttonRow.addStretch(1)
        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttonRow.addWidget(cancelButton)
        self._exportButton = QPushButton("Export")
        self._exportButton.clicked.connect(self._doExport)
        buttonRow.addWidget(self._exportButton)
        form.addLayout(buttonRow)

        projectController.viewSettingsChanged.connect(self._refreshCellSizes)
        projectController.meshReady.connect(self._refreshWarnings)
        projectController.paletteChanged.connect(self._refreshValidation)

        self._refreshCellSizes()
        self._refreshWarnings()
        self._refreshDestPreview()
        self._refreshValidation()

    # -- destination ------------------------------------------------------

    def _chooseParentDir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._parentDir)
        if chosen:
            self._parentDir = chosen
            self._refreshDestPreview()

    def _destinationPath(self):
        return os.path.join(self._parentDir, self._folderNameEdit.text().strip())

    def _refreshDestPreview(self):
        self._destPreview.setText(self._destinationPath())

    # -- cell size ---------------------------------------------------------

    def _setCellWidth(self, value):
        self._pc.canvasController.setCellWidth(value)

    def _setCellHeight(self, value):
        self._pc.canvasController.setCellHeight(value)

    def _refreshCellSizes(self):
        settings = self._pc.project.viewSettings
        self._cellWidth = settings.cellWidth
        self._cellHeight = settings.cellHeight
        self._widthStepper.setText(f"{self._cellWidth:g} mm")
        self._heightStepper.setText(f"{self._cellHeight:g} mm")

    # -- validation -------------------------------------------------------

    def _refreshValidation(self):
        palette = self._pc.project.canvas.palette
        unnamed = unnamedColorIndices(palette)
        duplicates = duplicateColorNames(palette)

        problems = []
        if unnamed:
            problems.append("Name every color before exporting: " + ", ".join(f"color {i}" for i in unnamed))
        if duplicates:
            problems.append("These names are used by more than one color: " + ", ".join(duplicates))
        self._validationLabel.setText("\n".join(problems))

        self._refreshDestPreview()
        self._exportButton.setEnabled(not problems and bool(self._folderNameEdit.text().strip()))

    # -- warnings -----------------------------------------------------

    def _refreshWarnings(self):
        self._warningsList.clear()
        for warning in self._pc.project.mesh.warnings:
            self._warningsList.addItem(warning)

    # -- export -------------------------------------------------------

    def _doExport(self):
        outputDir = self._destinationPath()
        try:
            paths = self._pc.project.exportObjs(outputDir)
        except Exception as error:
            QMessageBox.critical(self, "Export Failed", str(error))
            return
        QMessageBox.information(self, "Export Complete", f"Wrote {len(paths)} file(s) to:\n{outputDir}")
        self.accept()
