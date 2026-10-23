"""Local system observations, evidence workspaces, and a rootless Kali toolbox.

All commands are argument arrays. No user input is interpreted by a shell.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__

DATA_DIR = Path(os.environ.get("LIVARA_DATA_DIR", "/usr/share/livara"))
IMAGE = "localhost/livara-kali:0.1.0-core"
PROFILES = {
    "core": "Network discovery, DNS, packet analysis, and everyday utilities",
    "web": "Kali web application testing collection",
    "forensics": "Kali digital forensics collection",
    "wireless": "Kali wireless tools (hardware access requires a dedicated environment)",
    "passwords": "Kali password auditing collection",
    "reverse": "Kali reverse engineering collection",
    "osint": "Kali information gathering collection",
    "vulnerability": "Kali vulnerability assessment collection",
    "full": "Complete kali-linux-everything collection; large online download",
}
TOOLS = (
    {"name": "Nmap", "command": "nmap", "category": "Network", "description": "Explore hosts and services", "help": "--help"},
    {"name": "Wireshark", "command": "wireshark", "category": "Network", "description": "Inspect packet captures visually", "help": "--help"},
    {"name": "tcpdump", "command": "tcpdump", "category": "Network", "description": "Read and filter packet captures", "help": "--help"},
    {"name": "dig", "command": "dig", "category": "Network", "description": "Investigate DNS records", "help": "-h"},
    {"name": "Whois", "command": "whois", "category": "Network", "description": "Look up domain registration", "help": "--help"},
    {"name": "OpenSSL", "command": "openssl", "category": "Crypto", "description": "Inspect certificates and cryptography", "help": "help"},
    {"name": "Lynis", "command": "lynis", "category": "Host security", "description": "Audit local security configuration", "help": "show"},
    {"name": "ClamAV", "command": "clamscan", "category": "Host security", "description": "Scan files with antivirus signatures; update definitions before use", "help": "--help"},
    {"name": "YARA", "command": "yara", "category": "Malware analysis", "description": "Match files against your detection rules", "help": "--help"},
    {"name": "Hashdeep", "command": "hashdeep", "category": "Forensics", "description": "Hash and audit collections of files", "help": "-h"},
    {"name": "Sleuth Kit (native)", "command": "fls", "category": "Forensics", "description": "List files in disk-image filesystems", "help": "-V"},
    {"name": "ExifTool (native)", "command": "exiftool", "category": "Forensics", "description": "Inspect file metadata", "help": "-ver"},
    {"name": "GnuPG", "command": "gpg", "category": "Crypto", "description": "Verify signatures and manage encryption keys", "help": "--help"},
    {"name": "Cryptsetup", "command": "cryptsetup", "category": "Crypto", "description": "Manage encrypted storage", "help": "--help"},
    {"name": "Strace", "command": "strace", "category": "Diagnostics", "description": "Observe process system calls", "help": "--help"},
    {"name": "Lsof", "command": "lsof", "category": "Diagnostics", "description": "Inspect open files and sockets", "help": "-h"},
    {"name": "MTR", "command": "mtr", "category": "Network", "description": "Diagnose network routes and packet loss", "help": "--help"},
    {"name": "ShellCheck", "command": "shellcheck", "category": "Code review", "description": "Find common shell script errors", "help": "--help"},
    {"name": "Kali shell", "command": None, "category": "Kali", "description": "Enter your isolated Kali workbench", "profile": "core"},
    {"name": "Nikto", "command": "nikto", "category": "Web", "description": "Review web server configuration", "profile": "web"},
    {"name": "SQLmap", "command": "sqlmap", "category": "Web", "description": "Test SQL injection in an authorized lab", "profile": "web"},
    {"name": "Gobuster", "command": "gobuster", "category": "Web", "description": "Discover web content in an authorized lab", "profile": "web"},
    {"name": "Sleuth Kit", "command": "fls", "category": "Forensics", "description": "Examine filesystem evidence", "profile": "forensics"},
    {"name": "ExifTool", "command": "exiftool", "category": "Forensics", "description": "Read file metadata", "profile": "forensics"},
    {"name": "Binwalk", "command": "binwalk", "category": "Forensics", "description": "Explore binary and firmware files", "profile": "forensics"},
    {"name": "Wireless collection", "command": "aircrack-ng", "category": "Wireless", "description": "Kali wireless assessment tools", "profile": "wireless"},
    {"name": "Password auditing collection", "command": "john", "category": "Passwords", "description": "Password strength analysis and auditing tools", "profile": "passwords"},
    {"name": "Reverse engineering collection", "command": "radare2", "category": "Reverse engineering", "description": "Debuggers, disassemblers, and binary analysis tools", "profile": "reverse"},
    {"name": "Information gathering collection", "command": "theHarvester", "category": "OSINT", "description": "Kali reconnaissance and information gathering tools", "profile": "osint"},
    {"name": "Vulnerability collection", "command": "nuclei", "category": "Assessment", "description": "Kali vulnerability assessment tools", "profile": "vulnerability"},
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_text(path: str | Path, default: str = "") -> str:
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return default


def os_info(path: str | Path = "/etc/os-release") -> dict[str, str]:
    result = {}
    for line in read_text(path).splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            result[key] = value.strip('"\'')
    return result


def run_capture(args: list[str], timeout: int = 5) -> str | None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def system_status() -> dict:
    info = os_info()
    memory = {}
    for line in read_text("/proc/meminfo").splitlines():
        key, _, value = line.partition(":")
        if value.strip():
            memory[key] = int(value.split()[0]) * 1024
    disk = shutil.disk_usage(Path.home())
    interfaces = []
    for path in sorted(Path("/sys/class/net").glob("*")):
        if path.name != "lo":
            interfaces.append({"name": path.name, "state": read_text(path / "operstate", "unknown")})
    return {
        "livara_version": __version__,
        "distribution": info.get("PRETTY_NAME", "Unknown Linux"),
        "ubuntu_base": info.get("UBUNTU_CODENAME", info.get("VERSION_CODENAME", "unknown")),
        "kernel": os.uname().release,
        "architecture": os.uname().machine,
        "hostname": os.uname().nodename,
        "uptime_seconds": int(float(read_text("/proc/uptime", "0").split()[0])),
        "memory_total": memory.get("MemTotal", 0),
        "memory_available": memory.get("MemAvailable", 0),
        "disk_total": disk.total,
        "disk_free": disk.free,
        "interfaces": interfaces,
        "native_tools_installed": sum(bool(t["command"] and shutil.which(t["command"])) for t in TOOLS if "profile" not in t),
        "podman_available": bool(shutil.which("podman")),
    }


def shield_report() -> list[dict[str, str]]:
    """Read-only checks. An unreadable control is unknown, never a passing check."""
    checks = []
    for title, path, expected, detail in (
        ("Address randomization", "/proc/sys/kernel/randomize_va_space", "2", "Full process address randomization"),
        ("Kernel log protection", "/proc/sys/kernel/dmesg_restrict", "1", "Limit kernel logs to privileged users"),
        ("Hardlink protection", "/proc/sys/fs/protected_hardlinks", "1", "Restrict unsafe hardlinks"),
        ("Symlink protection", "/proc/sys/fs/protected_symlinks", "1", "Restrict unsafe symbolic links"),
    ):
        value = read_text(path)
        checks.append({"name": title, "state": "pass" if value == expected else "review" if value else "unknown", "detail": detail})
    firewall = run_capture(["systemctl", "is-active", "ufw.service"])
    # An active oneshot unit alone does not prove that netfilter rules are loaded.
    ufw_state = run_capture(["ufw", "status"])
    if ufw_state and "Status: active" in ufw_state:
        state, detail = "pass", "UFW reports active firewall rules"
    elif ufw_state and "Status: inactive" in ufw_state:
        state, detail = "review", "UFW is inactive; open Firewall Settings to configure it"
    else:
        state, detail = "unknown", "Use sudo ufw status to inspect active rules"
        if firewall == "active":
            detail += "; UFW service is active"
    checks.append({"name": "Host firewall", "state": state, "detail": detail})
    updates = run_capture(["systemctl", "is-enabled", "apt-daily-upgrade.timer"])
    checks.append({"name": "Automatic update timer", "state": "pass" if updates == "enabled" else "unknown", "detail": "Ubuntu's automatic update schedule"})
    return checks


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"Not a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, expected: str | None = None) -> tuple[str, bool]:
    if expected is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ValueError("Expected SHA-256 must contain exactly 64 hexadecimal characters")
    actual = sha256_file(path)
    return actual, expected is None or hmac.compare_digest(actual, expected.lower())


def atomic_json(path: Path, data: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".livara-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def cases_root() -> Path:
    return Path.home() / "Livara" / "Cases"


def create_case(name: str, directory: Path | None = None) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("Use 1–64 letters, digits, hyphens, or underscores; start with a letter or digit")
    parent = (directory if directory is not None else cases_root()).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / name
    target.mkdir(mode=0o700)  # Refuse to overwrite an existing workspace.
    for folder in ("evidence", "notes", "reports"):
        (target / folder).mkdir(mode=0o700)
    atomic_json(target / "case.json", {"schema": 1, "name": name, "created_at": utc_now(), "livara_version": __version__})
    (target / "notes" / "journal.txt").write_text(f"{name}\nCreated {utc_now()}\n\nScope and authorization:\n\nObservations:\n")
    return target


def require_case(path: Path) -> Path:
    path = path.expanduser().resolve()
    metadata = path / "case.json"
    if metadata.is_symlink() or not metadata.is_file():
        raise ValueError(f"Not a Livara case: {path}")
    data = json.loads(metadata.read_text())
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("Unsupported case format")
    return path


def case_inventory(path: Path) -> dict[str, str]:
    files = {}
    for entry in sorted(path.rglob("*")):
        if entry.is_symlink():
            raise ValueError(f"Symbolic links cannot be sealed: {entry.relative_to(path)}")
        if entry == path / "manifest.json":
            continue
        if entry.is_file():
            files[entry.relative_to(path).as_posix()] = sha256_file(entry)
        elif not entry.is_dir():
            raise ValueError(f"Unsupported special file: {entry.relative_to(path)}")
    return files


def seal_case(path: Path) -> dict:
    path = require_case(path)
    files = case_inventory(path)
    manifest = {"schema": 1, "algorithm": "sha256", "sealed_at": utc_now(), "files": files}
    atomic_json(path / "manifest.json", manifest)
    return manifest


def verify_case(path: Path) -> dict:
    path = require_case(path)
    manifest_path = path / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("The case manifest must not be a symbolic link")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("algorithm") != "sha256" or not isinstance(manifest.get("files"), dict):
        raise ValueError("Unsupported case manifest")
    expected = manifest["files"]
    for name, digest in expected.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not re.fullmatch(r"[a-f0-9]{64}", str(digest)):
            raise ValueError("Invalid path or digest in case manifest")
    actual = case_inventory(path)
    changed = sorted(name for name in expected.keys() & actual.keys() if not hmac.compare_digest(expected[name], actual[name]))
    missing = sorted(expected.keys() - actual.keys())
    added = sorted(actual.keys() - expected.keys())
    return {"ok": not (changed or missing or added), "checked": len(actual), "changed": changed, "missing": missing, "added": added}


def toolbox_image(profile: str) -> str:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    return f"localhost/livara-kali:0.1.0-{profile}"


def toolbox_config() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "livara" / "toolbox.json"


def toolbox_storage() -> Path | None:
    config = toolbox_config()
    if not config.exists():
        return None
    data = json.loads(config.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("storage"), str) or not Path(data["storage"]).is_absolute():
        raise ValueError("Invalid toolbox storage configuration")
    return Path(data["storage"])


def configure_toolbox_storage(directory: Path) -> Path:
    directory = directory.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not directory.is_dir():
        raise ValueError("The toolbox storage must be a directory")
    if "boot=casper" in read_text("/proc/cmdline") and run_capture(["findmnt", "-n", "-o", "FSTYPE", "--target", str(directory)]) in ("overlay", "tmpfs", "ramfs"):
        raise ValueError("Choose a folder on a mounted persistent disk, outside the temporary live filesystem")
    config = toolbox_config()
    config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(config, {"schema": 1, "storage": str(directory)})
    return directory


def podman_command(*args: str) -> list[str]:
    storage = toolbox_storage()
    return ["podman", *(["--root", str(storage)] if storage else []), *args]


def toolbox_setup_command(profile: str, refresh: bool = False) -> list[str]:
    image = toolbox_image(profile)
    archive = DATA_DIR / "toolbox" / "kali-core.tar.gz"
    if profile == "core" and archive.is_file() and not refresh:
        return podman_command("load", "--input", str(archive))
    containerfile = DATA_DIR / "toolbox" / "Containerfile"
    if not containerfile.is_file():
        raise ValueError(f"Toolbox definition missing: {containerfile}. Install livara-desktop or set LIVARA_DATA_DIR.")
    return podman_command("build", "--pull=always", "--tag", image, "--build-arg", f"LIVARA_PROFILE={profile}", "--file", str(containerfile), str(containerfile.parent))


def toolbox_run_command(profile: str, command: list[str], directory: Path | None = None) -> list[str]:
    image = toolbox_image(profile)
    directory = (directory or Path.home() / "Livara" / "Workspace").expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError("The work directory must be a directory")
    # --mount has comma-delimited syntax; reject commas instead of changing meaning.
    if "," in str(directory):
        raise ValueError("The toolbox work directory cannot contain a comma")
    args = podman_command("run", "--rm", "--interactive")
    if os.isatty(0) and os.isatty(1):
        args.append("--tty")
    args += ["--userns=keep-id", "--cap-drop=ALL", "--security-opt=no-new-privileges",
             "--read-only", "--pids-limit=256", "--memory=2g", "--network=slirp4netns:allow_host_loopback=false",
             "--tmpfs=/tmp:rw,nosuid,size=256m", "--env=HOME=/tmp", "--workdir=/work",
             "--mount", f"type=bind,source={directory},destination=/work", image]
    return args + (command or ["/bin/bash"])


def execute(args: list[str]) -> int:
    if not shutil.which(args[0]):
        raise ValueError(f"{args[0]} is not installed. On Ubuntu: sudo apt install podman uidmap slirp4netns fuse-overlayfs")
    return subprocess.call(args)

