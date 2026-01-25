from utils.notes import Notes, NoteInsert, Queries
import tsunami as nami

class Endpoint(nami.Endpoint):
    def init(self):
        pass

    def get(self) -> Notes:
        return "Hello"

    def cleanup(self):
        pass