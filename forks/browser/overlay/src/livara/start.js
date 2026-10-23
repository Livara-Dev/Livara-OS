/* Local Livara start dashboard. No telemetry, fetches, or remote assets. */
/* global ChromeUtils, Services */
"use strict";

(() => {
  const PREF = "browser.livara.start.dashboard";
  const PREFIX = "browser.livara.";
  const $ = id => document.getElementById(id);
  const root = document.documentElement;
  const accents = { purple: "#bd9aff", orchid: "#e2a4ed", ocean: "#95c5ff", rose: "#ffabcf" };
  const initial = () => ({
    pins: [{ name: "Livara Chat", url: "https://chat.livara.org/" }, { name: "DuckDuckGo", url: "https://duckduckgo.com/" }],
    notes: "", quiet: false, timer: { remaining: 25 * 60000, deadline: 0, length: 25 },
  });
  let privateWindow = true;
  try {
    const { PrivateBrowsingUtils } = ChromeUtils.importESModule("resource://gre/modules/PrivateBrowsingUtils.sys.mjs");
    privateWindow = PrivateBrowsingUtils.isContentWindowPrivate(window);
  } catch {
    // If this context cannot establish privacy state, keep all dashboard data
    // in memory rather than risk writing private-window notes to the profile.
  }
  let memory = initial();
  let notesTimeout;
  let notesDirty = false;
  let formOpen = false;
  const systemMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

  function safeLink(value) {
    try {
      const url = new URL(String(value));
      if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || !url.hostname) {
        return null;
      }
      return url.href.slice(0, 2048);
    } catch {
      return null;
    }
  }

  function sanitize(value) {
    const fallback = initial();
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      return fallback;
    }
    const pins = Array.isArray(value.pins) ? value.pins.slice(0, 24).flatMap(pin => {
      if (!pin || typeof pin !== "object") {
        return [];
      }
      const url = safeLink(pin.url);
      const name = String(pin.name || "Shortcut").slice(0, 40);
      return url ? [{ name, url }] : [];
    }) : fallback.pins;
    const raw = value.timer && typeof value.timer === "object" ? value.timer : {};
    const finite = (number, fallback, min, max) => Number.isFinite(number) ? Math.max(min, Math.min(max, number)) : fallback;
    return {
      pins, notes: typeof value.notes === "string" ? value.notes.slice(0, 20000) : "",
      quiet: value.quiet === true,
      timer: {
        length: Math.round(finite(raw.length, 25, 1, 180)),
        remaining: finite(raw.remaining, 25 * 60000, 0, 180 * 60000),
        deadline: finite(raw.deadline, 0, 0, Date.now() + 180 * 60000),
      },
    };
  }

  function read() {
    if (privateWindow) {
      return sanitize(memory);
    }
    try {
      return sanitize(JSON.parse(Services.prefs.getStringPref(PREF, "null")));
    } catch {
      return initial();
    }
  }

  function update(change) {
    const state = read();
    change(state);
    const clean = sanitize(state);
    if (privateWindow) {
      memory = clean;
      render();
      return true;
    }
    try {
      Services.prefs.setStringPref(PREF, JSON.stringify(clean));
      return true;
    } catch {
      $("dashboard-status").textContent = "Profile storage is unavailable. Your changes could not be saved.";
      return false;
    }
  }

  function appearance() {
    const bool = (key, fallback) => Services.prefs.getBoolPref(PREFIX + key, fallback);
    const string = (key, fallback) => Services.prefs.getStringPref(PREFIX + key, fallback);
    const selected = string("appearance", "dark");
    root.dataset.appearance = selected === "system" ? (systemDark.matches ? "dark" : "light") : selected === "light" ? "light" : "dark";
    root.dataset.glass = String(bool("glass", true));
    root.dataset.reducedMotion = String(bool("reduced-motion", false) || systemMotion.matches);
    root.style.setProperty("--accent", accents[string("accent", "purple")] || accents.purple);
    root.style.setProperty("--radius", Math.max(8, Math.min(28, Services.prefs.getIntPref(PREFIX + "radius", 20))) + "px");
    const size = Math.max(12, Math.min(18, Services.prefs.getIntPref(PREFIX + "font-size", 14)));
    root.style.fontSize = size + "px";
    $("network-mode").textContent = "Normal session · onion requests blocked";
  }

  function element(tag, text = "") {
    const node = document.createElementNS("http://www.w3.org/1999/xhtml", tag);
    node.textContent = text;
    return node;
  }

  function renderPins(pins) {
    const list = $("pins");
    list.replaceChildren();
    pins.forEach((pin, index) => {
      const row = element("div");
      row.className = "pin";
      const link = element("a");
      link.href = pin.url;
      link.title = pin.url;
      link.rel = "noreferrer noopener";
      const symbol = element("span", pin.name[0].toUpperCase());
      symbol.className = "pin-symbol";
      const name = element("span", pin.name);
      name.className = "pin-title";
      link.append(symbol, name);
      const remove = element("button", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", "Remove " + pin.name + " shortcut");
      remove.addEventListener("click", () => {
        update(state => {
          // Match both fields so stale dashboard tabs cannot remove a different
          // shortcut after another tab edits the list.
          const found = state.pins.findIndex(item => item.name === pin.name && item.url === pin.url);
          if (found >= 0) {
            state.pins.splice(found, 1);
          }
        });
      });
      row.append(link, remove);
      list.append(row);
    });
  }

  function remaining(timer) {
    return timer.deadline ? Math.max(0, timer.deadline - Date.now()) : timer.remaining;
  }

  function renderTimer() {
    const timer = read().timer;
    const milliseconds = remaining(timer);
    const seconds = Math.ceil(milliseconds / 1000);
    $("timer").textContent = String(Math.floor(seconds / 60)).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0");
    $("timer-toggle").textContent = timer.deadline && milliseconds > 0 ? "Pause focus" : milliseconds <= 0 ? "Start again" : "Start focus";
    $("timer-status").textContent = milliseconds <= 0 ? "Focus complete. Take a moment for yourself." : timer.deadline ? "Keep a little space for this one thing." : "One thing at a time.";
    $("focus-minutes").disabled = Boolean(timer.deadline && milliseconds > 0);
    if (document.activeElement !== $("focus-minutes")) {
      $("focus-minutes").value = String(timer.length);
    }
  }

  function render() {
    const state = read();
    renderPins(state.pins);
    root.dataset.quiet = String(state.quiet);
    $("focus-view").setAttribute("aria-pressed", String(state.quiet));
    $("focus-view").textContent = state.quiet ? "Show dashboard" : "Quiet view";
    if (!notesDirty && document.activeElement !== $("notes")) {
      $("notes").value = state.notes;
    }
    $("notes-count").textContent = $("notes").value.length + " / 20000";
    renderTimer();
  }

  function saveNotes() {
    clearTimeout(notesTimeout);
    if (!notesDirty) {
      return;
    }
    const value = $("notes").value.slice(0, 20000);
    if (update(state => { state.notes = value; })) {
      notesDirty = false;
      $("notes-state").textContent = privateWindow ? "MEMORY ONLY" : "SAVED LOCALLY";
    } else {
      $("notes-state").textContent = "NOT SAVED";
    }
  }

  function showPinForm(show) {
    formOpen = show;
    $("pin-form").hidden = !show;
    $("add-pin").setAttribute("aria-expanded", String(show));
    if (show) {
      $("pin-label").focus();
    }
  }

  $("add-pin").addEventListener("click", () => showPinForm(!formOpen));
  $("cancel-pin").addEventListener("click", () => showPinForm(false));
  $("pin-form").addEventListener("submit", event => {
    event.preventDefault();
    const url = safeLink($("pin-url").value.trim());
    const name = $("pin-label").value.trim().slice(0, 40);
    if (!url || !name) {
      $("dashboard-status").textContent = "Use a name and an http:// or https:// address without a username or password.";
      return;
    }
    if (read().pins.length >= 24) {
      $("dashboard-status").textContent = "You can keep up to 24 shortcuts. Remove one to add another.";
      return;
    }
    if (update(state => { state.pins.push({ name, url }); })) {
      $("pin-form").reset();
      showPinForm(false);
      $("dashboard-status").textContent = "Shortcut saved.";
    }
  });
  $("notes").addEventListener("input", () => {
    notesDirty = true;
    $("notes-count").textContent = $("notes").value.length + " / 20000";
    $("notes-state").textContent = "SAVING…";
    clearTimeout(notesTimeout);
    notesTimeout = setTimeout(saveNotes, 400);
  });
  $("notes").addEventListener("blur", saveNotes);
  $("clear-notes").addEventListener("click", () => {
    if ($("notes").value && window.confirm("Clear the notes saved in this browser profile?")) {
      $("notes").value = "";
      notesDirty = true;
      saveNotes();
    }
  });
  $("focus-view").addEventListener("click", () => update(state => { state.quiet = !state.quiet; }));
  $("timer-toggle").addEventListener("click", () => update(state => {
    const value = remaining(state.timer);
    if (state.timer.deadline && value > 0) {
      state.timer.remaining = value;
      state.timer.deadline = 0;
    } else {
      state.timer.remaining = value > 0 ? value : state.timer.length * 60000;
      state.timer.deadline = Date.now() + state.timer.remaining;
    }
  }));
  $("timer-reset").addEventListener("click", () => update(state => {
    state.timer.remaining = state.timer.length * 60000;
    state.timer.deadline = 0;
  }));
  $("focus-minutes").addEventListener("change", () => update(state => {
    state.timer.length = Math.max(1, Math.min(180, Math.round(Number($("focus-minutes").value) || 25)));
    state.timer.remaining = state.timer.length * 60000;
    state.timer.deadline = 0;
  }));
  $("search-form").addEventListener("submit", event => {
    if (!$("search").value.trim()) {
      event.preventDefault();
    }
  });

  function clock() {
    const now = new Date();
    $("clock").textContent = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(now);
    $("clock").dateTime = now.toISOString();
    $("date").textContent = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(now);
  }
  const observer = { observe(subject, topic, name) {
    if (name === PREF) {
      render();
    } else {
      appearance();
    }
  } };
  Services.prefs.addObserver(PREFIX, observer);
  systemMotion.addEventListener("change", appearance);
  systemDark.addEventListener("change", appearance);
  const timerId = setInterval(() => { clock(); renderTimer(); }, 1000);
  window.addEventListener("pagehide", () => {
    saveNotes();
    clearInterval(timerId);
    Services.prefs.removeObserver(PREFIX, observer);
    systemMotion.removeEventListener("change", appearance);
    systemDark.removeEventListener("change", appearance);
  }, { once: true });
  $("notes-state").textContent = privateWindow ? "MEMORY ONLY" : "LOCAL";
  appearance();
  render();
  clock();
})();
