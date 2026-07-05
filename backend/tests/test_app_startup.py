import importlib
import sys
import unittest
from pathlib import Path


class StartupTests(unittest.TestCase):
    def test_import_does_not_import_rembg(self):
        backend_dir = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(backend_dir))
        sys.modules.pop("app", None)
        original_rembg = sys.modules.pop("rembg", None)
        sys.modules["rembg"] = None

        try:
            importlib.import_module("app")
        finally:
            if original_rembg is None:
                sys.modules.pop("rembg", None)
            else:
                sys.modules["rembg"] = original_rembg

if __name__ == "__main__":
    unittest.main()
