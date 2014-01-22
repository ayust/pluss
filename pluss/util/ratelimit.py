import functools

from pluss.app import app
from pluss.util.cache import Cache

RATE_LIMIT_CACHE_KEY_TEMPLATE = 'pluss--remoteip--ratelimit--1--%s'

def ratelimited(func):
    """Includes the wrapped handler in the global rate limiter (60 calls/min)."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        ratelimit_key = RATE_LIMIT_CACHE_KEY_TEMPLATE % flask.request.remote_addr
        # Increment the existing minute's counter, or start a new one if none exists
        # (relies on the short-circuiting of 'or')
        remote_ip_rate = Cache.incr(ratelimit_key) or Cache.set(ratelimit_key, 1, time=60)
        if remote_ip_rate > 60:
            if remote_ip_rate in (61, 100, 1000, 10000):
                app.logging.info('Rate limited %s - %d requests/min.',
                    flask.request.remote_addr, remote_ip_rate)
            message = 'Rate limit exceeded. Please do not make more than 60 requests per minute.'
            return message, 503, {'Retry-After': 60} # Service Unavailable
        return func(*args, **kwargs)

    return wrapper


# vim: set ts=4 sts=4 sw=4 et:
