import re
from urllib.parse import urlsplit

_ALLOWED_HOSTS = {
    "x.com",
    "www.x.com",
    "mobile.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
}

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_POST_ID_RE = re.compile(r"^[0-9]{1,20}$")


def _reject_url_features(value: str, parsed) -> None:
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or ":" in parsed.netloc
    ):
        raise ValueError(f"URL with credentials or port is not allowed: {value}")


def _reject_prefix(value: str) -> str:
    if value.startswith("@"):
        return value[1:]
    return value


def parse_username(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid X user locator: {value!r}")

    candidate = value.strip()
    if not candidate:
        raise ValueError("Invalid X user locator: empty value")

    parsed = urlsplit(candidate)
    if parsed.scheme in ("http", "https"):
        host = (parsed.hostname or "").lower()
        if host not in _ALLOWED_HOSTS:
            raise ValueError(f"Unrelated URL is not an X user locator: {value}")

        _reject_url_features(value, parsed)

        segments = parsed.path.removeprefix("/").removesuffix("/").split("/")
        if len(segments) != 1:
            raise ValueError(f"Invalid X user URL: {value}")

        username = _reject_prefix(segments[0])
    else:
        if "/" in candidate:
            raise ValueError(f"Invalid X user locator: {value}")
        username = _reject_prefix(candidate)

    if not _USERNAME_RE.fullmatch(username):
        raise ValueError(f"Invalid X username: {value}")

    return username


def parse_post_locator(value: str | int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Invalid X post locator: {value!r}")

    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"Invalid X post locator: {value}")
        return value

    if not isinstance(value, str):
        raise ValueError(f"Invalid X post locator: {value!r}")

    candidate = value.strip()
    if len(candidate) >= 2 and candidate[0] in "\"'" and candidate[-1] == candidate[0]:
        candidate = candidate[1:-1]
    if not candidate:
        raise ValueError("Invalid X post locator: empty value")

    parsed = urlsplit(candidate)
    if parsed.scheme in ("http", "https"):
        host = (parsed.hostname or "").lower()
        if host not in _ALLOWED_HOSTS:
            raise ValueError(f"Unrelated URL is not an X post locator: {value}")

        _reject_url_features(value, parsed)

        segments = parsed.path.removeprefix("/").removesuffix("/").split("/")
        if (
            len(segments) != 3
            or segments[1] != "status"
            or not _USERNAME_RE.fullmatch(segments[0])
        ):
            raise ValueError(f"Invalid X post URL: {value}")

        post_id = segments[2]
    else:
        post_id = candidate

    if not _POST_ID_RE.fullmatch(post_id):
        raise ValueError(f"Invalid X post ID: {value}")

    result = int(post_id)
    if result <= 0:
        raise ValueError(f"Invalid X post ID: {value}")

    return result
