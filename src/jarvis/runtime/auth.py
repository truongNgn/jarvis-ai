import hmac
from urllib.parse import urlsplit

from jarvis.runtime.protocol import Rejected


def authorize(headers, token):
    if headers.get("origin") is not None:
        raise Rejected("browser_origin_forbidden")
    host = headers.get("host", "")
    if host not in {"127.0.0.1:18765", "localhost:18765", "broker:18765"}:
        raise Rejected("host_forbidden")
    supplied = headers.get("authorization", "")
    if not hmac.compare_digest(supplied, "Bearer " + token):
        raise Rejected("unauthorized")


def endpoint(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.port != 18765 or parsed.path not in {"", "/"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise Rejected("non_loopback_broker")
    return url.rstrip("/")
