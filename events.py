# import time, threading

# class EventBus:
#     def __init__(self):
#         self.events, self.subscribers, self._lock = [], [], threading.Lock()

#     def emit(self, agent, status, detail=""):
#         ev = {"ts": round(time.time(), 2), "agent": agent, "status": status, "detail": detail}
#         with self._lock:
#             self.events.append(ev)
#         for fn in self.subscribers:
#             fn(ev)
#         return ev

#     def subscribe(self, fn): self.subscribers.append(fn)

# bus = EventBus()
import time, threading

ctx = threading.local()          # per-thread session id

class EventBus:
    def __init__(self):
        self.events, self.subscribers, self._lock = [], [], threading.Lock()

    def emit(self, agent, status, detail=""):
        ev = {"ts": round(time.time(), 2), "agent": agent, "status": status,
              "detail": detail, "sid": getattr(ctx, "sid", None)}
        with self._lock:
            self.events.append(ev)
            self.events = self.events[-500:]
        for fn in self.subscribers:
            fn(ev)
        return ev

    def subscribe(self, fn): self.subscribers.append(fn)

bus = EventBus()