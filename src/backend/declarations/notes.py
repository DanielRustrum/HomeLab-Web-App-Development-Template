from dataclasses import dataclass
import db

type NoteId = int

@db.table
@dataclass
class Note:
    id: NoteId
    title: str
    body: str
    created_at: str

@db.table
@dataclass
class Notebook:
    id: int
    note_id: NoteId

@dataclass
class Notes:
    notes: list[Note]
