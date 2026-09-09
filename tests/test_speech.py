import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herdr_tts import speech


class RawPlayer(unittest.TestCase):
    def test_pw_play_explicitly_enables_raw_input(self):
        with mock.patch.object(speech.shutil, "which", return_value="/usr/bin/pw-play"):
            self.assertEqual(
                speech._raw_player(22050),
                [
                    "pw-play",
                    "--raw",
                    "--rate=22050",
                    "--channels=1",
                    "--format=s16",
                    "-",
                ],
            )


if __name__ == "__main__":
    unittest.main()
