"""Light-weight background agent framework.

Each Agent is a daemon thread that wakes on its own interval and refreshes a
cache (its 'job'). Agents register themselves in AGENTS; start_agents() is
called from the FastAPI startup hook so they run the moment the main system
boots. Failures are swallowed and recorded in status — an agent can never
take the app down.
"""
import threading
import time
import traceback

AGENTS: list = []
_STATUS: dict = {}


class Agent:
    def __init__(self, name: str, interval_sec: int, job, note: str = ""):
        self.name = name
        self.interval = interval_sec
        self.job = job
        self.note = note
        self.thread = None
        self.stop = threading.Event()
        AGENTS.append(self)

    def _run(self):
        while True:
            try:
                self.job()
                _STATUS[self.name] = {"last_run": time.time(), "ok": True,
                                      "note": self.note}
            except Exception as e:
                _STATUS[self.name] = {"last_run": time.time(), "ok": False,
                                      "note": f"{self.note} · err {e}",
                                      "tb": traceback.format_exc(limit=2)}
            if self.stop.wait(self.interval):
                break

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=self._run, name=f"agent:{self.name}",
                                       daemon=True)
        self.thread.start()


def start_agents():
    for a in AGENTS:
        a.start()


def agent_status():
    return {a.name: dict(_STATUS.get(a.name, {"last_run": None, "ok": None,
                                              "note": a.note + " · not run yet"}))
            for a in AGENTS}
