# Make Livara yours

Livara Settings has a searchable catalog of **94 real desktop preferences**, organized into Look, Windows, Dock, Type, Spaces, Focus, Input and Display. Availability comes from the installed GNOME schemas; missing or managed settings are disabled. Dependent controls explain the prerequisite that currently keeps them inactive, such as manual Night Light times while automatic scheduling is on. Shell glass, window effects and dock controls also report whether their desktop extension is actually loaded, disabled, incompatible or failed, instead of treating an installed schema as proof that its service works. A saved preference can require compatible hardware or a running desktop service to have an effect.

Press **Ctrl+F** to search across sections. Changes apply as you explore; the preview reflects your look, and **Try a window** opens a real window for testing controls and fullscreen. Save, rename or restore a named look from the Look section; deleting one offers Undo. Each section has its own reset action.

The separate **App icons** page changes launcher/dock icons for default and installed apps. Choose a local image per app, search customized launchers and restore their original icons. These choices remain independent of desktop accents and appearance presets. See [App icons](app-icons.md) for image formats, storage and application-specific limits.

| Area | Customization |
| --- | --- |
| Look | Dark/light, eight accents, four Livara wallpapers, your own wallpaper, image fit, glass and blur |
| Windows | Traffic-light controls, fullscreen/maximize action, opening/closing effects, focus behavior, placement, dialogs, titlebar actions and tiling |
| Dock | Edge, icon size, floating/panel layout, hiding, window avoidance, trash and mounted media |
| Type | Interface, document, monospace and title fonts; text scale, smoothing, hinting and subpixel order |
| Spaces | Workspace behavior, names/count, multi-display workspace behavior, clock details and battery percentage |
| Focus | Notification banners, lock-screen notifications, recent-file/application history and idle/lock delays |
| Input | Installed cursor themes, pointer size/location, text cursor, repeat timing, mouse response and supported touchpad features |
| Display | Night Light, temperature and automatic/manual scheduling |

Choose a local **PNG, JPEG or WebP** as your wallpaper. Livara validates the file, permits up to 64 MiB/100 megapixels, and updates the light, dark and lock-screen background preferences. Accent or appearance changes preserve the chosen image. Selecting a bundled wallpaper or clearing the custom image returns to the selected Livara background. Files stay in their original location; a saved preset records the path rather than copying the image. Keep that file available when restoring the preset.

Font pickers use installed font families and real Pango font descriptions, including size and style. Livara's Latin and Persian families remain available alongside multilingual system fonts. Each application can keep its own font preferences; browser/editor appearance and the separate official Tor Browser follow their own rules.

Save a named look to retain your visual and layout choices, then apply, rename or delete it. The default snapshot covers appearance, fonts, dock, workspaces, visual window controls and pointer appearance. It does **not** silently capture mouse handedness, touchpad disabling, keyboard repeat, focus/raise behavior, Night Light, notifications, history or screen-lock settings. Applying a preset never re-enables desktop motion when animations are off. Changing those preferences directly remains available. Choosing Full Glass explicitly restores glass, the default blur and animations together; Efficient rendering disables all three together. Resetting the Windows section can restore the default animation preference because it is an explicit reset, rather than an aesthetic preset.

Presets use a private `~/.config/livara/appearance-presets.json` file (0600) inside a private folder (0700). The store accepts at most 64 named presets containing only validated, allowlisted values. Atomic replacement and a per-user file lock protect updates; corrupted files and symbolic-link targets are preserved with an error instead of being overwritten. There are no shell commands, script hooks or arbitrary GSettings paths in preset data.

Section reset acts only on that section's known preferences. Single-control palette, dock and window-style changes preserve the original primary and derived preference values if applying the change fails. Wallpaper writes similarly restore light, dark and lock-screen backgrounds if one target rejects the update. Bulk changes are checked before writing; a failure restores previous user overrides where the desktop backend permits it. Unavailable keys remain untouched. Presets containing an unavailable key skip it rather than creating a setting. A missing custom wallpaper is reported before applying the preset.

The dock stays visible when both hiding options are off. Enabling auto-hide or window avoidance switches it out of fixed mode; turning both off restores fixed mode. Presets and section reset keep those native extension preferences consistent.

Livara bounds some controls more narrowly than GNOME's schema: for example, its Night Light slider is 1000–10000 K and repeat timing uses practical UI limits. Those are Livara input limits, not a claim that the underlying schemas enforce the same bounds. Night Light depends on GNOME's color service and supported displays; input settings depend on compatible devices/drivers. Use the regular system display/device tools for controls outside this catalog.

See [window controls](window-controls.md) for native fullscreen/F11 behavior and the GTK stylesheet restart limitation. The official Tor Browser bundle/profile remains unchanged by these customizations.

The [GNOME 46 schema audit](preferences-schema-audit.json) records all 94 mappings and 224 accepted native value samples, including every declared choice and numeric endpoint. Storage, typed values, scoped presets, motion preservation, rollback, wallpaper ordering and derived dock modes also have automated tests.
