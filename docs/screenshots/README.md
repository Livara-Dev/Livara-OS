# Livara screenshot gallery

The gallery contains 62 original PNG captures of the available Livara applications,
desktop previews and font specimens. Each catalog entry identifies its capture
context. Application captures made under Xvfb and nested GNOME previews are not
screenshots of a newly booted Livara ISO. Sample notes and focus sessions are
identified as demonstration data; graphics diagnostics show the test container.

`catalog.json` lists the captures and the components that could not be captured.
No mock screenshots substitute for an unbuilt application or an untested boot
screen. In particular, the normal Livara Browser's full Gecko build remains
unqualified. The separate official Tor Browser retains its original appearance.

The current set includes all 17 Essentials feature pages, its compact layout, the native command palette, an installer requirements screen, all eight Settings sections, additional control/search
and preview views, Studio's redesigned dashboard and workspaces, and four nested
desktop views. `native-manifest.json` records native-app capture context;
`desktop-manifest.json` records the separate compositor and Tor captures.

Create the self-contained offline HTML gallery and a ZIP of the original PNGs:

```sh
python3 scripts/package-screenshots.py
```

Outputs are `dist/livara-os-screenshot-gallery.html` and
`dist/livara-os-screenshots.zip`, with SHA-256 files alongside them. The HTML
embeds its images and needs no network access. Click a capture to enlarge it or
download its unchanged original PNG. These files are visual review artifacts;
they do not build an ISO or demonstrate hardware compatibility.
