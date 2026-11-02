# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo>=4,<5"]
# ///
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import bson  # pyright: ignore[reportMissingImports]

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Module:
    source: Path

    @classmethod
    def find(cls, slug: str) -> Self:
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug), f"Invalid game slug: {slug}"

        sources = list((ROOT / "tts-workshop" / slug).glob("*.json"))
        assert len(sources) == 1, f"Expected one JSON save for {slug}; found {len(sources)}"
        source = sources[0]

        assert source.stem.isascii() and source.stem.isdecimal(), f"Expected a Workshop ID filename: {source.name}"
        assert 0 < int(source.stem) < 2**64, "Invalid Workshop ID"

        return cls(source)

    def encode(self) -> bytes:
        document = json.loads(self.source.read_text(encoding="utf-8-sig"))
        assert isinstance(document, dict), "Expected a JSON object"
        return bson.encode(document)

    def update(self) -> None:
        payload = self.encode()
        with tempfile.TemporaryDirectory(prefix="tts-update-") as temporary:
            content = Path(temporary) / f"{self.source.stem}.bson"
            content.write_bytes(payload)
            print(f"Updating {self.source.parent.name} (Workshop {self.source.stem})", flush=True)
            steam_workshop("update-file", "286160", self.source.stem, str(content))


def steam_workshop(*args: str) -> None:
    subprocess.run(["steam-workshop", *args], check=True)


def main() -> None:
    assert len(sys.argv) == 2, "Usage: mise tts-update <game-slug>"
    Module.find(sys.argv[1]).update()


if __name__ == "__main__":
    main()
