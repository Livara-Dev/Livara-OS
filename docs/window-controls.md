# Window controls and motion

Livara's native Settings, Center, Task Manager, Studio, GPU Settings and Chat use accessible red, yellow and green window controls. Settings → Personalize lets you choose traffic lights or standard controls, the physical left or right edge, a 10–22 px diameter, visible symbols, three individual colors and the green-button action. The default colors are `#ff5f57`, `#febc2e` and `#28c840`.

In those Livara apps, green enters or leaves **fullscreen** by default. You can instead choose maximize/restore. **Shift-click green** always maximizes or restores, and **F11** toggles fullscreen. Red follows each app's normal close-request guard; yellow minimizes. Keyboard focus, action labels and hover symbols remain available. The controls keep the same physical edge in right-to-left interfaces.

GTK3/GTK4 apps also receive the selected traffic-light styling through a marked section in `~/.config/gtk-3.0/gtk.css` and `gtk-4.0/gtk.css`. Existing CSS outside that section is preserved. Selecting standard controls removes Livara's section. Other applications retain their own button actions: a green GTK stock maximize button still maximizes. Reopen apps that retain an older stylesheet loaded at startup. Apps using their own decorations or refusing user CSS can differ.

The desktop package now runs **Livara Session Appearance** at GNOME login for both installed and live accounts. This installs the user's selected GTK controls even when the account has never opened Settings; older versions only generated that CSS when a preference was changed or the live-session defaults were applied. After updating, run `livara-session-refresh` as your ordinary desktop user to refresh immediately, then reopen existing GTK applications. This refresh does not reset settings or change the user's CSS outside Livara's managed section. A linked, oversized or nonregular stylesheet is preserved and reported instead of overwritten.

The GNOME desktop extension implements separate opening/closing effects: Zoom, Lift, Fade or Off, with an 80–600 ms duration. Effects follow reduced motion, stop when windows disappear and do not change the window manager's fullscreen/maximize actions. Native window controls use bounded hover transitions, also respecting reduced motion.

Livara Browser and Livara Code draw their own controls. Their app appearance settings are independent of GTK settings. In **Livara Browser → Livara → Window controls**, choose traffic lights/standard, side, size, symbols, colors and fullscreen/maximize. Green defaults to fullscreen; Shift-click maximizes/restores; the browser's F11 shortcut remains available. Standard style restores the upstream native browser controls and their actions. Livara Code offers the equivalent preferences under `livara.windowControls`, including the green action; its default is also fullscreen, with Shift-click for maximize/restore and F11 for fullscreen. Standard editor controls retain their original maximize/restore behavior. Its upstream native titlebar option remains available after an application restart. See the [editor settings table](code-editor.md#window-controls).

The separate **official Tor Browser is unchanged**. These custom controls, fonts, browser preferences and style resources are not installed into its bundle or profile.

Browser popup windows with a hidden navigation toolbar retain their stock titlebar controls, styled with the selected traffic-light colors, rather than hiding the only usable controls. These stock popup buttons keep their native maximize/restore action. Code's source controller now rebinds replaced titlebar controls after workbench layout changes and releases old listeners. That controller change requires a Code build; updating only an existing Code bundle's CSS does not install new TypeScript behavior.

Code's Linux startup default is also applied in the shared window configuration
used by its main process. A renderer-only default arrives too late for the first
native window and previously left an unstyled native overlay in place. Explicit
native, custom and hidden control choices remain respected. The separate Code
DEB in the desktop update ships the compiled startup and lifecycle fixes; its
release gate tests the real default window and native button behavior.

Code's Linux default also selects custom controls in the shared platform accessor before Electron creates the first window. Registering this default only in the renderer was too late: a fresh profile could launch with native overlay controls, which the Livara controller intentionally leaves alone. The source patch changes the Linux startup default and matching configuration schema together; an explicit native/hidden control choice or native titlebar remains respected. The release runtime test starts with a fresh profile and checks the actual controls, native actions and rebinding behavior.

The native GTK4 implementation was exercised with GTK 4.14.5 and libadwaita 1.5, including actual fullscreen, F11, maximize/restore, live preferences, RTL placement and close guards. The GTK3 stylesheet parsed without errors in GTK 3.24.49 at the minimum, default and maximum sizes. Livara Code's emitted controller/contribution and CSS were exercised in the already source-built Electron app, including the real fullscreen command, live preferences and native button actions; the complete workbench was not rebuilt after those changes. GTK CSS/storage helpers and browser control actions/preferences have automated checks. The normal Gecko source fork has not been compiled in this authoring environment; its controls are source-validated and require the local full browser build for runtime qualification.

For desktop update 0.1.1, the complete Code workbench was subsequently rebuilt
from source. Its real default controls, fullscreen/F11, recreated-node keyboard
bindings, maximize/restore and minimize all passed under Xvfb/Openbox with the
sandbox enabled. See the [current qualification](desktop-update-qualification.json)
and its linked hosted build for this newer evidence.
