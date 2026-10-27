class XReaderError(Exception):
    category = "reader_error"
    code = "READER_ERROR"
    retryable = False

    def __init__(
        self, message: str, *, retryable: bool | None = None,
        retry_after_seconds: int | None = None, endpoint: str | None = None,
    ) -> None:
        super().__init__(message)
        if retryable is not None:
            self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.endpoint = endpoint


class UserNotFound(XReaderError):
    category = "not_found"
    code = "USER_NOT_FOUND"


class PostNotFound(XReaderError):
    category = "not_found"
    code = "POST_NOT_FOUND"


class AccountUnavailable(XReaderError):
    category = "account_unavailable"
    code = "ACCOUNT_UNAVAILABLE"


class EndpointBusy(AccountUnavailable):
    category = "endpoint_busy"
    code = "ENDPOINT_BUSY"
    retryable = True


class RequestRateLimited(XReaderError):
    category = "rate_limited"
    code = "LOCAL_RATE_LIMIT"
    retryable = True


class UpstreamTimeout(XReaderError):
    category = "timeout"
    code = "UPSTREAM_TIMEOUT"
    retryable = True


class UpstreamUnavailable(XReaderError):
    category = "upstream_unavailable"
    code = "UPSTREAM_UNAVAILABLE"
    retryable = True
