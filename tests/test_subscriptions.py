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
    assert "成功追更 1 项" in message
    assert storage.transfers == [("share45", ["ep45"])]


def test_channel_subscription_uses_season_and_episode_baseline(tmp_path):
    cases = [
        (
            "season-one",
            "Show.S01E08.mkv",
            ["ep201", "ep202"],
        ),
        (
            "season-two",
            "Show.S02E01.mkv",
            ["ep202"],
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
    assert "成功追更 2 项" in message
    assert storage.transfers == [("share-seasons", ["ep208", "ep301"])]


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
    assert "成功追更 2 项" in message
    assert storage.transfers == [
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
    assert "成功追更 1 项" in message
    assert storage.transfers == [("share-selected", ["ep109"])]
