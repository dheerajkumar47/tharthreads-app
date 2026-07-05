# Thar Threads — Catalog Swap App

Upload your blank catalog template + another brand's catalog photo. Tap **Swap** and the
server detects the model, removes the background completely (no garden, no floor, no other
brand's logo/text), and pastes just the model into the empty space on your template —
matching the "i want this after add model image" example. Then **Download**.

## How it works

- `backend/app.py` — FastAPI server with one endpoint, `POST /api/swap`, that:
  1. Runs the source photo through `rembg` (U^2-Net, human-segmentation model) to cut the
     model out with a transparent background.
  2. Auto-crops to the model's bounding box.
  3. Resizes it to fit the empty space on your blank template (coordinates tuned to your
     template's layout — see `PLACEMENT_BOX` in `app.py`) and pastes it in, bottom-anchored
     so the feet line up with the template's floor line.
  4. Returns the finished PNG.
- `frontend/index.html` — a single mobile-friendly page: two upload boxes, a Swap button,
  a Download button. No build step, plain HTML/JS.

## Project structure

```
tharthreads-app/
├── backend/
│   ├── app.py            FastAPI server + compositing logic
│   └── requirements.txt
├── frontend/
│   └── index.html        upload / swap / download UI
├── Dockerfile             for one-command deploy anywhere
└── README.md
```

## Run it on your own computer

Requires Python 3.10+.

```bash
cd tharthreads-app/backend
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Open `http://localhost:8000` in a browser. The first request will download the
background-removal model (~170MB, one-time, needs internet access) — after that it's
instant. To use it from your phone, run it on your computer and open
`http://<your-computer's-LAN-IP>:8000` from your phone on the same Wi-Fi, or deploy it
properly (below) to get a real link.

## Deploy it as a real link (free options)

**Render.com** (easiest):
1. Push this folder to a GitHub repo.
2. Render dashboard → New → Web Service → connect the repo.
3. Render will detect the `Dockerfile` automatically and build/deploy it.
4. You get a public URL like `https://tharthreads-app.onrender.com` — open it on any
   phone or computer.

**Railway.app**: same idea — connect the repo, it detects the Dockerfile, deploys, gives
you a public URL.

Either works fine on their free tiers for personal/small-business use. If the app feels
slow to "wake up" after being idle (normal on free tiers), that's the host sleeping the
service, not a bug.

## Tuning the model placement

If a different template has the empty space in a different spot, open `backend/app.py`
and adjust the `PLACEMENT_BOX` percentages (`x0`, `y0`, `x1`, `y1` — fractions of the
template's width/height). No other code needs to change.

## Notes

- Works best with clear, well-lit, full-body catalog photos as the source.
- If the cutout looks off (e.g. a hand or the dupatta gets clipped), it's usually because
  the segmentation model wasn't confident at that edge — try a source photo with a plainer
  background for best results.
- This was developed and tested in a network-restricted sandbox where the model download
  itself couldn't be tested live — run it locally once after downloading to confirm output
  quality before relying on it for real catalogs.
