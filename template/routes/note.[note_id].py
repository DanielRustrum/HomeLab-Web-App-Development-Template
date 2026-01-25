from utils.notes import Notes, NoteInsert, Queries
import tsunami as nami

class Endpoint(nami.Endpoint):
    def init(self):
        pass

    def get(self) -> Notes:
        return Queries.get_notes()

    def post(self, note: NoteInsert) -> None:
        Queries.add_note(note)

    def cleanup(self):
        pass