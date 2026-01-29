import tsunami as nami
from utils import note_empty as note

class Endpoint(nami.Endpoint):
    def init(self):
        pass

    def get(self) -> note.Notes:
        return [ note.Note("Hello!", "Lets Go!", "sdfsdfsdf", "sfdsdfsdf") ]

    def post(self, note: note.Note) -> None:
        print("endpoint: ", note)

    def cleanup(self):
        pass