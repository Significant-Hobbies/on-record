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
    ai_project_id: str
    extract_model: str
    force_model: str
    podcast_index_key: str
    podcast_index_secret: str
    pipeline_version: str = "claims-v1"
    prompt_version: str = "extract-v2"


def settings() -> Settings:
    api_base = os.environ.get("API_BASE", "http://127.0.0.1:8787").rstrip("/")
    return Settings(
        api_base=api_base,
        admin_token=os.environ.get("ADMIN_TOKEN", ""),
        ai_base_url=os.environ.get("AI_BASE_URL", "https://ai-gateway.sassmaker.com/v1").rstrip(
            "/"
        ),
        ai_api_key=os.environ.get("AI_API_KEY", ""),
        ai_model=os.environ.get("AI_MODEL", "auto"),
        ai_project_id=os.environ.get("AI_PROJECT_ID", "on-record"),
        extract_model=os.environ.get("ON_RECORD_EXTRACT_MODEL", "")
        or os.environ.get("AI_MODEL", "gemini-2.5-flash"),
        # Empty means "any model above the reasoning floor", which is what we
        # want day to day. Set it to pin one deliberately, e.g. when a specific
        # model is being evaluated.
        force_model=os.environ.get("ON_RECORD_FORCE_MODEL", ""),
        podcast_index_key=os.environ.get("PODCAST_INDEX_KEY", ""),
        podcast_index_secret=os.environ.get("PODCAST_INDEX_SECRET", ""),
    )
