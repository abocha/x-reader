import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from twscrape.models import AccountAbout, Media, TextLink, Tweet, User, UserRef

from x_reader.normalize import normalize_about, normalize_tweet, normalize_user


def test_normalize_tweet_returns_compact_public_shape():
    normalize = importlib.import_module("x_reader.normalize")
    normalize_tweet = getattr(normalize, "normalize_tweet", None)

    assert normalize_tweet is not None

    tweet = {
        "id": 2095601211869421726,
        "url": "https://x.com/sama/status/2095601211869421726",
        "date": "2026-09-03T19:53:57Z",
        "rawContent": "Astra is here.",
        "user": {
            "id": 1605,
            "username": "sama",
            "displayname": "Sam Altman",
            "followersCount": 6126532,
        },
        "replyCount": 10,
        "retweetCount": 20,
        "likeCount": 30,
        "quoteCount": 40,
        "bookmarkedCount": 50,
        "viewCount": 60,
        "conversationId": 2095601211869421726,
        "inReplyToTweetId": None,
        "links": [
            {
                "url": "https://openai.com/",
                "text": "openai.com",
                "tcourl": "https://t.co/example",
            }
        ],
        "media": {
            "photos": [],
            "videos": [],
            "animated": [],
        },
        "editControl": {"irrelevant": True},
        "_type": "snscrape.modules.twitter.Tweet",
    }

    result = normalize_tweet(tweet)

    assert result == {
        "id": "2095601211869421726",
        "url": "https://x.com/sama/status/2095601211869421726",
        "created_at": "2026-09-03T19:53:57Z",
        "text": "Astra is here.",
        "author": {
            "id": "1605",
            "username": "sama",
            "name": "Sam Altman",
        },
        "is_reply": False,
        "is_repost": False,
        "is_quote": False,
        "is_pinned": False,
        "conversation_id": "2095601211869421726",
        "reply_to_id": None,
        "metrics": {
            "replies": 10,
            "reposts": 20,
            "likes": 30,
            "quotes": 40,
            "bookmarks": 50,
            "views": 60,
        },
        "links": [
            {
                "url": "https://openai.com/",
                "text": "openai.com",
            }
        ],
        "media": {
            "photos": [],
            "videos": [],
            "animated": [],
        },
        "lang": None,
        "mentions": [],
        "hashtags": [],
        "possibly_sensitive": None,
        "card": None,
        "quoted_post": None,
        "reposted_post": None,
    }


def test_normalize_tweet_preserves_quoted_post():
    normalize = importlib.import_module("x_reader.normalize")
    normalize_tweet = normalize.normalize_tweet

    quoted = {
        "id": 111,
        "url": "https://x.com/other/status/111",
        "date": "2026-09-01T10:00:00Z",
        "rawContent": "Original insight",
        "user": {"id": 2, "username": "other", "displayname": "Other"},
        "media": {"photos": [{"url": "https://example.com/pic.jpg"}]},
    }
    tweet = {
        "id": 222,
        "url": "https://x.com/sama/status/222",
        "date": "2026-09-03T19:53:57Z",
        "rawContent": "This is interesting",
        "user": {"id": 1605, "username": "sama", "displayname": "Sam Altman"},
        "conversationId": 222,
        "inReplyToTweetId": None,
        "quotedTweet": quoted,
        "links": [],
        "media": {},
    }

    result = normalize_tweet(tweet)

    assert result["is_quote"] is True
    assert result["quoted_post"]["id"] == "111"
    assert result["quoted_post"]["author"]["username"] == "other"
    assert result["quoted_post"]["text"] == "Original insight"
    assert result["quoted_post"]["media"] == {
        "photos": [{"url": "https://example.com/pic.jpg"}]
    }


def test_normalize_tweet_preserves_reposted_post():
    normalize = importlib.import_module("x_reader.normalize")
    normalize_tweet = normalize.normalize_tweet

    original = {
        "id": 333,
        "url": "https://x.com/original_author/status/333",
        "date": "2026-09-02T08:00:00Z",
        "rawContent": "Original text",
        "user": {"id": 7, "username": "original_author", "displayname": "Original"},
    }
    tweet = {
        "id": 444,
        "url": "https://x.com/reposter/status/444",
        "date": "2026-09-03T19:53:57Z",
        "rawContent": "Original text",
        "user": {"id": 1605, "username": "reposter", "displayname": "Reposter"},
        "conversationId": 444,
        "inReplyToTweetId": None,
        "retweetedTweet": original,
        "links": [],
        "media": {},
    }

    result = normalize_tweet(tweet)

    assert result["is_repost"] is True
    assert result["author"]["username"] == "reposter"
    assert result["reposted_post"]["id"] == "333"
    assert result["reposted_post"]["author"]["username"] == "original_author"
    assert result["reposted_post"]["text"] == "Original text"


def test_normalize_tweet_tolerates_missing_optional_fields():
    normalize = importlib.import_module("x_reader.normalize")
    normalize_tweet = normalize.normalize_tweet

    result = normalize_tweet({"id": 1, "user": {}})

    assert result["id"] == "1"
    assert result["url"] is None
    assert result["text"] is None
    assert result["conversation_id"] is None
    assert result["quoted_post"] is None
    assert result["reposted_post"] is None


@pytest.fixture
def upstream_user():
    return User(
        id=7,
        id_str="7",
        url="https://x.com/example",
        username="example",
        displayname="Example",
        rawDescription="Description",
        created=datetime(2020, 1, 1, tzinfo=timezone.utc),
        followersCount=10,
        friendsCount=20,
        statusesCount=30,
        favouritesCount=40,
        listedCount=50,
        mediaCount=60,
        location="Somewhere",
        profileImageUrl="https://example.com/avatar.jpg",
        verified=False,
        blue=True,
    )


@pytest.fixture
def upstream_tweet(upstream_user):
    return Tweet(
        id=123,
        id_str="123",
        url="https://x.com/example/status/123",
        date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        user=upstream_user,
        lang="en",
        rawContent="Example post",
        replyCount=1,
        retweetCount=2,
        likeCount=3,
        quoteCount=4,
        bookmarkedCount=5,
        conversationId=123,
        conversationIdStr="123",
        hashtags=["example"],
        cashtags=[],
        mentionedUsers=[UserRef(8, "8", "other", "Other")],
        links=[TextLink("https://example.com/", "example.com", "https://t.co/example")],
        media=Media(),
    )


def test_normalize_user_upstream_fields(upstream_user):
    assert normalize_user(upstream_user.dict()) == {
        "id": "7",
        "username": "example",
        "name": "Example",
        "description": "Description",
        "created_at": "2020-01-01T00:00:00Z",
        "followers": 10,
        "following": 20,
        "posts_count": 30,
        "location": "Somewhere",
        "verified": False,
        "blue_verified": True,
        "url": "https://x.com/example",
    }


@pytest.mark.parametrize("blue", [True, False, None])
def test_normalize_user_uses_blue_not_blue_verified(upstream_user, blue):
    upstream_user.blue = blue
    user = upstream_user.dict()
    user["blueVerified"] = not blue
    assert normalize_user(user)["blue_verified"] is blue


@pytest.mark.parametrize("value", [None, {}])
def test_normalize_empty_user_and_about(value):
    assert normalize_user(value) is None
    assert normalize_about(value) is None


def test_normalize_user_null_optional_fields():
    result = normalize_user({"id": None, "username": None, "blue": None})
    assert all(value is None for value in result.values())


def test_normalize_about_upstream_fields():
    about = AccountAbout.parse({
        "core": {"screen_name": "example", "name": "Example"},
        "rest_id": "7",
        "about_profile": {
            "account_based_in": "Somewhere",
            "location_accurate": False,
            "affiliate_username": None,
            "username_changes": {"count": 2, "last_changed_at_msec": "1704067200000"},
        },
        "verification_info": {
            "is_identity_verified": True,
            "reason": {"verified_since_msec": "1735689600000"},
        },
    })
    assert normalize_about(about.dict()) == {
        "account_based_in": "Somewhere",
        "location_accurate": False,
        "affiliate_username": None,
        "username_changes": 2,
        "username_last_changed_at": "2024-01-01T00:00:00Z",
        "identity_verified": True,
        "verified_since": "2025-01-01T00:00:00Z",
    }


def test_normalize_about_upstream_nulls():
    about = AccountAbout.parse({
        "about_profile": None,
        "core": None,
        "verification_info": None,
    })
    assert all(value is None for value in normalize_about(about.dict()).values())


@pytest.mark.parametrize(
    "value",
    [
        None, True, False, "", "invalid", 0, -1, "0", "-1", [], {},
        float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", 10**400,
    ],
)
def test_normalize_about_invalid_timestamps(value):
    result = normalize_about({
        "username_last_changed_at": value,
        "verified_since_msec": value,
    })
    assert result["username_last_changed_at"] is None
    assert result["verified_since"] is None


@pytest.mark.parametrize("value", [1704067200123, 1704067200123.0, " 1704067200123 "])
def test_normalize_about_timestamp_milliseconds(value):
    result = normalize_about({
        "username_last_changed_at": value,
        "verified_since_msec": value,
    })
    assert result["username_last_changed_at"] == "2024-01-01T00:00:00Z"
    assert result["verified_since"] == "2024-01-01T00:00:00Z"


def test_normalize_tweet_upstream_fields_and_unavailable_quote(upstream_tweet):
    upstream_tweet.isQuoteStatus = True
    result = normalize_tweet(upstream_tweet.dict())
    assert result["is_quote"] is True
    assert result["quoted_post"] is None
    assert result["created_at"] == "2026-01-01T00:00:00Z"
    assert result["mentions"] == [{"username": "other", "id": "8"}]
    assert result["hashtags"] == ["example"]
    assert result["links"] == [{"url": "https://example.com/", "text": "example.com"}]
    assert result["metrics"]["bookmarks"] == 5
    assert result["metrics"]["views"] is None


@pytest.mark.parametrize("flag,expected", [(True, True), (False, False), (None, True)])
def test_normalize_quote_flag_precedence(flag, expected):
    result = normalize_tweet({"isQuoteStatus": flag, "quotedTweet": {"id": 2}})
    assert result["is_quote"] is expected


@pytest.mark.parametrize(
    "field,output",
    [("quotedTweet", "quoted_post"), ("retweetedTweet", "reposted_post")],
)
def test_normalize_nested_upstream_links_and_cycles(upstream_tweet, field, output):
    tweet = upstream_tweet.dict()
    child = upstream_tweet.dict()
    child["user"] = None
    tweet[field] = child
    child["quotedTweet"] = tweet
    child["retweetedTweet"] = child
    result = normalize_tweet(tweet)
    assert result[output] == {
        "id": "123",
        "url": upstream_tweet.url,
        "created_at": "2026-01-01T00:00:00Z",
        "text": "Example post",
        "author": {"id": None, "username": None, "name": None},
        "links": [{"url": "https://example.com/", "text": "example.com"}],
        "media": {"photos": [], "videos": [], "animated": []},
    }
    json.dumps(result, default=str)
    assert normalize_tweet(tweet, nested=True)[output] is None


def test_normalize_tweet_optional_nulls():
    tweet = dict.fromkeys([
        "user", "links", "media", "mentionedUsers", "hashtags", "quotedTweet",
        "retweetedTweet", "isQuoteStatus", "card", "possibly_sensitive",
    ])
    result = normalize_tweet(tweet)
    assert result["author"] == {"id": None, "username": None, "name": None}
    assert result["links"] == result["mentions"] == result["hashtags"] == []
    assert result["media"] == {}
    assert result["quoted_post"] is result["reposted_post"] is None
    assert result["card"] is result["possibly_sensitive"] is None
    assert result["is_quote"] is result["is_repost"] is False
    tweet["quotedTweet"] = tweet.copy()
    assert normalize_tweet(tweet)["quoted_post"]["links"] == []


def test_normalize_tweet_filters_invalid_optional_entries():
    result = normalize_tweet({
        "links": [None, "invalid", {"url": "https://example.com/", "text": None}],
        "mentionedUsers": [None, "invalid", {"username": "other", "id": 8}],
        "hashtags": [None, "example"],
    })
    assert result["links"] == [{"url": "https://example.com/", "text": None}]
    assert result["mentions"] == [{"username": "other", "id": "8"}]
    assert result["hashtags"] == ["example"]


def test_normalized_timestamps_use_utc_for_aware_values():
    offset = timezone(timedelta(hours=7))
    moment = datetime(2026, 1, 1, 7, 30, tzinfo=offset)
    tweet = {"id": 1, "date": moment, "user": {"id": 2}, "quotedTweet": {"id": 3, "date": moment, "user": {"id": 4}}}
    result = normalize_tweet(tweet)
    assert result["created_at"] == "2026-01-01T00:30:00Z"
    assert result["quoted_post"]["created_at"] == "2026-01-01T00:30:00Z"
    assert normalize_user({"id": 2, "created": moment})["created_at"] == "2026-01-01T00:30:00Z"
