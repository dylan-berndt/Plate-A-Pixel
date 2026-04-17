from utils import *

root = Grid(Padding(12, 12, 12, 12))

button = Button(lambda x: print("PRESSED")).add(Text("Hello"))

root.add(button, (1, 1), (1, 1))

manager = Window((800, 600), root)

while True:
    manager.update()