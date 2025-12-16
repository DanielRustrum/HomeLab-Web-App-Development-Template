from dataclasses import dataclass
from .db import Database

@Database.table
@dataclass
class Test:
    name: str
    age: int


@dataclass
class Potota:
    typr: str

@Database.table
@dataclass
class Tomato:
    name: str
    age: int
    test: Potota

class Route:
    def __init__(self):
        pass

    def index(self) -> Test:
        return Test("test", 0)