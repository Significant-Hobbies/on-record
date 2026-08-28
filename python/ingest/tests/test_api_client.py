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
