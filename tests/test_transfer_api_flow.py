"""Critical API flow regression: search candidates -> async transfer -> task center."""

from moviesync.app import create_app


def test_search_to_transfer_task_center_flow(tmp_path, monkeypatch):
    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    client = app.test_client()
    try:
        setup = client.post(
            "/api/setup",
            json={"username": "admin", "password": "password123"},
        )
        assert setup.status_code == 200
        with client.session_transaction() as session:
            csrf_token = session["csrf_token"]
        headers = {"X-CSRF-Token": csrf_token}

        candidate = {
            "source_id": "telegram",
            "source_name": "Telegram",
            "channel": "demo",
            "pwd_id": "share123",
            "files": [{"fid": "file1", "file_name": "Show.S01E01.mkv"}],
        }
        monkeypatch.setattr(
            services["search"],
            "search_movie_candidates",
            lambda movie, config: [candidate],
        )

        searched = client.post(
            "/api/search-candidates",
            json={"movies": [{"title": "Test Show"}]},
            headers=headers,
        )
        assert searched.status_code == 200
        search_body = searched.get_json()
        assert search_body["success"] is True
        assert search_body["candidates_map"]["Test Show"] == [candidate]
        assert "stoken" not in str(search_body)

        def transfer(movie, selected_candidate, target_fid, config, progress):
            assert movie["title"] == "Test Show"
            assert selected_candidate["pwd_id"] == "share123"
            assert target_fid == "0"
            progress(80, "转存中")
            return True, "转存成功", {"success": 1, "skipped": 0, "failed": 0}

        monkeypatch.setattr(
            services["search"],
            "transfer_selected_resource_with_progress",
            transfer,
        )
        submitted = client.post(
            "/api/transfer-selected",
            json={
                "movie": {"title": "Test Show"},
                "candidate": candidate,
                "target_fid": "0",
            },
            headers=headers,
        )
        assert submitted.status_code == 200
        task_body = submitted.get_json()
        assert task_body["success"] is True
        task_id = task_body["task"]["id"]
        assert "retry_payload" not in task_body["task"]
        assert "dedupe_key" not in task_body["task"]

        # Wait for the actual background task to finish before reading the task center.
        services["tasks"].executor.shutdown(wait=True)
        listed = client.get("/api/tasks")
        assert listed.status_code == 200
        task = next(item for item in listed.get_json()["tasks"] if item["id"] == task_id)
        assert task["status"] == "success"
        assert task["title"] == "Test Show"
        assert "retry_payload" not in task

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.get_json()["task"]["status"] == "success"
        assert "retry_payload" not in detail.get_json()["task"]
    finally:
        services["tasks"].shutdown()
        services["subscriptions"].stop_scheduler()

def test_transfer_rejects_empty_or_malformed_file_selection(tmp_path):
    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    client = app.test_client()
    try:
        setup = client.post(
            "/api/setup",
            json={"username": "admin", "password": "password123"},
        )
        assert setup.status_code == 200
        with client.session_transaction() as session:
            headers = {"X-CSRF-Token": session["csrf_token"]}

        invalid_files = [
            [],
            ["not-a-file-object"],
            [{"file_name": "episode.mkv"}],
            [None],
        ]
        for files in invalid_files:
            response = client.post(
                "/api/transfer-selected",
                json={
                    "movie": {"title": "Validation Test"},
                    "candidate": {
                        "source_id": "test-source",
                        "pwd_id": "share123",
                        "files": files,
                    },
                    "target_fid": "0",
                },
                headers=headers,
            )
            assert response.status_code == 400
            assert response.get_json()["success"] is False

        assert services["tasks"].list_tasks() == []
    finally:
        services["tasks"].shutdown()
        services["subscriptions"].stop_scheduler()
