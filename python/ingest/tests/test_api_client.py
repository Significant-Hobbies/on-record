from on_record_ingest.api_client import ApiClient


class _PagedClient:
    def __init__(self, rows):
        self.rows = rows
        self.requests = []

    def get(self, path, params):
        captured = dict(params)
        self.requests.append((path, captured))
        offset = int(captured["offset"])
        limit = min(int(captured["limit"]), 200)
        return {"episodes": self.rows[offset : offset + limit]}


def test_list_episodes_pages_through_the_api_cap():
    api = object.__new__(ApiClient)
    api._client = _PagedClient([{"id": str(index)} for index in range(450)])
    api._json = lambda response: response

    rows = api.list_episodes(status="published", page_size=1000)

    assert len(rows) == 450
    assert [request[1]["offset"] for request in api._client.requests] == ["0", "200", "400"]
    assert all(request[1]["limit"] == "200" for request in api._client.requests)


def _transport(statuses, calls):
    import httpx

    from on_record_ingest.api_client import RetryTransientTransport

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(statuses[min(len(calls), len(statuses)) - 1])

    return RetryTransientTransport(httpx.MockTransport(handler), sleep=lambda _s: None)


def test_transient_worker_errors_on_reads_are_retried():
    import httpx

    calls = []
    client = httpx.Client(base_url="https://api.test", transport=_transport([500, 200], calls))

    assert client.get("/admin/episodes/x").status_code == 200
    assert calls == [("GET", "/admin/episodes/x")] * 2


def test_upserts_retry_but_other_writes_are_sent_once():
    import httpx

    calls = []
    client = httpx.Client(base_url="https://api.test", transport=_transport([503, 200], calls))
    assert client.post("/admin/people/upsert", json={"people": []}).status_code == 200
    assert len(calls) == 2

    calls.clear()
    client = httpx.Client(base_url="https://api.test", transport=_transport([500, 200], calls))
    assert client.post("/admin/episodes/x/claims", json={}).status_code == 500
    assert len(calls) == 1


def test_persistent_worker_error_still_surfaces():
    import httpx

    calls = []
    client = httpx.Client(base_url="https://api.test", transport=_transport([500], calls))

    assert client.get("/admin/people").status_code == 500
    assert len(calls) == 3
