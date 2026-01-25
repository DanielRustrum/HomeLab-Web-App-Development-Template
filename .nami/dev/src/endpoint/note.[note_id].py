from utils.notes import Notes, NoteInsert, Queries
from tsunami import endpoints

class Endpoint(endpoints.Endpoint):
    def init(self):
        pass

    def get(self) -> Notes:
        return Queries.get_notes()

    def post(self, note: NoteInsert) -> None:
        Queries.add_note(note)

    def cleanup(self):
        pass