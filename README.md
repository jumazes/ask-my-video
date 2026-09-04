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

## Deploy (Render)

The `Dockerfile` at the repo root is a standard Docker web service - Render
builds and runs it directly. The container reads the port to bind to from
the `PORT` environment variable Render injects at runtime.

1. Create a free account at https://render.com (no credit card required)
   and connect your GitHub account.
2. **New -> Web Service**, pick this repository. Render should detect the
   `Dockerfile` automatically; if asked, set the runtime/environment to
   **Docker**.
3. Choose the **Free** instance type.
4. Under **Environment**, add an environment variable named
   `GEMINI_API_KEY` with your key. Never commit it - it stays out of the
   image entirely (`.env` is gitignored and the Dockerfile only copies
   `backend/`, `frontend/`, and `requirements.txt`).
5. Deploy. The first build takes a few minutes (installing torch); Render
   then serves the app at `https://<service-name>.onrender.com`.

Free-tier note: the service spins down after 15 minutes of inactivity, so
the first request after a while takes a bit longer to wake it back up.

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
