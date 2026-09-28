import pytest

from x_reader.locators import parse_post_locator, parse_username


@pytest.mark.parametrize(
    "value",
    [
        "synthwavedd",
        "@synthwavedd",
        "https://x.com/synthwavedd",
        "https://www.x.com/synthwavedd",
        "https://twitter.com/synthwavedd",
        "https://mobile.twitter.com/synthwavedd",
        "http://mobile.x.com/synthwavedd/",
        "https://x.com/synthwavedd/?lang=en#profile",
        "  @synthwavedd  ",
    ],
)
def test_user_locators_resolve_to_username(value: str):
    assert parse_username(value) == "synthwavedd"


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.com/synthwavedd",
        "https://x.com/a/b",
        "https://x.com/synthwavedd/status/123",
        "user!name",
        "a" * 16,
        "",
        "@",
        "https://x.com/",
        "https://user:pass@x.com/synthwavedd",
        "https://x.com:8443/synthwavedd",
        "https://x.com//synthwavedd",
        "https://x.com/synthwavedd//",
        "https://x.com/synthwavedd;params",
        "https://x.com/synthwavedd/;params",
        "https://x.com:/synthwavedd",
        "https://x.com:bad/synthwavedd",
        "https://x.com:99999/synthwavedd",
        "https://user@x.com/synthwavedd",
        "https://@x.com/synthwavedd",
        "https://x.com.evil.com/synthwavedd",
        "https://[x.com/synthwavedd",
        "https://x.com/%73ynthwavedd",
        "https://x.com/../synthwavedd",
        "ftp://x.com/synthwavedd",
        "//x.com/synthwavedd",
        None,
        123,
    ],
)
def test_invalid_user_locators_rejected(value):
    with pytest.raises(ValueError):
        parse_username(value)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2099846714345611773", 2099846714345611773),
        ('"2099846714345611773"', 2099846714345611773),
        (
            "https://x.com/synthwavedd/status/2099846714345611773",
            2099846714345611773,
        ),
        (
            "https://twitter.com/synthwavedd/status/2099846714345611773",
            2099846714345611773,
        ),
        (2099846714345611773, 2099846714345611773),
        (" '123' ", 123),
        ('"https://x.com/a/status/123"', 123),
        ("'https://twitter.com/a/status/123'", 123),
        ("https://mobile.x.com/A_1/status/123/?s=20#post", 123),
        ("http://www.twitter.com/a/status/123/", 123),
    ],
)
def test_post_locators_resolve_to_numeric_id(value, expected: int):
    assert parse_post_locator(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.com/synthwavedd/status/123",
        "https://x.com/synthwavedd/status/abc",
        "https://x.com/synthwavedd/status/123/photo",
        "0",
        "-5",
        True,
        None,
        "",
        "12.5",
        "https://user:pass@x.com/a/status/123",
        "https://x.com:8443/a/status/123",
        "https://x.com:/a/status/123",
        "https://x.com:bad/a/status/123",
        "https://x.com:99999/a/status/123",
        "https://user@x.com/a/status/123",
        "https://@x.com/a/status/123",
        "https://x.com//a/status/123",
        "https://x.com/a//status/123",
        "https://x.com/a/status//123",
        "https://x.com/a/status/123//",
        "https://x.com/a/status/123;params",
        "https://x.com/a/status/123/;params",
        "https://x.com/a/status/123/extra",
        "https://x.com/@a/status/123",
        "https://x.com/a-b/status/123",
        "https://x.com/a.b/status/123",
        "https://x.com/abcdefghijklmnop/status/123",
        "https://x.com/é/status/123",
        "https://x.com/%61/status/123",
        "https://x.com/a/status/%31",
        "https://x.com/a/status/１２３",
        "https://x.com/a/Status/123",
        "https://x.com/a/status/0",
        "https://x.com.evil.com/a/status/123",
        "https://[x.com/a/status/123",
        "ftp://x.com/a/status/123",
        "//x.com/a/status/123",
        '"123',
        '123"',
        "'123",
        "123'",
        "\"123'",
        "'123\"",
        '""123""',
        "''123''",
        "\"'123'\"",
        '"https://x.com/a/status/123',
        "https://x.com/a/status/123'",
        "1" * 21,
        False,
        0,
        -1,
        12.5,
    ],
)
def test_invalid_post_locators_rejected(value):
    with pytest.raises(ValueError):
        parse_post_locator(value)
