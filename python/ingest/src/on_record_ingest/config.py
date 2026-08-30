from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_base: str
    admin_token: str
    ai_base_url: str
    ai_api_key: str
    ai_model: str
    extract_model: str
    force_model: str
    attribution_model: str
    youtube_api_key: str
    podcast_index_key: str
    podcast_index_secret: str
    pipeline_version: str = "claims-v1"
    prompt_version: str = "extract-v4"


def settings() -> Settings:
    api_base = os.environ.get("API_BASE", "http://127.0.0.1:8787").rstrip("/")
    return Settings(
        api_base=api_base,
        admin_token=os.environ.get("ADMIN_TOKEN", ""),
        ai_base_url=os.environ.get("AI_BASE_URL", "").rstrip("/"),
        ai_api_key=os.environ.get("AI_API_KEY", ""),
        ai_model=os.environ.get("AI_MODEL", ""),
        extract_model=os.environ.get("ON_RECORD_EXTRACT_MODEL", "")
        or os.environ.get("AI_MODEL", ""),
        # Optional deliberate override for extraction experiments.
        force_model=os.environ.get("ON_RECORD_FORCE_MODEL", ""),
        # Judging a short passage, not reproducing text — a small local model
        # is both sufficient and fast enough to run over every attribution.
        attribution_model=os.environ.get("ON_RECORD_ATTRIBUTION_MODEL", "qwen/qwen3.5-4b"),
        youtube_api_key=os.environ.get("YOUTUBE_API_KEY", ""),
        podcast_index_key=os.environ.get("PODCAST_INDEX_KEY", ""),
        podcast_index_secret=os.environ.get("PODCAST_INDEX_SECRET", ""),
    )
