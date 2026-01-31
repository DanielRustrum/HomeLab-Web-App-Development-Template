class Suite:
    def setup(self):
        pass

    def cleanup(self):
        pass

    class Tests:
        def create_note(self, expects):
            return expects.condition(True)