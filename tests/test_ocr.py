import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from faction_tracker.ocr import find_tesseract


class FindTesseractTests(unittest.TestCase):
    def test_env_var_can_point_at_install_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "tesseract.exe"
            exe.write_text("fake", encoding="utf-8")
            with mock.patch.dict(os.environ, {"TESSERACT_CMD": tmp}, clear=False):
                self.assertEqual(find_tesseract(), str(exe))


if __name__ == "__main__":
    unittest.main()
