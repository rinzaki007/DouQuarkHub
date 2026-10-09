from moviesync.services.subscriptions import SubscriptionManager


class FakeStorageTargets:
    def resolve_resource(self, resource, target_id=None):
        return {
            "target_id": target_id or "demo-storage",
            "files": [
                {"fid": "ep1", "file_name": "Show.S01E01.1080p.mkv"},
                {"fid": "ep2", "file_name": "Show.S01E02.1080p.mkv"},
            ],
            "token": "token",
            "error": None,
        }

    def create_folder(self, name, parent_id="0", target_id=None):
        assert target_id == "demo-storage"
        return "folder-1"

    def transfer(self, resource, files, target_id="0", storage_target_id=None, token=None):
        assert storage_target_id == "demo-storage"
        assert token == "token"
        assert target_id == "folder-1"
        assert [item["fid"] for item in files] == ["ep1", "ep2"]
        return True, "ok"


class FakeResourceSources:
    def __init__(self):
        self.config_store = None
        self.shares = [
            {"channel": "demo", "pwd_id": "share1"},
            {"channel": "demo", "pwd_id": "share2"},
        ]

    def search_channel(self, source_id, channel, title):
        return list(self.shares)


class FakeLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


def test_subscription_uses_storage_target_card(tmp_path):
    manager = SubscriptionManager(
        tmp_path / "subscriptions.json",
        FakeStorageTargets(),
        FakeResourceSources(),
        FakeLogger(),
    )
    sub = manager.add_subscription(
        title="Show",
        pwd_id="share123",
        target_fid="0",
        storage_target_id="demo-storage",
    )

    ok, message = manager.check_subscription_now(sub["id"])

    assert ok is True
    assert "成功追更 2 项" in message
    saved = manager.get_subscriptions()[0]
    assert saved["storage_target_id"] == "demo-storage"
    assert saved["saved_episodes"] == [1, 2]


class DynamicStorageTargets(FakeStorageTargets):
    def __init__(self):
        self.files = [
            {"fid": "ep1", "file_name": "Show.S01E01.1080p.mkv"},
            {"fid": "ep2", "file_name": "Show.S01E02.1080p.mkv"},
        ]
        self.transfers = []

    def resolve_resource(self, resource, target_id=None):
        return {
            "target_id": target_id or "demo-storage",
            "files": list(self.files),
            "token": "token",
            "error": None,
        }

    def transfer(self, resource, files, target_id="0", storage_target_id=None, token=None):
        self.transfers.append([item["fid"] for item in files])
        return True, "ok"


def test_subscription_tracks_new_files_from_selected_source(tmp_path):
    storage = DynamicStorageTargets()
    manager = SubscriptionManager(
        tmp_path / "subscriptions.json",
        storage,
        FakeResourceSources(),
        FakeLogger(),
    )
    sub = manager.add_subscription(
        title="Show",
        pwd_id="share123",
        target_fid="0",
        storage_target_id="demo-storage",
        files=[{"fid": "ep1"}, {"fid": "ep2"}],
    )

    ok, message = manager.check_subscription_now(sub["id"])
    assert ok is True
    assert "暂无新更新" in message
    assert storage.transfers == []

    storage.files.append(
        {"fid": "ep3", "file_name": "Show.S01E03.1080p.mkv"}
    )

    ok, message = manager.check_subscription_now(sub["id"])
    assert ok is True
    assert "成功追更 1 项" in message
    assert storage.transfers == [["ep3"]]

    saved = manager.get_subscriptions()[0]
    assert "ep3" in saved["tracked_file_keys"]


class ChannelStorageTargets:
    def __init__(self):
        self.shares = {
            "share1": [
                {"fid": "ep1", "file_name": "Show.S01E01.mkv"},
            ],
            "share2": [
                {"fid": "ep2", "file_name": "Show.S01E02.mkv"},
            ],
        }
        self.transfers = []

    def resolve_resource(self, resource, target_id=None):
        pwd_id = resource["pwd_id"]
        return {
            "target_id": target_id or "demo-storage",
            "files": list(self.shares.get(pwd_id, [])),
            "token": "token-" + pwd_id,
            "error": None,
        }

    def create_folder(self, name, parent_id="0", target_id=None):
        return "folder-1"

    def transfer(self, resource, files, target_id="0", storage_target_id=None, token=None):
        self.transfers.append((resource["pwd_id"], [item["fid"] for item in files]))
        return True, "ok"


def test_subscription_monitors_selected_channel_shares(tmp_path):
    storage = ChannelStorageTargets()
    manager = SubscriptionManager(
        tmp_path / "subscriptions.json",
        storage,
        FakeResourceSources(),
        FakeLogger(),
    )
    sub = manager.add_subscription(
        title="Show",
        pwd_id="share1",
        target_fid="0",
        storage_target_id="demo-storage",
        source_id="telegram",
        channel="demo",
        files=[{"fid": "ep1"}],
    )

    ok, message = manager.check_subscription_now(sub["id"])
    assert ok is True
    assert "成功追更 1 项" in message
    assert storage.transfers == [("share2", ["ep2"])]

    storage.shares["share3"] = [
        {"fid": "ep3", "file_name": "Show.S01E03.mkv"},
    ]
    manager.resource_sources.shares.append(
        {"channel": "demo", "pwd_id": "share3"}
    )

    ok, message = manager.check_subscription_now(sub["id"])
    assert ok is True
    assert "成功追更 1 项" in message
    assert storage.transfers[-1] == ("share3", ["ep3"])


def test_channel_subscription_uses_selected_episode_as_baseline(tmp_path):
    storage = ChannelStorageTargets()
    storage.shares = {
        "share44": [
            {"fid": "ep44", "file_name": "Show.S01E44.mkv"},
        ],
        "share45": [
            {"fid": "ep45", "file_name": "Show.S01E45.mkv"},
        ],
        "share10": [
            {"fid": "ep10", "file_name": "Show.S01E10.mkv"},
        ],
    }
    sources = FakeResourceSources()
    sources.shares = [
        {"channel": "demo", "pwd_id": "share10"},
        {"channel": "demo", "pwd_id": "share44"},
        {"channel": "demo", "pwd_id": "share45"},
    ]
    manager = SubscriptionManager(
        tmp_path / "subscriptions.json",
        storage,
        sources,
        FakeLogger(),
    )
    sub = manager.add_subscription(
        title="Show",
        pwd_id="share44",
        target_fid="0",
        storage_target_id="demo-storage",
        source_id="telegram",
        channel="demo",
        files=[{"fid": "ep44", "file_name": "Show.S01E44.mkv"}],
    )

    ok, message = manager.check_subscription_now(sub["id"])

    assert ok is True
    assert "成功追更 2 项" in message
    assert storage.transfers == [("share44", ["ep44"]), ("share45", ["ep45"])]


def test_channel_subscription_uses_season_and_episode_baseline(tmp_path):
    cases = [
        (
            "season-one",
            "Show.S01E08.mkv",
            ["ep108", "ep201", "ep202"],
        ),
        (
            "season-two",
            "Show.S02E01.mkv",
            ["ep201", "ep202"],
        ),
    ]

    for case_name, selected_name, expected_fids in cases:
        storage = ChannelStorageTargets()
        storage.shares = {
            "share-seasons": [
                {"fid": "ep101", "file_name": "Show.S01E01.mkv"},
                {"fid": "ep108", "file_name": "Show.S01E08.mkv"},
                {"fid": "ep201", "file_name": "Show.S02E01.mkv"},
                {"fid": "ep202", "file_name": "Show.S02E02.mkv"},
            ],
        }
        sources = FakeResourceSources()
        sources.shares = [
            {"channel": "demo", "pwd_id": "share-seasons"},
        ]
        manager = SubscriptionManager(
            tmp_path / f"{case_name}.json",
            storage,
            sources,
            FakeLogger(),
        )
        selected_fid = "ep108" if "S01E08" in selected_name else "ep201"
        sub = manager.add_subscription(
            title="Show",
            pwd_id="share-seasons",
            target_fid="0",
            storage_target_id="demo-storage",
            source_id="telegram",
            channel="demo",
            files=[{"fid": selected_fid, "file_name": selected_name}],
        )

        ok, message = manager.check_subscription_now(sub["id"])

        assert ok is True
        assert "成功追更" in message
        assert [fid for _, fids in storage.transfers for fid in fids] == expected_fids



def test_channel_subscription_tracks_selected_episode_and_later_seasons_in_one_share(tmp_path):
    storage = ChannelStorageTargets()
    storage.shares = {
        "share-seasons": [
            {"fid": "ep207", "file_name": "Show.S02E07.mkv"},
            {"fid": "ep208", "file_name": "Show.S02E08.mkv"},
            {"fid": "ep301", "file_name": "Show.S03E01.mkv"},
        ],
    }
    sources = FakeResourceSources()
    sources.shares = [{"channel": "demo", "pwd_id": "share-seasons"}]
    manager = SubscriptionManager(
        tmp_path / "same-share.json",
        storage,
        sources,
        FakeLogger(),
    )

    sub = manager.add_subscription(
        title="Show",
        pwd_id="share-seasons",
        target_fid="0",
        storage_target_id="demo-storage",
        source_id="telegram",
        channel="demo",
        files=[{"fid": "ep207", "file_name": "Show.S02E07.mkv"}],
    )

    ok, message = manager.check_subscription_now(sub["id"])

    assert ok is True
    assert "成功追更 3 项" in message
    assert storage.transfers == [("share-seasons", ["ep207", "ep208", "ep301"])]


def test_channel_subscription_tracks_later_episodes_across_separate_shares(tmp_path):
    storage = ChannelStorageTargets()
    storage.shares = {
        "share-selected": [
            {"fid": "ep207", "file_name": "Show.S02E07.mkv"},
        ],
        "share-next": [
            {"fid": "ep208", "file_name": "Show.S02E08.mkv"},
        ],
        "share-next-season": [
            {"fid": "ep301", "file_name": "Show.S03E01.mkv"},
        ],
    }
    sources = FakeResourceSources()
    sources.shares = [
        {"channel": "demo", "pwd_id": "share-selected"},
        {"channel": "demo", "pwd_id": "share-next"},
        {"channel": "demo", "pwd_id": "share-next-season"},
    ]
    manager = SubscriptionManager(
        tmp_path / "multi-share.json",
        storage,
        sources,
        FakeLogger(),
    )

    sub = manager.add_subscription(
        title="Show",
        pwd_id="share-selected",
        target_fid="0",
        storage_target_id="demo-storage",
        source_id="telegram",
        channel="demo",
        files=[{"fid": "ep207", "file_name": "Show.S02E07.mkv"}],
    )

    ok, message = manager.check_subscription_now(sub["id"])

    assert ok is True
    assert "成功追更 3 项" in message
    assert storage.transfers == [
        ("share-selected", ["ep207"]),
        ("share-next", ["ep208"]),
        ("share-next-season", ["ep301"]),
    ]


def test_channel_subscription_checks_selected_share_when_channel_search_is_empty(tmp_path):
    storage = ChannelStorageTargets()
    storage.shares = {
        "share-selected": [
            {"fid": "ep108", "file_name": "Show.S01E08.mkv"},
            {"fid": "ep109", "file_name": "Show.S01E09.mkv"},
        ],
    }
    sources = FakeResourceSources()
    sources.shares = []
    manager = SubscriptionManager(
        tmp_path / "empty-channel-search.json",
        storage,
        sources,
        FakeLogger(),
    )

    sub = manager.add_subscription(
        title="Show",
        pwd_id="share-selected",
        target_fid="0",
        storage_target_id="demo-storage",
        source_id="telegram",
        channel="demo",
        files=[{"fid": "ep108", "file_name": "Show.S01E08.mkv"}],
    )

    ok, message = manager.check_subscription_now(sub["id"])

    assert ok is True
    assert "成功追更 2 项" in message
    assert storage.transfers == [("share-selected", ["ep108", "ep109"])]



def test_channel_subscription_checkpoints_successful_share_before_later_share_fails(tmp_path):
    class FailsOnceOnSecondShare(ChannelStorageTargets):
        def __init__(self):
            super().__init__()
            self.failed = False

        def transfer(self, resource, files, target_id="0", storage_target_id=None, token=None):
            if resource["pwd_id"] == "share2" and not self.failed:
                self.failed = True
                self.transfers.append((resource["pwd_id"], [item["fid"] for item in files]))
                return False, "模拟第二个分享转存失败"
            return super().transfer(resource, files, target_id, storage_target_id, token)

    storage = FailsOnceOnSecondShare()
    storage.shares = {
        "share1": [{"fid": "ep1", "file_name": "Show.S01E01.mkv"}],
        "share2": [{"fid": "ep2", "file_name": "Show.S01E02.mkv"}],
    }
    sources = FakeResourceSources()
    sources.shares = [{"channel": "demo", "pwd_id": "share1"}, {"channel": "demo", "pwd_id": "share2"}]
    manager = SubscriptionManager(tmp_path / "partial-success.json", storage, sources, FakeLogger())
    sub = manager.add_subscription(
        title="Show",
        pwd_id="share1",
        target_fid="0",
        storage_target_id="demo-storage",
        source_id="telegram",
        channel="demo",
        files=[{"fid": "ep1", "file_name": "Show.S01E01.mkv"}],
    )

    ok, message = manager.check_subscription_now(sub["id"])
    assert ok is False
    assert "转存失败" in message
    saved = manager.get_subscriptions()[0]
    assert "share1:ep1" in saved["tracked_file_keys"]
    assert "share1:ep1" in saved["saved_episodes"]

    ok, message = manager.check_subscription_now(sub["id"])
    assert ok is True
    assert "成功追更 1 项" in message
    assert storage.transfers.count(("share1", ["ep1"])) == 1
    assert storage.transfers.count(("share2", ["ep2"])) == 2


def test_uncertain_subscription_transfer_is_held_until_user_confirms(tmp_path):
    class UncertainStorage(ChannelStorageTargets):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def transfer(self, resource, files, target_id="0", storage_target_id=None, token=None):
            self.calls += 1
            return False, "转存结果不确定：请求可能已到达网盘"

    storage = UncertainStorage()
    storage.shares = {
        "share-selected": [{"fid": "ep1", "file_name": "Show.S01E01.mkv"}],
    }
    sources = FakeResourceSources()
    sources.shares = [{"channel": "demo", "pwd_id": "share-selected"}]
    manager = SubscriptionManager(
        tmp_path / "uncertain-transfer.json",
        storage,
        sources,
        FakeLogger(),
    )
    sub = manager.add_subscription(
        title="Show",
        pwd_id="share-selected",
        target_fid="0",
        storage_target_id="demo-storage",
        source_id="telegram",
        channel="demo",
        files=[{"fid": "ep1", "file_name": "Show.S01E01.mkv"}],
    )

    ok, message = manager.check_subscription_now(sub["id"])
    assert ok is False
    assert "转存结果不确定" in message
    saved = manager.get_subscriptions()[0]
    assert saved["pending_save_uncertain"] is True
    assert saved["pending_save_keys"] == ["share-selected:ep1"]

    ok, message = manager.check_subscription_now(sub["id"])
    assert ok is False
    assert "待核实" in message
    assert storage.calls == 1

    ok, message = manager.resolve_pending_save(sub["id"], "saved")
    assert ok is True
    saved = manager.get_subscriptions()[0]
    assert saved["pending_save_keys"] == []
    assert saved["pending_save_uncertain"] is False
    assert "share-selected:ep1" in saved["tracked_file_keys"]
    assert storage.calls == 1


def test_interrupted_subscription_with_pending_files_recovers_as_uncertain(tmp_path):
    import json

    path = tmp_path / "interrupted-subscriptions.json"
    path.write_text(
        json.dumps([{
            "id": "interrupted",
            "title": "Show",
            "pwd_id": "share",
            "status": "running",
            "pending_save_keys": ["share:file1"],
            "tracked_file_keys": [],
            "saved_episodes": [],
            "run_history": [],
        }]),
        encoding="utf-8",
    )
    manager = SubscriptionManager(path, ChannelStorageTargets(), FakeResourceSources(), FakeLogger())
    recovered = manager.get_subscriptions()[0]
    assert recovered["status"] == "failed"
    assert recovered["pending_save_uncertain"] is True
    ok, message = manager.check_subscription_now("interrupted")
    assert ok is False
    assert "待核实" in message



class SelectiveResolutionStorageTargets(ChannelStorageTargets):
    def __init__(self, broken_shares):
        super().__init__()
        self.broken_shares = set(broken_shares)

    def resolve_resource(self, resource, target_id=None):
        if resource["pwd_id"] in self.broken_shares:
            return {
                "target_id": target_id or "demo-storage",
                "files": [],
                "token": None,
                "error": "临时解析失败",
            }
        return super().resolve_resource(resource, target_id)


def test_channel_subscription_does_not_report_no_updates_when_all_shares_fail_resolution(tmp_path):
    storage = SelectiveResolutionStorage({"share1", "share2"})
    sources = FakeResourceSources()
    manager = SubscriptionManager(
        tmp_path / "all-shares-failed.json",
        storage,
        sources,
        FakeLogger(),
    )
    sub = manager.add_subscription(
        title="Show",
        pwd_id="share1",
        target_fid="0",
        storage_target_id="demo-storage",
        source_id="telegram",
        channel="demo",
        files=[{"fid": "ep1", "file_name": "Show.S01E01.mkv"}],
    )

    ok, message = manager.check_subscription_now(sub["id"])

    assert ok is False
    assert "频道资源解析失败" in message
    assert "暂无新更新" not in message
    saved = manager.get_subscriptions()[0]
    assert saved["status"] == "failed"
    assert saved["retry_count"] == 1
    assert storage.transfers == []


def test_channel_subscription_reports_partial_resolution_failure_without_resaving_successes(tmp_path):
    storage = SelectiveResolutionStorage({"share2"})
    sources = FakeResourceSources()
    manager = SubscriptionManager(
        tmp_path / "partial-share-failure.json",
        storage,
        sources,
        FakeLogger(),
    )
    sub = manager.add_subscription(
        title="Show",
        pwd_id="share1",
        target_fid="0",
        storage_target_id="demo-storage",
        source_id="telegram",
        channel="demo",
        files=[{"fid": "ep1", "file_name": "Show.S01E01.mkv"}],
    )

    ok, message = manager.check_subscription_now(sub["id"])

    assert ok is False
    assert "已转存 1 项" in message
    assert "部分频道资源解析失败" in message
    assert storage.transfers == [("share1", ["ep1"])]
    saved = manager.get_subscriptions()[0]
    assert "share1:ep1" in saved["tracked_file_keys"]
    assert saved["status"] == "failed"

    # A later retry still sees the already-recorded success and never submits it twice.
    ok, _ = manager.check_subscription_now(sub["id"])
    assert ok is False
    assert storage.transfers == [("share1", ["ep1"])]
