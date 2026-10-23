#!/usr/bin/python3
"""Launch an unmodified official Tor Browser from a private, persistent user copy.

No Livara preferences, fonts, profiles, proxy settings, extensions, or command-line
security overrides are added to Tor Browser. Its own updater owns the user copy.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

BASE = Path("/opt/tor-browser")
DATA = Path(__file__).resolve().parent
PRIMARY = "EF6E286DDA85EA2A4BA7DE684E2C6E8793298290"


def _root_user() -> bool:
    return os.getuid() == 0 or os.geteuid() == 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _metadata(manifest: Path | None, files_manifest: Path | None) -> tuple[dict, list[dict]]:
    if manifest is None:
        manifest = DATA / "tor-upstream.json"
        if not manifest.is_file():
            manifest = DATA.parents[2] / "forks/tor/upstream.json"
    if files_manifest is None:
        files_manifest = DATA / "tor-files.json"
        if not files_manifest.is_file():
            files_manifest = manifest.with_name("files.json")
    if manifest.stat().st_size > 2 * 1024 * 1024 or files_manifest.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Official Tor Browser metadata is too large")
    pin = json.loads(manifest.read_text())
    if pin.get("schema") != 1 or pin.get("primary_fingerprint") != PRIMARY or not re.fullmatch(r"\d+\.\d+(?:\.\d+)*", pin.get("version", "")):
        raise ValueError("Official Tor Browser release metadata is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", pin.get("sha256", "")) or _sha256(files_manifest) != pin.get("assets", {}).get("files.json"):
        raise ValueError("Official Tor Browser file manifest does not match its release pin")
    listing = json.loads(files_manifest.read_text())
    entries = listing.get("entries", [])
    if listing.get("schema") != 1 or listing.get("archive_root") != "tor-browser" or not 1 <= len(entries) <= 10000:
        raise ValueError("Official Tor Browser file manifest is invalid")
    paths = set()
    for entry in entries:
        name = entry["path"]
        parts = PurePosixPath(name).parts
        if not parts or name.startswith("/") or ".." in parts or "\\" in name or name in paths:
            raise ValueError("Unsafe path in the official Tor Browser file manifest")
        paths.add(name)
    if not {"Browser/start-tor-browser", "Browser/firefox", "Browser/firefox.real"} <= paths:
        raise ValueError("Official Tor Browser launch files are missing from the pin")
    return pin, entries


def _verify_base(base: Path, entries: list[dict]) -> None:
    if base.is_symlink() or not base.is_dir():
        raise ValueError("The immutable official Tor Browser bundle is not installed")
    expected = {entry["path"]: entry for entry in entries}
    present = set()
    for directory, dirs, files in os.walk(base, followlinks=False):
        for name in dirs + files:
            filename = Path(directory) / name
            relative = filename.relative_to(base).as_posix()
            if relative not in expected:
                raise ValueError(f"The installed official Tor Browser has an unexpected file: {relative}")
            present.add(relative)
            entry, info = expected[relative], filename.lstat()
            if entry["type"] == "directory":
                valid = stat.S_ISDIR(info.st_mode)
            elif entry["type"] == "symlink":
                valid = stat.S_ISLNK(info.st_mode) and os.readlink(filename) == entry["target"]
            elif entry["type"] == "file":
                valid = stat.S_ISREG(info.st_mode) and info.st_size == entry["size"] and _sha256(filename) == entry["sha256"]
                # The root-owned shared installation needs a+rX permissions so
                # users can copy it. Byte contents and owner execute bits stay
                # unchanged; the user's containing directory supplies privacy.
                valid = valid and bool(info.st_mode & 0o100) == bool(entry["mode"] & 0o100)
            else:
                raise ValueError("Unsupported official Tor Browser installation entry")
            if not valid:
                raise ValueError(f"The installed official Tor Browser differs from the signed bundle: {relative}")
    if present != set(expected):
        raise ValueError("The installed official Tor Browser bundle is incomplete")


def _private_directory(directory: Path) -> None:
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or directory.is_symlink() or info.st_uid != os.getuid():
        raise ValueError("Tor Browser storage must be a real directory owned by the current user")
    directory.chmod(0o700)


def prepare_user_copy(base: Path, data: Path, pin: dict, entries: list[dict]) -> Path:
    """Copy once under a lock; preserve all subsequent official updates/profile data."""
    _private_directory(data)
    version = pin["version"]
    destination = data / version
    lock = os.open(data / f".{version}.copy.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            raise ValueError("Invalid Tor Browser installation lock")
        os.fchmod(lock, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.is_symlink():
            raise ValueError("Tor Browser user storage cannot be a symbolic link")
        if destination.exists():
            _private_directory(destination)
            marker = destination / ".livara-origin.json"
            if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 4096:
                raise ValueError("The existing Tor Browser copy has no valid origin record; preserve or back it up before reinstalling")
            origin = json.loads(marker.read_text())
            if origin.get("baseline_version") != version or origin.get("archive_sha256") != pin["sha256"]:
                raise ValueError("The existing Tor Browser copy uses a different baseline; it was not overwritten")
            tree = destination / "tor-browser"
        else:
            _verify_base(base, entries)
            stage = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=data))
            try:
                tree = stage / "tor-browser"
                shutil.copytree(base, tree, symlinks=True, copy_function=shutil.copy2)
                _verify_base(tree, entries)
                # This marker is outside the unchanged official browser tree.
                marker = stage / ".livara-origin.json"
                with os.fdopen(os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
                    json.dump({"schema": 1, "baseline_version": version, "archive_sha256": pin["sha256"]}, stream)
                    stream.write("\n")
                os.rename(stage, destination)
                tree = destination / "tor-browser"
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        if tree.is_symlink() or not tree.is_dir():
            raise ValueError("The private Tor Browser copy is invalid")
        launcher = tree / "Browser/start-tor-browser"
        if launcher.is_symlink() or not launcher.is_file() or not os.access(launcher, os.X_OK):
            raise ValueError("The private Tor Browser official launcher is missing")
        return launcher
    finally:
        os.close(lock)


def validate_urls(urls: list[str]) -> list[str]:
    for url in urls:
        if not isinstance(url, str) or any(ord(character) < 32 or ord(character) == 127 for character in url):
            raise ValueError("Invalid Tor Browser address")
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Tor mode accepts HTTP and HTTPS addresses, including valid v3 .onion services")
        _ = parsed.port
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname.endswith(".onion"):
            service = hostname.split(".")[-2]
            if not re.fullmatch(r"[a-z2-7]{56}", service):
                raise ValueError("Use a current 56-character v3 .onion address")
            value = base64.b32decode(service.upper())
            if value[-1] != 3 or value[32:34] != hashlib.sha3_256(b".onion checksum" + value[:32] + value[-1:]).digest()[:2]:
                raise ValueError("The v3 .onion address checksum is invalid")
    return list(urls)


def run_tor_browser(urls: list[str], browser_args: list[str] | None = None, *, base_directory: Path | None = None,
                    data_directory: Path | None = None, manifest_path: Path | None = None,
                    files_manifest_path: Path | None = None) -> int:
    """Launch the official engine without added preferences or command-line flags."""
    if _root_user():
        print("Livara Tor: official Tor Browser must run as a regular desktop user; root launch is refused.", file=sys.stderr)
        return 2
    try:
        if browser_args:
            raise ValueError("Official Tor Browser mode does not accept custom browser/profile/security arguments")
        urls = validate_urls(list(urls))
        pin, entries = _metadata(manifest_path, files_manifest_path)
        base = base_directory if base_directory is not None else BASE
        data = data_directory if data_directory is not None else Path.home() / ".local/share/livara/tor-browser"
        launcher = prepare_user_copy(Path(base), Path(data), pin, entries)
        environment = os.environ.copy()
        for key in list(environment):
            if key.startswith(("LIVARA_TOR_", "MOZ_DISABLE_")) or key in ("MOZ_NO_REMOTE", "MOZ_PROFILE", "MOZ_FORCE_DISABLE_E10S"):
                environment.pop(key, None)
        # Tor Browser's original script selects its Tor process, profile,
        # security settings and bundled fonts. No Livara skin or prefs are used.
        result = subprocess.run([str(launcher), *urls], cwd=launcher.parent, env=environment, check=False)
        return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Livara Tor: {error}", file=sys.stderr)
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*")
    return run_tor_browser(parser.parse_args(argv).urls)


if __name__ == "__main__":
    raise SystemExit(main())
