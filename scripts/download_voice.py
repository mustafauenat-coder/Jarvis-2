"""Explicit one-time download; runtime synthesis never downloads anything."""
import hashlib
import json
from pathlib import Path

import httpx

from app.storage import data_dir
from app.voice import VOICE

REVISION = "e7229f7d33a10e145e109b886d661984201ac3c4"
BASE = f"https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}/de/de_DE/thorsten/high/"


def main():
    folder = data_dir() / "voices"
    folder.mkdir(exist_ok=True)
    manifest = {"revision": REVISION, "files": {}}
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for filename in (VOICE + ".onnx", VOICE + ".onnx.json", "MODEL_CARD"):
            target = folder / filename
            temporary = target.with_name(target.name + ".part")
            digest = hashlib.sha256()
            print("Lade", filename)
            try:
                with client.stream("GET", BASE + filename) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)
                            digest.update(chunk)
                if filename.endswith(".json"):
                    json.loads(temporary.read_text(encoding="utf-8"))
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            manifest["files"][filename] = digest.hexdigest()
    (folder / "download-manifest.json").write_text(json.dumps(manifest, indent=2))
    print("Stimme gespeichert unter", folder)


if __name__ == "__main__":
    main()
