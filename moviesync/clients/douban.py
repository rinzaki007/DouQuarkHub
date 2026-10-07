from __future__ import annotations

import json
from urllib.parse import quote

from .http import ApiError, HttpClient

DOUBAN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://movie.douban.com/explore",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


class DoubanClient:
    def __init__(self):
        self.http = HttpClient(DOUBAN_HEADERS)

    def get_movies(self, tag: str, sort_type: str) -> list[dict]:
        tag = tag if tag in {"电影", "电视剧", "综艺", "动漫"} else "电影"
        sort_type = sort_type if sort_type in {"U", "T", "R"} else "U"
        if tag == "电影":
            url = "https://m.douban.com/rexxar/api/v2/subject/recent_hot/movie"
            params = {
                "start": "0",
                "limit": "100",
                "category": "最新" if sort_type in {"T", "R"} else "热门",
                "type": "全部",
            }
        else:
            url = "https://m.douban.com/rexxar/api/v2/tv/recommend"
            cat_map = {
                "动漫": {"类型": "动画", "形式": "电视剧"},
                "综艺": {"类型": "", "形式": "综艺"},
                "电视剧": {"类型": "", "形式": "电视剧"},
            }
            params = {
                "refresh": "0",
                "start": "0",
                "count": "100",
                "selected_categories": json.dumps(cat_map[tag], ensure_ascii=False),
                "tags": tag,
                "sort": "R" if sort_type in {"T", "R"} else "U",
            }
        response, payload = self.http.request_json(
            "GET",
            url,
            timeout=10,
            retries=1,
            params=params,
        )

        if response.status_code != 200:
            raise ApiError(f"豆瓣返回 HTTP {response.status_code}")

        items = self._extract_items(payload)

        # 豆瓣移动端接口偶尔会调整 recent_hot 的响应或直接拒绝请求。
        # 电影列表失败时，回退到仍在使用的 movie/recommend 接口。
        if not items and tag == "电影":
            fallback_params = {
                "refresh": "0",
                "start": "0",
                "count": "100",
                "selected_categories": json.dumps(
                    {"类型": ""},
                    ensure_ascii=False,
                ),
                "uncollect": "false",
                "tags": "",
            }
            fallback_response, fallback_payload = self.http.request_json(
                "GET",
                "https://m.douban.com/rexxar/api/v2/movie/recommend",
                timeout=10,
                retries=1,
                params=fallback_params,
            )
            if fallback_response.status_code == 200:
                items = self._extract_items(fallback_payload)

        return [
            self._normalize_item(item)
            for item in items
            if isinstance(item, dict) and item.get("title")
        ]

    @staticmethod
    def _extract_items(payload: object) -> list[dict]:
        if isinstance(payload, list):
            return [
                item for item in payload
                if isinstance(item, dict)
            ]

        if not isinstance(payload, dict):
            return []

        for key in (
            "subjects",
            "items",
            "subject_collection_items",
            "recommend_items",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return [
                    item for item in value
                    if isinstance(item, dict)
                ]

        return []

    def search(self, query: str) -> list[dict]:
        query = str(query or "").strip()
        if not query:
            return []
        response, payload = self.http.request_json(
            "GET",
            f"https://movie.douban.com/j/subject_suggest?q={quote(query)}",
            timeout=8,
            retries=1,
        )
        if response.status_code != 200 or not isinstance(payload, list):
            raise ApiError(f"豆瓣搜索失败（HTTP {response.status_code}）")
        return [
            {
                "title": item.get("title"),
                "cover": item.get("img", ""),
                "rate": item.get("year", "搜索"),
                "url": f"https://movie.douban.com/subject/{item.get('id')}/",
            }
            for item in payload
            if item.get("title") and item.get("id")
        ]

    @staticmethod
    def _normalize_item(item: dict) -> dict:
        subject_id = item.get("id") or (item.get("target") or {}).get("id")
        rating = (item.get("rating") or {}).get("value", "暂无")
        pic = item.get("pic") or {}
        cover_data = item.get("cover") or {}
        cover = (
            pic.get("normal")
            or pic.get("large")
            or cover_data.get("url")
            or item.get("cover_url", "")
            or ""
        )
        return {
            "title": item.get("title"),
            "cover": cover,
            "rate": str(rating),
            "url": f"https://movie.douban.com/subject/{subject_id}/" if subject_id else "https://movie.douban.com/",
        }
