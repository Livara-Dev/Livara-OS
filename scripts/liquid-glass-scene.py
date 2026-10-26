#!/usr/bin/env python3
"""Actual Wayland client for the disposable compositor optical test."""
import os

os.environ['GDK_BACKEND'] = 'wayland'
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

app = Gtk.Application(application_id='org.livara.OpticsProbe')


def activate(application):
    window = Gtk.ApplicationWindow(application=application,
                                  title='Live optical test window',
                                  default_width=950, default_height=600)
    area = Gtk.DrawingArea()
    changed = [False]

    def update(fd, condition):
        if condition & GLib.IO_HUP:
            return False
        if not os.read(fd, 4096):
            return False
        changed[0] = True
        area.queue_draw()
        return True

    def draw(widget, cr, width, height):
        cr.set_source_rgb(.12, .3, .5)
        cr.paint()
        for x in range(0, width, 40):
            cr.set_source_rgb(*((.95, .38, .56) if changed[0] else (.5, .78, .94)))
            cr.rectangle(x, 0, 20, height)
            cr.fill()

    GLib.io_add_watch(0, GLib.IO_IN | GLib.IO_HUP, update)
    area.set_draw_func(draw)
    window.set_child(area)
    window.present()


app.connect('activate', activate)
app.run(None)
