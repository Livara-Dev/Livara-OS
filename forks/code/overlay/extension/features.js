/* SPDX-License-Identifier: MIT */
'use strict';
const fs = require('node:fs/promises');
const {constants} = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const LIMITS = Object.freeze({files: 1000, entries: 6000, directories: 256, depth: 16,
    textBytes: 1024 * 1024, scanFileBytes: 512 * 1024, scanBytes: 16 * 1024 * 1024,
    inventoryFileBytes: 4 * 1024 * 1024, inventoryBytes: 64 * 1024 * 1024,
    hashBytes: 32 * 1024 * 1024, matches: 500});
const EXCLUDED = new Set(['.git', '.hg', '.svn', 'node_modules', '.venv', 'venv', '__pycache__',
    '.cache', 'dist', 'build', 'target', 'out', 'coverage', '.next', '.nuxt']);
const BINARY = /\.(png|jpe?g|gif|webp|ico|pdf|zip|gz|xz|7z|woff2?|ttf|mp[34]|exe|dll|so|sqlite3?)$/i;
const inside = (root, file) => { const relative = path.relative(root, file); return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative)); };

async function readBounded(file, root, limit) {
    let handle;
    try {
        handle = await fs.open(file, constants.O_RDONLY | (constants.O_NOFOLLOW || 0));
        const stat = await handle.stat();
        if (!stat.isFile() || stat.size > limit) return null;
        // On Livara/Linux, resolve the opened descriptor, so swapping a parent
        // directory for an outside symlink cannot escape the workspace boundary.
        let actual;
        try { actual = await fs.realpath(`/proc/self/fd/${handle.fd}`); }
        catch { actual = await fs.realpath(file); }
        if (!inside(root, actual)) return null;
        const buffer = Buffer.alloc(Math.min(limit + 1, stat.size + 1));
        let length = 0;
        while (length < buffer.length) {
            const result = await handle.read(buffer, length, buffer.length - length, length);
            if (!result.bytesRead) break;
            length += result.bytesRead;
        }
        if (length > limit || length > stat.size) return null;
        return buffer.subarray(0, length);
    } catch (error) {
        if (['EACCES', 'EPERM', 'ENOENT', 'ELOOP', 'EISDIR', 'ENOTDIR'].includes(error.code)) return null;
        throw error;
    } finally { if (handle) await handle.close(); }
}

async function workspaceFiles(root, token = {}) {
    root = await fs.realpath(root);
    const files = [], stack = [{directory: root, depth: 0}];
    let entries = 0, directories = 0, truncated = false;
    while (stack.length && !token.isCancellationRequested) {
        if (++directories > LIMITS.directories) { truncated = true; break; }
        const {directory, depth} = stack.pop();
        let listing;
        try {
            if (!inside(root, await fs.realpath(directory))) continue;
            listing = await fs.opendir(directory);
            for await (const item of listing) {
                if (token.isCancellationRequested) break;
                if (++entries > LIMITS.entries || files.length >= LIMITS.files) { truncated = true; break; }
                if (item.isSymbolicLink()) continue;
                const filename = path.join(directory, item.name);
                if (item.isDirectory()) {
                    if (EXCLUDED.has(item.name)) continue;
                    if (depth < LIMITS.depth) stack.push({directory: filename, depth: depth + 1});
                    else truncated = true;
                } else if (item.isFile()) files.push(filename);
            }
        } catch (error) {
            if (!['EACCES', 'EPERM', 'ENOENT', 'ENOTDIR'].includes(error.code)) throw error;
        }
        if (truncated && (files.length >= LIMITS.files || entries > LIMITS.entries)) break;
    }
    files.sort();
    return {root, files, truncated, cancelled: Boolean(token.isCancellationRequested)};
}

function formatJSON(text) {
    // Reject numbers that ordinary JSON.parse/stringify would silently round or
    // turn into null. Strings are consumed as tokens, including escaped quotes.
    const tokens = /"(?:\\.|[^"\\])*"|(-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;
    const decimal = raw => {
        const parsed = /^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(raw);
        let digits = (parsed[2] + (parsed[3] || '')).replace(/^0+/, '');
        if (!digits) return parsed[1] ? '-0' : '0';
        let exponent = Number(parsed[4] || 0) - (parsed[3] || '').length;
        if (!Number.isSafeInteger(exponent)) return null;
        const zeros = /0+$/.exec(digits)?.[0].length || 0;
        if (zeros) { digits = digits.slice(0, -zeros); exponent += zeros; }
        return `${parsed[1]}${digits}e${exponent}`;
    };
    for (const match of text.matchAll(tokens)) {
        if (!match[1]) continue;
        const number = Number(match[1]);
        if (!Number.isFinite(number) || (Number.isInteger(number) && !Number.isSafeInteger(number)) ||
            decimal(match[1]) !== decimal(JSON.stringify(number)))
            throw new Error('JSON contains a number that cannot be formatted without precision loss.');
    }
    function sorted(value, depth = 0) {
        if (depth > 128) throw new Error('JSON nesting exceeds the safe formatting limit.');
        if (Array.isArray(value)) return value.map(item => sorted(item, depth + 1));
        if (value && typeof value === 'object') {
            const result = Object.create(null);
            for (const key of Object.keys(value).sort()) result[key] = sorted(value[key], depth + 1);
            return result;
        }
        return value;
    }
    return JSON.stringify(sorted(JSON.parse(text)), null, 2) + '\n';
}

function boundedText(vscode, editor) {
    const selection = editor.selection;
    let range = selection;
    if (!selection || selection.isEmpty) {
        range = new vscode.Range(new vscode.Position(0, 0), editor.document.positionAt(LIMITS.textBytes + 1));
    } else if (Math.abs(editor.document.offsetAt(selection.end) - editor.document.offsetAt(selection.start)) > LIMITS.textBytes) {
        throw new Error('Select at most 1 MiB of text.');
    }
    const text = editor.document.getText(range);
    if (Buffer.byteLength(text, 'utf8') > LIMITS.textBytes) throw new Error('This text exceeds the 1 MiB command limit.');
    return {text, range};
}

async function privateNotes(directory) {
    await fs.mkdir(directory, {recursive: true, mode: 0o700});
    const stat = await fs.lstat(directory);
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('Private notes storage must be a real directory.');
    await fs.chmod(directory, 0o700);
    const filename = path.join(directory, 'notes.md');
    let handle;
    try {
        try {
            handle = await fs.open(filename, constants.O_RDWR | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW || 0), 0o600);
            await handle.writeFile('# Livara private notes\n\n', 'utf8');
        } catch (error) {
            if (error.code !== 'EEXIST') throw error;
            handle = await fs.open(filename, constants.O_RDWR | (constants.O_NOFOLLOW || 0));
        }
        if (!(await handle.stat()).isFile()) throw new Error('Private notes storage must be a regular file.');
        await handle.chmod(0o600);
    } finally { if (handle) await handle.close(); }
    return filename;
}

function registerFeatures(vscode, context, clock = {}) {
    const now = clock.now || (() => performance.now());
    const schedule = clock.setInterval || setInterval;
    const unschedule = clock.clearInterval || clearInterval;
    const push = disposable => { context.subscriptions.push(disposable); return disposable; };
    const command = (id, action) => push(vscode.commands.registerCommand(id, async (...args) => {
        try { return await action(...args); }
        catch (error) { await vscode.window.showErrorMessage(`Livara: ${error.message}`); return undefined; }
    }));
    const editor = () => { const current = vscode.window.activeTextEditor; if (!current) throw new Error('Open a text document first.'); return current; };
    const progress = (title, action) => vscode.window.withProgress({location: vscode.ProgressLocation.Notification, title, cancellable: true}, action);
    const workspace = async () => {
        const folders = (vscode.workspace.workspaceFolders || []).filter(folder => folder.uri.scheme === 'file');
        if (!folders.length) throw new Error('Open a local workspace folder first.');
        const selected = folders.length === 1 ? folders[0] : (await vscode.window.showQuickPick(
            folders.map(folder => ({label: folder.name, description: folder.uri.fsPath, folder})), {placeHolder: 'Choose a workspace folder'}))?.folder;
        return selected ? fs.realpath(selected.uri.fsPath) : null;
    };

    const storage = context.globalStorageUri;
    // Desktop's local user-data provider uses a physical fsPath but exposes a
    // vscode-userdata URI. Accept only the local desktop alias, never a remote
    // authority, web host or remote extension host.
    const localUserData = storage.scheme === 'vscode-userdata' && vscode.UIKind?.Desktop !== undefined &&
        vscode.env.uiKind === vscode.UIKind?.Desktop && !vscode.env.remoteName && !storage.authority;
    const noteDirectory = (storage.scheme === 'file' || localUserData) && path.isAbsolute(storage.fsPath)
        ? path.join(storage.fsPath, 'private') : null;
    let notesPath;
    command('livara.notes', async () => {
        if (!noteDirectory) throw new Error('Private notes require local extension storage.');
        notesPath = await privateNotes(noteDirectory);
        return vscode.window.showTextDocument(await vscode.workspace.openTextDocument(vscode.Uri.file(notesPath)));
    });
    push(vscode.workspace.onDidSaveTextDocument(document => {
        if (notesPath && document.uri.scheme === 'file' && document.uri.fsPath === notesPath)
            privateNotes(noteDirectory).catch(error => vscode.window.showErrorMessage(`Livara notes: ${error.message}`));
    }));

    const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 70);
    status.name = 'Livara Focus';
    let interval, deadline = 0, remaining = 0, paused = false;
    const stopInterval = () => { if (interval !== undefined) unschedule(interval); interval = undefined; };
    const render = () => {
        const seconds = Math.max(0, Math.ceil((paused ? remaining : deadline - now()) / 1000));
        if (!paused && seconds === 0) {
            stopInterval(); deadline = 0;
            status.text = '$(pass) Focus complete'; status.command = 'livara.focusStart'; status.tooltip = 'Start another Livara focus session';
            vscode.window.showInformationMessage('Livara focus complete. Take a moment to rest.');
            return;
        }
        status.text = `$(clock) ${paused ? 'Paused ' : 'Focus '}${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
        status.command = 'livara.focusPause'; status.tooltip = paused ? 'Resume focus timer' : 'Pause focus timer';
    };
    command('livara.focusStart', async () => {
        const value = await vscode.window.showInputBox({title: 'Livara Focus', prompt: 'Focus duration in minutes (1–180)', value: '25',
            validateInput: text => /^\d+$/.test(text) && Number(text) >= 1 && Number(text) <= 180 ? null : 'Enter a whole number from 1 to 180.'});
        if (value === undefined) return;
        const minutes = Number(value);
        if (!/^\d+$/.test(value) || minutes < 1 || minutes > 180) throw new Error('Focus duration must be 1–180 whole minutes.');
        stopInterval(); paused = false; remaining = minutes * 60000; deadline = now() + remaining;
        render(); status.show(); interval = schedule(render, 1000);
        return minutes;
    });
    command('livara.focusPause', () => {
        if (!deadline && !paused) return;
        if (paused) { paused = false; deadline = now() + remaining; interval = schedule(render, 1000); }
        else { remaining = Math.max(0, deadline - now()); paused = true; stopInterval(); }
        render();
    });
    command('livara.focusCancel', () => { stopInterval(); deadline = remaining = 0; paused = false; status.hide(); });
    push({dispose() { stopInterval(); status.dispose(); }});

    command('livara.todos', async () => {
        const root = await workspace(); if (!root) return;
        return progress('Livara · Scan workspace TODOs', async (_reporter, token) => {
            const scan = await workspaceFiles(root, token), matches = [];
            let total = 0, skipped = 0;
            for (const file of scan.files) {
                if (token.isCancellationRequested || matches.length >= LIMITS.matches) break;
                if (BINARY.test(file)) { skipped++; continue; }
                const bytes = await readBounded(file, root, Math.min(LIMITS.scanFileBytes, LIMITS.scanBytes - total));
                if (!bytes || bytes.includes(0)) { skipped++; continue; }
                total += bytes.length;
                const lines = bytes.toString('utf8').split(/\r?\n/);
                for (let line = 0; line < lines.length && matches.length < LIMITS.matches; line++) {
                    const found = /\b(TODO|FIXME|HACK|XXX)\b[:\t -]*(.*)/.exec(lines[line]);
                    if (found) matches.push({label: `${found[1]} · ${found[2].trim().slice(0, 180)}`, description: `${path.relative(root, file)}:${line + 1}`, file, line});
                }
                if (total >= LIMITS.scanBytes) { scan.truncated = true; break; }
            }
            if (matches.length >= LIMITS.matches) scan.truncated = true;
            if (!token.isCancellationRequested && matches.length) {
                const selected = await vscode.window.showQuickPick(matches, {placeHolder: `Livara TODOs · ${matches.length} matches${scan.truncated ? ' (limit reached)' : ''}`});
                if (selected) await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(vscode.Uri.file(selected.file)),
                    {selection: new vscode.Range(selected.line, 0, selected.line, 0)});
            } else if (!token.isCancellationRequested) await vscode.window.showInformationMessage('Livara: no TODO markers found within the scan limits.');
            return {matches, files: scan.files.length, skipped, truncated: scan.truncated, cancelled: Boolean(token.isCancellationRequested)};
        });
    });

    command('livara.hashFile', async () => {
        const current = vscode.window.activeTextEditor;
        let bytes, label;
        if (current) {
            const selected = boundedText(vscode, current);
            bytes = Buffer.from(selected.text, 'utf8'); label = current.selection?.isEmpty === false ? 'selection (UTF-8)' : 'open document (UTF-8)';
        } else {
            const chosen = await vscode.window.showOpenDialog({canSelectFiles: true, canSelectFolders: false, canSelectMany: false, openLabel: 'Hash file bytes'});
            if (!chosen?.length) return;
            if (chosen[0].scheme !== 'file') throw new Error('Select a local file.');
            const file = chosen[0].fsPath, root = await fs.realpath(path.dirname(file));
            bytes = await readBounded(file, root, LIMITS.hashBytes); label = path.basename(file);
            if (!bytes) throw new Error('Select a regular file of at most 32 MiB.');
        }
        const hash = crypto.createHash('sha256').update(bytes).digest('hex');
        if (await vscode.window.showInformationMessage(`SHA-256 · ${label}\n${hash}`, 'Copy hash') === 'Copy hash') await vscode.env.clipboard.writeText(hash);
        return hash;
    });

    const insert = async factory => {
        const current = editor(), selections = current.selections || [current.selection];
        if (selections.length > 64) throw new Error('Use at most 64 cursors for generated text.');
        if (!await current.edit(builder => { for (const selection of selections) builder.replace(selection, factory()); })) throw new Error('The document changed; try again.');
    };
    command('livara.insertUUID', () => insert(() => crypto.randomUUID()));
    command('livara.insertPassword', async () => {
        const value = await vscode.window.showInputBox({title: 'Livara · Insert a secure password', prompt: 'Length (16–128). Inserted directly; never copied or logged.', value: '24',
            validateInput: text => /^\d+$/.test(text) && Number(text) >= 16 && Number(text) <= 128 ? null : 'Enter a whole number from 16 to 128.'});
        if (value === undefined) return;
        const length = Number(value);
        if (!/^\d+$/.test(value) || length < 16 || length > 128) throw new Error('Password length must be 16–128.');
        const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%+-_';
        return insert(() => Array.from({length}, () => alphabet[crypto.randomInt(alphabet.length)]).join(''));
    });
    command('livara.formatJSON', async () => {
        const current = editor(), selected = boundedText(vscode, current), formatted = formatJSON(selected.text);
        if (!await current.edit(builder => builder.replace(selected.range, formatted))) throw new Error('The document changed; try again.');
        return formatted;
    });

    const snapshots = new Map();
    const provider = {provideTextDocumentContent: uri => snapshots.get(uri.toString()) || ''};
    push(vscode.workspace.registerTextDocumentContentProvider('livara-compare', provider));
    push(vscode.workspace.onDidCloseTextDocument(document => { if (document.uri.scheme === 'livara-compare') snapshots.delete(document.uri.toString()); }));
    push({dispose() { snapshots.clear(); }});
    command('livara.compareClipboard', async () => {
        const selected = boundedText(vscode, editor()), clipboard = await vscode.env.clipboard.readText();
        if (Buffer.byteLength(clipboard, 'utf8') > LIMITS.textBytes) throw new Error('Clipboard comparison is limited to 1 MiB.');
        while (snapshots.size > 6) snapshots.delete(snapshots.keys().next().value);
        const id = crypto.randomUUID(), left = vscode.Uri.parse(`livara-compare:/${id}/document.txt`), right = vscode.Uri.parse(`livara-compare:/${id}/clipboard.txt`);
        snapshots.set(left.toString(), selected.text); snapshots.set(right.toString(), clipboard);
        await vscode.commands.executeCommand('vscode.diff', left, right, 'Livara · Document ↔ Clipboard', {preview: true});
        return {left, right};
    });

    command('livara.inventory', async () => {
        const root = await workspace(); if (!root) return;
        return progress('Livara · Build workspace inventory', async (_reporter, token) => {
            const scan = await workspaceFiles(root, token), files = [];
            let total = 0, skipped = 0;
            for (const file of scan.files) {
                if (token.isCancellationRequested) break;
                const bytes = await readBounded(file, root, Math.min(LIMITS.inventoryFileBytes, LIMITS.inventoryBytes - total));
                if (!bytes) { skipped++; continue; }
                total += bytes.length;
                files.push({path: path.relative(root, file).split(path.sep).join('/'), bytes: bytes.length,
                    sha256: crypto.createHash('sha256').update(bytes).digest('hex')});
                if (total >= LIMITS.inventoryBytes) { scan.truncated = true; break; }
            }
            const result = {workspace: path.basename(root), generatedAt: new Date().toISOString(), limits: LIMITS,
                truncated: scan.truncated, cancelled: Boolean(token.isCancellationRequested), skipped, files};
            // The explicit command opens an unsaved document. It never writes or
            // uploads an inventory outside the selected workspace.
            if (!token.isCancellationRequested) await vscode.window.showTextDocument(await vscode.workspace.openTextDocument({language: 'json', content: JSON.stringify(result, null, 2) + '\n'}));
            return result;
        });
    });

    command('livara.newProject', async () => {
        const template = await vscode.window.showQuickPick([
            {label: 'Python starter', id: 'python'}, {label: 'Web starter', id: 'web'}, {label: 'Notes workspace', id: 'notes'}
        ], {placeHolder: 'Choose a Livara starter · no code is run'});
        if (!template) return;
        const chosen = await vscode.window.showOpenDialog({canSelectFiles: false, canSelectFolders: true, canSelectMany: false, openLabel: 'Choose project parent'});
        if (!chosen?.length) return;
        if (chosen[0].scheme !== 'file') throw new Error('Choose a local parent folder.');
        const name = await vscode.window.showInputBox({title: 'Livara · New project', prompt: 'A new folder name (1–64 letters, digits, dots, dashes or underscores)',
            validateInput: text => /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(text) ? null : 'Start with a letter or digit. Do not use paths.'});
        if (name === undefined) return;
        if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(name)) throw new Error('Invalid project folder name.');
        const parent = await fs.realpath(chosen[0].fsPath), target = path.join(parent, name);
        await fs.mkdir(target, {mode: 0o700}); // Exclusive: never reuse/overwrite an existing project.
        const templates = {
            python: {'README.md': `# ${name}\n\nA Livara Python starter.\n\nRun manually: python3 main.py\n`, 'main.py': 'def main():\n    print("Hello from Livara.")\n\n\nif __name__ == "__main__":\n    main()\n', '.gitignore': '__pycache__/\n.venv/\n*.pyc\n'},
            web: {'README.md': `# ${name}\n\nOpen index.html manually in your browser. No dependencies are installed.\n`, 'index.html': `<!doctype html>\n<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${name}</title><link rel="stylesheet" href="style.css"><main><h1>${name}</h1><p>Made with Livara Code.</p></main></html>\n`, 'style.css': 'body{background:#000;color:#e8d2ff;font-family:system-ui;margin:12vh auto;max-width:52rem;padding:2rem}h1{color:#c88cff}\n'},
            notes: {'README.md': `# ${name}\n\nYour Livara notes workspace.\n`, 'notes.md': '# Notes\n\n## Ideas\n\n## Next steps\n', '.gitignore': '.DS_Store\n*.tmp\n'}
        };
        for (const [filename, content] of Object.entries(templates[template.id] || {}))
            await fs.writeFile(path.join(target, filename), content, {flag: 'wx', mode: 0o644});
        await vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(target), {forceNewWindow: true});
        return target;
    });
}

exports.registerFeatures = registerFeatures;
exports.testing = {LIMITS, workspaceFiles, readBounded, formatJSON, privateNotes};
