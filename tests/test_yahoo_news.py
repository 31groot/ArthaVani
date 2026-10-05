from finance_agent.providers import yahoo as yahoo_module
from finance_agent.providers.yahoo import YahooProvider


def test_news_uses_yahoo(monkeypatch):
    yahoo_module._news_cache.clear()

    class FakeTicker:
        def get_news(self, count):
            return [
                {
                    "content": {
                        "title": "Yahoo headline",
                        "provider": {"displayName": "Yahoo"},
                        "pubDate": "2026-10-06T00:00:00Z",
                        "canonicalUrl": {
                            "url": "https://example.com/yahoo",
                        },
                    }
                }
            ]

    monkeypatch.setattr(
        YahooProvider,
        "ticker",
        staticmethod(lambda symbol: FakeTicker()),
    )

    monkeypatch.setattr(
        yahoo_module,
        "_google_news_rss",
        lambda symbol, count: [],
    )

    result = YahooProvider().news("^NSEI", 3)

    assert len(result) == 1
    assert result[0]["title"] == "Yahoo headline"
    assert result[0]["publisher"] == "Yahoo"


def test_news_falls_back_to_google_rss(monkeypatch):
    yahoo_module._news_cache.clear()

    class FakeTicker:
        def get_news(self, count):
            raise RuntimeError("Yahoo rate limited")

    monkeypatch.setattr(
        YahooProvider,
        "ticker",
        staticmethod(lambda symbol: FakeTicker()),
    )

    monkeypatch.setattr(
        yahoo_module,
        "_google_news_rss",
        lambda symbol, count: [
            {
                "title": "RSS fallback headline",
                "publisher": "Investing.com India",
                "published": "Mon, 05 Oct 2026 16:29:48 GMT",
                "url": "https://example.com/rss",
            }
        ],
    )

    result = YahooProvider().news("^NSEI", 3)

    assert len(result) == 1
    assert result[0]["title"] == "RSS fallback headline"
    assert result[0]["publisher"] == "Investing.com India"


def test_news_uses_cache(monkeypatch):
    yahoo_module._news_cache.clear()

    calls = {"count": 0}

    class FakeTicker:
        def get_news(self, count):
            calls["count"] += 1
            return [
                {
                    "content": {
                        "title": "Cached headline",
                        "provider": {"displayName": "Yahoo"},
                        "pubDate": "2026-10-06T00:00:00Z",
                        "canonicalUrl": {
                            "url": "https://example.com/cached",
                        },
                    }
                }
            ]

    monkeypatch.setattr(
        YahooProvider,
        "ticker",
        staticmethod(lambda symbol: FakeTicker()),
    )

    monkeypatch.setattr(
        yahoo_module,
        "_google_news_rss",
        lambda symbol, count: [],
    )

    provider = YahooProvider()

    first = provider.news("^NSEI", 3)
    second = provider.news("^NSEI", 3)

    assert first == second
    assert calls["count"] == 1
