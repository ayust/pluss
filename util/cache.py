import hashlib
import json
try:
	import memcache
	_hush_pyflakes = (memcache,)
	del _hush_pyflakes
except ImportError:
	memcache = None

class Cache(object):
	"""Wrapper around a singleton memcache client.

	Note: If the 'memcache' library is not available,
	this wrapper will do nothing - call() will transparently
	always call the provided function, and everything else
	will simply return None.
	"""

	client = memcache and memcache.Client(['127.0.0.1:11211'], debug=0)

	@classmethod
	def call(cls, func, *args, **kwargs):
		if not cls.client:
			return func(*args, **kwargs)

		call_dump = json.dumps([func.__module__, func.__name__, args, kwargs])
		memcache_key = 'pluss--%s' % hashlib.md5(call_dump).hexdigest()
		result = cls.client.get(memcache_key)
		if not result:
			result = func(*args, **kwargs)
			cls.client.set(memcache_key, result)
		return result

	@classmethod
	def get(cls, *args, **kwargs):
		return cls.client and cls.client.get(*args, **kwargs)

	@classmethod
	def set(cls, *args, **kwargs):
		return cls.client and cls.client.set(*args, **kwargs)

	@classmethod
	def delete(cls, *args, **kwargs):
		return cls.client and cls.client.delete(*args, **kwargs)

	@classmethod
	def incr(cls, *args, **kwargs):
		return cls.client and cls.client.incr(*args, **kwargs)

	@classmethod
	def decr(cls, *args, **kwargs):
		return cls.client and cls.client.decr(*args, **kwargs)
