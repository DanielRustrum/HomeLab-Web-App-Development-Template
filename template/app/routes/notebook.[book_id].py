import tsunami as nami

from utils.note_empty import Notes

class Endpoint(nami.Endpoint):
    def init(self):
        pass

    def get(self) -> Notes:
        return "Hello"

    def cleanup(self):
        pass