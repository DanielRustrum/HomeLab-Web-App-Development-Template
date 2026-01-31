import tsunami as nami

class Endpoint(nami.Endpoint):
    def get(self) -> str:
        return "Endpoint Doesn't Exist"
