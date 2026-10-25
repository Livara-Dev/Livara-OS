"""Original Halo hero material shared by native Livara workspaces."""
from pathlib import Path


def artwork_path():
    candidates = (Path(__file__).resolve().parents[2] / "artwork/livara-halo.png",
                  Path("/usr/share/backgrounds/livara/livara-halo.png"))
    return next((p for p in candidates if p.is_file()), None)


def hero(eyebrow, title, description, actions):
    from gi.repository import Gtk, Pango
    overlay = Gtk.Overlay(css_classes=["halo-hero"], hexpand=True)
    overlay.set_overflow(Gtk.Overflow.HIDDEN)
    path = artwork_path()
    if path:
        picture = Gtk.Picture.new_for_filename(str(path))
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_can_shrink(True)
        overlay.set_child(picture)
    else:
        overlay.set_child(Gtk.Box(height_request=300))
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                      css_classes=["halo-copy"], valign=Gtk.Align.CENTER)
    for side in ("top", "bottom", "start", "end"):
        getattr(content, "set_margin_" + side)(28)
    for text, name in ((eyebrow, "halo-eyebrow"), (title, "halo-title"), (description, "halo-description")):
        label = Gtk.Label(label=text, xalign=0, wrap=True, css_classes=[name])
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(31 if name == "halo-title" else 43)
        label.set_halign(Gtk.Align.FILL)
        label.set_hexpand(True)
        if name == "halo-eyebrow":
            label.set_wrap(False)
            label.set_ellipsize(Pango.EllipsizeMode.END)
        content.append(label)
    content.append(actions)
    overlay.add_overlay(content)
    overlay.set_measure_overlay(content, True)
    return overlay
