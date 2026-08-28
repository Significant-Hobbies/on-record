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

    def upsert_people(self, people: list[dict[str, Any]], batch: int = 100) -> list[str]:
        """Seed the roster in batches.

        The worker reads then writes per person, so a 1,255-person roster in one
        request is 2,500 D1 round-trips and times out.
        """
        ids: list[str] = []
        for start in range(0, len(people), batch):
            payload = self._json(
                self._client.post(
                    "/admin/people/upsert", json={"people": people[start : start + batch]}
                )
            )
            ids.extend(payload.get("ids") or [])
        return ids

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

    def list_shows(self) -> list[dict[str, Any]]:
        payload = self._json(self._client.get("/admin/shows"))
        return list(payload.get("shows") or [])

    def list_people(self) -> list[dict[str, Any]]:
        payload = self._json(self._client.get("/admin/people"))
        return list(payload.get("people") or [])

    def get_episode(self, episode_id: str) -> dict[str, Any]:
        return self._json(self._client.get(f"/admin/episodes/{episode_id}"))

    def get_raw(self, episode_id: str, key: str | None = None) -> dict[str, Any]:
        params = {"key": key} if key else {}
        return self._json(self._client.get(f"/admin/episodes/{episode_id}/raw", params=params))

    def reverify(self, episode_id: str) -> dict[str, Any]:
        """Re-check an episode's claims, resuming until the worker reports done."""
        totals = {"kept": 0, "quoteGone": 0, "speakerChanged": 0, "total": 0}
        for _ in range(50):
            page = self._json(
                self._client.post(f"/admin/episodes/{episode_id}/reverify", json={}, timeout=120.0)
            )
            totals["quoteGone"] += int(page.get("quoteGone") or 0)
            totals["speakerChanged"] += int(page.get("speakerChanged") or 0)
            totals["kept"] += int(page.get("kept") or 0)
            totals["total"] = int(page.get("total") or 0)
            if page.get("done"):
                break
        return totals

    def retime(self, episode_id: str) -> dict[str, Any]:
        return self._json(self._client.post(f"/admin/episodes/{episode_id}/retime", json={}))

    def list_episodes(
        self, status: str | None = None, show_id: str | None = None, page_size: int = 200
    ) -> list[dict[str, Any]]:
        """Every matching episode, paged. The endpoint caps a single response."""
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if show_id:
            params["showId"] = show_id
        out: list[dict[str, Any]] = []
        offset = 0
        request_limit = max(1, min(page_size, 200))
        while True:
            params["limit"] = str(request_limit)
            params["offset"] = str(offset)
            payload = self._json(self._client.get("/admin/episodes", params=params))
            rows = list(payload.get("episodes") or [])
            out.extend(rows)
            if len(rows) < request_limit:
                return out
            offset += len(rows)

    def set_episode_people(self, episode_id: str, people: list[dict[str, Any]]) -> None:
        self._json(
            self._client.post(f"/admin/episodes/{episode_id}/people", json={"people": people})
        )

    def repair_speakers(self, episode_id: str, repairs: list[dict[str, Any]]) -> dict[str, Any]:
        return self._json(
            self._client.post(f"/admin/episodes/{episode_id}/speakers", json={"repairs": repairs})
        )

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
