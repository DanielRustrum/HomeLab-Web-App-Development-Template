from declarations.notes import Notes, Note, Queries
from backend.core import endpoints

class Endpoint(endpoints.Endpoint):
    def init(self):
        pass

    def get(self) -> Notes:
        return Queries.get_notes()

    def post(self, note: Note) -> None:
        Queries.add_note(note)

    def cleanup(self):
        pass