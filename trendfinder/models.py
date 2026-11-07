from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlparse


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_url(url: str) -> str:
    """Only HTTP(S) citations; never put tokens/credentials into reports."""
    try:
        p = urlparse(url)
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
            return ""
        sensitive = {"key", "api_key", "apikey", "token", "access_token", "auth", "signature", "sig"}
        query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in sensitive])
        return p._replace(query=query, fragment="").geturl()[:2048]
    except ValueError:
        return ""


@dataclass
class Candidate:
    id: str
    name: str
    aliases: list[str]
    query: str
    stack: str
    ram_gb: int
    setup: list[str]
    risks: list[str]
    cz_copy: str
    sk_copy: str
    project_id: str = ""


@dataclass
class Observation:
    candidate: str
    source: str
    family: str
    title: str
    url: str
    market: str = "GLOBAL"
    metric: str = "mention"
    value: float = 1.0
    published_at: str = ""
    series: list[dict] = field(default_factory=list)
    attrs: dict = field(default_factory=dict)
    observed_at: str = field(default_factory=utcnow)
    id: str = ""

    def __post_init__(self):
        self.title = self.title[:400]
        self.url = safe_url(self.url)
        if not self.id:
            key = f"{self.candidate}|{self.source}|{self.url}|{self.metric}|{self.market}"
            self.id = sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceResult:
    source: str
    state: str = "ok"
    message: str = ""
    observations: list[Observation] = field(default_factory=list)

    def status(self) -> dict:
        return {"source": self.source, "state": self.state, "message": self.message,
                "observations": len(self.observations)}
