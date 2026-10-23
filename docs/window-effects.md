# Window controls and transitions

Livara Settings provides the original traffic-light control style, native controls, button size, symbols, individual colors, button placement, green-button behavior in Livara applications, and window transition style and speed. The accessible close, minimize and maximize/fullscreen actions are retained. Controls are implemented by the native application helper and managed GTK styling; GNOME Shell CSS does not redraw application-owned titlebars.

In Livara's own applications, the green button defaults to true fullscreen. Its setting can choose maximize instead. Shift+green maximizes or restores, and F11 toggles fullscreen. Stock GTK decorations and application-owned titlebars can retain their native maximize behavior. Browser and editor titlebars depend on the controls those applications expose.

## Real compositor transitions

The GNOME 46 extension animates the original window actor using finite Clutter property transitions:

| Setting | Opening | Closing |
| --- | --- | --- |
| Zoom | Centered 92% scale and fade into the full window | Fade while scaling to 94% |
| Lift | Rise 18 pixels while fading in | Move down 12 pixels while fading out |
| Fade | Opacity only | Opacity only |
| Off | Complete normal-window opening immediately | Complete normal-window closing immediately |

Duration is adjustable from **80–600 ms**, with **220 ms** as the default. At most twelve window actors animate concurrently; additional windows complete immediately. Animation uses the existing actor, without screen captures, window clones, extra shaders, recurring JavaScript timers or per-frame JavaScript allocation.

Only ordinary, non-transient application windows receive these transitions. Dialogs, attached dialogs, popups, fullscreen windows and native workspace/minimize/maximize transitions retain GNOME's handling. GNOME's own actor eligibility and skipped-actor checks are preserved. The effects are original macOS-inspired zoom/fade/lift behavior, not Apple's proprietary animation implementation or a claimed exact Genie effect.

Turning off system animations, including through Livara's Efficient rendering action, prevents these transitions. Opening Overview, locking the session, changing the animation style, cancelling an effect or disabling the extension finishes pending operations and restores actor properties. Glass transparency is independent of window animation settings.

## Window-manager completion and compatibility

GNOME 46 binds its map/destroy signal callbacks in the WindowManager constructor. Replacing a method on the object afterward would not replace those bound callbacks. Livara therefore blocks only the first standard handlers while installed, connects its handlers, and retains the original methods for native window bookkeeping.

For an ordinary window, the original map/destroy method runs with a temporarily scoped animation predicate and completion method. In GNOME 46.2 the no-animation completion happens synchronously, before the map method's first `await`. Native notify/dimming/disconnection bookkeeping runs normally, while Livara defers the operation's completion until its transition stops. Other actors continue through the original predicate and completion functions. Property descriptors are restored immediately after this synchronous handoff.

A pending operation is marked finished before cancelling its transitions. Reentrant `onStopped`, compositor cancellation, actor destruction and extension shutdown therefore complete that operation once. Disabling restores the original signal handlers with balanced block/unblock calls. Missing handlers, incompatible standard methods or non-writable completion methods leave native behavior active. Use a single window-animation extension at a time; third-party extensions that also replace these private window-manager handlers are outside this integration's supported combination.

The API was checked against these pinned upstream sources:

- [GNOME Shell 46.2 windowManager.js](https://gitlab.gnome.org/GNOME/gnome-shell/-/blob/46.2/js/ui/windowManager.js): constructor signal bindings; `_shouldAnimateActor`; `_mapWindow`/`_destroyWindow`; corresponding completion methods; `kill-window-effects`.
- [GJS 1.80.2 GObject overrides](https://gitlab.gnome.org/GNOME/gjs/-/blob/1.80.2/modules/core/overrides/GObject.js): `signal_handler_find(instance, {signalId: 'map'})`, handler block/unblock and connected checks.

## Settings schema

The new keys in `org.livara.desktop` are:

```text
window-button-style          traffic-lights | default
window-button-size           10..22 pixels
window-button-symbols        true | false
window-close-color           #RRGGBB
window-minimize-color        #RRGGBB
window-maximize-color        #RRGGBB
window-green-action          fullscreen | maximize
window-animation-style       zoom | lift | fade | off
window-animation-duration    80..600 milliseconds
```

Colors are validated by the settings/backend and styling helper before use. The existing `org.gnome.desktop.wm.preferences button-layout` preference controls left/right placement. Global `org.gnome.desktop.interface enable-animations` controls reduced motion.

## Validation

`tests/test_window_effects.py` is included in normal Python unittest discovery and `make check`. Its Node fixtures execute the production `windowEffects.js` state machine and check styles, native bookkeeping, exact-once completion, stop/cancel/disable, original handler restoration, destroyed actors, reduced motion, lock/Overview, skipped window types, API/transition failures, actor scoping and concurrency/duration limits. Schema choices and bounds are checked too.

An actual Ubuntu 24.04 GJS process also verified signal lookup/block/unblock/is-connected, replacement and restoration of an inherited GI method, and SpiderMonkey module parsing for both extension modules.

The production extension then passed an actual **GNOME Shell 46.0 nested Wayland compositor** run under Xvfb: all three styles opened and closed real GTK windows, each native map/destroy operation completed once, reduced motion skipped Livara transitions, and disabling mid-map drained the operation and restored working native handlers. The test used an isolated Gio memory settings backend and GNOME's test-only `force_animations` switch to exercise motion on software rendering. Production retains GNOME's normal animation inhibition on software renderers. The live desktop reported two compositor blur effects and two reflective rims at radius 18, with 622 observed Shell actors.

The [qualification record](window-effects-qualification.json) contains the real operation counters. [Desktop screenshots](screenshots/desktop-manifest.json) were captured directly from that compositor at 1440×900 with installed Livara assets/defaults and Ubuntu Dock. They show a minimal source preview, not the full security-tool catalog or an ISO boot. Physical session services and hardware were not tested; a rebuilt Livara ISO remains unqualified.
