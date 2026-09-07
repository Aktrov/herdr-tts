import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herdr_tts import selection


class ResolveText(unittest.TestCase):
    def setUp(self):
        os.environ.pop("HERDR_PLUGIN_CONTEXT_JSON", None)

    def test_context_selection_wins(self):
        os.environ["HERDR_PLUGIN_CONTEXT_JSON"] = json.dumps(
            {"selected_text": "  hello world  "}
        )
        text, source = selection.resolve_text()
        self.assertEqual(text, "hello world")
        self.assertEqual(source, "context")

    def test_falls_back_to_clipboard(self):
        os.environ["HERDR_PLUGIN_CONTEXT_JSON"] = json.dumps(
            {"selected_text": None}
        )
        with mock.patch.object(
            selection, "_from_clipboard", return_value=("clip text", "clipboard/x")
        ):
            text, source = selection.resolve_text()
        self.assertEqual(text, "clip text")
        self.assertEqual(source, "clipboard/x")

    def test_truncation(self):
        os.environ["HERDR_PLUGIN_CONTEXT_JSON"] = json.dumps(
            {"selected_text": "word " * 50}
        )
        text, _ = selection.resolve_text(max_chars=20)
        self.assertTrue(text.endswith("text truncated."))
        self.assertLess(len(text), 60)

    def test_nothing(self):
        with mock.patch.object(
            selection, "_from_clipboard", return_value=("", "clipboard-empty")
        ):
            text, _ = selection.resolve_text()
        self.assertEqual(text, "")


if __name__ == "__main__":
    unittest.main()
