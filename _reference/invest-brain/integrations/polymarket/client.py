from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
import json
import socket
import time
import urllib.error
import urllib.request

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"
USER_AGENT = "invest-brain-polymarket-readonly/0.1"


class PolymarketAPIError(RuntimeError):
    pass


@dataclass
class PolymarketClient:
    timeout: int = 20
    sleep_seconds: float = 0.05

    def _get_json(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise PolymarketAPIError(f"HTTP {exc.code} for {url}") from exc
        except urllib.error.URLError as exc:
            raise PolymarketAPIError(f"URL error for {url}: {exc.reason}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise PolymarketAPIError(f"timeout for {url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise PolymarketAPIError(f"invalid JSON for {url}: {exc}") from exc
        finally:
            if self.sleep_seconds:
                time.sleep(self.sleep_seconds)

    def public_search(self, query: str, limit: int = 10) -> dict[str, Any]:
        url = f"{GAMMA_BASE}/public-search?{urlencode({'q': query, 'limit': limit})}"
        data = self._get_json(url)
        if not isinstance(data, dict):
            raise PolymarketAPIError("public-search returned non-object payload")
        return data

    def event(self, event_id: str) -> dict[str, Any]:
        data = self._get_json(f"{GAMMA_BASE}/events/{event_id}")
        if not isinstance(data, dict):
            raise PolymarketAPIError(f"event {event_id} returned non-object payload")
        return data

    def price(self, token_id: str, side: str) -> dict[str, Any]:
        side_value = side.lower()
        if side_value not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        return self._get_json(f"{CLOB_BASE}/price?{urlencode({'token_id': token_id, 'side': side_value})}")

    def orderbook(self, token_id: str) -> dict[str, Any]:
        data = self._get_json(f"{CLOB_BASE}/book?{urlencode({'token_id': token_id})}")
        if not isinstance(data, dict):
            raise PolymarketAPIError("orderbook returned non-object payload")
        return data

    def trades(self, condition_id: str, limit: int = 5) -> list[dict[str, Any]]:
        data = self._get_json(f"{DATA_BASE}/trades?{urlencode({'market': condition_id, 'limit': limit})}")
        if not isinstance(data, list):
            raise PolymarketAPIError("trades returned non-list payload")
        return data
