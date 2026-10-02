"""requests Session that tolerates servers requiring TLS legacy renegotiation (e.g. api.mospi.gov.in).
This only relaxes a client-side OpenSSL3 compatibility flag; it does not bypass any access control."""
import ssl
import requests
from requests.adapters import HTTPAdapter

UA = "RajkotPriceIndex/0.1 (student research; contact: you@example.com)"


class _LegacyTLS(HTTPAdapter):
    def init_poolmanager(self, *a, **k):
        ctx = ssl.create_default_context()
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        k["ssl_context"] = ctx
        super().init_poolmanager(*a, **k)


def session(user_agent: str = UA) -> requests.Session:
    s = requests.Session()
    s.mount("https://", _LegacyTLS())
    s.headers["User-Agent"] = user_agent
    return s
