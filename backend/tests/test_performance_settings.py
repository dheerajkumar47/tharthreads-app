import io
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import app


class PerformanceSettingsTests(unittest.TestCase):
    def test_source_image_is_downscaled_before_background_removal(self):
        source = Image.new("RGB", (3000, 2000), "white")
        buf = io.BytesIO()
        source.save(buf, format="PNG")

        cutout = Image.new("RGBA", (100, 200), (0, 0, 0, 255))
        remove = Mock(return_value=cutout)

        with patch.dict(sys.modules, {"rembg": Mock(remove=remove)}):
            app.cutout_model(buf.getvalue())

        image_sent_to_rembg = remove.call_args.args[0]
        self.assertLessEqual(max(image_sent_to_rembg.size), app.MAX_SEGMENTATION_SIDE)

    def test_alpha_matting_is_disabled_by_default_for_hosted_speed(self):
        source = Image.new("RGB", (20, 20), "white")
        buf = io.BytesIO()
        source.save(buf, format="PNG")

        cutout = Image.new("RGBA", (20, 20), (0, 0, 0, 255))
        remove = Mock(return_value=cutout)

        with patch.dict(sys.modules, {"rembg": Mock(remove=remove)}):
            app.cutout_model(buf.getvalue())

        self.assertIs(remove.call_args.kwargs["alpha_matting"], False)

    def test_uses_people_segmentation_model_by_default(self):
        self.assertEqual(app.REMBG_MODEL, "u2net_human_seg")


if __name__ == "__main__":
    unittest.main()
