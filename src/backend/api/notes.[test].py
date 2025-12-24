from dataclasses import dataclass
import backend.core.endpoints as endpoints

@dataclass
class Test:
    test: str

class Endpoint(endpoints.Endpoint):
    def get(self) -> Test:
        return Test("fsdf")
