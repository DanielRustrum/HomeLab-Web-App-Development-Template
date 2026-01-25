from utils.notes import Notes, NoteInsert, Queries
from tsunami import endpoints

class Endpoint(endpoints.Endpoint):
    def init(self):
        pass

    def get(self) -> Notes:
        return "Hello"

    def cleanup(self):
        pass