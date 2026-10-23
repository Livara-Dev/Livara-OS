/* SPDX-License-Identifier: MIT */
const vscode = require('vscode');
function activate(context) {
    require('./features.js').registerFeatures(vscode, context);
    let panel;
    const welcome = () => {
        if (panel) { panel.reveal(); return; }
        panel = vscode.window.createWebviewPanel('livaraWelcome', 'Livara · Create something', vscode.ViewColumn.One, {
            enableScripts: false,
            enableCommandUris: ['workbench.action.files.openFolder', 'workbench.action.files.newUntitledFile', 'workbench.action.showCommands', 'workbench.action.terminal.new', 'workbench.extensions.action.showExtensions', 'livara.chat', 'livara.focus', 'livara.notes', 'livara.focusStart', 'livara.focusPause', 'livara.focusCancel', 'livara.todos', 'livara.hashFile', 'livara.insertUUID', 'livara.insertPassword', 'livara.formatJSON', 'livara.compareClipboard', 'livara.inventory', 'livara.newProject'],
            localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, 'media')]
        });
        const logo = panel.webview.asWebviewUri(vscode.Uri.joinPath(context.extensionUri, 'media', 'livara-code.png'));
        panel.webview.html = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${panel.webview.cspSource} data:; style-src 'unsafe-inline';"><meta name="viewport" content="width=device-width, initial-scale=1"><style>
        *{box-sizing:border-box}body{margin:0;background:#000;color:#eadcf7;font-family:'Livara Sans','Livara Persian','Noto Sans',sans-serif}main{max-width:980px;margin:7vh auto;padding:30px}header{display:flex;gap:24px;align-items:center}img{width:112px;height:112px;object-fit:contain}small{letter-spacing:4px;color:#b88de0;font-size:11px}h1{font-size:45px;font-weight:600;margin:10px 0;letter-spacing:-1.2px}p{color:#a990bb;line-height:1.7}section{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-top:36px}a{display:block;border:1px solid #3a1953;border-radius:20px;padding:22px;color:#e5c8ff;background:linear-gradient(130deg,#170723,#08020c);text-decoration:none}a:hover,a:focus{border-color:#bc83ff;background:#241030;outline:2px solid #bc83ff;outline-offset:2px}strong{display:block;font-size:17px;margin-bottom:9px}.sub{font-size:12px;color:#ab8cbe}.foot{font-size:12px;margin-top:28px;color:#9b7ab0}@media(max-width:650px){section{grid-template-columns:1fr}h1{font-size:32px}img{width:78px;height:78px}}@media(prefers-reduced-motion:no-preference){a{transition:background 140ms ease,border-color 140ms ease}}
        </style></head><body><main><header><img src="${logo}" alt="Livara Code"><div><small>LIVARA CODE / YOUR NEXT IDEA</small><h1>Make something yours.</h1><p>Pure black. A little purple. Room for your next idea.</p></div></header><section>
        <a href="command:workbench.action.files.openFolder"><strong>Open your workspace ↗</strong><span class="sub">Explorer, source control and project search.</span></a>
        <a href="command:workbench.action.files.newUntitledFile"><strong>Start with a blank page ↗</strong><span class="sub">Your first line, with nothing in the way.</span></a>
        <a href="command:workbench.action.terminal.new"><strong>A terminal that feels at home ↗</strong><span class="sub">The Livara palette and your everyday shell.</span></a>
        <a href="command:workbench.extensions.action.showExtensions"><strong>Make your toolkit bigger ↗</strong><span class="sub">Explore extensions from Open VSX.</span></a>
        <a href="command:livara.focus"><strong>Find your focus ↗</strong><span class="sub">Toggle a quiet, full-screen coding space.</span></a>
        <a href="command:livara.chat"><strong>Open Livara Chat ↗</strong><span class="sub">chat.livara.org in your browser.</span></a>
<a href="command:livara.notes"><strong>Your private notebook ↗</strong><span class="sub">Local notes stored separately from your project.</span></a><a href="command:livara.focusStart"><strong>A little time to focus ↗</strong><span class="sub">Start a real countdown, then pause or resume it.</span></a><a href="command:livara.todos"><strong>Find your next step ↗</strong><span class="sub">Build a bounded TODO and FIXME index.</span></a><a href="command:livara.inventory"><strong>Record your workspace ↗</strong><span class="sub">Read-only SHA-256 inventory for project files.</span></a><a href="command:livara.newProject"><strong>Start a small project ↗</strong><span class="sub">Create a Python or web starter without running it.</span></a><a href="command:livara.formatJSON"><strong>Give JSON some order ↗</strong><span class="sub">Sort keys and format the active selection or document.</span></a><a href="command:livara.compareClipboard"><strong>See the difference ↗</strong><span class="sub">Compare your text with the current clipboard.</span></a><a href="command:livara.hashFile"><strong>A fingerprint for your file ↗</strong><span class="sub">Read the current file and calculate SHA-256.</span></a>        </section><p class="foot">Ctrl+P · Quick open &nbsp; / &nbsp; Ctrl+Shift+P · Commands &nbsp; / &nbsp; Ctrl+Alt+L · This studio<br>Built from an open-source workbench. Workspace Trust stays on. Product telemetry is off.</p></main></body></html>`;
        panel.onDidDispose(() => { panel = undefined; }, null, context.subscriptions);
    };
    context.subscriptions.push(vscode.commands.registerCommand('livara.welcome', welcome));
    context.subscriptions.push(vscode.commands.registerCommand('livara.chat', () => vscode.env.openExternal(vscode.Uri.parse('https://chat.livara.org'))));
    context.subscriptions.push(vscode.commands.registerCommand('livara.focus', () => vscode.commands.executeCommand('workbench.action.toggleZenMode')));
    if (!context.globalState.get('livara.welcomed')) {
        context.globalState.update('livara.welcomed', true);
        if (!vscode.workspace.workspaceFolders && !vscode.window.activeTextEditor) { welcome(); }
    }
}
exports.activate = activate;
exports.deactivate = function () {};
