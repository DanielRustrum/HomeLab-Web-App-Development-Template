from declarations.notes import Notes, Note, Notebook

import backend.core.endpoints as endpoints

class Endpoint(endpoints.Endpoint):
    def init(self):
        pass

    def auth(self):
        pass

    def get(self) -> Notes:
        return Notes([Note(0, "test", "Ttestsets", "03030")])
        
    def post(self, note: Note, blank: int) -> None:
        pass

    def cleanup(self):
        pass