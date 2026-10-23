/* Livara browser window controls; GPL-3.0-or-later. */
/* global Services */
"use strict";

var LivaraWindowControls = (() => {
  const HTML = "http://www.w3.org/1999/xhtml";
  let box;
  let values;
  const buttons = new Map();
  let listening = false;

  function stockAction(selector, fallback) {
    const original = document.querySelector(selector);
    if (original) {
      original.click(); // Keep the browser's existing close guards/native actions.
    } else {
      fallback();
    }
  }

  function fullscreen() {
    if (typeof window.BrowserFullScreen === "function") {
      window.BrowserFullScreen();
    } else {
      window.fullScreen = !window.fullScreen;
    }
  }

  function maximized() {
    return document.documentElement.getAttribute("sizemode") === "maximized" ||
      (typeof window.STATE_MAXIMIZED === "number" && window.windowState === window.STATE_MAXIMIZED);
  }

  function maximize() {
    if (window.fullScreen) {
      fullscreen();
    }
    if (maximized()) {
      stockAction(".titlebar-restore", () => window.restore());
    } else {
      stockAction(".titlebar-max", () => window.maximize());
    }
  }

  function green(event) {
    if (event.shiftKey || values["controls-green"] === "maximize") {
      maximize();
    } else {
      fullscreen();
    }
    updateState();
  }

  function updateState() {
    if (!box) {
      return;
    }
    const greenButton = buttons.get("maximize");
    const isFullscreen = values["controls-green"] === "fullscreen";
    const active = isFullscreen ? window.fullScreen : maximized();
    const title = isFullscreen ? (active ? "Exit fullscreen" : "Enter fullscreen") :
      (active ? "Restore window" : "Maximize window");
    greenButton.setAttribute("aria-label", title);
    greenButton.setAttribute("title", title + " · Shift-click to maximize or restore · F11 toggles fullscreen");
    greenButton.firstChild.textContent = isFullscreen ? (active ? "↙" : "↗") : (active ? "◇" : "+");
  }

  function create() {
    box = document.createElementNS(HTML, "div");
    box.id = "livara-window-controls";
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", "Window controls");
    box.setAttribute("dir", "ltr");
    const actions = [
      ["close", "Close window", "×", () => stockAction(".titlebar-close", () => {
        if (typeof window.BrowserTryToCloseWindow === "function") {
          window.BrowserTryToCloseWindow();
        } else {
          window.close();
        }
      })],
      ["minimize", "Minimize window", "−", () => stockAction(".titlebar-min", () => window.minimize())],
      ["maximize", "Enter fullscreen", "↗", green],
    ];
    for (const [action, title, symbol, run] of actions) {
      const button = document.createElementNS(HTML, "button");
      button.className = "livara-window-control livara-" + action;
      button.setAttribute("type", "button");
      button.setAttribute("title", title);
      button.setAttribute("aria-label", title);
      const label = document.createElementNS(HTML, "span");
      label.textContent = symbol;
      label.setAttribute("aria-hidden", "true");
      button.append(label);
      button.addEventListener("click", run);
      box.append(button);
      buttons.set(action, button);
    }
    if (!listening) {
      window.addEventListener("sizemodechange", updateState);
      window.addEventListener("fullscreen", updateState);
      listening = true;
    }
  }

  function refresh(prefs) {
    values = prefs;
    const root = document.documentElement;
    const nav = document.getElementById("nav-bar");
    if (!nav) {
      return;
    }
    if (values["controls-style"] !== "traffic-lights") {
      root.removeAttribute("livara-window-controls");
      box?.remove();
      return;
    }
    if (!box) {
      create();
    }
    // The XUL toolbar follows locale direction; physical left/right stays explicit.
    const rtl = window.getComputedStyle(nav).direction === "rtl";
    const leading = (values["controls-side"] === "left") !== rtl;
    if (leading && nav.firstChild !== box) {
      nav.prepend(box);
    } else if (!leading && nav.lastChild !== box) {
      nav.append(box);
    }
    root.setAttribute("livara-window-controls", "traffic-lights");
    box.setAttribute("symbols", String(values["controls-symbols"]));
    box.style.setProperty("--livara-control-size", values["controls-size"] + "px");
    for (const action of ["close", "minimize", "maximize"]) {
      box.style.setProperty("--livara-control-" + action, values["controls-" + action]);
    }
    updateState();
  }

  function dispose() {
    document.documentElement.removeAttribute("livara-window-controls");
    box?.remove();
    if (listening) {
      window.removeEventListener("sizemodechange", updateState);
      window.removeEventListener("fullscreen", updateState);
      listening = false;
    }
  }

  window.addEventListener("unload", dispose, { once: true });
  return Object.freeze({ refresh, dispose });
})();
