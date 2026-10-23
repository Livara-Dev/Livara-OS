# Livara Code source fork

This directory contains the source transformation and additional code for the Livara Code fork. The full upstream source is fetched by immutable commit, verified with SHA-256, and compiled locally by the builder. The ZIP does not carry a prebuilt editor or a renamed upstream binary.

- `upstream.json`: exact source, Node and Electron pins.
- `patches/0002-standalone-build.patch`: standalone build changes and removal of the unrelated Copilot extension build.
- `apply.py`: product identity, first-party visible text, Linux/app icons, compiled workbench import and default settings.
- `overlay/core/`: actual TypeScript workbench contribution and CSS compiled into Electron.
- `overlay/extension/`: bundled Livara welcome hub, theme, file icons and twelve tools.
- `test-features.cjs`: real filesystem, crypto, editor command and timer integration tests with an API harness.

Build from the project root: `bash scripts/build-code.sh`. The final Docker stage is `artifact`; it contains `/artifacts/livara-code-linux-x64.tar.xz`. See `docs/code-editor.md` for the exact scope and qualification.

New code in this directory uses MIT licenses, compatible with the upstream license. Original licenses, third-party notices and technical compatibility identifiers remain intact. Supplied/adapted logo artwork and the Livara fonts retain their separately documented licenses.
