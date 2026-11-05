"""Settings. Secrets (API keys) are read from the environment / .env by the SDKs, never stored here."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]  # repo root (src/ey_hackathon/rag/config.py)


@dataclass(frozen=True)
class Settings:
    corpus_dir: Path
    chroma_dir: Path
    embedding_model: str
    claude_model: str


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")  # does not override variables already set in the shell
    return Settings(
        corpus_dir=ROOT / "rag-system",
        chroma_dir=ROOT / ".chroma",
        embedding_model=os.environ.get("EMBEDDING_MODEL") or "text-embedding-3-small",
        claude_model=os.environ.get("CLAUDE_MODEL") or "claude-sonnet-5-5",
    )
