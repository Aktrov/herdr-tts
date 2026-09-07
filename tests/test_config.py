import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herdr_tts.config import DEFAULTS, load_config, _tiny_toml, _coerce


class TinyToml(unittest.TestCase):
    def test_types(self):
        d = _tiny_toml(
            'engine = "spd-say"\n'
            "length_scale = 1.2\n"
            "max_chars = 500\n"
            "spool_fallback = false\n"
            'speak_command = ["ssh", "box", "say"]\n'
            "# comment line\n"
            'voice = "en_US-ryan-high"  # trailing comment\n'
        )
        self.assertEqual(d["engine"], "spd-say")
        self.assertEqual(d["length_scale"], 1.2)
        self.assertEqual(d["max_chars"], 500)
        self.assertIs(d["spool_fallback"], False)
        self.assertEqual(d["speak_command"], ["ssh", "box", "say"])
        self.assertEqual(d["voice"], "en_US-ryan-high")

    def test_hash_inside_string_kept(self):
        self.assertEqual(_coerce('"a # b"'), "a # b")

    def test_ignores_tables(self):
        d = _tiny_toml('engine = "piper"\n[section]\nkey = 1\n')
        # top-level keys parse; anything under a table header is skipped
        self.assertEqual(d.get("engine"), "piper")
        self.assertNotIn("key", d)


class LoadConfig(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(load_config(Path(td)), DEFAULTS)

    def test_overrides_and_unknown_keys_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "config.toml").write_text(
                'engine = "command"\nbogus_key = 5\n'
            )
            cfg = load_config(Path(td))
            self.assertEqual(cfg["engine"], "command")
            self.assertNotIn("bogus_key", cfg)
            self.assertEqual(cfg["voice"], DEFAULTS["voice"])


if __name__ == "__main__":
    unittest.main()
