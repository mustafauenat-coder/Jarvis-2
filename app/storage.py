"""Private runtime state, never in the source tree."""
import json
import os
import tempfile
import uuid
from pathlib import Path


def data_dir():
    root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    path = (root / "jarvis-2").resolve()
    repo = Path(__file__).resolve().parents[1]
    if path == repo or repo in path.parents:
        raise RuntimeError("XDG_CONFIG_HOME muss außerhalb des Projekts liegen.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
    return path


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_dir()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "accounts.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {
            "host": "urn:uuid:" + str(uuid.uuid4()), "active": None, "accounts": {}}
        self.save()

    def save(self):
        fd, name = tempfile.mkstemp(dir=self.root)
        try:
            if os.name != "nt":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def active(self):
        return self.data["accounts"].get(self.data["active"])
