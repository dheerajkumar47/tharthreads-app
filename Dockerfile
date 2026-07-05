FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Download the segmentation model at build time so the first user request does
# not spend minutes fetching it on the live Render instance.
ENV REMBG_MODEL=u2net_human_seg
ENV MAX_SEGMENTATION_SIDE=768
ENV ALPHA_MATTING=false
RUN python -c "import os; from rembg import new_session; new_session(os.environ['REMBG_MODEL'])"

COPY backend/ ./backend/
COPY frontend/ ./frontend/

WORKDIR /app/backend
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
