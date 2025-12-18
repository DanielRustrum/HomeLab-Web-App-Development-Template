from dataclasses import dataclass
from declarations.notes import Notes, Note, Notebook

import db, endpoints

class Endpoint(endpoints.Endpoint):
    def init(self):
        pass

    def auth(self):
        pass

    def get(self) -> Notes:
        with db.Query(Note) as notes:
            return notes.execute()
        
    def post(self, note: Note, blank: int) -> None:
        with db.Query([Note, Notebook]) as [notes, notebook]:
            notes.insert(note).execute()
            notebook.insert(note).execute()

    def cleanup(self):
        pass