class XReaderError(Exception):
    category = "reader_error"


class UserNotFound(XReaderError):
    category = "not_found"


class PostNotFound(XReaderError):
    category = "not_found"


class AccountUnavailable(XReaderError):
    category = "account_unavailable"


class UpstreamTimeout(XReaderError):
    category = "timeout"


class UpstreamUnavailable(XReaderError):
    category = "upstream_unavailable"
