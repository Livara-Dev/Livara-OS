"""Read-only CPU, Intel/NVIDIA graphics observations and an explicit driver plan.

No command is executed merely by inspecting this module or its report. Hardware
support is reported as observed, never inferred from an RTX model label alone.
"""
from __future__ import annotations

import csv
import io
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

DRIVER_BRANCH = 580
DRIVER_PACKAGES = (
    "linux-generic-hwe-24.04",
    "linux-modules-nvidia-580-open-generic-hwe-24.04",
    "nvidia-driver-580-open",
    "nvidia-prime",
)


def generation(model: str) -> str | None:
    """Recognize GeForce RTX consumer generations; workstation names stay unknown."""
    match = re.search(r"\b(?:GeForce\s+)?RTX\s+(20|30|40|50)[5-9]0\b", model, re.I)
    return {"20": "Turing / RTX 20", "30": "Ampere / RTX 30", "40": "Ada / RTX 40", "50": "Blackwell / RTX 50"}.get(match[1]) if match else None


def run_readonly(arguments: list[str], *, timeout: int = 8) -> tuple[int, str]:
    if not shutil.which(arguments[0]):
        return 127, "Not installed"
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, errors="replace", timeout=timeout, check=False)
        return result.returncode, (result.stdout if result.returncode == 0 else result.stderr).strip()[:65536]
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)


def pci_devices(root: Path = Path("/sys/bus/pci/devices"), *, vendor: str = "0x10de") -> list[dict]:
    devices = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []
    for path in entries:
        try:
            if path.joinpath("vendor").read_text().strip().lower() != vendor.lower():
                continue
            device_class = int(path.joinpath("class").read_text().strip(), 16)
            if device_class >> 16 != 3:
                continue
            device_id = path.joinpath("device").read_text().strip()
            driver = path.joinpath("driver").resolve(strict=True).name if path.joinpath("driver").exists() else "unbound"
            devices.append({"slot": path.name, "device_id": device_id, "driver": driver})
        except (OSError, ValueError):
            continue
    return devices


def read_optional(path: Path, limit: int = 4096) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as source:
            return source.read(limit).strip()
    except OSError:
        return "Unavailable"


def cpu_observation(cpuinfo: Path = Path("/proc/cpuinfo"), cpu_root: Path = Path("/sys/devices/system/cpu")) -> dict:
    """Observe model and kernel frequency controls without changing power policy.

    Physical core counts use complete unique socket/core pairs. A Core Ultra
    label does not supply a P/E topology or identify the exact architecture.
    """
    text = read_optional(cpuinfo, 2**20)
    records = []
    for block in text.split("\n\n"):
        record = {}
        for line in block.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                record[key.strip()] = value.strip()
        if "processor" in record:
            records.append(record)
    first = records[0] if records else {}
    model = first.get("model name", "Unavailable")
    plain_model = re.sub(r"\((?:R|TM)\)", "", model, flags=re.I)
    ultra = bool(re.search(r"\bCore\s+Ultra\s+7\b", plain_model, re.I))
    pairs = {(item["physical id"], item["core id"]) for item in records if "physical id" in item and "core id" in item}
    physical = len(pairs) if records and all("physical id" in item and "core id" in item for item in records) else None
    policies = []
    try:
        paths = sorted((cpu_root / "cpufreq").glob("policy*"))
    except OSError:
        paths = []
    for policy in paths[:256]:
        if not policy.is_dir():
            continue
        policies.append({"policy": policy.name,
                         "driver": read_optional(policy / "scaling_driver"),
                         "governor": read_optional(policy / "scaling_governor"),
                         "energy_preference": read_optional(policy / "energy_performance_preference")})
    flags = set(first.get("flags", "").split())
    return {"model": model, "vendor": first.get("vendor_id", "Unavailable"),
            "family": first.get("cpu family", "Unavailable"), "model_id": first.get("model", "Unavailable"),
            "stepping": first.get("stepping", "Unavailable"), "microcode": first.get("microcode", "Unavailable"),
            "core_ultra_7": ultra, "logical_processors_observed": len(records),
            "physical_cores_observed": physical,
            "intel_pstate": read_optional(cpu_root / "intel_pstate" / "status"),
            "hwp_advertised": "hwp" in flags, "frequency_policies": policies}


def combined_assessment(devices: list[dict], gpus: list[dict], module_text: str, intel_devices: list[dict]) -> str:
    if devices or gpus:
        prefix = "Intel and NVIDIA display devices were both detected. " if intel_devices else ""
        return prefix + assess(devices, gpus, module_text)
    if intel_devices:
        drivers = ", ".join(sorted({item["driver"] for item in intel_devices}))
        return f"Intel graphics detected; observed kernel driver(s): {drivers}. NVIDIA drivers are not needed for the Intel GPU. Rendering and media acceleration require a workload test."
    return "No Intel or NVIDIA display device was detected in this environment. Virtual machines and containers may not expose the host GPU."


def parse_smi(text: str) -> list[dict]:
    result = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) != 5:
            continue
        model, version, bus, memory, temperature = [part.strip() for part in row]
        if not model or not re.fullmatch(r"\d+(?:\.\d+)+", version):
            continue
        result.append({"model": model, "driver": version, "pci_bus": bus,
                       "memory_mib": memory, "temperature_c": temperature,
                       "generation": generation(model) or "Not classified"})
    return result


def assess(devices: list[dict], gpus: list[dict], module_text: str = "") -> str:
    if not devices and not gpus:
        return "No NVIDIA display device was detected in this environment."
    if not gpus:
        return "NVIDIA hardware detected; a working NVIDIA driver was not verified. Inspect the driver report before installing or rebooting."
    for gpu in gpus:
        major = int(gpu["driver"].split(".")[0])
        if gpu["generation"] == "Blackwell / RTX 50":
            if major < 570:
                return "RTX 50 hardware requires NVIDIA 570 or newer with open kernel modules; the observed driver is too old."
            if "Open Kernel Module" not in module_text:
                return "RTX 50 detected; the open NVIDIA kernel module has not been verified."
    return "NVIDIA management queries succeeded. Rendering, external displays, suspend and each application still require hardware testing."


def diagnostics() -> dict:
    devices = pci_devices()
    intel_devices = pci_devices(vendor="0x8086")
    cpu = cpu_observation()
    smi_code, smi_text = run_readonly(["nvidia-smi", "--query-gpu=name,driver_version,pci.bus_id,memory.total,temperature.gpu", "--format=csv,noheader,nounits"])
    gpus = parse_smi(smi_text) if smi_code == 0 else []
    _, pci_text = run_readonly(["lspci", "-Dnnk"])
    try:
        module_text = Path("/proc/driver/nvidia/version").read_text()[:4096].strip()
    except OSError:
        module_text = "Not loaded or unavailable"
    _, secure_boot = run_readonly(["mokutil", "--sb-state"])
    _, prime = run_readonly(["prime-select", "query"])
    _, power_profile = run_readonly(["powerprofilesctl", "get"])
    version_text = platform.release()
    try:
        cmdline = Path("/proc/cmdline").read_text()
    except OSError:
        cmdline = ""
    return {
        "kernel": version_text, "architecture": platform.machine(),
        "session": os.environ.get("XDG_SESSION_TYPE", "Unknown"),
        "live_session": "boot=casper" in cmdline,
        "devices": devices, "intel_devices": intel_devices, "cpu": cpu,
        "gpus": gpus, "module": module_text, "power_profile": power_profile,
        "secure_boot": secure_boot, "prime_mode": prime,
        "nvidia_smi": smi_text if smi_code != 0 else "Query succeeded",
        "pci_display_lines": "\n".join(line for line in pci_text.splitlines() if any(token in line.lower() for token in ("nvidia", "vga compatible", "3d controller", "display controller", "kernel driver in use"))),
        "assessment": combined_assessment(devices, gpus, module_text, intel_devices),
        "nvidia_assessment": assess(devices, gpus, module_text),
        "recommended_packages": list(DRIVER_PACKAGES),
    }


def installation_command() -> list[str]:
    """Fixed argv for the intentionally user-triggered authenticated install."""
    return ["livara-terminal", "--", "bash", "-c",
            'sudo apt-get update && sudo apt-get install "$@"; result=$?; '
            'printf "\\nInstaller exit status: %s\\nPress Enter to close." "$result"; read -r reply',
            "livara-graphics", *DRIVER_PACKAGES]


def report_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    print(report_json(diagnostics()), end="")
