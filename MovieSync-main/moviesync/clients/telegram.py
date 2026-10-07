from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .http import ApiError, HttpClient

CHANNEL_RE = re.compile(r"^[A-Za-z0-9_]{2,64}$")
QUARK_RE = re.compile(r"(?:https?://)?(?:pan\.)?quark\.cn/s/([A-Za-z0-9]+)", re.IGNORECASE)
TG_HEADERS = {"User-Agent": "Mozilla/5.0"}


def normalize_channel_id(value: object) -> str:
    channel_id = str(value or "").strip().lstrip("@")
    return channel_id if CHANNEL_RE.fullmatch(channel_id) else ""


class TelegramClient:
    def __init__(self):
        self.http = HttpClient(TG_HEADERS)

    def check_channel(self, channel: object) -> bool:
        channel_id = normalize_channel_id(channel.get("id", "") if isinstance(channel, dict) else channel)
        if not channel_id:
            return False
        try:
            response = self.http.session.get(f"https://t.me/s/{quote(channel_id)}", timeout=4)
            return response.status_code == 200 and "tgme_channel_info" in response.text
        except Exception:
            return False

    def search_channel(self, channel: object, title: str) -> list[dict]:
        if isinstance(channel, dict):
            channel_id = normalize_channel_id(channel.get("id"))
            channel_name = str(channel.get("name") or channel_id).strip()
        else:
            channel_id = normalize_channel_id(channel)
            channel_name = channel_id
        if not channel_id:
            return []

        response = self.http.session.get(
            f"https://t.me/s/{quote(channel_id)}?q={quote(title)}",
            timeout=5,
        )
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        results: list[dict] = []
        simple_target = self._simplify(title)
        for message in soup.select("div.tgme_widget_message_text"):
            plain_text = message.get_text(" ", strip=True)
            simple_plain = self._simplify(plain_text)
            if title not in plain_text and (not simple_target or simple_target not in simple_plain):
                continue

            links = [anchor.get("href", "") for anchor in message.select("a[href]")]
            raw_sources = links + [plain_text]
            pwd_ids: list[str] = []
            seen: set[str] = set()
            for raw in raw_sources:
                for pwd_id in QUARK_RE.findall(raw or ""):
                    if pwd_id not in seen:
                        seen.add(pwd_id)
                        pwd_ids.append(pwd_id)
            for pwd_id in pwd_ids:
                results.append({"channel": channel_name, "pwd_id": pwd_id})
        return results

    @staticmethod
    def _simplify(value: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fa5]", "", value or "")
