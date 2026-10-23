# Livara Studio

Livara Studio is a native GTK 4 / libadwaita application, launched with `livara-studio`. It contains **32 distinct local features**: 30 tools in a searchable workbench, a private Notebook, and a Focus room. The AMOLED black and iris interface opens on an Overview with real saved-note and completed-session totals, pinned tools, and recent successful tools. The tools use the Python standard library and make no network requests. Page transitions, result transitions, and the timer respect the desktop's reduced-motion preference. The native mac-style window controls and F11 fullscreen use Livara’s shared window preferences.

| # | Feature | Working behavior |
| --- | --- | --- |
| 1 | Private Notebook | Create and search pages; start with a blank, project, daily-intentions, or research template; browse a read-only archive, restore pages, and export Markdown or plain text. |
| 2 | Focus room | Set an intention; choose a 15/25/45/60-minute preset or a custom 1–180-minute duration; start, pause, resume, and reset a countdown. Only completed sessions enter local history and real progress totals. |
| 3 | Unicode lens | Count code points, words, lines, and UTF-8 bytes; inspect character names and categories. |
| 4 | Line workshop | Trim, remove blank lines, deduplicate, and sort lists in an explicit order. |
| 5 | Text comparison | Produce a unified line diff between two texts. |
| 6 | HTML entity desk | Encode and decode character entities; it is not an HTML sanitizer. |
| 7 | Base64 desk | Encode UTF-8 text and strictly decode Base64 back to text. |
| 8 | URL component encoder | Percent-encode or decode an individual URL component. |
| 9 | JSON formatter | Validate strict JSON, sort keys, and select indentation. |
| 10 | CSV ↔ JSON table | Convert header-based CSV and JSON arrays of scalar-valued objects. |
| 11 | TOML inspector | Parse TOML into a readable JSON structure. |
| 12 | JWT reader | Decode the header and payload while explicitly reporting that signatures are unverified. |
| 13 | Pattern lab | Run a regular expression in an isolated process with a one-second deadline and input/output limits. |
| 14 | Password forge | Generate passwords locally with a cryptographic random source and show the source-alphabet entropy. |
| 15 | Identity seeds | Generate random version 4 UUIDs. |
| 16 | Safe calculator | Evaluate a narrow arithmetic AST and approved math functions; no Python `eval` or shell is used. |
| 17 | Unit bridge | Convert length, temperature, and binary-storage units with compatible-unit validation. |
| 18 | Time bridge | Convert Unix seconds and ISO 8601 timestamps to UTC and local time. |
| 19 | Subnet notebook | Calculate CIDR boundaries and address counts, including IPv6, without scanning hosts. |
| 20 | URL anatomy | Inspect URL components and query fields without fetching the URL; embedded passwords are not echoed. |
| 21 | Domain alphabet | Convert a hostname between Unicode and Python's built-in IDNA encoding without a DNS query. |
| 22 | Color prism | Convert hexadecimal/RGB colors to RGB, HSL, HSV, and relative luminance. |
| 23 | Contrast lens | Calculate opaque sRGB contrast and the applicable WCAG text thresholds. |
| 24 | File passport | Read file size, guessed MIME type, permissions, ownership IDs, and filesystem timestamps. |
| 25 | Folder map | Summarize regular-file sizes/extensions and show the largest files, skipping symbolic links. |
| 26 | Duplicate finder | Identify equal-size files with equal SHA-256 content hashes; it does not delete or move files. |
| 27 | Log window | Read a bounded tail of a text log without loading the whole file. |
| 28 | Text fingerprint | Compute an exact UTF-8 SHA-256, SHA-512, or BLAKE2b digest. |
| 29 | UTF-8 hex desk | Encode UTF-8 text as hexadecimal or strictly decode it back to text. |
| 30 | Case & naming | Convert Unicode text to upper/lower/title/casefold or readable snake_case and kebab-case. |
| 31 | JSON path lens | Select nested JSON values with bounded dotted/index paths or RFC 6901 pointers, including Persian object keys. |
| 32 | Markdown outline | Inspect headings, links, fenced-code blocks, and word counts, or turn simple Markdown into plain text without rendering or fetching resources. |

The workbench keeps input and result side by side. Search combines words from tool names, categories, and descriptions; a category filter and Favorites view narrow the library. Pin or unpin a tool on its workspace. Successful runs add that tool to recent activity. Errors remain readable in the result pane with a clear correction message. Output controls copy a successful result, save it as a private text file, reuse it as input, or place it in an explicitly unsaved Notebook draft. File tools use a local file or folder chooser. An output is never executed as a command. Filesystem scans and pattern matching run away from the GTK event loop.

Up to six tool workspaces retain their input and result drafts **in the running process only**. The workspace metadata file records favorite tool IDs, the last eight successful tool IDs with UTC timestamps, and appearance choices. It never records tool inputs, results, generated passwords, or opened file contents. Explicitly saved Notebook pages and explicitly exported files contain the content the user chose to keep.

The Customize menu changes iris/ocean/mint/rose accents, comfortable/compact card padding, and editor text size from 11 to 22 pixels. These choices persist across launches. Interface and editor font families follow the desktop’s configured interface and monospace fonts, including changes made while Studio is open.

| Shortcut | Action |
| --- | --- |
| Ctrl+1 / 2 / 3 / 4 | Overview / Tool library / Notebook / Focus room |
| Ctrl+F | Focus tool search |
| Ctrl+Enter | Run the current tool when the workbench is open |
| Ctrl+Shift+C | Copy the current successful result |
| Ctrl+S | Save the open Notebook page |
| Ctrl+Shift+Space | Start, pause, or resume the focus timer |
| F11 | Toggle native fullscreen |

Notebook pages use `~/.local/share/livara/studio/notes/`, completed focus records use `~/.local/share/livara/studio/focus.jsonl`, and tool/appearance metadata uses `~/.local/share/livara/studio/workspace.json`. The `XDG_DATA_HOME` setting is honored. Private directories use mode `0700` and saved records use mode `0600`; this is filesystem privacy, **not encryption**. Archived note JSON files remain in the Notebook `archive/` directory and can be restored through the app. Notebook text is limited to 256 KiB per page. Opening another page, creating a template, switching the archive view, or closing the app offers Save/Discard/Cancel when edits are unsaved. Closing with a running or paused timer also asks before stopping it. In a live session, save or copy work to a mounted persistent disk before shutting down, as the live home directory is temporary.

Ordinary input fields are limited to 1 MiB. Folder scans stop explicitly at 5,000 files; duplicate hashing stops at a 256 MiB read budget. Pattern lab allows at most 20,000 input characters and a 512-character pattern, returns at most 200 matches, and runs with a one-second process deadline. Log Window reads at most the file's last 1 MiB. These are interactive workstation utilities, not substitutes for forensic acquisition, cryptographic signature verification, or a complete accessibility audit.

The backend is in `src/livara/studio.py`, the native interface in `src/livara/studio_gui.py`, and correctness, boundary, privacy, and persistence checks in `tests/test_studio.py` and `tests/test_studio_workspace.py`. The native redesign was also exercised through real GTK interactions for Overview, search/no-results, worker output, session drafts, Notebook save/archive/restore, Focus pause/resume/reset, and appearance changes. Screenshots in the gallery are identified as native-app captures in a container, not a booted Livara ISO.
