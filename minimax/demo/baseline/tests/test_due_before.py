"""Target tests for the SDD change: the due_before upper-bound filter.

These tests are identical in the before and after trees. They must fail before
the change because the target behaviour is absent, and pass after the change.
"""

from __future__ import annotations


def test_due_before_includes_boundary_day(client):
    response = client.get("/tasks?due_before=2026-01-31&limit=100")
    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] == 4
    assert [item["id"] for item in body["items"]] == [1, 2, 4, 7]
    assert all(item["due_date"] <= "2026-01-31" for item in body["items"])


def test_due_before_combines_with_status_and_pagination(client):
    filtered = client.get("/tasks?due_before=2026-01-31&status=todo").get_json()
    assert filtered["total"] == 2
    assert [item["id"] for item in filtered["items"]] == [1, 2]

    page = client.get("/tasks?due_before=2026-01-31&status=todo&limit=1&offset=1").get_json()
    assert page["total"] == 2
    assert page["limit"] == 1
    assert page["offset"] == 1
    assert [item["id"] for item in page["items"]] == [2]


def test_due_before_invalid_date_returns_400(client):
    for value in ("2026-13-01", "not-a-date", "2026-02-30"):
        response = client.get(f"/tasks?due_before={value}")
        assert response.status_code == 400, value
        error = response.get_json()["error"]
        assert error["code"] == "invalid_argument"
        assert error["field"] == "due_before"


def test_due_before_excludes_tasks_without_due_date(client):
    body = client.get("/tasks?due_before=2026-12-31").get_json()
    assert body["total"] == 7
    assert 5 not in {item["id"] for item in body["items"]}
    assert all(item["due_date"] is not None for item in body["items"])


def test_due_before_empty_result_keeps_metadata(client):
    body = client.get("/tasks?due_before=2025-01-01").get_json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["limit"] == 50
    assert body["offset"] == 0
