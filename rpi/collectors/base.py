"""Collector framework: polite HTTP, immutable raw snapshots, normalised Observation records."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import time
import urllib.robotparser
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests


@dataclass
class Observation:
    obs_date: dt.date
    source_id: str
    source_sku: str
    title: str
    item_id: str
    pincode: str
    price: float
    regular_price: float | None = None
    qty_base: float | None = None
    base_unit: str | None = None       # 'g' | 'ml' | 'pc'
    in_stock: bool = True
    on_promo: bool = False
    delivery_fee: float = 0.0


class Collector(ABC):
    source_id: str
    last_snapshot_id: int | None = None

    @abstractmethod
    def collect(self, on_date: dt.date):
        """Yield Observation objects."""


class RobotsDisallowed(RuntimeError):
    pass


def robots_allows(robots_txt: str, user_agent: str, url: str) -> bool:
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return rp.can_fetch(user_agent, url)


class PoliteClient:
    """HTTP client with rate limiting, retries, robots.txt compliance and an honest User-Agent.

    Deliberately has NO proxy rotation, CAPTCHA solving or bot-protection evasion.
    """

    def __init__(self, user_agent: str, min_delay: float = 2.0, timeout: float = 20.0,
                 retries: int = 3, respect_robots: bool = True, session=None,
                 sleep=time.sleep, clock=time.monotonic):
        self.ua, self.min_delay, self.timeout, self.retries = user_agent, min_delay, timeout, retries
        self.respect_robots = respect_robots
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._sleep, self._clock = sleep, clock
        self._last = {}          # host -> last request time
        self._robots = {}        # host -> robots.txt text ('' if none)

    def _wait(self, host: str):
        last = self._last.get(host)
        if last is not None:
            gap = self.min_delay - (self._clock() - last)
            if gap > 0:
                self._sleep(gap)
        self._last[host] = self._clock()

    def _check_robots(self, url: str):
        p = urlparse(url)
        host = f"{p.scheme}://{p.netloc}"
        if host not in self._robots:
            try:
                r = self.session.get(f"{host}/robots.txt", timeout=self.timeout)
                self._robots[host] = r.text if r.status_code == 200 else ""
            except requests.TooManyRedirects:
                self._robots[host] = ""          # robots.txt redirect-loops to the home page => none published
            except requests.RequestException:
                # Cannot verify -> be conservative
                raise RobotsDisallowed(f"could not fetch robots.txt for {host}; refusing to proceed")
        if not robots_allows(self._robots[host], self.ua, url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        if self.respect_robots:
            self._check_robots(url)
        host = urlparse(url).netloc
        last_exc = None
        for attempt in range(self.retries):
            self._wait(host)
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                if r.status_code in (429, 500, 502, 503, 504):
                    self._sleep(min(60, 2 ** attempt * 3))
                    last_exc = RuntimeError(f"HTTP {r.status_code}")
                    continue
                return r
            except requests.RequestException as e:
                last_exc = e
                self._sleep(min(60, 2 ** attempt * 3))
        raise RuntimeError(f"GET failed after {self.retries} attempts: {last_exc}")


class SnapshotStore:
    """Immutable, content-addressed raw payload archive + DB index (reproducibility)."""

    def __init__(self, conn, raw_dir: Path):
        self.conn, self.raw_dir = conn, Path(raw_dir)

    def save(self, source_id: str, url: str, params: dict | None, content: bytes,
             status: int, ext: str = "json") -> int:
        sha = hashlib.sha256(content).hexdigest()
        day = dt.date.today().isoformat()
        d = self.raw_dir / source_id / day
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{sha[:16]}.{ext}"
        if not path.exists():
            path.write_bytes(content)
        safe = {k: v for k, v in (params or {}).items() if "key" not in k.lower()}  # never store secrets
        cur = self.conn.execute(
            "INSERT INTO raw_snapshots(source_id,fetched_at,url,params_json,http_status,sha256,path,n_bytes) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (source_id, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), url,
             json.dumps(safe, sort_keys=True), status, sha, str(path), len(content)))
        self.conn.commit()
        return cur.lastrowid
