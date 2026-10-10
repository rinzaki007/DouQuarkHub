"""Regression tests for lazy compatibility clients."""


def test_lazy_telegram_client_is_shared_after_first_access(monkeypatch):
    import moviesync.clients.telegram as telegram_module
    from moviesync.clients.compat import LazyTelegramClient

    created = []

    class FakeTelegramClient:
        def __init__(self):
            created.append(self)

        def check_channel(self, channel):
            return channel == "demo"

    monkeypatch.setattr(telegram_module, "TelegramClient", FakeTelegramClient)
    proxy = LazyTelegramClient()

    assert proxy._client is None
    assert proxy.check_channel("demo") is True
    assert proxy._client is created[0]
    assert proxy._get_client() is created[0]



def test_builtin_telegram_card_does_not_require_legacy_context_client(monkeypatch):
    import card_templates.telegram as card_module

    class OwnedClient:
        pass

    monkeypatch.setattr(card_module, "TelegramClient", OwnedClient)
    card = card_module.create_card({"config_store": object()})

    assert isinstance(card.client, OwnedClient)
