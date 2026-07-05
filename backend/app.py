"""
Thar Threads - Catalog Model Swap
----------------------------------
Upload a blank catalog template + one or more other-brand catalog photos.
The server sends each source photo to remove.bg (a dedicated background-
removal cloud API) to cut the model out cleanly, then pastes each cutout
into the empty space on the blank template. Returns one PNG for a single
source photo, or a ZIP of PNGs when multiple source photos are uploaded
at once.

Why remove.bg instead of a local model: this app runs on a free hosting
tier with very little RAM/CPU, which isn't enough to reliably run a local
background-removal model - it was crashing/timing out in practice.
remove.bg processes the image on their servers instead, so it's fast and
doesn't need much from the host. Free for the first ~50 images/month per
API key; a few cents each beyond that.

Setup:
    1. Get a free API key at https://www.remove.bg/api
    2. Set it as the REMOVE_BG_API_KEY environment variable (in Render's
       dashboard for the deployed version, or in backend/config.py for
       local testing - see config.py).
    3. pip install -r requirements.txt
    4. uvicorn app:app --reload --port 8000
Then open http://localhost:8000 in a browser.
"""

import io
import os
import time
import zipfile
from pathlib import Path

import requests
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFilter

# The API key comes from an environment variable first (that's what Render
# uses - set it in the service's Environment tab, never committed to git).
# Falls back to backend/config.py for convenience when testing locally.
try:
    from config import REMOVE_BG_API_KEY as _CONFIG_KEY
except ImportError:
    _CONFIG_KEY = None

REMOVE_BG_API_KEY = os.getenv("REMOVE_BG_API_KEY") or _CONFIG_KEY
REMOVE_BG_ENDPOINT = "https://api.remove.bg/v1.0/removebg"

app = FastAPI(title="Thar Threads Catalog Swap")

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
    """Send the source photo to remove.bg and return a tightly-cropped
    RGBA cutout of just the model, background fully removed."""
    if not REMOVE_BG_API_KEY or REMOVE_BG_API_KEY == "PASTE_YOUR_KEY_HERE":
        raise HTTPException(
            status_code=500,
            detail=(
                "No remove.bg API key configured. Set the REMOVE_BG_API_KEY "
                "environment variable (Render dashboard) or paste it into "
                "backend/config.py for local testing."
            ),
        )

    response = requests.post(
        REMOVE_BG_ENDPOINT,
        files={"image_file": source_bytes},
        data={"size": "auto"},
        headers={"X-Api-Key": REMOVE_BG_API_KEY},
        timeout=60,
    )

    if response.status_code != 200:
        try:
            detail = response.json()["errors"][0]["title"]
        except Exception:
            detail = response.text[:200]
        raise HTTPException(status_code=502, detail=f"remove.bg error: {detail}")

    result = Image.open(io.BytesIO(response.content)).convert("RGBA")

    # Tight crop around the visible pixels, with a small padding margin
    # so nothing right at the edge (loose hair, dupatta tips) gets clipped.
    bbox = result.split()[-1].getbbox()
    if bbox is None:
        raise HTTPException(
            status_code=422,
            detail="Could not detect a model in that photo - try a clearer, full-body shot.",
        )
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
    started = time.perf_counter()
    cutout = cutout_model(source_bytes)
    cutout_done = time.perf_counter()
    final_image = composite(blank_bytes, cutout)
    buf = io.BytesIO()
    final_image.save(buf, format="PNG")
    finished = time.perf_counter()
    print(
        "swap timing "
        f"cutout={cutout_done - started:.2f}s "
        f"composite={finished - cutout_done:.2f}s "
        f"total={finished - started:.2f}s",
        flush=True,
    )
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
            except HTTPException:
                # Skip photos remove.bg couldn't process, but keep going
                # with the rest of the batch instead of failing it all.
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
