/* Livara browser chrome. Compiled into browser.jar; GPL-3.0-or-later. */
/* global ChromeUtils, Components, Services, gBrowserInit, LivaraWindowControls */
"use strict";

var LivaraUI = (() => {
  const PREFIX = "browser.livara.";
  const HTML = "http://www.w3.org/1999/xhtml";
  const { classes: Cc, interfaces: Ci, results: Cr } = Components;
  const accents = Object.freeze({
    purple: "#bd9aff", orchid: "#e2a4ed", ocean: "#95c5ff", rose: "#ffabcf",
  });
  const defaults = Object.freeze({
    glass: true, "reduced-motion": false, density: "comfortable", radius: 20,
    accent: "purple", appearance: "dark", "font-size": 14,
    "controls-style": "traffic-lights", "controls-size": 14,
    "controls-symbols": false, "controls-side": "left",
    "controls-close": "#ff5f57", "controls-minimize": "#febc2e",
    "controls-maximize": "#28c840", "controls-green": "fullscreen",
  });
  const choices = Object.freeze({
    appearance: ["dark", "light", "system"], density: ["comfortable", "compact"],
    "controls-style": ["traffic-lights", "default"], "controls-side": ["left", "right"],
    "controls-green": ["fullscreen", "maximize"],
  });
  const colorPrefs = new Set(["controls-close", "controls-minimize", "controls-maximize"]);
  let panel;
  let status;
  let controls = [];
  let initialized = false;
  let waitingForStartup = false;
  const systemMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  const bounds = name => name === "font-size" ? [12, 18] : name === "controls-size" ? [10, 22] : [8, 28];

  function validString(name, value) {
    if (colorPrefs.has(name)) {
      return /^#[0-9a-fA-F]{6}$/.test(value);
    }
    return name === "accent" ? Object.hasOwn(accents, value) : choices[name]?.includes(value);
  }

  function read(name) {
    const fallback = defaults[name];
    try {
      if (typeof fallback === "boolean") {
        return Services.prefs.getBoolPref(PREFIX + name, fallback);
      }
      if (typeof fallback === "number") {
        const [min, max] = bounds(name);
        return Math.max(min, Math.min(max, Services.prefs.getIntPref(PREFIX + name, fallback)));
      }
      const value = Services.prefs.getStringPref(PREFIX + name, fallback);
      return validString(name, value) ? value : fallback;
    } catch {
      return fallback;
    }
  }

  function write(name, value) {
    if (!Object.hasOwn(defaults, name)) {
      return;
    }
    try {
      if (typeof defaults[name] === "boolean") {
        Services.prefs.setBoolPref(PREFIX + name, Boolean(value));
      } else if (typeof defaults[name] === "number") {
        const [min, max] = bounds(name);
        Services.prefs.setIntPref(PREFIX + name, Math.max(min, Math.min(max, Math.round(Number(value) || defaults[name]))));
      } else if (validString(name, value)) {
        Services.prefs.setStringPref(PREFIX + name, value);
      }
    } catch (error) {
      console.error("Livara appearance preference could not be saved", error);
      if (status) {
        status.textContent = "This preference is managed and cannot be changed.";
      }
    }
  }

  function apply() {
    const root = document.documentElement;
    root.setAttribute("livara-glass", String(read("glass")));
    root.setAttribute("livara-density", read("density"));
    root.setAttribute("livara-reduced-motion", String(read("reduced-motion") || systemMotion.matches));
    root.setAttribute("livara-appearance", read("appearance") === "system" ? (systemDark.matches ? "dark" : "light") : read("appearance"));
    root.style.setProperty("--livara-font-size", read("font-size") + "px");
    root.style.setProperty("--livara-accent", accents[read("accent")]);
    root.style.setProperty("--livara-radius", read("radius") + "px");
    LivaraWindowControls.refresh(Object.fromEntries(Object.keys(defaults)
      .filter(name => name.startsWith("controls-"))
      .map(name => [name, read(name)])));
    for (const [name, input] of controls) {
      if (input.type === "checkbox") {
        input.checked = read(name);
      } else {
        input.value = String(read(name));
      }
    }
    const button = document.getElementById("livara-style-button");
    if (button) {
      button.setAttribute("label", "Livara");
      button.setAttribute("tooltiptext", "Customize Livara Browser");
    }
  }

  const prefObserver = { observe: apply };
  // Block before any direct HTTP(S) channel can connect. The DNS block is also
  // locked at process startup by Livara's autoconfig. No fallback to direct mode.
  const onionObserver = {
    observe(subject) {
      try {
        const channel = subject.QueryInterface(Ci.nsIHttpChannel);
        const host = channel.URI.asciiHost.toLowerCase().replace(/\.+$/, "");
        if (host === "onion" || host.endsWith(".onion")) {
          channel.cancel(Cr.NS_ERROR_UNKNOWN_HOST);
        }
      } catch (error) {
        // This observer only receives HTTP channels; invalid/hostless URIs have
        // no onion host and cannot become a direct connection through this path.
        console.debug("Livara onion channel inspection", error);
      }
    },
  };
  Services.obs.addObserver(onionObserver, "http-on-modify-request");

  function html(tag, attrs = {}, text = "") {
    const node = document.createElementNS(HTML, tag);
    for (const [key, value] of Object.entries(attrs)) {
      node.setAttribute(key, value);
    }
    if (text) {
      node.textContent = text;
    }
    return node;
  }

  function control(container, name, title, description, options) {
    const label = html("label", { class: "livara-setting", for: "livara-" + name });
    const copy = html("span");
    copy.append(html("strong", {}, title), html("small", {}, description));
    let input;
    if (Array.isArray(options)) {
      input = html("select", { id: "livara-" + name });
      for (const [value, title] of options) {
        input.append(html("option", { value }, title));
      }
    } else {
      input = html("input", { id: "livara-" + name, ...options });
    }
    input.addEventListener("change", () => write(name, input.type === "checkbox" ? input.checked : input.value));
    label.append(copy, input);
    container.append(label);
    controls.push([name, input]);
  }

  function launchTor() {
    try {
      const file = Cc["@mozilla.org/file/local;1"].createInstance(Ci.nsIFile);
      file.initWithPath("/usr/bin/livara-browser");
      if (!file.exists() || !file.isExecutable()) {
        throw new Error("Livara's system launcher is not installed");
      }
      const process = Cc["@mozilla.org/process/util;1"].createInstance(Ci.nsIProcess);
      process.init(file);
      process.noShell = true;
      process.runAsync(["--tor"], 1, null, false);
      status.textContent = "Opening the official Tor Browser as a separate application.";
    } catch (error) {
      status.textContent = "Tor Browser could not start: " + error.message;
    }
  }

  function buildPanel() {
    panel = document.createXULElement("panel");
    panel.id = "livara-appearance-panel";
    panel.setAttribute("type", "arrow");
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Customize Livara Browser");
    const content = html("section", { class: "livara-panel" });
    const header = html("header", { class: "livara-panel-heading" });
    header.append(html("img", { src: "chrome://browser/content/livara/livara-browser.png", alt: "", width: "42", height: "42" }));
    const title = html("div");
    title.append(html("h1", {}, "Make it Livara."), html("p", {}, "Your browser. Your atmosphere."));
    header.append(title);
    content.append(header);
    control(content, "glass", "Liquid glass", "Translucent chrome with luminous edges", { type: "checkbox" });
    control(content, "reduced-motion", "Reduce motion", "Also follows your system motion preference", { type: "checkbox" });
    control(content, "appearance", "Theme", "Dark, light, or your system preference", [["dark", "Dark"], ["light", "Light"], ["system", "System"]]);
    control(content, "font-size", "Chrome text size", "Adjust browser controls: 12 to 18 pixels", { type: "range", min: "12", max: "18", step: "1", "aria-label": "Browser chrome text size in pixels" });
    control(content, "density", "Spacing", "Keep vertical tabs spacious or compact", [["comfortable", "Comfortable"], ["compact", "Compact"]]);
    control(content, "accent", "Accent", "A coordinated color across Livara chrome", Object.keys(accents).map(key => [key, key[0].toUpperCase() + key.slice(1)]));
    control(content, "radius", "Corner radius", "Shape your chrome: 8 to 28 pixels", { type: "range", min: "8", max: "28", step: "1", "aria-label": "Corner radius in pixels" });
    const windowHeading = html("h2", {}, "Window controls");
    content.append(windowHeading);
    control(content, "controls-style", "Control style", "Livara traffic lights or the browser's standard controls", [["traffic-lights", "Traffic lights"], ["default", "Standard"]]);
    control(content, "controls-side", "Physical side", "Applies to this browser, including right-to-left interfaces", [["left", "Left"], ["right", "Right"]]);
    control(content, "controls-size", "Button size", "Traffic-light diameter: 10 to 22 pixels", { type: "range", min: "10", max: "22", step: "1", "aria-label": "Window control diameter in pixels" });
    control(content, "controls-symbols", "Always show symbols", "Symbols also appear on hover or keyboard focus", { type: "checkbox" });
    control(content, "controls-green", "Green button", "Shift-click maximizes or restores; F11 toggles fullscreen", [["fullscreen", "Fullscreen"], ["maximize", "Maximize"]]);
    for (const [name, title] of [["close", "Close color"], ["minimize", "Minimize color"], ["maximize", "Green-control color"]]) {
      control(content, "controls-" + name, title, "Choose your own traffic-light color", { type: "color", "aria-label": title });
    }
    const actions = html("div", { class: "livara-panel-actions" });
    const restore = html("button", { type: "button" }, "Reset appearance");
    restore.addEventListener("click", () => {
      for (const name of Object.keys(defaults)) {
        if (!Services.prefs.prefIsLocked(PREFIX + name)) {
          Services.prefs.clearUserPref(PREFIX + name);
        }
      }
    });
    actions.append(restore);
    const tools = [
      ["Search open tabs", () => window.gURLBar.search("% ")],
      ["Move tab sidebar", () => Services.prefs.setBoolPref("zen.tabs.vertical.right-side", !Services.prefs.getBoolPref("zen.tabs.vertical.right-side", false))],
      ["Customize toolbar", () => window.gCustomizeMode.enter()],
      ["Browser settings", () => window.openPreferences()],
      ["Toggle fullscreen (F11)", () => window.BrowserFullScreen()],
    ];
    for (const [title, run] of tools) {
      const button = html("button", { type: "button" }, title);
      button.addEventListener("click", () => {
        panel.hidePopup();
        run();
      });
      actions.append(button);
    }
    const reader = html("button", { type: "button" }, "Reader view");
    const readerButton = document.getElementById("reader-mode-button");
    reader.disabled = !readerButton || (readerButton.hidden && !readerButton.hasAttribute("readeractive"));
    reader.addEventListener("click", () => {
      panel.hidePopup();
      document.getElementById("reader-mode-button")?.click();
    });
    reader.id = "livara-reader-action";
    actions.append(reader);
    content.append(actions);
    const network = html("section", { class: "livara-network" });
    network.append(html("strong", { class: "livara-mode" }, "Normal session · onion requests blocked"));
    network.append(html("p", {}, "Open the official, unchanged Tor Browser as a separate application. Livara Browser keeps its normal connection and blocks onion addresses."));
    const tor = html("button", { type: "button", class: "livara-tor-launch" }, "Open Tor Browser");
    tor.addEventListener("click", launchTor);
    network.append(tor);
    status = html("p", { role: "status", "aria-live": "polite", class: "livara-status" });
    network.append(status);
    content.append(network);
    panel.append(content);
    document.getElementById("mainPopupSet").append(panel);
    apply();
  }

  function openPanel(event) {
    if (!panel) {
      buildPanel();
    }
    const anchor = document.getElementById("livara-style-button");
    if (anchor) {
      const readerButton = document.getElementById("reader-mode-button");
      document.getElementById("livara-reader-action").disabled = !readerButton || (readerButton.hidden && !readerButton.hasAttribute("readeractive"));
      panel.openPopup(anchor, "after_end", 0, 0, false, false, event);
    }
  }

  function init() {
    if (initialized) {
      return;
    }
    initialized = true;
    const { CustomizableUI } = ChromeUtils.importESModule("moz-src:///browser/components/customizableui/CustomizableUI.sys.mjs");
    if (CustomizableUI.getWidget("livara-style-button")?.provider !== CustomizableUI.PROVIDER_API) {
      CustomizableUI.createWidget({
        id: "livara-style-button", type: "button", defaultArea: "nav-bar",
        label: "Livara", tooltiptext: "Customize Livara Browser",
        onCommand(event) {
          event.target.ownerDocument.defaultView.LivaraUI.openPanel(event);
        },
      });
    }
    if (!Services.prefs.getBoolPref(PREFIX + "toolbar-initialized", false)) {
      if (!CustomizableUI.getPlacementOfWidget("livara-style-button")) {
        CustomizableUI.addWidgetToArea("livara-style-button", "nav-bar");
      }
      Services.prefs.setBoolPref(PREFIX + "toolbar-initialized", true);
    }
    Services.prefs.addObserver(PREFIX, prefObserver);
    systemMotion.addEventListener("change", apply);
    systemDark.addEventListener("change", apply);
    apply();
  }

  const startupObserver = {
    observe(subject) {
      if (subject === window) {
        Services.obs.removeObserver(startupObserver, "browser-delayed-startup-finished");
        waitingForStartup = false;
        init();
      }
    },
  };
  if (window.gBrowserInit?.delayedStartupFinished) {
    init();
  } else {
    waitingForStartup = true;
    Services.obs.addObserver(startupObserver, "browser-delayed-startup-finished");
  }
  try {
    const { AboutNewTab } = ChromeUtils.importESModule("resource:///modules/AboutNewTab.sys.mjs");
    AboutNewTab.newTabURL = "chrome://browser/content/livara/start.xhtml";
  } catch (error) {
    console.error("Livara start page could not be registered", error);
  }
  window.addEventListener("unload", () => {
    Services.obs.removeObserver(onionObserver, "http-on-modify-request");
    if (waitingForStartup) {
      Services.obs.removeObserver(startupObserver, "browser-delayed-startup-finished");
    }
    if (initialized) {
      Services.prefs.removeObserver(PREFIX, prefObserver);
    }
    systemMotion.removeEventListener("change", apply);
    systemDark.removeEventListener("change", apply);
  }, { once: true });
  return Object.freeze({ openPanel });
})();
