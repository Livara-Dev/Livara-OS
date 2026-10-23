"""Live Linux resource observations and identity-checked process control.

The GUI never receives a naked PID for an action. A selected process carries
its start time and owner; a Linux pidfd pins that exact process while signaling.
"""
from __future__ import annotations

import json
import os
import signal
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Process:
    pid: int
    name: str
    state: str
    parent: int
    uid: int
    started: int
    ticks: int
    rss: int
    threads: int
    command: str
    cpu: float = 0.0

    @property
    def identity(self) -> tuple[int, int]:
        return self.pid, self.started


@dataclass(frozen=True)
class Snapshot:
    sampled_at: float
    cpu: float
    logical_cpus: int
    memory_total: int
    memory_used: int
    memory_available: int
    swap_total: int
    swap_used: int
    network_receive: float
    network_send: float
    network_totals: dict[str, tuple[int, int]]
    uptime: float
    load: tuple[float, float, float]
    disk_total: int
    disk_used: int
    disk_free: int
    processes: tuple[Process, ...]


def parse_cpu(text: str) -> tuple[int, int]:
    """Total /proc/stat CPU ticks, excluding already-counted guest fields."""
    line = next((line for line in text.splitlines() if line.startswith("cpu ")), None)
    if not line:
        raise ValueError("Aggregate CPU observation is unavailable")
    values = [int(value) for value in line.split()[1:9]]
    if len(values) < 4:
        raise ValueError("Incomplete CPU observation")
    return sum(values), values[3] + (values[4] if len(values) > 4 else 0)


def cpu_usage(previous: tuple[int, int] | None, current: tuple[int, int]) -> float:
    if previous is None:
        return 0.0
    total = current[0] - previous[0]
    idle = current[1] - previous[1]
    if total <= 0 or idle < 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (total - idle) / total))


def parse_memory(text: str) -> dict[str, int]:
    values = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and value.split():
            values[key] = int(value.split()[0]) * 1024
    total = values.get("MemTotal", 0)
    available = min(total, values.get("MemAvailable", sum(values.get(key, 0) for key in ("MemFree", "Buffers", "Cached"))))
    swap = values.get("SwapTotal", 0)
    return {
        "memory_total": total, "memory_available": available,
        "memory_used": max(0, total - available),
        "swap_total": swap, "swap_used": max(0, swap - values.get("SwapFree", 0)),
    }


def parse_network(text: str) -> dict[str, tuple[int, int]]:
    interfaces = {}
    for line in text.splitlines():
        name, separator, data = line.partition(":")
        if not separator or name.strip() == "lo":
            continue
        values = data.split()
        if len(values) >= 9:
            interfaces[name.strip()] = (int(values[0]), int(values[8]))
    return interfaces


def network_rates(previous: dict[str, tuple[int, int]], current: dict[str, tuple[int, int]], elapsed: float) -> tuple[float, float]:
    if elapsed <= 0:
        return 0.0, 0.0
    received = sent = 0
    for name in current.keys() & previous.keys():
        received += max(0, current[name][0] - previous[name][0])
        sent += max(0, current[name][1] - previous[name][1])
    return received / elapsed, sent / elapsed


def parse_process_stat(text: str) -> dict:
    # comm can contain spaces and closing parentheses, so split at its last ).
    left, right = text.find("("), text.rfind(")")
    if left < 1 or right <= left:
        raise ValueError("Malformed process observation")
    pid = int(text[:left].strip())
    parts = text[right + 1:].split()
    if len(parts) < 22:
        raise ValueError("Incomplete process observation")
    return {
        "pid": pid, "name": text[left + 1:right], "state": parts[0],
        "parent": int(parts[1]), "ticks": int(parts[11]) + int(parts[12]),
        "threads": int(parts[17]), "started": int(parts[19]),
        "rss": max(0, int(parts[21])) * os.sysconf("SC_PAGE_SIZE"),
    }


def read_process(pid: int, proc: Path = Path("/proc")) -> Process:
    folder = proc / str(pid)
    try:
        fields = parse_process_stat((folder / "stat").read_text(errors="replace"))
        status = (folder / "status").read_text(errors="replace")
        uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
        uid = int(uid_line.split()[2])  # Effective UID, matching signal permission.
        try:
            command = (folder / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace").strip()
        except PermissionError:
            command = ""
        # A second read avoids combining fields from a PID reused during sampling.
        latest = parse_process_stat((folder / "stat").read_text(errors="replace"))
        if fields["started"] != latest["started"]:
            raise ProcessLookupError("The process changed while being observed")
        return Process(**fields, uid=uid, command=command or f"[{fields['name']}]")
    except (FileNotFoundError, StopIteration, ValueError, IndexError) as error:
        raise ProcessLookupError("The process is no longer available") from error


class Sampler:
    def __init__(self, proc: Path = Path("/proc"), directory: Path | None = None):
        self.proc = proc
        self.directory = directory or Path.home()
        self.previous_cpu = None
        self.previous_network: dict[str, tuple[int, int]] = {}
        self.previous_time: float | None = None
        self.previous_processes: dict[tuple[int, int], Process] = {}
        self.clock_ticks = os.sysconf("SC_CLK_TCK")

    def sample(self) -> Snapshot:
        now = time.monotonic()
        elapsed = now - self.previous_time if self.previous_time is not None else 0
        cpu = parse_cpu((self.proc / "stat").read_text())
        memory = parse_memory((self.proc / "meminfo").read_text())
        network = parse_network((self.proc / "net/dev").read_text())
        receive, send = network_rates(self.previous_network, network, elapsed)
        processes = []
        for folder in self.proc.iterdir():
            if not folder.name.isdecimal():
                continue
            try:
                process = read_process(int(folder.name), self.proc)
                previous = self.previous_processes.get(process.identity)
                usage = max(0, process.ticks - previous.ticks) / self.clock_ticks / elapsed * 100 if previous and elapsed > 0 else 0.0
                process = Process(**{**asdict(process), "cpu": usage})
                processes.append(process)
            except (OSError, ValueError):
                continue
        disk = shutil.disk_usage(self.directory)
        uptime = float((self.proc / "uptime").read_text().split()[0])
        load = tuple(float(value) for value in (self.proc / "loadavg").read_text().split()[:3])
        snapshot = Snapshot(
            sampled_at=now, cpu=cpu_usage(self.previous_cpu, cpu),
            logical_cpus=os.cpu_count() or 1, **memory,
            network_receive=receive, network_send=send, network_totals=network,
            uptime=uptime, load=load, disk_total=disk.total, disk_used=disk.used,
            disk_free=disk.free, processes=tuple(processes),
        )
        self.previous_cpu, self.previous_time, self.previous_network = cpu, now, network
        self.previous_processes = {process.identity: process for process in processes}
        return snapshot


ACTION_SIGNALS = {"pause": signal.SIGSTOP, "resume": signal.SIGCONT, "terminate": signal.SIGTERM}


def control_process(selected: Process, action: str, proc: Path = Path("/proc")) -> None:
    """Signal only the selected identity, pinned with a pidfd. Never escalates."""
    if action not in ACTION_SIGNALS:
        raise ValueError("Unknown process action")
    if selected.pid <= 1 or selected.pid == os.getpid():
        raise PermissionError("Livara does not control this protected process")
    if selected.uid != os.geteuid():
        raise PermissionError("Only processes owned by your user can be controlled")
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("Safe process control requires Linux pidfd support")
    current = read_process(selected.pid, proc)
    if (current.started, current.uid) != (selected.started, selected.uid):
        raise ProcessLookupError("The selected process has exited or changed identity")
    descriptor = os.pidfd_open(selected.pid, 0)
    try:
        # If reuse happened before pidfd_open, refuse the new identity. If reuse
        # happens afterwards, pidfd_send_signal still refers to the old process.
        current = read_process(selected.pid, proc)
        if (current.started, current.uid) != (selected.started, selected.uid):
            raise ProcessLookupError("The selected process has exited or changed identity")
        signal.pidfd_send_signal(descriptor, ACTION_SIGNALS[action], None, 0)
    finally:
        os.close(descriptor)


def export_snapshot(snapshot: Snapshot, path: Path) -> None:
    """Create a private report without silently replacing an existing file."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        observations = asdict(snapshot)
        observations["sampled_at_monotonic_seconds"] = observations.pop("sampled_at")
        json.dump({"schema": 1, "source": "Livara Task Manager", "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **observations}, stream, indent=2)
        stream.write("\n")


def format_bytes(value: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


def format_uptime(seconds: float) -> str:
    minutes = int(seconds) // 60
    days, remainder = divmod(minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    return (f"{days}d " if days else "") + f"{hours}h {minutes}m"
