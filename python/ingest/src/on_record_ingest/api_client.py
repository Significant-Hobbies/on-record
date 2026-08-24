from __future__ import annotations

from typing import Any

import httpx

from .config import Settings


class ApiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.api_base,
            headers={"Authorization": f"Bearer {settings.admin_token}"},
            timeout=60.0,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def _json(self, response: httpx.Response) -> Any:
        response.raise_for_status()
        return response.json()

    def upsert_people(self, people: list[dict[str, Any]]) -> list[str]:
        payload = self._json(self._client.post("/admin/people/upsert", json={"people": people}))
        return list(payload.get("ids") or [])

    def upsert_shows(self, shows: list[dict[str, Any]]) -> list[str]:
        payload = self._json(self._client.post("/admin/shows/upsert", json={"shows": shows}))
        return list(payload.get("ids") or [])

    def upsert_topics(self, topics: list[dict[str, Any]]) -> list[str]:
        payload = self._json(self._client.post("/admin/topics/upsert", json={"topics": topics}))
        return list(payload.get("ids") or [])

    def upsert_episode(self, episode: dict[str, Any]) -> str:
        payload = self._json(self._client.post("/admin/episodes/upsert", json=episode))
        return str(payload["id"])

    def put_raw(self, episode_id: str, key: str, content: str, content_type: str) -> None:
        self._json(
            self._client.post(
                f"/admin/episodes/{episode_id}/raw",
                json={"key": key, "content": content, "contentType": content_type},
            )
        )

    def put_segments(
        self, episode_id: str, segments: list[dict[str, Any]], transcript_kind: str
    ) -> list[str]:
        payload = self._json(
            self._client.post(
                f"/admin/episodes/{episode_id}/segments",
                json={"segments": segments, "transcriptKind": transcript_kind},
            )
        )
        return list(payload.get("ids") or [])

    def get_episode(self, episode_id: str) -> dict[str, Any]:
        return self._json(self._client.get(f"/admin/episodes/{episode_id}"))

    def get_raw(self, episode_id: str) -> dict[str, Any]:
        return self._json(self._client.get(f"/admin/episodes/{episode_id}/raw"))

    def list_episodes(
        self, status: str | None = None, show_id: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if show_id:
            params["showId"] = show_id
        payload = self._json(self._client.get("/admin/episodes", params=params))
        return list(payload.get("episodes") or [])

    def set_episode_status(self, episode_id: str, **fields: Any) -> None:
        self._json(self._client.post(f"/admin/episodes/{episode_id}/status", json=fields))

    def post_claims(
        self, episode_id: str, claims: list[dict[str, Any]], llm_runs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return self._json(
            self._client.post(
                f"/admin/episodes/{episode_id}/claims",
                json={"claims": claims, "llmRuns": llm_runs},
            )
        )

    def ingest_run(self, payload: dict[str, Any]) -> str:
        return str(self._json(self._client.post("/admin/ingest-runs", json=payload))["id"])
