import tsunami as nami
from utils import notes as note

class Endpoint(nami.Endpoint):
    def get(self) -> note.Notes:
        return note.Queries.get_notes()

    def post(self, payload: note.NoteInsert) -> None:
        note.Queries.add_note(payload)
