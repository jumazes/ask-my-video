"""Loads settings from the .env file (see .env.example for the full list).

python-dotenv reads .env into the process environment; os.environ.get() then
reads each value with a fallback default for anything left unset.
"""

import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
CHUNK_MAX_WORDS = int(os.environ.get("CHUNK_MAX_WORDS", 180))
CHUNK_OVERLAP_WORDS = int(os.environ.get("CHUNK_OVERLAP_WORDS", 40))
TOP_K = int(os.environ.get("TOP_K", 5))
