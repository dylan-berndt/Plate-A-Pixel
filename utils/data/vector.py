

class Vector2:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __add__(self, summand):
        if type(summand) == Vector2:
            return Vector2(self.x + summand.x, self.y + summand.y)
        if type(summand) in [int, float]:
            return Vector2(self.x + summand, self.y + summand)

    def __mul__(self, multiplicand):
        if type(multiplicand) == Vector2:
            return Vector2(self.x * multiplicand.x, self.y * multiplicand.y)
        if type(multiplicand) in [int, float]:
            return Vector2(self.x * multiplicand, self.y * multiplicand)

    def __imul__(self, multiplicand):
        self = self * multiplicand

    __rmul__ = __mul__

    def __matmul__(self, multiplicand):
        if type(multiplicand) == Vector2:
            return self.x * multiplicand.x + self.y * multiplicand.y
