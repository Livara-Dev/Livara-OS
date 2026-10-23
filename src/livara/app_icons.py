"""Per-user desktop icons, without changing application commands or packages."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET

MAX_DESKTOP = 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024


def _local_resource(value):
    if value.startswith("#"): return True
    # Inline raster artwork is common in scalable app logos. Nested SVGs and
    # arbitrary data types remain disallowed; no URL/file resources are loaded.
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\s]+)", value)
    if not match: return False
    try: data = base64.b64decode(re.sub(r"\s", "", match[2]), validate=True)
    except ValueError: return False
    return len(data) <= MAX_IMAGE and (data.startswith(b"\x89PNG\r\n\x1a\n") if match[1] == "png" else
            data.startswith(b"\xff\xd8\xff") if match[1] == "jpeg" else data.startswith(b"RIFF") and data[8:12] == b"WEBP")


def desktop_id(value):
    if (not isinstance(value, str) or not value.endswith(".desktop") or len(value) <= 8
            or len(value.encode("utf-8")) > 255 or any(c in value for c in "/\\")
            or any(unicodedata.category(c).startswith("C") for c in value)):
        raise ValueError("This app does not have a supported desktop launcher ID")
    return value


def _read(path, maximum, *, follow=False):
    path = Path(path).resolve(strict=True) if follow else Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError("Choose a regular file within the size limit")
        data = stream.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError("This file is too large")
        return data


def replace_icon(data: bytes, icon: str) -> bytes:
    """Touch only main-section Icon keys, including localized Icon variants."""
    if len(data) > MAX_DESKTOP or b"\0" in data or any(c in icon for c in "\r\n\0"):
        raise ValueError("Invalid launcher or icon path")
    text = data.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    value = "Icon=" + icon.replace("\\", "\\\\") + newline
    output, inside, found, inserted = [], False, False, False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip("\ufeff").strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if inside and not inserted:
                if output and not output[-1].endswith("\n"): output[-1] += newline
                output.append(value); inserted = True
            inside = stripped == "[Desktop Entry]"
            if inside:
                if found: raise ValueError("The launcher has duplicate main sections")
                found = True
        if inside and re.match(r"^\s*Icon(?:\[[^\]]+\])?\s*=", line):
            if not inserted: output.append(value); inserted = True
            continue
        output.append(line)
    if not found: raise ValueError("This file has no desktop entry")
    if inside and not inserted:
        if output and not output[-1].endswith("\n"): output[-1] += newline
        output.append(value)
    return "".join(output).encode("utf-8")


def render_icon(path):
    """Decode a bounded local image into a self-contained 512px PNG."""
    data = _read(path, MAX_IMAGE, follow=True)
    if not data: raise ValueError("This image is empty")
    # GdkPixbuf's ICO loader cannot read PNG-compressed ICO entries. Decode
    # the largest embedded PNG directly, retaining alpha and bounded loading.
    if data[:4] == b"\x00\x00\x01\x00" and len(data) >= 6:
        count = struct.unpack_from("<H", data, 4)[0]
        if not 1 <= count <= 256 or len(data) < 6 + count * 16:
            raise ValueError("This ICO directory is invalid")
        candidates = []
        for index in range(count):
            width, height, _, _, _, _, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + index * 16)
            if offset >= 6 + count * 16 and offset + size <= len(data):
                payload = data[offset:offset + size]
                if payload.startswith(b"\x89PNG\r\n\x1a\n"):
                    candidates.append(((width or 256) * (height or 256), payload))
        if candidates: data = max(candidates, key=lambda item: item[0])[1]
    # SVGs must be self-contained; rasterizing also avoids external references
    # and removes the need to keep the user's original image in place.
    if data.startswith(b"\x1f\x8b"):
        raise ValueError("Use an uncompressed SVG or a raster image")
    if data.lstrip(b" \t\r\n\xef\xbb\xbf").startswith(b"<") or Path(path).suffix.lower() == ".svg":
        if re.search(br"<!DOCTYPE|<!ENTITY|@import|<\s*(?:script|foreignObject)\b", data, re.I):
            raise ValueError("Choose a self-contained SVG without scripts or imports")
        try:
            tree = ET.fromstring(data)
        except ET.ParseError as error:
            raise ValueError("This SVG could not be read") from error
        if tree.tag.rsplit("}", 1)[-1] != "svg":
            raise ValueError("This XML file is not an SVG icon")
        for node in tree.iter():
            if node.tag.rsplit("}", 1)[-1].lower() in ("script", "foreignobject"):
                raise ValueError("Choose an SVG without scripts or embedded HTML")
            for key, value in node.attrib.items():
                if key.rsplit("}", 1)[-1] in ("href", "src") and not _local_resource(value):
                    raise ValueError("SVG icons cannot load external files or images")
            for value in [*node.attrib.values(), node.text or ""]:
                if re.search(r"@import", value, re.I):
                    raise ValueError("SVG icons cannot import stylesheets")
                for url in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", value, re.I):
                    if not _local_resource(url):
                        raise ValueError("SVG icons cannot load external resources")
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib
    loader = GdkPixbuf.PixbufLoader.new()
    dimensions = []
    def size_prepared(decoder, width, height):
        dimensions.append((width, height))
        factor = min(512 / max(width, 1), 512 / max(height, 1), 1)
        decoder.set_size(max(1, round(width * factor)), max(1, round(height * factor)))
    loader.connect("size-prepared", size_prepared)
    try:
        loader.write(data); loader.close()
        pixbuf = loader.get_pixbuf()
        if pixbuf is None or not dimensions:
            raise ValueError("This file is not a supported image")
        if any(w > 8192 or h > 8192 or w * h > 16_777_216 for w, h in dimensions):
            raise ValueError("Use an image up to 8192px and 16 megapixels")
        ok, png = pixbuf.save_to_bufferv("png", [], [])
        if not ok: raise ValueError("The icon could not be converted")
        return bytes(png)
    except GLib.Error as error:
        raise ValueError("This file could not be decoded as an icon") from error


@dataclass(frozen=True)
class App:
    id: str
    name: str
    filename: str
    icon: object = None
    visible: bool = True


def installed_apps():
    from gi.repository import Gio
    apps = []
    for item in Gio.AppInfo.get_all():
        identifier, filename = item.get_id(), getattr(item, "get_filename", lambda: None)()
        try: desktop_id(identifier)
        except ValueError: continue
        if filename:
            apps.append(App(identifier, item.get_display_name() or identifier, filename, item.get_icon(), item.should_show()))
    return sorted(apps, key=lambda app: (app.name.casefold(), app.id))


def search_apps(apps, query="", *, include_hidden=False):
    words = unicodedata.normalize("NFKC", query[:256]).casefold().split()
    return [app for app in apps if (include_hidden or app.visible) and
            all(word in unicodedata.normalize("NFKC", app.name + " " + app.id).casefold() for word in words)]


class IconManager:
    def __init__(self, data_home=None):
        value = data_home or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
        self.data = Path(value)
        if not self.data.is_absolute() or any(c in str(self.data) for c in "\r\n\0"):
            raise ValueError("The user data directory must be an absolute local path")
        self.applications = self.data / "applications"
        self.root = self.data / "livara/app-icons"

    @staticmethod
    def _directory(path, private=False):
        if path.is_symlink(): raise ValueError("An icon storage folder is a symbolic link")
        path.mkdir(parents=True, exist_ok=True, mode=0o700 if private else 0o755)
        if not path.is_dir() or path.stat().st_uid != os.getuid():
            raise ValueError("Icon storage must belong to this user")
        if private: path.chmod(0o700)

    def paths(self, identifier):
        identifier = desktop_id(identifier)
        folder = self.root / hashlib.sha256(identifier.encode()).hexdigest()
        return self.applications / identifier, folder, folder / "state.json"

    def customized(self, identifier):
        return self.paths(identifier)[2].exists()

    @contextmanager
    def _lock(self):
        self._directory(self.data)
        self._directory(self.applications)
        self._directory(self.data / "livara", True)
        self._directory(self.root, True)
        fd = os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError("Invalid icon storage lock")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally: os.close(fd)

    @staticmethod
    def _atomic(path, data, mode=0o600):
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".livara-")
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), mode); stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name): os.unlink(name)

    def _state(self, path, identifier):
        if not path.exists() and not path.is_symlink(): return None
        try:
            state = json.loads(_read(path, 2 * MAX_DESKTOP))
            if set(state) != {"version", "id", "original", "source", "desktop_hashes"} or state["version"] != 1 or state["id"] != identifier:
                raise ValueError()
            if state["original"] is not None:
                original = base64.b64decode(state["original"], validate=True)
                if len(original) > MAX_DESKTOP: raise ValueError()
            if not isinstance(state["source"], str) or not Path(state["source"]).is_absolute(): raise ValueError()
            hashes = state["desktop_hashes"]
            if not isinstance(hashes, list) or not 1 <= len(hashes) <= 2 or any(h is not None and not re.fullmatch(r"[a-f0-9]{64}", h) for h in hashes): raise ValueError()
            return state
        except (ValueError, TypeError, OSError) as error:
            raise ValueError("The icon backup is unreadable; existing files were preserved") from error

    @staticmethod
    def _check_current(target, state):
        current = _read(target, MAX_DESKTOP) if target.exists() or target.is_symlink() else None
        digest = hashlib.sha256(current).hexdigest() if current is not None else None
        if state and digest not in state["desktop_hashes"]:
            raise ValueError("This launcher was edited outside Livara. Preserve those edits before changing its icon again")
        return current

    def apply(self, app, image, *, renderer=render_icon):
        png = renderer(image)
        if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > MAX_IMAGE:
            raise ValueError("The icon could not be converted into a bounded PNG")
        target, folder, state_path = self.paths(app.id)
        with self._lock():
            self._directory(folder, True)
            old_state_bytes = _read(state_path, 2 * MAX_DESKTOP) if state_path.exists() else None
            state = self._state(state_path, app.id)
            current = self._check_current(target, state)
            if state is None:
                state = {"version": 1, "id": app.id, "original": base64.b64encode(current).decode() if current is not None else None,
                         "source": str(Path(app.filename).absolute()), "desktop_hashes": []}
            origin = Path(state["source"])
            data = current if state["original"] is not None else _read(origin, MAX_DESKTOP, follow=True)
            if data is None: raise ValueError("This app's original launcher is unavailable")
            asset = folder / (hashlib.sha256(png).hexdigest() + ".png")
            content = replace_icon(data, str(asset))
            new_hash = hashlib.sha256(content).hexdigest()
            state["desktop_hashes"] = list(dict.fromkeys([new_hash, hashlib.sha256(current).hexdigest() if current is not None else None]))
            self._atomic(asset, png, 0o644)
            try:
                self._atomic(state_path, json.dumps(state).encode())
                self._atomic(target, content, 0o644)
                state["desktop_hashes"] = [new_hash]
                self._atomic(state_path, json.dumps(state).encode())
            except Exception:
                if current is None: target.unlink(missing_ok=True)
                else: self._atomic(target, current, 0o644)
                if old_state_bytes is None: state_path.unlink(missing_ok=True)
                else: self._atomic(state_path, old_state_bytes)
                raise
            for old in folder.glob("*.png"):
                if old != asset and re.fullmatch(r"[a-f0-9]{64}\.png", old.name): old.unlink()
        self.refresh_cache()
        return asset

    def restore(self, identifier):
        target, folder, state_path = self.paths(identifier)
        with self._lock():
            state = self._state(state_path, identifier)
            if state is None: return False
            self._check_current(target, state)
            original = None if state["original"] is None else base64.b64decode(state["original"], validate=True)
            restored_hash = hashlib.sha256(original).hexdigest() if original is not None else None
            state["desktop_hashes"] = list(dict.fromkeys([state["desktop_hashes"][0], restored_hash]))
            self._atomic(state_path, json.dumps(state).encode())
            if original is None: target.unlink(missing_ok=True)
            else: self._atomic(target, original, 0o644)
            state_path.unlink()
            for asset in folder.glob("*.png"):
                if re.fullmatch(r"[a-f0-9]{64}\.png", asset.name): asset.unlink()
        self.refresh_cache()
        return True

    def refresh_cache(self):
        try:
            subprocess.run(["update-desktop-database", str(self.applications)], timeout=5, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired): pass
