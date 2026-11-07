# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo>=4,<5"]
# ///
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Self
from urllib.parse import unquote, urlsplit

import bson  # pyright: ignore[reportMissingImports]

ROOT = Path(__file__).resolve().parents[1]
ASSETS_HOSTNAME = "assets.tabtop.wynd.is"


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
        self.validate_assets(document)
        return bson.encode(document)

    def validate_assets(self, document: dict[str, object]) -> None:
        missing = []
        for url in sorted(set(urls(document))):
            parsed = urlsplit(url)
            if parsed.hostname != ASSETS_HOSTNAME:
                continue
            path = (ROOT / unquote(parsed.path).lstrip("/")).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                missing.append(url)
        assert not missing, f"Missing local assets for {self.source.parent.name}:\n" + "\n".join(missing)

    def update(self) -> None:
        payload = self.encode()
        with tempfile.TemporaryDirectory(prefix="tts-update-") as temporary:
            content = Path(temporary) / f"{self.source.stem}.bson"
            content.write_bytes(payload)
            print(f"Updating {self.source.parent.name} (Workshop {self.source.stem})", flush=True)
            steam_workshop("update-file", "286160", self.source.stem, str(content))


def urls(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield from re.findall(r"https?://[^\s\"'<>\\]+", value.replace("\\/", "/"))
    elif isinstance(value, dict):
        for item in value.values():
            yield from urls(item)
    elif isinstance(value, list):
        for item in value:
            yield from urls(item)


def steam_workshop(*args: str) -> None:
    subprocess.run(["steam-workshop", *args], check=True)


def main() -> None:
    assert len(sys.argv) == 2, "Usage: mise tts-update <game-slug>"
    Module.find(sys.argv[1]).update()


if __name__ == "__main__":
    main()
