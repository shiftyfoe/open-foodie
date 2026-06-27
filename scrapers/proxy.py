"""Proxy manager — fetches, tests, and rotates free HTTPS proxies."""

import re
import random
import requests

# User-agent for proxy fetching/testing
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def fetch_proxies_from_proxyscrape() -> list[str]:
    """Fetch HTTPS proxies from proxyscrape API."""
    url = (
        "https://api.proxyscrape.com/v4/"
        "free-proxy-list/get?request=display_proxies"
        "&proxy_format=protocolipport&format=text&protocol=http&timeout=5000"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        lines = resp.text.strip().splitlines()
        return [line.strip() for line in lines if line.strip()]
    except Exception as exc:
        print(f"  ⚠ proxyscrape fetch failed: {exc}")
        return []


def fetch_proxies_from_geonode() -> list[str]:
    """Fetch HTTPS proxies from geonode API."""
    url = (
        "https://proxylist.geonode.com/api/proxy-list"
        "?limit=50&page=1&sort_by=lastChecked&sort_type=desc"
        "&protocols=https%2Chttp&speed=fast"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        proxies = []
        for item in data.get("data", []):
            ip = item.get("ip")
            port = item.get("port")
            protocols = item.get("protocols", [])
            if ip and port:
                proto = "https" if "https" in protocols else "http"
                proxies.append(f"{proto}://{ip}:{port}")
        return proxies
    except Exception as exc:
        print(f"  ⚠ geonode fetch failed: {exc}")
        return []


def fetch_proxies() -> list[str]:
    """Fetch proxies from multiple sources, deduplicate."""
    all_proxies = []
    all_proxies.extend(fetch_proxies_from_proxyscrape())
    all_proxies.extend(fetch_proxies_from_geonode())
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in all_proxies:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def test_proxy(proxy_url: str, url: str = "https://httpbin.org/ip", timeout: int = 8) -> bool:
    """Test if a proxy can reach a URL."""
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        resp = requests.get(url, proxies=proxies, timeout=timeout, headers={"User-Agent": _UA})
        return resp.status_code == 200
    except Exception:
        return False


def test_instagram_proxy(proxy_url: str, timeout: int = 10) -> bool:
    """Test if a proxy can reach Instagram without being blocked."""
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        resp = requests.get(
            "https://www.instagram.com/instagram/",
            proxies=proxies,
            timeout=timeout,
            headers={"User-Agent": _UA},
            allow_redirects=True,
        )
        if resp.status_code == 200:
            # Check we didn't get redirected to login
            return "/accounts/login" not in resp.url
        return False
    except Exception:
        return False


class ProxyPool:
    """Round-robin proxy pool with dead-proxy removal."""

    def __init__(self, proxies: list[str] | None = None):
        self._proxies = list(proxies or [])
        self._index = 0

    def __len__(self) -> int:
        return len(self._proxies)

    def __bool__(self) -> bool:
        return bool(self._proxies)

    def get(self) -> dict:
        """Get next proxy as requests-compatible dict, or empty dict if pool is empty."""
        if not self._proxies:
            return {}
        proxy = self._proxies[self._index % len(self._proxies)]
        self._index += 1
        return {"http": proxy, "https": proxy}

    def remove(self, proxy_url: str) -> None:
        """Remove a dead proxy from the pool."""
        if proxy_url in self._proxies:
            self._proxies.remove(proxy_url)
            # Adjust index if needed
            if self._index >= len(self._proxies) and self._proxies:
                self._index = self._index % len(self._proxies)

    @classmethod
    def build(cls, min_working: int = 3, test_ig: bool = False) -> "ProxyPool":
        """Fetch proxies, test them, return a pool of working ones."""
        print("  Fetching proxies...")
        raw = fetch_proxies()
        print(f"  Got {len(raw)} raw proxies")

        if not raw:
            return cls()

        # Test proxies (sample up to 20 to avoid slow builds)
        sample = random.sample(raw, min(20, len(raw)))
        working = []
        for proxy in sample:
            if test_ig:
                ok = test_instagram_proxy(proxy)
                label = "IG"
            else:
                ok = test_proxy(proxy)
                label = "httpbin"
            if ok:
                working.append(proxy)
                print(f"  ✓ {proxy} ({label})")
            if len(working) >= min_working:
                break

        print(f"  {len(working)}/{len(sample)} proxies working")
        return cls(working)
