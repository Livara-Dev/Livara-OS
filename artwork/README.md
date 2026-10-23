# Artwork

The purple glass L was supplied by the user for Livara OS. `livara-logo.png` is a transparent-background adaptation prepared with an image editing tool. It is incorporated into the SVG application icon and desktop wallpapers and is used by the boot splash. The supplied mark and its adaptation retain their original rights; the project's GPL grant does not independently relicense that mark.

The surrounding wallpaper compositions, Livara interface icons, and other original project artwork are GPL-3.0-or-later. No Apple interface assets or fonts are bundled.

The desktop uses pre-rendered 3840 × 2160 PNG wallpapers to keep SVG filter work out of the login path. Editable SVG compositions are retained. Regenerate a wallpaper with `rsvg-convert -w 3840 -h 2160 artwork/livara-glass.svg -o artwork/livara-glass.png` from `librsvg2-bin`; the Verdant source is `livara-wallpaper.svg`.

`livara-browser.png` and `livara-code.png` are separately generated adaptations of the supplied glass L, with a globe and coding brackets respectively. Their corresponding `org.livara.*.svg` wrappers embed the PNG for scalable icon lookup. The other native app launchers share the Livara identity mark. These derivatives retain the supplied mark’s original rights. No Ubuntu logo is intentionally included in Livara artwork.
