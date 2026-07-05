import io
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException
from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import app


def png_bytes(size=(20, 30), color=(0, 0, 0, 255)):
    image = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class RemoveBgIntegrationTests(unittest.TestCase):
    def test_missing_api_key_returns_clear_error(self):
        with patch.object(app, "REMOVE_BG_API_KEY", None):
            with self.assertRaises(HTTPException) as ctx:
                app.cutout_model(png_bytes())

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("REMOVE_BG_API_KEY", ctx.exception.detail)

    def test_cutout_model_calls_remove_bg_with_secret_header(self):
        response = Mock(status_code=200, content=png_bytes())

        with patch.object(app, "REMOVE_BG_API_KEY", "test-key"):
            with patch.object(app.requests, "post", return_value=response) as post:
                cutout = app.cutout_model(b"source-photo")

        self.assertEqual(cutout.mode, "RGBA")
        post.assert_called_once()
        _, kwargs = post.call_args
        self.assertEqual(kwargs["headers"]["X-Api-Key"], "test-key")
        self.assertEqual(kwargs["data"], {"size": "auto"})
        self.assertEqual(kwargs["timeout"], 60)
        self.assertEqual(kwargs["files"], {"image_file": b"source-photo"})

    def test_remove_bg_error_becomes_bad_gateway(self):
        response = Mock(status_code=402, text="quota exceeded")
        response.json.side_effect = ValueError("not json")

        with patch.object(app, "REMOVE_BG_API_KEY", "test-key"):
            with patch.object(app.requests, "post", return_value=response):
                with self.assertRaises(HTTPException) as ctx:
                    app.cutout_model(b"source-photo")

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("remove.bg error", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
