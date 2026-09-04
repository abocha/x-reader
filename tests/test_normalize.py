import importlib


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
            "username": "sama",
            "name": "Sam Altman",
        },
        "metrics": {
            "replies": 10,
            "reposts": 20,
            "likes": 30,
            "quotes": 40,
            "bookmarks": 50,
            "views": 60,
        },
        "conversation_id": "2095601211869421726",
        "reply_to_id": None,
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
    }
