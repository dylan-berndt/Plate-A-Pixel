import sys
from PySide6.QtWidgets import QApplication
from utils import *

app = QApplication(sys.argv)

root = Grid((12, 12, 12, 12))

button = Button(lambda: print("PRESSED")).add(Text("Hello"))

root.add(button, (1, 1), (1, 1))

window = Window((800, 600), root, caption="Plate A Pixel")
window.show()

sys.exit(app.exec())
