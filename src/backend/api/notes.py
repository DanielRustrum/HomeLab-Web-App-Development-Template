from dataclasses import dataclass, field
from db import Database as db

@db.table
@dataclass
class Note:
    id: int
    title: str
    body: str
    created_at: str

@dataclass
class Notes:
    notes: list[Note]

class Route:
    def __init__(self):
        pass

    def index(self) -> Notes:
        with db(Note) as table:
            return table.execute()