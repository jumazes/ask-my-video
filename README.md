---
title: Video Q&A
emoji: 🎬
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# YouTube / Podcast RAG Chatbot

A retrieval-augmented generation (RAG) chatbot that answers questions about
YouTube videos and podcasts, with responses grounded in the actual
transcript and cited by timestamp.

The pipeline favors clarity over abstraction: transcript ingestion,
chunking, embedding, retrieval, and generation are each implemented as
plain, readable functions rather than hidden behind a framework.

## How it works

```
YouTube URL
   |
   v
youtube_ingest.py  -> parse video ID -> fetch timestamped transcript segments
   |
   v
chunking.py        -> group segments into overlapping, timestamped chunks
   |
   v
embeddings.py       -> embed each chunk's text (sentence-transformers, local, CPU)
   |
   v
vectorstore.py      -> keep chunks + embedding matrix in memory (nothing written to disk)
   |
   v (on question)
embeddings.py       -> embed the user's question
   |
   v
vectorstore.py      -> cosine similarity (dot product, normalized vectors) -> top-k chunks
   |
   v
rag.py              -> sort chunks chronologically, build context block, call Gemini
   |
   v
main.py (FastAPI)   -> return {answer, sources[]} as JSON
   |
   v
frontend/app.js     -> render chat bubble + "Sources: 03:12, 07:45"
```

**Stack:** Python + FastAPI backend, plain HTML/JS/CSS frontend (no build
step), local `sentence-transformers` embeddings (no API key needed), a
hand-rolled in-memory numpy vector search (no vector DB, nothing on disk),
and Google's Gemini API (free tier) for answer generation.

## Setup

1. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\Activate.ps1
   ```
   (If PowerShell blocks script execution: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
   `sentence-transformers` pulls in `torch` - first install can take a
   few minutes. The embedding model itself (~90MB) downloads on first run.

3. Copy `.env.example` to `.env` and add your Gemini API key (free, no
   credit card - get one at https://aistudio.google.com/apikey):
   ```
   GEMINI_API_KEY=your-key-here
   ```

## Run

```
venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000, paste a YouTube URL with captions available,
click Ingest, then ask questions in the chat box below.

API docs (Swagger UI) are at http://127.0.0.1:8000/docs.

## Deploy (Hugging Face Spaces)

The `Dockerfile` and the YAML block at the top of this README are Hugging
Face Spaces config (`sdk: docker`, `app_port: 7860`) - Spaces builds and
runs this Dockerfile directly, no extra setup needed on their side.

1. Create a new Space at https://huggingface.co/new-space - pick the
   **Docker** SDK, any name/visibility.
2. Push this repo to the Space's git remote (shown on the Space's page,
   looks like `https://huggingface.co/spaces/<user>/<space-name>`):
   ```
   git remote add space https://huggingface.co/spaces/<user>/<space-name>
   git push space master
   ```
3. In the Space's **Settings -> Variables and secrets**, add a secret
   named `GEMINI_API_KEY` with your key. Never commit it - `.env` is
   gitignored and the Dockerfile only copies `backend/`, `frontend/`,
   and `requirements.txt`, so it can't leak in even by accident.
4. The Space builds (a few minutes - it's downloading/installing torch)
   and then serves the app at `https://<user>-<space-name>.hf.space`.

## Known limitations

- Only works for videos that have captions (manual or auto-generated).
- English is preferred; falls back to whatever transcript is available.
- No authentication - anyone with the deployed link can use it, sharing
  the same Gemini free-tier quota. Suitable for small-scale personal use,
  not for public traffic.
- No conversation memory - each question is answered independently.
- **Nothing persists to disk, by design.** Ingested videos live only in
  the server process's memory - restart the server (or the machine) and
  you'll need to re-ingest. The browser doesn't remember the last video
  either; each page load starts fresh.

## Possible extensions

- Swap the vector store for Chroma if you outgrow linear search.
- Swap embeddings for an external API (OpenAI/Voyage) if you want higher quality.
- Stream the answer token-by-token instead of waiting for the full response.
- Add multi-turn chat memory.
- Add opt-in disk persistence if you decide you want ingested videos to
  survive a restart.
