def normalize_tweet(tweet: dict) -> dict:
    return {
        "id": str(tweet["id"]),
        "url": tweet["url"],
        "created_at": tweet["date"],
        "text": tweet["rawContent"],
        "author": {
            "username": tweet["user"]["username"],
            "name": tweet["user"]["displayname"],
        },
        "metrics": {
            "replies": tweet["replyCount"],
            "reposts": tweet["retweetCount"],
            "likes": tweet["likeCount"],
            "quotes": tweet["quoteCount"],
            "bookmarks": tweet["bookmarkedCount"],
            "views": tweet["viewCount"],
        },
        "conversation_id": str(tweet["conversationId"]),
        "reply_to_id": (
            str(tweet["inReplyToTweetId"])
            if tweet["inReplyToTweetId"] is not None
            else None
        ),
        "links": [
            {
                "url": link["url"],
                "text": link["text"],
            }
            for link in tweet["links"]
        ],
        "media": tweet["media"],
    }
