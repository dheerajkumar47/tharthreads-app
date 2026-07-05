# Thar Threads Catalog Swap App

Upload one blank catalog template and one or more other-brand catalog photos. The app removes the model background with remove.bg, places each model into the empty area of your template, and returns finished PNG catalog images.

## How It Works

- `backend/app.py` is a FastAPI server with:
  - `POST /api/swap`: one blank template plus one source photo returns one PNG.
  - `POST /api/swap-batch`: one blank template plus many source photos returns a ZIP of PNGs. The current mobile frontend uses `/api/swap` repeatedly so each PNG appears directly on the page.
- `frontend/index.html` is a plain HTML/JS mobile-friendly UI with no build step.
- Background removal is handled by remove.bg, not a local ML model. This keeps Render deployment small and avoids RAM crashes on free/small instances.

## Required Secret

Set this environment variable in Render:

```text
REMOVE_BG_API_KEY=your_remove_bg_api_key
```

For local testing only, you may create `backend/config.py`:

```python
REMOVE_BG_API_KEY = "your_remove_bg_api_key"
```

`backend/config.py` is ignored by git and must not be committed.

## Run Locally

Requires Python 3.10+.

```bash
cd tharthreads-app/backend
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Open:

```text
http://localhost:8000
```

## Deploy On Render

1. Push this repo to GitHub.
2. In Render, create a new Web Service from the GitHub repo.
3. Use Docker runtime. The root `Dockerfile` is the production build.
4. Add `REMOVE_BG_API_KEY` in the Render service Environment tab.
5. Deploy.

## Tuning Placement

If a template has the empty space in a different spot, edit `PLACEMENT_BOX` in `backend/app.py`.

## Notes

- Works best with clear, full-body catalog photos.
- remove.bg account limits and billing apply to background removal usage.
- Free hosting may still sleep after inactivity, but image processing should not crash from local ML memory usage anymore.
