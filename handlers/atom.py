import datetime
import json
import logging
import re

from BeautifulSoup import BeautifulSoup as soup
from xml.sax.saxutils import escape as xhtml_escape
import tornado.web

from handlers.oauth import OAuth2Handler
from util import dateutils
from util.cache import Cache
from util.config import Config
from util.route import route

@route(r'/atom/(\d+)')
class AtomHandler(tornado.web.RequestHandler):
	"""Fetches the public posts for a given G+ user id as an Atom feed."""

	profile_json_url = 'https://www.googleapis.com/plus/v1/people/me/activities/public?maxResults=10'
	cache_key_template = 'pluss--gplusid--atom--2--%s'
	ratelimit_key_template = 'pluss--remoteip--ratelimit--1--%s'

	space_compress_regex = re.compile(r'\s+')


	@tornado.web.asynchronous
	def get(self, user_id):

		ratelimit_key = self.ratelimit_key_template % self.request.remote_ip
		remote_ip_rate = Cache.incr(ratelimit_key)
		if remote_ip_rate is None:
			Cache.set(ratelimit_key, 1, time=60)
		elif remote_ip_rate > 60:
			self.set_status(503)
			self.set_header('Retry-After', '60')
			self.write('Rate limit exceeded. Please do not make more than 60 requests per minute.')

			# Don't log every single time we rate limit a host (that would get spammy fast),
			# but do log significant breakpoints on exactly how spammy a host is being.
			if remote_ip_rate in (61, 100, 1000, 10000):
				logging.info('Rate limited IP %s - %s requests/min' % (self.request.remote_ip, remote_ip_rate))

			return self.finish()

		self.gplus_user_id = user_id

		if len(user_id) != 21:
			self.write("Google+ profile IDs are exactly 21 digits long. Please specify a proper profile ID.")
			return self.finish()

		self.cache_key = self.cache_key_template % user_id
		cached_result = Cache.get(self.cache_key)
		flush_requested = self.request.arguments.get('flush', [None])[0]
		if cached_result:
			if not Config.getboolean('cache', 'allow-flush') or not flush_requested:
				return self._respond(**cached_result)

		OAuth2Handler.authed_fetch(user_id, self.profile_json_url, self._on_api_response)

	def _respond(self, headers=None, body='', **kwargs):
		if headers is None:
			headers = {}

		# Potentially just send a 304 Not Modified if the browser supports it.
		if 'If-Modified-Since' in self.request.headers:
			remote_timestamp = dateutils.from_http_format(self.request.headers['If-Modified-Since'])

			# This check is necessary because we intentionally don't send Last-Modified for
			# empty feeds - if somehow a post shows up later, we'd want it to get served even if
			# the empty feed is 'newer' than the post (since we use latest post time for Last-Modified)
			if 'Last-Modified' in headers:

				local_timestamp = dateutils.from_http_format(headers['Last-Modified'])
				if local_timestamp <= remote_timestamp:
					# Hasn't been modified since it was last requested
					self.set_status(304)
					return self.finish()

		for (header, value) in headers.iteritems():
			self.set_header(header, value)
		self.write(body)

		return self.finish()

	def _on_api_response(self, response):
		if response is None:
			logging.error("API request for %s failed." % self.gplus_user_id)
			self.write("Unable to fetch content for this Google+ ID; it may not be authenticated. See http://%s for more information." % self.request.host)
			self.set_status(500)
			return self.finish()
		if response.error:
			logging.error("AsyncHTTPRequest error: %r" % response.error)
			return self.send_error(500)
		else:
			data = json.loads(response.body)

			headers = {'Content-Type': 'application/atom+xml'}
			params = {
				'userid': self.gplus_user_id,
				'baseurl': 'http://%s' % self.request.host,
				'requesturi': 'http://%s%s' % (self.request.host, self.request.uri.split('?', 1)[0]),
			}

			if 'items' not in data or not data['items']:
				params['lastupdate'] = dateutils.to_atom_format(datetime.datetime.today())
				return self._respond(headers, self.empty_feed_template.format(**params))

			posts = data['items']

			lastupdate = max(dateutils.from_iso_format(p['updated']) for p in posts)
			params['author'] = posts[0]['actor']['displayName']
			params['lastupdate'] = dateutils.to_atom_format(lastupdate)

			headers['Last-Modified'] = dateutils.to_http_format(lastupdate)

			params['entrycontent'] = u''.join(self.entry_template.format(**self.get_post_params(p)) for p in posts)

			body = self.feed_template.format(**params)

			Cache.set(self.cache_key, {'headers': headers, 'body': body}, time=Config.getint('cache', 'stream-expire'))
			return self._respond(headers, body)

	def get_post_params(self, post):
		post_updated = dateutils.from_iso_format(post['updated'])
		post_published = dateutils.from_iso_format(post['published'])
		post_id = post['id']
		permalink = post['url']
		item = post['object']
		
		if post['verb'] == 'post':

			content = [item['content']]

		elif post['verb'] == 'share':
			content = [post['annotation']]

			content.append('<br/><br/>')
			content.append('<a href="%s">%s</a>' % (item['actor']['url'], item['actor']['displayName']))
			content.append(' originally shared this post: ')
			content.append('<br/><blockquote>')
			content.append(item['content'])
			content.append('</blockquote>')
		else:
			content = []

		if 'attachments' in item: # attached content
			for attach in item['attachments']:

				content.append('<br/><br/>')
				if attach['objectType'] == 'article':
					# Attached link
					content.append('<a href="%s">%s</a>' % (attach['url'], attach['displayName']))
				elif attach['objectType'] == 'photo':
					# Attached image
					content.append('<img src="%s" alt="%s" />' % (attach['image']['url'],
						attach['image'].get('displayName', 'attached image'))) # G+ doesn't always supply alt text...
				elif attach['objectType'] == 'video':
					# Attached video
					content.append('Video: <a href="%s">%s</a>' % (attach['url'], attach['displayName']))
				else:
					# Unrecognized attachment type
					content.append('[unsupported post attachment of type "%s"]' % attach['objectType'])

		# If no actual parseable content was found, just link to the post
		post_content = u''.join(content) or permalink

		# Generate the post title out of just text [max: 100 characters]
		post_title = u' '.join(x.string for x in soup(post_content).findAll(text=True))
		post_title = self.space_compress_regex.sub(' ', post_title)
		if len(post_title) > 100:
			if post_title == permalink:
				post_title = u"A public G+ post"
			else:
				candidate_title = post_title[:97]
				if '&' in candidate_title[-5:]: # Don't risk cutting off HTML entities
					candidate_title = candidate_title.rsplit('&', 1)[0]
				if ' ' in candidate_title[-5:]: # Reasonably avoid cutting off words
					candidate_title = candidate_title.rsplit(' ', 1)[0]
				post_title = u"%s..." % candidate_title

		return {
			'title': post_title,
			'permalink': xhtml_escape(permalink),
			'postatomdate': dateutils.to_atom_format(post_updated),
			'postatompubdate': dateutils.to_atom_format(post_published),
			'postdate': post_published.strftime('%Y-%m-%d'),
			'id': xhtml_escape(post_id),
			'summary': xhtml_escape(post_content),
		}

	entry_template = u"""
 <entry>
  <title>{title}</title>
  <link href="{permalink}" rel="alternate" />
  <updated>{postatomdate}</updated>
  <published>{postatompubdate}</published>
  <id>tag:plus.google.com,{postdate}:/{id}/</id>
  <summary type="html">{summary}</summary>
 </entry>
"""

	feed_template = u"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">
 <title>{author} - Google+ Public Posts</title>
 <link href="https://plus.google.com/{userid}" rel="alternate" />
 <link href="{requesturi}" rel="self" />
 <id>https://plus.google.com/{userid}</id>
 <updated>{lastupdate}</updated>
 <author>
  <name>{author}</name>
 </author>
{entrycontent}
</feed>
"""

	empty_feed_template = u"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>No Public Items Found for {userid}</title>
  <link href="https://plus.google.com/{userid}" rel="alternate"></link>
  <link href="{requesturi}" rel="self"></link>
  <id>https://plus.google.com/{userid}</id>
  <updated>{lastupdate}</updated>
  <entry>
    <title>No Public Items Found</title>
    <link href="http://plus.google.com/{userid}"/>
    <id>https://plus.google.com/{userid}</id>
    <updated>{lastupdate}</updated>
    <published>{lastupdate}</published>
    <summary>Google+ user {userid}  has not made any posts public.</summary>
  </entry>
</feed>
"""
