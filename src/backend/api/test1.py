from dataclasses import dataclass
from .api.test import Tomato

class Route:
    def __init__(self):
        pass

    def index(self) -> Tomato:
        pot = Potota("T")
        return Tomato("test", 0, pot)