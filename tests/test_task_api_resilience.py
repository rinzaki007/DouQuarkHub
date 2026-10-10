"""Task center API resilience regression tests."""

from moviesync.app import create_app


def test_task_center_handles_malformed_persisted_timestamps(tmp_path):
    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    client = app.test_client()
    try:
        setup = client.post(
            "/api/setup",
            json={"username": "admin", "password": "password123"},
        )
        assert setup.status_code == 200

        services["tasks"].store.write([
            {
                "id": "malformed-time",
                "type": "transfer",
                "status": "success",
                "title": "旧任务",
                "updated_at": "not-a-timestamp",
                "created_at": None,
                "events": [],
            },
            {
                "id": "recent-task",
                "type": "transfer",
                "status": "success",
                "title": "新任务",
                "updated_at": 100,
                "created_at": 100,
                "events": [],
            },
            {
                "id": "non-finite-time",
                "type": "transfer",
                "status": "success",
                "title": "异常时间任务",
                "updated_at": float("nan"),
                "created_at": float("inf"),
                "events": [],
            },
        ])

        response = client.get("/api/tasks")
        assert response.status_code == 200
        tasks = response.get_json()["tasks"]
        assert [task["id"] for task in tasks] == [
            "recent-task",
            "malformed-time",
            "non-finite-time",
        ]
    finally:
        services["tasks"].shutdown()
        services["subscriptions"].stop_scheduler()
