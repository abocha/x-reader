from x_reader.rate_limit import SlidingWindowRateLimiter


def test_sliding_window_expires_only_old_hits_at_the_boundary():
    now = 0.0
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10, clock=lambda: now)

    assert limiter.allow("mcp") is True
    now = 5.0
    assert limiter.allow("mcp") is True
    now = 9.0
    assert limiter.allow("mcp") is False
    now = 10.0
    assert limiter.allow("mcp") is True
    assert limiter.allow("mcp") is False
    now = 15.0
    assert limiter.allow("mcp") is True
