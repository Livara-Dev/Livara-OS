"""Window-action and live-control state tests do not need a display or GI."""
from types import SimpleNamespace
import unittest

from livara.native_controls import NativeHeaderbar, button_side, green_operation, packing_side


class Window:
    def __init__(self, fullscreen=False, maximized=False):
        self.full = fullscreen
        self.max = maximized
        self.operations = []

    def is_fullscreen(self):
        return self.full

    def is_maximized(self):
        return self.max

    def fullscreen(self):
        self.operations.append("fullscreen")
        self.full = True

    def unfullscreen(self):
        self.operations.append("unfullscreen")
        self.full = False

    def maximize(self):
        self.operations.append("maximize")
        self.max = True

    def unmaximize(self):
        self.operations.append("unmaximize")
        self.max = False


class Label:
    def set_text(self, text):
        self.text = text


class Button:
    def __init__(self):
        self.label = Label()

    def set_tooltip_text(self, value):
        self.tooltip = value

    def update_property(self, properties, values):
        self.accessible_label = values[0]

    def get_child(self):
        return self.label


class NativeControlTests(unittest.TestCase):
    def handle(self, *, fullscreen=False, maximized=False, action="fullscreen", shift=False):
        handle = NativeHeaderbar.__new__(NativeHeaderbar)
        handle.window = Window(fullscreen, maximized)
        handle.values = {"window-green-action": action}
        handle._shift = shift
        handle.Gtk = SimpleNamespace(AccessibleProperty=SimpleNamespace(LABEL="label"))
        handle.buttons = {"maximize": Button()}
        return handle

    def test_layout_selects_close_side_and_preserves_physical_edge_in_rtl(self):
        self.assertEqual(button_side("close,minimize,maximize:"), "start")
        self.assertEqual(button_side(":minimize,maximize,close"), "end")
        self.assertEqual(button_side("minimize:close"), "end")
        self.assertEqual(button_side(None), "start")
        self.assertEqual(packing_side("close,minimize,maximize:", rtl=True), "end")
        self.assertEqual(packing_side(":minimize,maximize,close", rtl=True), "start")
        self.assertEqual(packing_side(":minimize,maximize,close"), "end")

    def test_green_operation_uses_native_state_and_shift_override(self):
        self.assertEqual(green_operation("fullscreen", fullscreen=False, maximized=True), "fullscreen")
        self.assertEqual(green_operation("fullscreen", fullscreen=True, maximized=False), "unfullscreen")
        self.assertEqual(green_operation("maximize", fullscreen=False, maximized=True), "unmaximize")
        self.assertEqual(green_operation("fullscreen", fullscreen=False, maximized=False, shift=True), "maximize")
        self.assertEqual(green_operation("unknown", fullscreen=False, maximized=False), "fullscreen")

    def test_green_click_toggles_fullscreen_and_updates_semantic_label(self):
        handle = self.handle()
        handle._green_clicked(None)
        self.assertEqual(handle.window.operations, ["fullscreen"])
        self.assertIn("Exit fullscreen", handle.buttons["maximize"].accessible_label)
        handle._green_clicked(None)
        self.assertEqual(handle.window.operations, ["fullscreen", "unfullscreen"])
        self.assertIn("Enter fullscreen", handle.buttons["maximize"].tooltip)

    def test_shift_green_leaves_fullscreen_then_maximizes_and_consumes_shift(self):
        handle = self.handle(fullscreen=True, shift=True)
        handle._green_clicked(None)
        self.assertEqual(handle.window.operations, ["unfullscreen", "maximize"])
        self.assertFalse(handle._shift)
        self.assertFalse(handle.window.full)
        self.assertTrue(handle.window.max)

    def test_maximize_preference_and_restore(self):
        handle = self.handle(action="maximize", maximized=True)
        handle._green_clicked(None)
        self.assertEqual(handle.window.operations, ["unmaximize"])
        self.assertIn("Maximize", handle.buttons["maximize"].accessible_label)
        handle._green_clicked(None)
        self.assertEqual(handle.window.operations, ["unmaximize", "maximize"])
        self.assertIn("Restore", handle.buttons["maximize"].accessible_label)

    def test_f11_ignores_green_preference_and_toggles_fullscreen(self):
        handle = self.handle(action="maximize")
        self.assertTrue(handle._fullscreen_shortcut())
        self.assertTrue(handle.window.full)
        self.assertTrue(handle._fullscreen_shortcut())
        self.assertFalse(handle.window.full)
        self.assertEqual(handle.window.operations, ["fullscreen", "unfullscreen"])


if __name__ == "__main__":
    unittest.main()
