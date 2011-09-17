"""OAuth2 access flow support."""

import datetime
import json
import logging
import urllib

from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop
import tornado.web

from util.cache import Cache
from util.config import Config
from util.db import TokenIdMapping
from util.route import route

@route(r'/auth', name="auth")
class AuthRedirector(tornado.web.RequestHandler):
	"""OAuth step #1: send the user to the OAuth auth provider."""
	
	def get(self):
		redir_uri = "https://accounts.google.com/o/oauth2/auth?%s" % urllib.urlencode({
			'client_id': Config.get('oauth', 'client-id'),
			'redirect_uri': 'http://%s/oauth2callback' % self.request.host,
			'scope': 'https://www.googleapis.com/auth/plus.me', # G+ API
			'response_type': 'code', # server-side webapp
		})
		self.redirect(redir_uri)

@route(r'/access_denied', name="auth_denied")
class AccessDeniedHandler(tornado.web.RequestHandler):
	"""Display a page indicating that authentication by Google was denied."""
	def get(self):
		self.render("denied_main.html")

@route(r'/oauth2callback', name="oauth2callback")
class OAuth2Handler(tornado.web.RequestHandler):
	"""OAuth step #2 - receive auth code, fetch access+refresh tokens."""

	auth_cache_key_template = "pluss--gplusid--oauth--1--%s"
	profile_cache_key_template = "pluss--gplusid--profile--1--%s"

	@tornado.web.asynchronous
	def get(self):
		"""Initial request handler for receiving auth code."""

		err = self.request.arguments.get('error', [None])[0]
		if err is not None:
			if err == 'access_denied':
				return self.redirect(self.reverse_url('auth_denied'))
			return self.send_error(500)	

		self.http_client = AsyncHTTPClient()

		code = self.request.arguments.get('code', [None])[0]
		if code is not None:
			self.gplus_auth_code = code
			# OAuth step #2: Receive authorization code, POST it
			# back to Google to get an access token and a refresh token.
			post_body = urllib.urlencode({
				'code': code,
				'client_id': Config.get('oauth', 'client-id'),
				'client_secret': Config.get('oauth', 'client-secret'),
				'redirect_uri': 'http://%s/oauth2callback' % self.request.host,
				'grant_type': 'authorization_code',
			})
			return self.http_client.fetch(
				'https://accounts.google.com/o/oauth2/token',
				self.on_token_request_complete,
				method='POST',
				body=post_body,
			)
	
		# If we got here, we don't recognize why this endpoint was called.
		self.send_error(501) # 501 Not Implemented

	def on_token_request_complete(self, response):
		"""Callback for the initial OAuth token request."""

		if response.code != 200:
			logging.error('Tried to get token based on code, but got %s with this instead: %s' % (response.code, response.body))
			return self.send_error(500)

		try:
			results = json.loads(response.body)
		except ValueError:
			logging.error('Tried to get token but got an unparseable response: %s' % response.body)
			return self.send_error(500)

		# sanity check
		if results['token_type'] != "Bearer":
			logging.error('Unknown token type received: %s' % results['token_type'])
			return self.send_error(500)

		self.gplus_access_token = results['access_token']
		self.gplus_refresh_token = results['refresh_token']
		self.gplus_expires_at = datetime.datetime.today() + datetime.timedelta(seconds=results['expires_in'])

		return self.fetch_person_by_token(
			self.gplus_access_token,
			self.on_profile_request_complete,
		)

	def on_profile_request_complete(self, person):
		"""Callback for the initial OAuth flow's call to fetch_person_by_token."""
		# We compute the time= param here to take into account potential time
		# spent during the API call.
		Cache.set(self.auth_cache_key_template  % person['id'], self.gplus_access_token,
			time=int((self.gplus_expires_at - datetime.datetime.today()).total_seconds()),
		)

		# store refresh token and gplus user id in database
		TokenIdMapping.update_refresh_token(person['id'], self.gplus_refresh_token)
	
		self.set_cookie('gplus_id', str(person['id']))
		self.redirect('/')

	# Everything below here is classmethods so they can be used during
	# requests beyond the initial OAuth authorization flow.
	#
	# Note that this means other handlers may import OAuth2Handler from
	# this module - be careful what you touch!

	@classmethod
	def fetch_person_by_id(cls, id, callback):
		"""Returns a dict representing a Person, given their G+ id."""

		# If we have them cached already, just return that.
		person = Cache.get(cls.profile_cache_key_template % id)
		if person:
			return person
		
		# If we don't have the person cached, but we do have an
		# access token, use that to fetch the person.
		cls.access_token_for_id(id,
			lambda token: cls.fetch_person_by_token(token, callback),
		)

	@classmethod
	def fetch_person_by_token(cls, token, callback):
		"""Returns a dict representing a Person, given an access token."""
		if token:
			http_client = AsyncHTTPClient()
			return http_client.fetch(
				'https://www.googleapis.com/plus/v1/people/me',
				lambda response: cls.on_fetch_person_complete(response, callback),
				headers={'Authorization': 'Bearer %s' % token},
			)
		else:
			return IOLoop.instance.add_callback(lambda: callback(None))

	@classmethod
	def on_fetch_person_complete(cls, response, callback):
		"""Callback for the people/me API call in fetch_person_by_token."""
		person = json.loads(response.body)
		Cache.set(cls.profile_cache_key_template % person['id'], person, time=Config.getint('cache', 'profile-expire'))
		return IOLoop.instance().add_callback(lambda: callback(person))

	@classmethod
	def access_token_for_id(cls, id, callback):
		"""Returns the access token for an id, acquiring a new one if necessary."""
		token = Cache.get(cls.auth_cache_key_template % id)
		if token:
			return IOLoop.instance().add_callback(lambda: callback(token))

		# If we don't have an access token cached, see if we have a refresh token
		token = TokenIdMapping.lookup_refresh_token(id)
		if token:
			post_body = urllib.urlencode({
				'client_id': Config.get('oauth', 'client-id'),
				'client_secret': Config.get('oauth', 'client-secret'),
				'refresh_token': token,
				'grant_type': 'refresh_token',
			})
			http_client = AsyncHTTPClient()
			return http_client.fetch(
				'https://accounts.google.com/o/oauth2/token',
				lambda response: cls.on_refresh_complete(response, id, callback),
				method='POST',
				body=post_body,
			)
		else:
			return IOLoop.instance().add_callback(lambda: callback(None))

	@classmethod
	def on_refresh_complete(cls, response, id, callback):
		"""Callback for request to get a new access token based on refresh token."""

		if response.code in (400, 401):

			if 'invalid_grant' in response.body:
				# Our refresh token is invalid, which means that we don't have
				# permission to access this user's content anymore. Forget them.
				Cache.delete(cls.auth_cache_key_template % id)
				Cache.delete(cls.profile_cache_key_template % id)
				TokenIdMapping.remove_id(id)

			return IOLoop.instance().add_callback(lambda: callback(None))

		elif response.code != 200:
			logging.error("Non-200 response to refresh token request (%s, id=%s): %r" % (response.code, id, response.body))
			return IOLoop.instance().add_callback(lambda: callback(None))

		results = json.loads(response.body)

		# sanity check
		if results['token_type'] != "Bearer":
			logging.error('Unknown token type received: %s' % results['token_type'])
			return IOLoop.instance().add_callback(lambda: callback(None))

		token = results['access_token']
		Cache.set(cls.auth_cache_key_template % id, token, time=results['expires_in'])

		IOLoop.instance().add_callback(lambda: callback(token))

	@classmethod
	def authed_fetch(cls, user_id, url, callback, _authed_fetch_retry=True, *args, **kwargs):
		"""Make an auth'd AsyncHTTPRequest as the given G+ user."""
		return cls.access_token_for_id(
			user_id,
			lambda token: cls.on_fetch_got_token(
				user_id, url, token, callback, _authed_fetch_retry=_authed_fetch_retry,
				*args, **kwargs
			),
		)

	@classmethod
	def on_fetch_got_token(cls, user_id, url, token, callback, _authed_fetch_retry, *args, **kwargs):
		if not token:
			return IOLoop.instance().add_callback(lambda: callback(None))

		headers = {'Authorization': 'Bearer %s' % token}
		if 'headers' in kwargs:
			kwargs['headers'].update(headers)
		else:
			kwargs['headers'] = headers

		def wrap_callback(response):
			if response.code == 401:
				Cache.delete(cls.auth_cache_key_template % user_id)

				# Retry once to see if we can use a refresh token to get a new key.
				if _authed_fetch_retry:
					cls.authed_fetch(user_id, url, callback, _authed_fetch_retry=False, *args, **kwargs)
			else:
				return callback(response)

		http_client = AsyncHTTPClient()
		return http_client.fetch(url, wrap_callback, *args, **kwargs)
