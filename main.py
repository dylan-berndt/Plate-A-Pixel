import sys
from PySide6.QtWidgets import QApplication
from utils import *

app = QApplication(sys.argv)

appController = AppController()
window = AppWindow(appController)
window.setCanvasArea(CanvasArea(appController, theme=window.theme))
window.setMeshElement(MeshElement(theme=window.theme))


def openExportDialog():
    controller = appController.activeController
    if controller is None:
        return
    ExportDialog(controller, theme=window.theme, parent=window).exec()


window.setExportHandler(openExportDialog)
window.show()

sys.exit(app.exec())
