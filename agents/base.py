from events import bus

class Agent:
    name = "agent"
    def __init__(self, cfg, llm=None):
        self.cfg, self.llm = cfg, llm
    def log(self, status, detail=""):
        bus.emit(self.name, status, detail)