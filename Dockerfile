FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image at build time, so the container
# never has to download it (or wait on Hugging Face Hub) on a cold start.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Render (and most Docker hosts) inject the port to listen on via $PORT -
# shell form CMD so that variable actually expands; falls back to 7860 for
# local `docker run`.
EXPOSE 7860

CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}
