from dataclasses import dataclass

@dataclass
class Note:
    title: str
    body: str
    test: str
    created_at: str

@dataclass
class Notes:
    notes: list[Note]