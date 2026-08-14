from __future__ import annotations

import unittest
from pathlib import Path

from synology_web_capture import _dismiss_taskbar_preview


class _Keyboard:
    def __init__(self):
        self.keys = []

    def press(self, key):
        self.keys.append(key)


class _Mouse:
    def __init__(self):
        self.moves = []

    def move(self, x, y):
        self.moves.append((x, y))


class _Mask:
    def __init__(self):
        self.visible = True
        self.events = 0

    def is_visible(self):
        return self.visible

    def evaluate(self, script):
        self.events += 1
        self.visible = False


class _Masks:
    def __init__(self, mask):
        self.mask = mask

    def count(self):
        return 1

    def nth(self, index):
        return self.mask


class _Page:
    def __init__(self, mask):
        self.main_frame = self
        self.frames = [self]
        self.keyboard = _Keyboard()
        self.mouse = _Mouse()
        self.mask = mask
        self.waits = []

    def locator(self, selector):
        return _Masks(self.mask)

    def wait_for_timeout(self, value):
        self.waits.append(value)


class DsmPreviewMaskTests(unittest.TestCase):
    def test_dispatches_mask_dismiss_and_verifies_hidden(self):
        mask = _Mask()
        page = _Page(mask)
        _dismiss_taskbar_preview(page, Path("diagnostics"))
        self.assertEqual(page.mouse.moves, [(960, 540)])
        self.assertEqual(page.keyboard.keys, ["Escape"])
        self.assertEqual(mask.events, 1)
        self.assertFalse(mask.visible)


if __name__ == "__main__":
    unittest.main()
