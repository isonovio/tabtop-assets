"""CI steps: transfer assets, save the manifest, purge successful changes."""

import hashlib
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Self

STATE = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "deploy"
PREFIX = os.environ.get("DEPLOY_PREFIX", "_test/ci").strip("/")
POINTER = re.compile(rb"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n?\Z")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def download_lfs(path: str, pointer: bytes) -> bytes:
    return subprocess.check_output(
        ["git", "-c", "lfs.fetchinclude=", "-c", "lfs.fetchexclude=", "lfs", "smudge", "--", path],
        input=pointer,
        env=dict(os.environ, GIT_LFS_SKIP_SMUDGE="0", GIT_LFS_SKIP_DOWNLOAD_ERRORS="0"),
    )


def bunny_storage(
    method: str,
    path: str,
    data: bytes | None = None,
    sha256: str | None = None,
) -> bytes | None:
    headers = {"AccessKey": os.environ["BUNNY_STORAGE_PASSWORD"]}
    if method == "PUT":
        assert data is not None
        headers["Checksum"] = sha256 or hashlib.sha256(data).hexdigest().upper()
        headers["Content-Type"] = mimetypes.guess_type(path)[0] or "application/octet-stream"
    path = "/".join(filter(None, (PREFIX, path)))
    endpoint = os.environ["BUNNY_STORAGE_ENDPOINT"].rstrip("/")
    req = urllib.request.Request(f"{endpoint}/{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        exc.close()
        if method in ("GET", "DELETE") and exc.code == 404:
            return None
        raise


def bunny_api(path: str, method: str = "GET") -> bytes:
    req = urllib.request.Request(
        f"https://api.bunny.net/{path}",
        headers={"AccessKey": os.environ["BUNNY_API_KEY"]},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


@dataclass(frozen=True)
class Checksum:
    sha256: str
    size: int

    def __post_init__(self) -> None:
        assert re.fullmatch(r"[0-9a-f]{64}", self.sha256), "Invalid SHA-256"
        assert type(self.size) is int and self.size >= 0, "Invalid size"

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        return cls(hashlib.sha256(data).hexdigest(), len(data))

    @classmethod
    def from_blob(cls, data: bytes) -> Self:
        if data.startswith(b"version https://git-lfs.github.com/spec/"):
            pointer = POINTER.fullmatch(data)
            assert pointer is not None, "Invalid LFS pointer"
            return cls(pointer[1].decode(), int(pointer[2]))
        else:
            return cls.from_bytes(data)


@dataclass
class Manifest:
    version: int = 1
    files: dict[str, Checksum] = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert self.version == 1, "Invalid manifest version"
        assert isinstance(self.files, dict), "Invalid manifest files"
        self.files = {
            path: Checksum(**entry) if isinstance(entry, dict) else entry for path, entry in self.files.items()
        }
        for path in self.files:
            self.validate_path(path)

    @staticmethod
    def validate_path(path: str) -> None:
        pattern = r"games/(?:[0-9a-z-]+/)*[0-9a-z-]+(?:\.[0-9a-z-]+)*"
        assert re.fullmatch(pattern, path), f"Invalid asset path: {path}"

    @classmethod
    def from_json(cls, data: str | bytes) -> Self:
        return cls(**json.loads(data))

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_bunny(cls) -> Self:
        raw = bunny_storage("GET", "_deploy/manifest.json")
        return cls.from_json(raw) if raw is not None else cls()

    @classmethod
    def from_local(cls) -> Self:
        files: dict[str, Checksum] = {}
        for record in git("ls-tree", "-rz", "HEAD", "--", "games/").split(b"\0"):
            if not record:
                continue
            meta, raw_path = record.split(b"\t", 1)
            mode, kind, blob = meta.decode().split()
            path = raw_path.decode("utf-8")
            assert mode in ("100644", "100755") and kind == "blob", f"Expected a regular file: {path}"
            files[path] = Checksum.from_blob(git("cat-file", "blob", blob))
        return cls(files=files)

    def to_bunny(self) -> None:
        bunny_storage("PUT", "_deploy/manifest.json", self.to_json().encode())

    def __sub__(self, other: Self) -> "Diff":
        return Diff(
            updates={path: entry for path, entry in self.files.items() if entry != other.files.get(path)},
            deletes=sorted(other.files.keys() - self.files.keys()),
        )

    def __iadd__(self, success: "Diff") -> Self:
        self.files.update(success.updates)
        for path in success.deletes:
            self.files.pop(path, None)
        return self


@dataclass
class Diff:
    updates: dict[str, Checksum] = field(default_factory=dict)
    deletes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.updates = {
            path: Checksum(**entry) if isinstance(entry, dict) else entry for path, entry in self.updates.items()
        }
        for path in [*self.updates, *self.deletes]:
            Manifest.validate_path(path)

    def __bool__(self) -> bool:
        return bool(self.updates or self.deletes)

    def upload(self) -> tuple[Self, list[str]]:
        success = type(self)()
        failure: list[str] = []
        print(
            f"{len(self.updates)} updates, {len(self.deletes)} deletes",
            flush=True,
        )
        for operation, paths in (
            ("update", list(self.updates)),
            ("delete", self.deletes),
        ):
            for path in paths:
                try:
                    if operation == "update":
                        data = git("show", f"HEAD:{path}")
                        if POINTER.fullmatch(data):
                            data = download_lfs(path, data)
                        assert Checksum.from_bytes(data) == self.updates[path], f"Asset checksum mismatch: {path}"
                        bunny_storage("PUT", path, data, self.updates[path].sha256)
                        success.updates[path] = self.updates[path]
                    else:
                        # A 404 is already absent, including a previous DELETE
                        # whose response or manifest update was lost.
                        bunny_storage("DELETE", path)
                        success.deletes.append(path)
                    print(f"{operation}: {path}", flush=True)
                except Exception as exc:  # noqa: BLE001
                    message = f"{operation}: {path}: {exc}"
                    failure.append(message)
                    print(f"::error::{message}", file=sys.stderr)
        return success, failure

    def purge(self) -> None:
        if not self:
            print("No successful changes to purge")
            return
        host = os.environ["BUNNY_PULL_ZONE_HOSTNAME"]
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host), "Invalid BUNNY_PULL_ZONE_HOSTNAME"
        failures: list[str] = []
        for asset in [*self.updates, *self.deletes]:
            path = "/".join(filter(None, (PREFIX, asset)))
            url = f"https://{host}/{path}"
            query = urllib.parse.urlencode({"url": url, "async": "false", "exactPath": "true"})
            try:
                bunny_api(f"purge?{query}", "POST")
                print(f"Purged {url}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append(url)
                print(f"::error::Purge failed: {url}: {exc}", file=sys.stderr)
            time.sleep(0.25)  # Pace requests below Bunny's exact-URL limit.
        assert not failures, f"{len(failures)} purges failed; rerun the purge job"


@dataclass
class Result:
    manifest: Manifest
    successes: Diff
    failures: list[str]

    def __post_init__(self) -> None:
        if isinstance(self.manifest, dict):
            self.manifest = Manifest(**self.manifest)
        if isinstance(self.successes, dict):
            self.successes = Diff(**self.successes)

    def save(self) -> None:
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / "result.json").write_text(f"{json.dumps(asdict(self))}\n")

    @classmethod
    def load(cls) -> Self:
        return cls(**json.loads((STATE / "result.json").read_text()))


def transfer() -> None:
    bunny = Manifest.from_bunny()
    local = Manifest.from_local()
    diff = local - bunny
    success, failure = diff.upload()
    bunny += success
    Result(bunny, success, failure).save()


def manifest() -> None:
    result = Result.load()
    if result.successes:
        result.manifest.to_bunny()
    assert not result.failures, f"{len(result.failures)} storage operations failed"


def purge() -> None:
    Result.load().successes.purge()


if __name__ == "__main__":
    try:
        match sys.argv[1]:
            case "transfer":
                transfer()
            case "manifest":
                manifest()
            case "purge":
                purge()
    except Exception as exc:  # noqa: BLE001
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)
