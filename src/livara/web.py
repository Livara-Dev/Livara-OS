"""Small, testable URL and private-storage helpers for Livara's web apps."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

START_URI = "about:blank"
CHAT_URI = "https://chat.livara.org"


def _web_uri(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError("Use an HTTP or HTTPS web address")
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Web addresses cannot contain spaces or control characters")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Enter sign-in details on the website, not in its address")
    try:
        host = parts.hostname.encode("idna").decode("ascii")
        port = parts.port
    except (ValueError, UnicodeError) as error:
        raise ValueError("Invalid web address") from error
    if ":" in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError as error:
            raise ValueError("Invalid IPv6 address") from error
        host = f"[{host}]"
    authority = host + (f":{port}" if port is not None else "")
    return urlunsplit((parts.scheme.lower(), authority,
                      quote(parts.path, safe="/%:@!$&'()*+,;=-._~"),
                      quote(parts.query, safe="%:@!$&'()*+,;=/?-._~"),
                      quote(parts.fragment, safe="%:@!$&'()*+,;=/?-._~")))


def normalize_address(value: str) -> str:
    """An explicit safe web URL, a local start page, or a DuckDuckGo search."""
    value = value.strip()
    if not value or value == START_URI:
        return START_URI
    if len(value) > 8192 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("The address is too long or contains control characters")
    scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)\s*:", value)
    local = re.match(r"^(localhost|127(?:\.\d{1,3}){3}|\[::1\])(?::\d+)?(?:[/?#]|$)", value, re.I)
    if local and not any(c.isspace() for c in value):
        return _web_uri("http://" + value)
    if re.match(r"^[^\s/:]+\.[^\s/:]+:\d+(?:[/?#]|$)", value):
        return _web_uri("https://" + value)
    if scheme:
        if scheme.group(1).lower() not in ("http", "https"):
            raise ValueError("Only HTTP and HTTPS addresses can be opened here")
        return _web_uri(value)
    if not any(c.isspace() for c in value) and ("." in value.split("/", 1)[0] or value.startswith("[")):
        return _web_uri("https://" + value)
    return "https://duckduckgo.com/?" + urlencode({"q": value})


def safe_download_name(suggested: str | None) -> str:
    value = (suggested or "download").replace("\\", "/").split("/")[-1]
    value = "".join(c for c in value if ord(c) >= 32 and ord(c) != 127).strip(" .")
    value = re.sub(r'[<>:"|?*]', "_", value)
    if not value or value in (".", ".."):
        value = "download"
    if value.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value = "_" + value
    return value[:180]


def ensure_new_destination(path: Path) -> Path:
    path = path.expanduser().absolute()
    if path.exists() or path.is_symlink():
        raise ValueError("That filename already exists. Choose a new name.")
    if not path.parent.is_dir():
        raise ValueError("Choose an existing destination folder")
    return path


def _xdg(name: str, fallback: Path) -> Path:
    candidate = Path(os.environ.get(name, str(fallback)))
    return candidate if candidate.is_absolute() else fallback


def browser_paths(chat: bool = False) -> tuple[Path, Path]:
    suffix = "chat" if chat else "browser"
    data = _xdg("XDG_DATA_HOME", Path.home() / ".local/share") / "livara" / suffix
    cache = _xdg("XDG_CACHE_HOME", Path.home() / ".cache") / "livara" / suffix
    for path in (data, cache):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)
    return data, cache


class BookmarkStore:
    """Explicitly saved bookmarks; private files and atomic writes."""

    def __init__(self, path: Path | None = None):
        self.path = path or (_xdg("XDG_CONFIG_HOME", Path.home() / ".config") / "livara/browser/bookmarks.json")

    def list(self) -> list[dict[str, str]]:
        if self.path.is_symlink():
            raise ValueError("The bookmark store must not be a symbolic link")
        if not self.path.exists():
            return []
        try:
            if self.path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("The bookmark store is too large")
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("bookmarks"), list):
                raise ValueError("Unsupported bookmark store")
            result = []
            for item in data["bookmarks"]:
                if not isinstance(item, dict) or not isinstance(item.get("title"), str) or not isinstance(item.get("url"), str):
                    raise ValueError("Invalid bookmark entry")
                result.append({"title": item["title"][:200], "url": _web_uri(item["url"])})
            if len(result) > 1000:
                raise ValueError("The bookmark store contains too many entries")
            return result
        except (json.JSONDecodeError, UnicodeError) as error:
            raise ValueError("The bookmark store could not be read; the existing file was preserved") from error

    def _save(self, items: list[dict[str, str]]) -> None:
        if self.path.is_symlink():
            raise ValueError("The bookmark store must not be a symbolic link")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".bookmarks-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump({"schema": 1, "bookmarks": items}, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def add(self, title: str, url: str) -> dict[str, str]:
        url = _web_uri(url)
        item = {"title": (title.strip() or url)[:200], "url": url}
        items = [entry for entry in self.list() if entry["url"] != url]
        if len(items) >= 1000:
            raise ValueError("The bookmark limit is 1000 entries")
        items.append(item)
        self._save(items)
        return item

    def remove(self, url: str) -> None:
        self._save([item for item in self.list() if item["url"] != url])
