# Livara RTX graphics

Livara's source build includes Ubuntu's **NVIDIA 580 open kernel driver**, the **Ubuntu 24.04 HWE kernel**, and **matching precompiled NVIDIA kernel modules**. It targets GeForce RTX 20, 30, 40, and 50 series, while retaining Mesa drivers for Intel and AMD graphics. Livara Graphics (`livara-graphics`) shows actual observations and an explicit repair workflow.

This is a driver integration target, not a hardware certification. No physical RTX board, laptop, external monitor, suspend/resume cycle, game, or CUDA application was tested in this environment. ISO publication requires the separate BIOS and UEFI live-boot checks to pass. Test the image on your specific machine before relying on it.

| GeForce family | Architecture | Included driver path |
| --- | --- | --- |
| RTX 20 | Turing | NVIDIA 580 open kernel modules plus matching NVIDIA userspace |
| RTX 30 | Ampere | NVIDIA 580 open kernel modules plus matching NVIDIA userspace |
| RTX 40 | Ada Lovelace | NVIDIA 580 open kernel modules plus matching NVIDIA userspace |
| RTX 50 | Blackwell | NVIDIA 580 **open** kernel modules and GSP firmware; Blackwell requires open modules and a supporting 570-or-newer branch |

NVIDIA documents open kernel modules for Turing and later in its [580 driver README](https://download.nvidia.com/XFree86/Linux-x86_64/580.178.04/README/kernel_open.html). The exact supported PCI products are listed in [supported chips](https://download.nvidia.com/XFree86/Linux-x86_64/580.178.04/README/supportedchips.html). A generation name alone cannot establish support for every future SKU, laptop firmware, display connection, or workload.

The kernel modules are open source. **NVIDIA's associated userspace driver and firmware remain subject to NVIDIA's licenses.** Including this stack does not make every part of the resulting distribution open source. The build uses Ubuntu's official `restricted` repository, not a random driver installer or third-party PPA.

## Build integration

The relevant package set is:

```text
linux-generic-hwe-24.04
linux-modules-nvidia-580-open-generic-hwe-24.04
nvidia-driver-580-open
nvidia-prime
ubuntu-drivers-common
mesa-vulkan-drivers
vulkan-tools
mokutil
pciutils
```

On 2026-10-22 the official Ubuntu 24.04 repositories resolved NVIDIA **580.178.04-0ubuntu0.24.04.1** and HWE **7.0.0-38.38~24.04.4** with corresponding precompiled modules. These are observed repository candidates, not hardcoded kernel ABI promises. The HWE and NVIDIA module metapackages track compatible updates. Builds require the packages to remain available.

The precompiled NVIDIA module metapackage provides the versioned `nvidia-dkms-580-open` dependency. Installing it together with the driver avoids compiling DKMS modules inside Docker against the host kernel. The build selects the latest actual `/boot/vmlinuz-*` image, refreshes its module indexes, and checks the NVIDIA 580 open-module license and all five module ABI versions before application extraction and again before final initramfs creation. It never selects a kernel from arbitrary directories under `/lib/modules`. A regression test using the real Ubuntu kernel and NVIDIA packages reproduced the old failure and verified this fix; see [package qualification](kernel-package-qualification.json) and `scripts/test-graphics-kernel.sh`. NVIDIA DRM kernel modesetting is enabled for the live desktop. Driver services are supplied by the upstream packages.

A compatibility graphics boot entry remains useful for diagnosis; graphics acceleration and glass effects are not expected under `nomodeset`. The preview bootloader is unsigned, so **Secure Boot must be disabled** for this preview even when Ubuntu-supplied NVIDIA modules themselves are signed. Creating a signed boot chain is separate work.

## Inspect your system

Open **Livara Graphics** and choose **Refresh observations**. The panel reads NVIDIA display PCI devices, their bound drivers, `nvidia-smi`, the loaded module's identity, kernel, session type, Secure Boot state, and PRIME mode. It never replaces missing readings with invented hardware or performance figures. Copy report copies the observations locally to your clipboard.

Equivalent commands:

```sh
python3 -m livara.gpu
nvidia-smi
modinfo -F license nvidia
vulkaninfo --summary
```

A successful `nvidia-smi` query verifies management communication with the driver. It does not by itself prove that GNOME, a game, Vulkan, or a particular application renders on that GPU. Check the renderer in the application you use. CUDA toolkits, machine-learning frameworks, Steam, and 32-bit gaming libraries are separate installations and are not implied by the base driver.

On a hybrid laptop, Intel/AMD may render the desktop while NVIDIA renders selected applications. This is normal and can save power. For an explicit OpenGL offload test, with `mesa-utils` installed:

```sh
__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia glxinfo -B
```

Firmware-controlled MUX switches, external connectors wired to the discrete GPU, and suspend behavior vary by laptop. Do not force the discrete GPU permanently just to make a status label change.

## Repair on a persistent installed desktop

The Graphics app's repair button is available only when NVIDIA hardware is detected, a terminal is available, and the session is not a temporary live boot. It first shows the exact package plan. Choosing **Open installer** launches a terminal, refreshes official package lists, and lets `sudo` and APT request authentication and package confirmation. Nothing installs merely by opening the app or collecting observations.

The fixed package plan is equivalent to:

```sh
sudo apt-get update
sudo apt-get install linux-generic-hwe-24.04 \
  linux-modules-nvidia-580-open-generic-hwe-24.04 nvidia-driver-580-open nvidia-prime
```

Save work and reboot after a successful install. The preview includes a Calamares configuration whose disk installation and reboot path remain unqualified; this repair path also serves users installing the Livara desktop package on an existing supported Ubuntu desktop. A live session uses the driver built into its image. Rebuild the source image to change that driver instead of installing another driver into its temporary overlay.

Do not combine NVIDIA's `.run` installer with this APT-managed stack. Do not disable GSP firmware for the open kernel modules. When a new GPU requires a newer driver branch than 580, update the driver, userspace, precompiled-module metapackages, tests, and documentation together rather than claiming support based solely on its RTX label.

## 64-bit Intel PCs and read-only observations

Livara builds **amd64 / x86-64**, which supports compatible 64-bit Intel and AMD processors. “amd64” names the instruction-set architecture; it does not mean that an AMD processor is required. An Intel Core Ultra 7 uses this 64-bit target. The Windows builder requires Docker Desktop's Linux amd64 engine with virtualization enabled and sufficient RAM and disk space; see [Windows build instructions](windows-build.md).

Livara does not add `-march=native`, AVX-512, or a particular Core Ultra SKU requirement to its own utilities. It keeps generic x86-64 binaries and upstream application build defaults. No custom CPU clock, governor, core-disabling, or power-profile tuning is required just to build or run a 64-bit image.

Livara Graphics additionally reports the actual CPU model, vendor, CPU family/model identifiers, microcode revision, observed logical processors, and physical socket/core pairs when exposed. It observes the kernel's frequency driver, Intel P-state status, per-policy energy preferences, and selected power profile. It does not infer P/E core counts or a precise processor architecture from the words “Ultra 7.” In a VM or container, these observations reflect what the guest exposes.

Intel display-class PCI devices are reported independently of NVIDIA devices, with their actually bound `i915`, `xe`, or other kernel driver. Neither Intel driver is forced globally. Intel and NVIDIA devices may coexist on a hybrid laptop; desktop rendering on Intel with selected applications offloaded to NVIDIA is normal. Livara does not force one GPU for every workload. Missing NVIDIA hardware does not mean an Intel GPU is missing or needs an NVIDIA driver.

The modern HWE kernel and Mesa stack provide the general Intel/AMD graphics path. Hardware media codecs, NPUs, and application-specific acceleration are separate capabilities and are not implied by “64-bit.” In particular, stock Ubuntu's `intel-media-va-driver-non-free` 24.1 package is not a promise of Lunar Lake VA-API support; Intel's [24.1 platform list](https://github.com/intel/media-driver/blob/intel-media-24.1.0/README.md#supported-platforms) lists Meteor Lake and Arrow Lake S, while its [24.4 list](https://github.com/intel/media-driver/blob/intel-media-24.4.4/README.md#supported-platforms) adds Lunar Lake and Arrow Lake H. This source kit does not add a separate custom Intel media-driver build merely to support a 64-bit Intel CPU.
