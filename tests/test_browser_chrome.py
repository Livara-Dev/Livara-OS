"""Checks for Livara's compiled Gecko chrome overlay and offline dashboard."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "forks/browser/overlay/src/livara"
NODE = shutil.which("node")


class BrowserResourceTests(unittest.TestCase):
    def test_start_page_has_strict_offline_csp_and_explicit_search(self):
        tree = ET.parse(OVERLAY / "start.xhtml")
        ns = {"h": "http://www.w3.org/1999/xhtml"}
        csp = next(node.attrib["content"] for node in tree.findall(".//h:meta", ns)
                   if node.attrib.get("http-equiv") == "Content-Security-Policy")
        self.assertIn("default-src 'none'", csp)
        self.assertIn("connect-src 'none'", csp)
        self.assertIn("form-action https://duckduckgo.com", csp)
        self.assertNotIn("unsafe-inline", csp)
        form = tree.find(".//h:form[@id='search-form']", ns)
        self.assertEqual(form.attrib["action"], "https://duckduckgo.com/")
        self.assertEqual(form.attrib["method"], "get")
        for tag, attribute in (("script", "src"), ("link", "href"), ("img", "src")):
            for node in tree.findall(f".//h:{tag}", ns):
                self.assertTrue(node.attrib[attribute].startswith("chrome://browser/content/livara/"))
        source = (OVERLAY / "start.js").read_text()
        self.assertNotRegex(source, r"\b(?:fetch|XMLHttpRequest|WebSocket|eval)\s*\(")
        self.assertNotIn("innerHTML", source)

    def test_jar_maps_all_source_resources_and_local_fonts(self):
        manifest = (OVERLAY / "jar.inc.mn").read_text()
        resources = re.findall(r"content/browser/livara/(\S+)\s+\(../../livara/(\S+)\)", manifest)
        self.assertEqual(len(resources), 11)
        self.assertTrue(all(dest == src for dest, src in resources))
        for dest, source in resources:
            if dest.endswith((".js", ".css", ".xhtml")):
                self.assertTrue((OVERLAY / source).is_file())
        for name in ("Regular", "SemiBold"):
            self.assertIn(f"fonts/LivaraSans-{name}.ttf", manifest)
            self.assertIn(f"fonts/LivaraPersian-{name}.ttf", manifest)
        self.assertIn("livara-browser.png", manifest)
        css = (OVERLAY / "livara-glass.css").read_text()
        self.assertIn('font-family: "Livara Sans"', css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("forced-colors", css)
        self.assertNotRegex(css, r"(?:#identity|#tracking-protection|#permissions).*display:\s*none")

    def test_persian_font_fallback_and_user_text_direction(self):
        for filename in ("livara-glass.css", "start.css"):
            css = (OVERLAY / filename).read_text()
            self.assertIn('"Livara Sans", "Livara Persian", "Noto Sans", sans-serif', css)
            for weight in ("Regular", "SemiBold"):
                self.assertIn(f'chrome://browser/content/livara/fonts/LivaraPersian-{weight}.ttf', css)
            self.assertIn('font-family: "Livara Persian"', css)
        tree = ET.parse(OVERLAY / "start.xhtml")
        for identifier in ("search", "pin-label", "notes"):
            node = tree.find(f".//*[@id='{identifier}']")
            self.assertEqual(node.attrib["dir"], "auto")
        self.assertIn("unicode-bidi: plaintext", (OVERLAY / "start.css").read_text())

    def test_tor_action_has_only_fixed_system_launcher_and_literal_flag(self):
        source = (OVERLAY / "LivaraUI.js").read_text()
        self.assertIn('file.initWithPath("/usr/bin/livara-browser")', source)
        self.assertIn('process.runAsync(["--tor"], 1, null, false)', source)
        self.assertNotRegex(source, r"(?:/bin/(?:ba)?sh|runw?\(.*url|eval\()")
        self.assertIn('AboutNewTab.newTabURL = "chrome://browser/content/livara/start.xhtml"', source)
        self.assertIn('"Open Tor Browser"', source)
        self.assertIn('Opening the official Tor Browser as a separate application.', source)
        self.assertNotIn('verifies its connection', source)
        for filename in ("LivaraUI.js", "start.js", "livara-glass.css", "start.css"):
            text = (OVERLAY / filename).read_text()
            self.assertNotIn("LIVARA_TOR_MODE", text)
            self.assertNotIn("torMode", text)
            self.assertNotIn("livara-tor=", text)
            self.assertNotIn("data-tor=", text)


@unittest.skipUnless(NODE, "Node is optional; syntax and chrome logic checks require it")
class BrowserJavaScriptTests(unittest.TestCase):
    def node(self, script):
        result = subprocess.run([NODE, "-e", script], cwd=ROOT, text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_all_chrome_scripts_parse(self):
        for name in ("LivaraUI.js", "LivaraWindowControls.js", "start.js"):
            result = subprocess.run([NODE, "--check", str(OVERLAY / name)],
                                    text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_window_controls_keep_native_actions_and_explicit_physical_sides(self):
        source_path = json.dumps(str(OVERLAY / "LivaraWindowControls.js"))
        self.node(r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert");
function element() {
  return {children: [], attrs: {}, handlers: {}, parent: null, style: {values: {}, setProperty(k,v) {this.values[k]=v;}},
    setAttribute(k,v) {this.attrs[k]=v;}, getAttribute(k) {return this.attrs[k];}, removeAttribute(k) {delete this.attrs[k];},
    get firstChild() {return this.children[0];}, get lastChild() {return this.children.at(-1);},
    remove() {if(this.parent) {this.parent.children=this.parent.children.filter(n=>n!==this);this.parent=null;}},
    append(...nodes) {for(const n of nodes) {n.remove();n.parent=this;this.children.push(n);}},
    prepend(n) {n.remove();n.parent=this;this.children.unshift(n);},
    addEventListener(k,fn) {this.handlers[k]=fn;}, click(e={shiftKey:false}) {this.handlers.click?.(e);}};
}
const root = element(), nav = element(), address = element(), events = new Map();
nav.append(address);
const calls={close:0,min:0,max:0,restore:0,fallbackClose:0};
const window={fullScreen:false,windowState:3,STATE_MAXIMIZED:1,
  BrowserFullScreen() {this.fullScreen=!this.fullScreen;},
  close() {calls.fallbackClose++;},
  getComputedStyle:() => ({direction:window.rtl?"rtl":"ltr"}),
  addEventListener:(k,fn)=>events.set(k,fn), removeEventListener:k=>events.delete(k)};
const originals={
  ".titlebar-close": {click() {calls.close++;}}, // Existing close guard owns closure.
  ".titlebar-min": {click() {calls.min++;}},
  ".titlebar-max": {click() {calls.max++;window.windowState=1;root.attrs.sizemode="maximized";}},
  ".titlebar-restore": {click() {calls.restore++;window.windowState=3;root.attrs.sizemode="normal";}}
};
const document={documentElement:root,getElementById:id=>id==="nav-bar"?nav:null,
  createElementNS:()=>element(),querySelector:selector=>originals[selector]};
const context={window,document,console};
vm.runInNewContext(fs.readFileSync(SOURCE,"utf8"),context);
const api=context.LivaraWindowControls;
const prefs={"controls-style":"traffic-lights","controls-size":18,"controls-symbols":false,
  "controls-side":"left","controls-green":"fullscreen","controls-close":"#ff5f57",
  "controls-minimize":"#febc2e","controls-maximize":"#28c840"};
api.refresh(prefs);
let box=nav.firstChild;assert.equal(box.id,"livara-window-controls");assert.equal(box.attrs.dir,"ltr");
const [close,min,green]=box.children;
assert.equal(close.attrs["aria-label"],"Close window");assert.equal(green.attrs["aria-label"],"Enter fullscreen");
assert.equal(box.style.values["--livara-control-size"],"18px");
close.click();min.click();assert.equal(calls.close,1);assert.equal(calls.min,1);assert.equal(calls.fallbackClose,0);
green.click();assert.equal(window.fullScreen,true);assert.equal(green.attrs["aria-label"],"Exit fullscreen");
green.click();assert.equal(window.fullScreen,false);
green.click({shiftKey:true});assert.equal(calls.max,1);assert.equal(window.windowState,1);
green.click({shiftKey:true});assert.equal(calls.restore,1);assert.equal(window.windowState,3);
api.refresh({...prefs,"controls-green":"maximize"});green.click();assert.equal(calls.max,2);
assert.equal(green.attrs["aria-label"],"Restore window");
window.fullScreen=true;green.click({shiftKey:true});
assert.equal(window.fullScreen,false);assert.equal(calls.restore,2);
api.refresh({...prefs,"controls-side":"right"});assert.equal(nav.lastChild,box);
window.rtl=true;api.refresh(prefs);assert.equal(nav.lastChild,box); // Physical left in an RTL toolbar.
api.refresh({...prefs,"controls-side":"right"});assert.equal(nav.firstChild,box);
api.refresh({...prefs,"controls-style":"default"});assert.equal(nav.children.length,1);
assert.equal(root.attrs["livara-window-controls"],undefined);assert.equal(nav.firstChild,address);
api.refresh(prefs);assert.equal(nav.children.length,2);assert.equal(box.children.length,3);
api.dispose();assert.equal(nav.children.length,1);assert(!events.has("sizemodechange"));
'''.replace("SOURCE", source_path))

    def test_browser_window_control_prefs_bound_size_and_reject_css_injection(self):
        source_path = json.dumps(str(OVERLAY / "LivaraUI.js"))
        self.node(r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert");
function load(overrides) {
  let captured;
  const window={gBrowserInit:{delayedStartupFinished:true},
    matchMedia:()=>({matches:false,addEventListener(){},removeEventListener(){}}),addEventListener(){}};
  const Services={prefs:{getBoolPref:(k,d)=>k.endsWith("toolbar-initialized")?true:(overrides[k]??d),
    getIntPref:(k,d)=>overrides[k]??d,getStringPref:(k,d)=>overrides[k]??d,addObserver(){}},
    obs:{addObserver(){}}};
  const document={documentElement:{setAttribute(){},style:{setProperty(){}}},getElementById:()=>null};
  const context={window,Services,document,console,Components:{classes:{},interfaces:{},results:{}},
    LivaraWindowControls:{refresh:values=>captured=values},
    ChromeUtils:{importESModule:()=>({AboutNewTab:{},CustomizableUI:{getWidget:()=>({})}})}};
  vm.runInNewContext(fs.readFileSync(SOURCE,"utf8"),context);
  return captured;
}
const bad=load({"browser.livara.controls-close":"red;}button{display:none}",
  "browser.livara.controls-side":"bottom","browser.livara.controls-size":999,
  "browser.livara.controls-style":"arbitrary","browser.livara.controls-green":"exec"});
assert.equal(bad["controls-close"],"#ff5f57");assert.equal(bad["controls-size"],22);
assert.equal(bad["controls-side"],"left");assert.equal(bad["controls-style"],"traffic-lights");
assert.equal(bad["controls-green"],"fullscreen");
const good=load({"browser.livara.controls-close":"#12aBcD","browser.livara.controls-size":9,
  "browser.livara.controls-style":"default","browser.livara.controls-side":"right",
  "browser.livara.controls-green":"maximize"});
assert.equal(good["controls-close"],"#12aBcD");assert.equal(good["controls-size"],10);
assert.equal(good["controls-style"],"default");assert.equal(good["controls-side"],"right");
assert.equal(good["controls-green"],"maximize");
'''.replace("SOURCE", source_path))

    def test_onion_cancellation_is_unconditional_even_with_legacy_tor_environment(self):
        source_path = json.dumps(str(OVERLAY / "LivaraUI.js"))
        self.node(r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert");
function load(mode) {
  const observers = new Map(), windowEvents = new Map();
  const window = { matchMedia: () => ({matches: false, addEventListener() {}, removeEventListener() {}}),
    addEventListener: (name, fn) => windowEvents.set(name, fn) };
  const Services = {env: {get: () => mode},
    obs: {addObserver: (o, t) => observers.set(t, o), removeObserver: (o, t) => {
      assert.equal(observers.get(t), o); observers.delete(t);
    }}, prefs: {removeObserver() { throw new Error("not registered yet"); }} };
  const context = {window, Services, Components: {classes: {}, interfaces: {nsIHttpChannel: {}}, results: {NS_ERROR_UNKNOWN_HOST: 23}},
    ChromeUtils: {importESModule: () => ({AboutNewTab: {}})}, console};
  vm.runInNewContext(fs.readFileSync(SOURCE, "utf8"), context);
  return {observer: observers.get("http-on-modify-request"), windowEvents, observers};
}
function canceled(app, host) {
  const calls = [];
  app.observer.observe({ QueryInterface() { return {URI: {asciiHost: host}, cancel(code) { calls.push(code); }}; }});
  return calls;
}
const normal = load("");
for (const host of ["site.onion", "sub.SITE.ONION.", "onion", "site.onion..."]) {
  assert.deepEqual(canceled(normal, host), [23], host);
}
for (const host of ["example.org", "onion.example.org", "notonion", "exampleonion"]) {
  assert.deepEqual(canceled(normal, host), [], host);
}
const tor = load("1");
assert.deepEqual(canceled(tor, "site.onion"), [23]);
// Unloading before delayed startup removes both strong observers without
// trying to unregister a preference observer that was never installed.
normal.windowEvents.get("unload")();
assert.equal(normal.observers.size, 0);
'''.replace("SOURCE", source_path))

    def test_dashboard_link_sanitizer_timer_and_private_storage(self):
        source_path = json.dumps(str(OVERLAY / "start.js"))
        self.node(r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert");
const source = fs.readFileSync(SOURCE, "utf8");
function element() {
  return {value: "", textContent: "", dataset: {}, style: {setProperty() {}}, children: [],
    append(...items) {this.children.push(...items);}, replaceChildren() {this.children=[];},
    setAttribute(name, value) {this[name]=value;}, addEventListener(name, fn) {this[name]=fn;},
    focus() {}, reset() {}, hidden: false};
}
function load(isPrivate) {
  const nodes = new Map(), saved = new Map();
  const get = id => { if(!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); };
  const root = element(), callbacks = {};
  const window = {matchMedia: () => ({matches:false, addEventListener() {}, removeEventListener() {}}),
    addEventListener: (name, fn) => callbacks[name] = fn, confirm: () => true};
  const Services = {env: {get: () => ""}, prefs: {
    getStringPref: (key, def) => saved.has(key) ? saved.get(key) : def,
    getBoolPref: (key, def) => def, getIntPref: (key, def) => def,
    setStringPref: (key, value) => saved.set(key, value), addObserver() {}, removeObserver() {}
  }};
  const document = {documentElement: root, getElementById: get,
    createElementNS: () => element(), activeElement: null};
  const context = {window, document, Services, URL, Intl, Date, console,
    ChromeUtils: {importESModule: () => ({PrivateBrowsingUtils: {isContentWindowPrivate: () => isPrivate}})},
    setInterval: () => 1, clearInterval() {}, setTimeout: () => 1, clearTimeout() {}};
  vm.runInNewContext(source, context);
  return {get, saved, callbacks};
}
const ordinary = load(false);
ordinary.get("notes").value = "private local thought";
ordinary.get("notes").input(); ordinary.get("notes").blur();
const state = JSON.parse(ordinary.saved.get("browser.livara.start.dashboard"));
assert.equal(state.notes, "private local thought");
ordinary.get("pin-label").value="Bad"; ordinary.get("pin-url").value="javascript:alert(1)";
ordinary.get("pin-form").submit({preventDefault() {}});
assert.equal(JSON.parse(ordinary.saved.get("browser.livara.start.dashboard")).pins.length, 2);
ordinary.get("pin-url").value="https://user:pass@example.org/";
ordinary.get("pin-form").submit({preventDefault() {}});
assert.equal(JSON.parse(ordinary.saved.get("browser.livara.start.dashboard")).pins.length, 2);
ordinary.get("pin-label").value="Docs"; ordinary.get("pin-url").value="https://example.org/docs";
ordinary.get("pin-form").submit({preventDefault() {}});
assert.equal(JSON.parse(ordinary.saved.get("browser.livara.start.dashboard")).pins[2].url,"https://example.org/docs");
ordinary.get("focus-minutes").value="999"; ordinary.get("focus-minutes").change();
assert.equal(JSON.parse(ordinary.saved.get("browser.livara.start.dashboard")).timer.length,180);
ordinary.get("timer-toggle").click();
const running = JSON.parse(ordinary.saved.get("browser.livara.start.dashboard")).timer;
assert(running.deadline > Date.now());
ordinary.get("timer-toggle").click();
const paused = JSON.parse(ordinary.saved.get("browser.livara.start.dashboard")).timer;
assert.equal(paused.deadline,0); assert(paused.remaining>0);
const privateApp = load(true);
privateApp.get("notes").value="do not persist"; privateApp.get("notes").input(); privateApp.get("notes").blur();
assert.equal(privateApp.saved.size,0);
assert.equal(privateApp.get("notes-state").textContent,"MEMORY ONLY");
'''.replace("SOURCE", source_path))


if __name__ == "__main__":
    unittest.main()
