import unittest
from pathlib import Path


class FrontendBatchMobileTests(unittest.TestCase):
    def test_multiple_sources_render_direct_images_instead_of_zip(self):
        html = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("/api/swap-batch", html)
        self.assertNotIn("tharthreads-catalogs.zip", html)
        self.assertIn('id="resultGrid"', html)
        self.assertIn("downloadResult", html)


if __name__ == "__main__":
    unittest.main()
