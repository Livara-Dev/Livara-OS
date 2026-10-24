# Build Livara on Windows

The source kit contains no ISO. **Extract the whole ZIP**, then double-click **Build-Livara.bat** to download build dependencies and generate an ISO on your own computer. It uses the source beside the BAT, including your local edits.

## Requirements

- A supported x86_64 Windows installation with **Docker Desktop running in Linux container mode**. The WSL 2 backend is recommended. A separately installed Ubuntu distribution, Python, Make, and Git Bash are not required.
- At least **16 GiB RAM allocated to Docker Desktop**, preferably **24 GiB or more**, and at least 2 CPUs for the full source build. These limits concern building the applications, not the installed OS's runtime requirements.
- At least **100 GiB free inside Docker Desktop's Linux disk**, preferably **150 GiB or more**, plus enough free space on the Windows destination drive for the resulting ISO. The physical drive holding Docker's virtual disk also needs that capacity. Firefox/Zen source, compiler toolchains, application builds, Docker images, and caches consume space beyond the final ISO.
- Internet access to Docker registries, Ubuntu/Kali repositories, GitHub, Tor Project release servers, and the upstream VS Code/Zen toolchain and dependency servers. Initial downloads are large. Compiling VS Code and Zen can take hours; time depends on CPU, memory, storage, and network speed.

Use a local folder such as `C:\Livara OS`. Spaces are supported. Commas, newlines, and network/UNC source paths are rejected because they cannot be represented reliably by this builder's Docker bind arguments. Install and start Docker Desktop yourself; the BAT does not change Windows features, install WSL, request an account login, or reboot the machine.

## Run

```bat
Build-Livara.bat
```

The result appears in the source folder's `dist` directory:

```text
dist\livara-os-0.1.0-amd64.iso
dist\livara-os-0.1.0-amd64.iso.sha256
dist\livara-os-0.1.0-packages.txt
dist\livara-desktop_0.1.1_all.deb
dist\build-<time>-<run>.log
```

The desktop package is built in a Linux container. The builder then downloads the pinned upstream VS Code and Zen source, applies the Livara fork recipes, and compiles both applications. Their archives are generated inside the Linux source volume as `dist/forks/livara-code-linux-x64.tar.xz` and `dist/forks/livara-browser-linux-x64.tar.xz`; both are required by the live filesystem build. The source ZIP contains recipes and Livara assets, without vendoring the upstream source trees or prebuilt application payloads.

For Tor mode, the builder separately downloads the pinned official Tor Browser bundle and checks its detached signature against the supplied official signing key. The artifact `dist/forks/livara-tor-browser-linux-x64.tar.xz` retains the official `tor-browser/` contents unchanged; Livara's Zen skin, fonts, and preferences are not applied to it. The live filesystem requires this third archive as well as the two source-built application archives.

The core Kali image is built and included for offline setup. The live filesystem and assembly tools then build from their Dockerfile targets. The ISO is assembled and hashed on a Linux volume; its checksum is checked again after copying the file to Windows. No disks are formatted and no host boot settings are changed.

Both check and full modes rebuild the Livara font binaries from the editable UFO/GLIF and TrueType XML (TTX) sources copied into the Linux source volume. Local outline edits are preserved and enter the desktop package; the automatic build does not regenerate or replace the editable source designs. The source kit also retains the Persian family's licensed upstream font and original FontForge sources.

For a smaller prerequisite/source check **without building an ISO**:

```bat
Build-Livara.bat -Check
```

`-Check` still downloads the small build controller and its build tools, including FontTools, HarfBuzz, GnuPG, and the Code fork's checksum-pinned Node.js runtime, then runs local source/recipe and built-in feature tests and creates the desktop `.deb`. It does **not** download or compile VS Code/Zen, install their npm dependencies, download the Tor Browser bundle, build the live root filesystem or Kali image, or run the ISO assembler. The `.deb` contains Livara integration and assets; it does not contain the application payloads, which the full image build installs separately. A successful check establishes local validation only; it does not establish that either application fork compiled, that a Tor Browser bundle was downloaded and verified, or that a new ISO boots. It writes `dist\CHECK-RESULT.txt` on success. An ISO left from an earlier run is not a product of this check; the check never deletes existing Windows outputs. The large RAM/disk thresholds apply to full builds, not this lightweight check.

Additional options:

```bat
Build-Livara.bat -Jobs 4
Build-Livara.bat -Check -KeepWork
Build-Livara.bat -CaBundle "C:\Certificates\combined-trust.pem"
```

`-Jobs` defaults to 2 and accepts 1 through 16. The full builder also limits workers to the allocated CPU count and a memory budget of 4 GiB per worker after reserving 8 GiB for linking and system work. Docker's reported usable RAM is rounded to the nearest GiB, allowing up to 512 MiB for WSL/kernel reservations. For example, a 16 GiB Docker allocation allows at most two workers; 24 GiB allows four. These are portable 64-bit x86 builds; the recipes do not add CPU-specific `-march=native` tuning.

The CA option accepts a trusted **combined PEM bundle**, or the path can be set in `LIVARA_BUILD_CA`. It is passed as a transient BuildKit secret to supported build steps, not installed in Livara. Docker Desktop itself must trust the certificate used by your registry/proxy. Configure proxy settings in Docker Desktop normally; configured proxy environment is forwarded to nested builds by argument name. TLS verification stays enabled. The recipe uses public base images; private-registry credential forwarding from Windows credential helpers is not implemented. Registry throttling or a blocked corporate mirror can still require Docker/network configuration outside this script.

## Why it uses Linux volumes

Windows filesystems do not preserve every Unix ownership bit, symlink, or device node required by a live Linux image. The builder copies project files into a uniquely named Linux Docker volume, normalizes Unix script line endings, and restores portable source permissions: directories and scripts use 0755, other files use 0644. This also makes the nested Docker helper executable after an NTFS copy. Rootfs extraction and ISO assembly take place on other Linux volumes. Only completed files are copied back to NTFS. PowerShell never pipes a binary filesystem export or ISO through its text pipeline.

The controller and helper containers share named volumes explicitly. Fork Docker builds stream their context through the Docker API and extract their finished archives through Docker create/copy operations. A `/project` path inside a container is never incorrectly supplied as a bind source on the Windows Docker host. Only a local Docker Desktop context is accepted. The controller has Docker socket access while building; run source you trust. Run one Livara build at a time; the Windows wrapper prevents simultaneous builds in the same Windows session.

## Failure and cleanup

Read the console and `dist\build-*.log`. Common causes include Docker Desktop not running, Windows container mode, insufficient Docker disk/RAM allocation, a blocked dependency server, an interrupted download, a Tor signature check failure, or an upstream compiler/dependency failure. The full build stops if any required application archive is missing; a source recipe is not treated as a compiled application. The wrapper returns a nonzero exit code on failure. The BAT keeps its window open when launched without arguments, as with a double-click. Command-line runs with switches do not pause; set `LIVARA_NO_PAUSE=1` for argument-free automation, or invoke `Build-Livara.ps1` directly.

Each run labels its containers and gives its three work volumes unique names. It removes only those resources by default. **Docker images and build cache remain**, so subsequent builds can reuse downloaded layers. It never runs a global Docker prune command. `-KeepWork` retains the volumes and prints their names for inspection; remove them in Docker Desktop when finished. If a successful build cannot be copied to Windows, the volumes are retained automatically to avoid losing the completed ISO.

To recover an output volume retained after a copy failure, use PowerShell from the source folder, substituting the printed volume name:

```powershell
docker --context desktop-linux run --rm --mount "type=volume,source=livara-output-REPLACE_ME,target=/output,readonly" --mount "type=bind,source=$PWD\dist,target=/export" livara-windows-builder:0.1.0 export
```

Once recovered, remove only the printed `livara-source-*`, `livara-build-*`, and `livara-output-*` volumes belonging to that run. Existing source files and Windows outputs are left in place.

## Validation scope

The controller image was built on a Linux Docker engine. Its `check` and `export` paths were exercised with a source folder containing spaces, CRLF shell input, an actual Debian package fixture, and excluded cache/output/environment files. A separate binary Docker export/extraction fixture preserved UID 1234, GID 2345, mode 0750, and a symbolic link. The PowerShell script parsed under PowerShell 7.4 on Linux. No ISO was created during those checks.

The final source integration check used the checksum-pinned Node 24.18.0 runtime, FontTools 4.46.0 and HarfBuzz 8.3.0. It ran 143 Python tests with one expected skip for an absent cached upstream Zen checkout; all 15 Node feature/control tests passed. The exported desktop package was inspected for current source/assets, all six rebuilt fonts, executable launchers, root ownership, and the new window-control and animation modules. This check used separate Linux source/build/output volumes and removed them afterward.

Native Windows/PowerShell 5.1/Docker Desktop execution, a complete source build of both application forks, and a freshly generated ISO from the current source revision still require qualification. In particular, a local `-Check` pass does not mean Zen was compiled. The source kit does not imply that the new image has already passed hardware, Secure Boot, or UEFI graphics testing. Start with a BIOS VM, 4 GB RAM, 2 CPUs, and 3D acceleration disabled after your local build finishes.

## Electron header TLS disconnect during npm install

A reported Docker Desktop/WSL2 build stopped at `@vscode/deviceid` with `Client network socket disconnected before secure TLS connection was established` while node-gyp requested Electron 43.7.7's `SHASUMS256.txt`. This was a network download failure during dependency installation; the npm upgrade notice and deprecation messages were not its cause.

The updated recipe fetches Electron and Node header archives from their official canonical HTTPS endpoints using curl with bounded retries for connection/TLS failures. Each archive has a committed SHA-256 pin. It validates the checkout's root, build and remote target versions, then primes a dedicated node-gyp cache before `npm ci`. This removes the per-module header/checksum downloads that failed in the report. Npm registry fetches also have bounded retries. TLS verification and archive integrity checks remain enabled; no insecure mirror or disabled native package replaces the failed dependency.

Download the updated source ZIP, extract the complete folder and run `Build-Livara.bat` again with Docker Desktop in Linux mode. Keep Docker's existing images/cache. Do not run a global Docker prune or upgrade npm merely because the log advertises a new version. Existing work-volume names in the report are diagnostic; they do not prove an ISO was completed.

The fix was tested by downloading and verifying all four pinned header archives and compiling an Electron 43.7.7 native addon through a real npm lifecycle with Docker networking disabled. The exact previously failing `@vscode/deviceid` 0.1.5 package also completed `npm rebuild` offline against the cached Electron headers. All three Node header targets configured offline. This specifically qualifies header cache preparation and npm cache use; it does not establish that the entire editor, browser or ISO build has finished on Windows.

## Mozilla compiler download returns HTTP 403

See [compiler recovery](browser-toolchain-recovery.md). The current full builder checks this dependency before compiling the editor, and caches checksum-verified compiler provenance and archives. Keep existing Docker caches; a network refusal is not fixed by deleting them.
