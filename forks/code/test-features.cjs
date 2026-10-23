/* SPDX-License-Identifier: MIT */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {registerFeatures, testing} = require('./overlay/extension/features.js');

class Position { constructor(line, character) { this.line = line; this.character = character; } }
class Range {
    constructor(a, b, c, d) { this.start = typeof a === 'number' ? new Position(a, b) : a; this.end = typeof a === 'number' ? new Position(c, d) : b; }
    get isEmpty() { return this.start.line === this.end.line && this.start.character === this.end.character; }
}
const uri = (scheme, fsPath) => ({scheme, fsPath, toString() { return `${scheme}:${fsPath}`; }});
function document(text = '', location = uri('untitled', '/fixture')) {
    return {text, uri: location,
        offsetAt(position) { const lines = this.text.split('\n'); return Math.min(this.text.length, lines.slice(0, position.line).reduce((n, line) => n + line.length + 1, 0) + position.character); },
        positionAt(offset) { const before = this.text.slice(0, offset).split('\n'); return new Position(before.length - 1, before.at(-1).length); },
        getText(range) { return range ? this.text.slice(this.offsetAt(range.start), this.offsetAt(range.end)) : this.text; }};
}
function textEditor(text = '') {
    const doc = document(text);
    const selection = new Range(new Position(0, 0), new Position(0, 0));
    return {document: doc, selection, selections: [selection], async edit(action) {
        const changes = [];
        action({replace(range, value) { changes.push({start: doc.offsetAt(range.start), end: doc.offsetAt(range.end), value}); }});
        changes.sort((a, b) => b.start - a.start);
        for (const change of changes) doc.text = doc.text.slice(0, change.start) + change.value + doc.text.slice(change.end);
        return true;
    }};
}
function harness(root, options = {}) {
    const commands = new Map(), providers = new Map(), input = [], quick = [], dialogs = [], calls = [], messages = [], errors = [], opened = [], shown = [], saves = new Set(), closes = new Set();
    const timers = new Map(); let now = 0, next = 0, clipboard = '', infoChoice;
    const disposeSet = (set, callback) => { set.add(callback); return {dispose() { set.delete(callback); }}; };
    const status = {show() { this.visible = true; }, hide() { this.visible = false; }, dispose() { this.disposed = true; }};
    const vscode = {
        Uri: {file: p => uri('file', p), parse: value => uri(value.slice(0, value.indexOf(':')), value.slice(value.indexOf(':') + 1))}, Position, Range,
        ProgressLocation: {Notification: 1}, StatusBarAlignment: {Left: 1}, UIKind: {Desktop: 1, Web: 2},
        commands: {
            registerCommand(id, callback) { assert(!commands.has(id)); commands.set(id, callback); return {dispose() { commands.delete(id); }}; },
            async executeCommand(id, ...args) { calls.push([id, ...args]); return commands.has(id) ? commands.get(id)(...args) : undefined; }
        },
        window: {activeTextEditor: undefined,
            async showInputBox() { return input.shift(); }, async showQuickPick(items) { const result = quick.shift(); return typeof result === 'function' ? result(items) : result; },
            async showOpenDialog() { return dialogs.shift(); },
            async showInformationMessage(message) { messages.push(message); return infoChoice; }, async showErrorMessage(message) { errors.push(message); },
            async showTextDocument(doc, options) { shown.push({doc, options}); return doc; },
            createStatusBarItem() { return status; },
            async withProgress(_options, callback) { return callback({report() {}}, {isCancellationRequested: false}); }
        },
        workspace: {workspaceFolders: [{name: 'fixture', uri: uri('file', root)}],
            async openTextDocument(arg) { const doc = typeof arg.content === 'string' ? document(arg.content) : document(await fs.readFile(arg.fsPath, 'utf8'), arg); opened.push(doc); return doc; },
            onDidSaveTextDocument: callback => disposeSet(saves, callback), onDidCloseTextDocument: callback => disposeSet(closes, callback),
            registerTextDocumentContentProvider(scheme, provider) { providers.set(scheme, provider); return {dispose() { providers.delete(scheme); }}; }
        },
        env: {uiKind: options.uiKind || 1, remoteName: options.remoteName,
            clipboard: {async readText() { return clipboard; }, async writeText(value) { clipboard = value; calls.push(['clipboard', value]); }}}
    };
    const context = {subscriptions: [], globalStorageUri: uri(options.storageScheme || 'file', options.storagePath || path.join(root, '.test-livara-storage'))};
    if (options.authority) context.globalStorageUri.authority = options.authority;
    registerFeatures(vscode, context, {now: () => now, setInterval: callback => { const id = ++next; timers.set(id, callback); return id; }, clearInterval: id => timers.delete(id)});
    return {vscode, context, commands, providers, input, quick, dialogs, calls, messages, errors, opened, shown, status, saves, closes, timers,
        run: id => commands.get('livara.' + id)(),
        advance(ms) { now += ms; for (const callback of [...timers.values()]) callback(); },
        set clipboard(value) { clipboard = value; }, get clipboard() { return clipboard; }, set infoChoice(value) { infoChoice = value; },
        dispose() { for (const item of context.subscriptions) item.dispose(); }};
}
async function fixture(t) { const root = await fs.mkdtemp(path.join(os.tmpdir(), 'livara-code-features-')); t.after(() => fs.rm(root, {recursive: true, force: true})); return root; }

test('all twelve commands register and timers/providers dispose cleanly', async t => {
    const app = harness(await fixture(t));
    assert.equal(app.commands.size, 12);
    app.input.push('1'); await app.run('focusStart'); assert.equal(app.timers.size, 1);
    app.dispose(); assert.equal(app.commands.size, 0); assert.equal(app.providers.size, 0); assert.equal(app.timers.size, 0); assert(app.status.disposed);
});

test('private notes use private real storage and preserve existing notes', async t => {
    const root = await fixture(t), app = harness(root);
    await app.run('notes'); assert.deepEqual(app.errors, []);
    const filename = app.opened.at(-1).uri.fsPath;
    assert.equal((await fs.stat(path.dirname(filename))).mode & 0o777, 0o700);
    assert.equal((await fs.stat(filename)).mode & 0o777, 0o600);
    await fs.writeFile(filename, 'My private idea'); await app.run('notes');
    assert.equal(await fs.readFile(filename, 'utf8'), 'My private idea');
    await fs.unlink(filename); const outside = path.join(root, 'outside'); await fs.writeFile(outside, 'untouched'); await fs.symlink(outside, filename);
    await app.run('notes'); assert(app.errors.length); assert.equal(await fs.readFile(outside, 'utf8'), 'untouched'); app.dispose();
});

test('private notes support the local desktop userdata alias and reject remote or web storage', async t => {
    const root = await fixture(t), app = harness(root, {storageScheme: 'vscode-userdata'});
    await app.run('notes'); assert.deepEqual(app.errors, []);
    const filename = app.opened.at(-1).uri.fsPath;
    assert.equal((await fs.stat(path.dirname(filename))).mode & 0o777, 0o700);
    assert.equal((await fs.stat(filename)).mode & 0o777, 0o600);
    app.dispose();
    for (const options of [
        {storageScheme: 'vscode-remote'},
        {storageScheme: 'vscode-userdata', uiKind: 2},
        {storageScheme: 'vscode-userdata', remoteName: 'ssh-remote'},
        {storageScheme: 'vscode-userdata', authority: 'remote-host'},
        {storageScheme: 'vscode-userdata', storagePath: 'relative/path'}
    ]) {
        const rejected = harness(root, options); await rejected.run('notes');
        assert.equal(rejected.opened.length, 0); assert.equal(rejected.errors.length, 1); rejected.dispose();
    }
});

test('focus countdown pauses, resumes, completes once and cancels without idle timers', async t => {
    const app = harness(await fixture(t));
    app.input.push('1'); assert.equal(await app.run('focusStart'), 1); assert.match(app.status.text, /1:00/);
    app.advance(20000); assert.match(app.status.text, /0:40/);
    await app.run('focusPause'); assert.equal(app.timers.size, 0); app.advance(120000); assert.match(app.status.text, /Paused 0:40/);
    await app.run('focusPause'); app.advance(40000); assert.equal(app.timers.size, 0); assert.match(app.status.text, /complete/);
    assert.equal(app.messages.filter(message => message.includes('focus complete')).length, 1);
    app.advance(40000); assert.equal(app.messages.length, 1);
    app.input.push('25'); await app.run('focusStart'); await app.run('focusCancel'); assert.equal(app.timers.size, 0); assert.equal(app.status.visible, false); app.dispose();
});

test('TODO scan excludes dependency directories, symlinks, binary and oversized content', async t => {
    const root = await fixture(t), outside = await fixture(t);
    await fs.writeFile(path.join(root, 'main.py'), '# TODO: build it\n# FIXME: improve it\n');
    await fs.mkdir(path.join(root, 'node_modules')); await fs.writeFile(path.join(root, 'node_modules', 'skip.js'), '// TODO outside dependency');
    await fs.mkdir(path.join(root, '.git')); await fs.writeFile(path.join(root, '.git', 'config'), 'TODO private git');
    await fs.writeFile(path.join(outside, 'private.txt'), 'TODO outside workspace'); await fs.symlink(outside, path.join(root, 'linked'));
    await fs.writeFile(path.join(root, 'big.txt'), 'TODO ' + 'x'.repeat(testing.LIMITS.scanFileBytes));
    await fs.writeFile(path.join(root, 'binary.bin'), Buffer.from([0, 84, 79, 68, 79]));
    const app = harness(root); app.quick.push(items => items[0]);
    const result = await app.run('todos'); assert.equal(result.matches.length, 2); assert(result.skipped >= 2); assert.deepEqual(app.errors, []);
    assert.equal(app.opened.at(-1).uri.fsPath, path.join(root, 'main.py')); assert.equal(app.shown.at(-1).options.selection.start.line, 0); app.dispose();
});

test('workspace walk caps files and never follows outside symlinks', async t => {
    const root = await fixture(t), outside = await fixture(t);
    await fs.writeFile(path.join(outside, 'secret.txt'), 'secret'); await fs.symlink(outside, path.join(root, 'outside'));
    await Promise.all(Array.from({length: testing.LIMITS.files + 8}, (_, n) => fs.writeFile(path.join(root, `${n}.txt`), 'x')));
    const scan = await testing.workspaceFiles(root); assert.equal(scan.files.length, testing.LIMITS.files); assert(scan.truncated);
    assert.equal(await testing.readBounded(path.join(root, 'outside', 'secret.txt'), root, 100), null);
});

test('hash command uses UTF8 selection or explicitly chosen original file bytes', async t => {
    const root = await fixture(t), app = harness(root);
    app.vscode.window.activeTextEditor = textEditor('alpha\nbeta');
    app.vscode.window.activeTextEditor.selection = new Range(new Position(0, 0), new Position(0, 5));
    app.infoChoice = 'Copy hash';
    const expected = crypto.createHash('sha256').update('alpha').digest('hex');
    assert.equal(await app.run('hashFile'), expected); assert.equal(app.clipboard, expected);
    app.vscode.window.activeTextEditor = undefined;
    const bytes = Buffer.from([0, 255, 13, 10]), file = path.join(root, 'raw.bin'); await fs.writeFile(file, bytes);
    app.dialogs.push([uri('file', file)]); assert.equal(await app.run('hashFile'), crypto.createHash('sha256').update(bytes).digest('hex')); app.dispose();
});

test('UUID and cryptographic password insert without leaking generated secrets', async t => {
    const app = harness(await fixture(t)); const editor = textEditor(); app.vscode.window.activeTextEditor = editor;
    await app.run('insertUUID'); assert.match(editor.document.text, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    const passwordEditor = textEditor(); app.vscode.window.activeTextEditor = passwordEditor; app.input.push('32'); await app.run('insertPassword');
    const password = passwordEditor.document.text; assert.equal(password.length, 32); assert.match(password, /^[ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%+\-_]+$/);
    assert.equal(app.clipboard, ''); assert(!app.messages.some(message => message.includes(password))); assert.deepEqual(app.errors, []); app.dispose();
});

test('JSON sorting preserves __proto__ data, refuses precision loss and never evaluates code', async t => {
    const app = harness(await fixture(t)), editor = textEditor('{"z":1,"__proto__":{"polluted":true},"a":{"b":2,"a":1}}'); app.vscode.window.activeTextEditor = editor;
    await app.run('formatJSON'); const parsed = JSON.parse(editor.document.text); assert(Object.hasOwn(parsed, '__proto__')); assert.equal({}.polluted, undefined); assert(editor.document.text.indexOf('"a"') < editor.document.text.indexOf('"z"'));
    for (const source of ['{"n":9007199254740993}', '{"n":1e400}', '{"n":0.1234567890123456789012345}', '{"n":-0}', '{"run":(global.pwned=true)}']) {
        const unchanged = textEditor(source); app.vscode.window.activeTextEditor = unchanged; await app.run('formatJSON'); assert.equal(unchanged.document.text, source);
    }
    assert.equal(global.pwned, undefined); assert.equal(app.errors.length, 5);
    assert.equal(testing.formatJSON('[1e3,0.1,1.00]'), '[\n  1000,\n  0.1,\n  1\n]\n'); app.dispose();
});

test('clipboard comparison uses readonly virtual snapshots, not files or text modification', async t => {
    const root = await fixture(t), app = harness(root), editor = textEditor('current text'); app.vscode.window.activeTextEditor = editor; app.clipboard = 'clipboard text';
    const result = await app.run('compareClipboard'); const provider = app.providers.get('livara-compare');
    assert.equal(result.left.scheme, 'livara-compare'); assert.equal(provider.provideTextDocumentContent(result.left), 'current text'); assert.equal(provider.provideTextDocumentContent(result.right), 'clipboard text');
    assert.equal(editor.document.text, 'current text'); assert.equal((await fs.readdir(root)).length, 0); assert.equal(app.calls.at(-1)[0], 'vscode.diff');
    for (const close of app.closes) close({uri: result.left}); assert.equal(provider.provideTextDocumentContent(result.left), ''); app.dispose();
});

test('inventory computes actual bounded SHA256 values and opens an unsaved document only', async t => {
    const root = await fixture(t), outside = await fixture(t);
    await fs.writeFile(path.join(root, 'source.txt'), 'source'); await fs.writeFile(path.join(root, 'binary.bin'), Buffer.from([0, 1, 2]));
    await fs.writeFile(path.join(outside, 'secret.txt'), 'private'); await fs.symlink(outside, path.join(root, 'linked'));
    const before = await fs.readdir(root), app = harness(root), result = await app.run('inventory');
    assert.equal(result.files.length, 2); assert.equal(result.files.find(file => file.path === 'source.txt').sha256, crypto.createHash('sha256').update('source').digest('hex'));
    assert(result.files.every(file => !path.isAbsolute(file.path) && !file.path.startsWith('..'))); assert.deepEqual(await fs.readdir(root), before); assert.equal(app.opened.at(-1).uri.scheme, 'untitled'); assert.deepEqual(app.errors, []); app.dispose();
});

test('new project exclusively creates selected template and never executes project code', async t => {
    const root = await fixture(t), app = harness(root);
    app.quick.push(items => items.find(item => item.id === 'python')); app.dialogs.push([uri('file', root)]); app.input.push('my-project');
    const target = await app.run('newProject'); assert.equal(target, path.join(root, 'my-project')); assert.match(await fs.readFile(path.join(target, 'main.py'), 'utf8'), /def main/);
    assert.deepEqual(app.calls.map(call => call[0]), ['vscode.openFolder']);
    await fs.writeFile(path.join(target, 'README.md'), 'preserve my work');
    app.quick.push(items => items[0]); app.dialogs.push([uri('file', root)]); app.input.push('my-project'); await app.run('newProject');
    assert.equal(await fs.readFile(path.join(target, 'README.md'), 'utf8'), 'preserve my work'); assert.equal(app.errors.length, 1);
    app.quick.push(items => items[0]); app.dialogs.push([uri('file', root)]); app.input.push('../escape'); await app.run('newProject'); assert.equal(app.errors.length, 2); app.dispose();
});
