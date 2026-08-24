from agent_core.node_http_api import NodeHttpApi


class _Enrollment:
    def resolve(self, payload):
        return {"schema": "resolve", "reference": payload["reference"]}

    def claim(self, payload, *, observed_at):
        return {"schema": "claim", "observed_at": observed_at, "ticket": payload["ticket"]}


class _Directory:
    def list_nodes(self):
        return {"schema": "list", "nodes": ["node-a"]}

    def node(self, node_id):
        if node_id == "missing":
            raise KeyError("unknown Node")
        return {"schema": "node", "node_id": node_id}

    def capabilities(self, node_id):
        return {"schema": "caps", "node_id": node_id}

    def nodes_for_capability(self, capability):
        return {"schema": "cap-nodes", "capability": capability}


def _api():
    return NodeHttpApi(
        enrollment=_Enrollment(),
        directory=_Directory(),
        now_iso=lambda: "2026-08-22T12:30:00Z",
    )


def test_routes_enrollment_and_directory_through_one_contract() -> None:
    api = _api()
    assert api.handle("POST", "/v1/nodes/enrollment/resolve", {"reference": "r"}).body["schema"] == "resolve"
    claim = api.handle("POST", "/v1/nodes/enrollment/claim", {"ticket": "t"})
    assert claim.status == 200
    assert claim.body["observed_at"] == "2026-08-22T12:30:00Z"
    assert api.handle("GET", "/v1/nodes").body["schema"] == "list"
    assert api.handle("GET", "/v1/nodes/node-a").body["node_id"] == "node-a"
    assert api.handle("GET", "/v1/nodes/node-a/capabilities").body["schema"] == "caps"
    assert api.handle("GET", "/v1/capabilities/camera.observe/nodes").body["capability"] == "camera.observe"


def test_routes_decode_capability_and_fail_closed_on_unknown_paths() -> None:
    api = _api()
    response = api.handle("GET", "/v1/capabilities/camera%2Eobserve/nodes")
    assert response.status == 200
    assert response.body["capability"] == "camera.observe"

    missing = api.handle("GET", "/v1/nodes/missing")
    assert missing.status == 404
    assert missing.body["error"] == "not_found"

    unknown = api.handle("POST", "/v1/nodes")
    assert unknown.status == 404
    assert unknown.body["error"] == "route_not_found"
