"""Regression tests: these behaviours must keep working after the change."""

from __future__ import annotations


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_list_returns_seed_rows_and_pagination_metadata(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] == 8
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert [item["id"] for item in body["items"]] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert body["items"][0]["title"] == "Fix login redirect"
    assert body["items"][0]["due_date"] == "2026-01-30"


def test_status_filter(client):
    body = client.get("/tasks?status=todo").get_json()
    assert body["total"] == 4
    assert {item["id"] for item in body["items"]} == {1, 2, 5, 8}


def test_priority_filter(client):
    body = client.get("/tasks?priority=high").get_json()
    assert body["total"] == 3
    assert {item["id"] for item in body["items"]} == {1, 4, 8}


def test_assignee_filter(client):
    body = client.get("/tasks?assignee=alice").get_json()
    assert body["total"] == 4
    assert {item["id"] for item in body["items"]} == {1, 3, 5, 8}


def test_filters_compose_and_pagination_offsets(client):
    body = client.get("/tasks?status=todo&priority=high").get_json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [1, 8]

    page = client.get("/tasks?limit=3&offset=2").get_json()
    assert page["total"] == 8
    assert [item["id"] for item in page["items"]] == [3, 4, 5]


def test_create_read_update_delete(client):
    created = client.post(
        "/tasks",
        json={
            "title": "Write release notes",
            "description": "Summarise the due_before change",
            "status": "todo",
            "priority": "medium",
            "assignee": "dana",
            "due_date": "2026-02-20",
        },
    )
    assert created.status_code == 201
    task = created.get_json()
    assert task["id"] == 9
    assert task["due_date"] == "2026-02-20"

    fetched = client.get(f"/tasks/{task['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["title"] == "Write release notes"

    updated = client.patch(f"/tasks/{task['id']}", json={"status": "done", "priority": "high"})
    assert updated.status_code == 200
    assert updated.get_json()["status"] == "done"
    assert updated.get_json()["priority"] == "high"

    deleted = client.delete(f"/tasks/{task['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/tasks/{task['id']}").status_code == 404


def test_create_validation_errors_use_json_error_shape(client):
    response = client.post("/tasks", json={"title": " ", "status": "todo"})
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == "invalid_argument"
    assert error["field"] == "title"


def test_invalid_status_and_limit_are_rejected(client):
    assert client.get("/tasks?status=blocked").status_code == 400
    assert client.get("/tasks?limit=0").status_code == 400
    assert client.get("/tasks?limit=abc").status_code == 400


def test_missing_task_returns_404_json(client):
    response = client.get("/tasks/999")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_unknown_route_returns_404_json(client):
    response = client.get("/no-such-route")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_create_rejects_invalid_date(client):
    response = client.post("/tasks", json={"title": "Bad date", "due_date": "2026-02-30"})
    assert response.status_code == 400
    assert response.get_json()["error"]["field"] == "due_date"
