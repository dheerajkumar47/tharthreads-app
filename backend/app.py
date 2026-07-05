"""
Thar Threads - Catalog Model Swap
----------------------------------
Upload a blank catalog template + one or more other-brand catalog photos.
The server removes the background locally (rembg / U^2-Net, a free,
open-source model - no API key, no per-image cost, no monthly cap) from
each source photo, then pastes each cutout into the empty space on the
blank template. Returns one PNG for a single source photo, or a ZIP of
PNGs when multiple source photos are uploaded at once.

This is fully free forever, but each swap takes roughly 1-3 minutes
since it's running on CPU instead of a paid cloud service.

Setup:
    1. pip install -r requirements.txt
    2. uvicorn app:app --reload --port 8000
Then open http://localhost:8000 in a browser.
"""

import io
import threading
import zipfile
from pathlib import Path
from typing import cast

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFilter

app = FastAPI(title="Thar Threads Catalog Swap")

# One rembg session, reused across requests. Loading the model is slow, so
# create it lazily on the first swap request instead of blocking app startup
# (otherwise the server looks "stuck" / connection-refused while it loads).
_session = None
_session_lock = threading.Lock()


def get_rembg_session():
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                from rembg import new_session

                _session = new_session("u2net_human_seg")
    return _session


# Where on the blank template the cut-out model gets placed, expressed
# as fractions of the template's own width/height so it scales to any
# template resolution automatically. Tuned against the Thar Threads
# lawn-collection template (empty area to the right of the text block).
PLACEMENT_BOX = {
    "x0": 0.43,
    "y0": 0.20,
    "x1": 0.975,
    "y1": 0.935,
}

# The model is scaled to fit PLACEMENT_BOX, then shrunk by this factor so
# it doesn't fill the box edge-to-edge (leaves headroom above, matches the
# reference look better). Lower = smaller model. Tune freely.
MODEL_SCALE_FACTOR = 0.91


def cutout_model(source_bytes: bytes) -> Image.Image:
    """Remove the background from the source catalog photo and return
    a tightly-cropped, clean-edged RGBA cutout of just the model.

    Single full-image, high-quality pass with alpha matting - this is
    the version that has actually produced clean edges with no leftover
    background. It's slow (roughly 1-3 minutes) because alpha matting is
    computationally heavy, but it's free and unlimited.
    """
    from rembg import remove

    src = Image.open(io.BytesIO(source_bytes)).convert("RGB")

    # rembg's type hints are loose (it can return bytes or an ndarray
    # depending on input type) - we always pass it a PIL Image, so it
    # always gives us a PIL Image back. The cast just tells the type
    # checker that, so it doesn't flag every line below as an error.
    result = cast(Image.Image, remove(
        src,
        session=get_rembg_session(),
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=8,
    ))

    alpha = result.split()[-1]
    bbox = alpha.getbbox()
    if bbox is None:
        raise HTTPException(
            status_code=422,
            detail="Could not detect a model in that photo - try a clearer, full-body shot.",
        )

    # Small padding margin so nothing right at the mask boundary (loose
    # hair, dupatta tips) gets clipped by the crop.
    pad = max(4, int(0.015 * max(result.size)))
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(result.width, x1 + pad)
    y1 = min(result.height, y1 + pad)
    return result.crop((x0, y0, x1, y1))


def composite(blank_bytes: bytes, cutout: Image.Image) -> Image.Image:
    """Paste the model cutout into the empty area of the blank template,
    scaled to fit and anchored to the bottom (so feet line up with the
    template's floor line)."""
    template = Image.open(io.BytesIO(blank_bytes)).convert("RGB")
    tw, th = template.size

    box_x0 = int(PLACEMENT_BOX["x0"] * tw)
    box_y0 = int(PLACEMENT_BOX["y0"] * th)
    box_x1 = int(PLACEMENT_BOX["x1"] * tw)
    box_y1 = int(PLACEMENT_BOX["y1"] * th)
    box_w = box_x1 - box_x0
    box_h = box_y1 - box_y0

    cw, ch = cutout.size
    scale = min(box_w / cw, box_h / ch) * MODEL_SCALE_FACTOR
    new_w, new_h = int(cw * scale), int(ch * scale)
    resized = cutout.resize((new_w, new_h), Image.Resampling.LANCZOS)

    paste_x = box_x0 + (box_w - new_w) // 2
    paste_y = box_y1 - new_h  # bottom-anchored

    # Soft grounding shadow under the feet, so the cutout doesn't look like
    # it's floating on the template's background.
    shadow_layer = Image.new("RGBA", template.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_w = int(new_w * 0.55)
    shadow_h = max(10, int(new_w * 0.06))
    shadow_cx = paste_x + new_w // 2
    shadow_cy = paste_y + new_h - int(shadow_h * 0.4)
    shadow_draw.ellipse(
        [shadow_cx - shadow_w // 2, shadow_cy - shadow_h // 2,
         shadow_cx + shadow_w // 2, shadow_cy + shadow_h // 2],
        fill=(20, 20, 20, 90),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_h * 0.4))
    template = Image.alpha_composite(template.convert("RGBA"), shadow_layer).convert("RGB")

    template.paste(resized, (paste_x, paste_y), resized)
    return template


def run_one_swap(blank_bytes: bytes, source_bytes: bytes) -> bytes:
    """Run the full pipeline for one source photo and return finished PNG bytes."""
    cutout = cutout_model(source_bytes)
    final_image = composite(blank_bytes, cutout)
    buf = io.BytesIO()
    final_image.save(buf, format="PNG")
    return buf.getvalue()


@app.post("/api/swap")
async def swap(
    blank_catalog: UploadFile = File(...),
    source_catalog: UploadFile = File(...),
):
    """Single-image swap: one blank template + one source photo -> one PNG."""
    blank_bytes = await blank_catalog.read()
    source_bytes = await source_catalog.read()

    png_bytes = run_one_swap(blank_bytes, source_bytes)
    return StreamingResponse(
        io.BytesIO(png_bytes),
        media_type="image/png",
        headers={"Content-Disposition": "attachment; filename=tharthreads-catalog.png"},
    )


@app.post("/api/swap-batch")
async def swap_batch(
    blank_catalog: UploadFile = File(...),
    source_catalogs: list[UploadFile] = File(...),
):
    """Batch swap: one blank template + many source photos -> a ZIP of PNGs.

    Used when uploading multiple other-brand catalog photos at once - each
    one gets its own finished poster, all bundled into a single download.
    """
    blank_bytes = await blank_catalog.read()

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for index, source_file in enumerate(source_catalogs, start=1):
            source_bytes = await source_file.read()
            try:
                png_bytes = run_one_swap(blank_bytes, source_bytes)
            except HTTPException as exc:
                # Skip photos the model couldn't process, but keep going
                # with the rest of the batch instead of failing the whole
                # request.
                continue
            original_name = Path(source_file.filename or f"photo-{index}").stem
            zf.writestr(f"tharthreads-{index:02d}-{original_name}.png", png_bytes)

    zip_buf.seek(0)
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=tharthreads-catalogs.zip"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve the frontend (index.html, etc.) from ../frontend at the root path.
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
