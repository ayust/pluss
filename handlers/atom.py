import datetime
import json
import logging
import re

from BeautifulSoup import BeautifulSoup as soup
from tornado.escape import xhtml_escape
from tornado.httpclient import AsyncHTTPClient
import tornado.web

from util.cache import Cache
from util.route import route

@route(r'/atom/(\d+)')
class AtomHandler(tornado.web.RequestHandler):
	"""Fetches the public posts for a given G+ user id as an Atom feed."""

	profile_json_url_template = 'https://plus.google.com/_/stream/getactivities/?sp=[1,2,"%s"]&rt=j'
	cache_key_template = 'pluss--gplusid--atom--%s'

	comma_fixer_regex = re.compile(r',(?=,)')
	space_compress_regex = re.compile(r'\s+')

	ATOM_DATEFMT = "%Y-%m-%dT%H:%M:%SZ"
	HTTP_DATEFMT = "%a, %d %b %Y %H:%M:%S GMT"

	@tornado.web.asynchronous
	def get(self, user_id):

		self.gplus_user_id = user_id

		if len(user_id) != 21:
			self.write("Google+ profile IDs are exactly 21 digits long. Please specify a proper profile ID.")
			return self.finish()

		self.cache_key = self.cache_key_template % user_id
		cached_result = Cache.get(self.cache_key)
		if cached_result and not self.request.arguments.get('flush', [None])[0]:
			return self._respond(**cached_result)

		http_client = AsyncHTTPClient()
		http_client.fetch(self.profile_json_url_template % user_id, self._on_http_response)

	def _respond(self, headers=(), body='', **kwargs):
		for (header, value) in headers:
			self.set_header(header, value)
		self.write(body)
		return self.finish()

	def _on_http_response(self, response):
		if response.error:
			logging.error("AsyncHTTPRequest error: %r" % response.error)
			self.send_error(500)
		else:
			pseudojson = response.body.lstrip(")]}'\n")
			pseudojson = self.comma_fixer_regex.sub(',null', pseudojson)
			pseudojson = pseudojson.replace('[,', '[null,')
			pseudojson = pseudojson.replace(',]', ',null]')

			data = json.loads(pseudojson)
			posts = data[0][0][1][0]

			headers = [('Content-Type', 'application/atom+xml')]
			params = {
				'userid': self.gplus_user_id,
				'baseurl': 'http://%s' % self.request.host,
				'requesturi': 'http://%s%s' % (self.request.host, self.request.uri),
			}

			if not posts:
				params['lastupdate'] = datetime.datetime.today().strftime(self.ATOM_DATEFMT)
				return self._respond(headers, self.empty_feed_template % params)

			# Return a maximum of 10 items
			posts = posts[:10]

			lastupdate = datetime.datetime.fromtimestamp(float(posts[0][5])/1000)
			params['author'] = posts[0][3]
			#params['authorimg'] = posts[0][18]
			params['lastupdate'] = lastupdate.strftime(self.ATOM_DATEFMT)

			headers.append( ('Last-Modified', lastupdate.strftime(self.HTTP_DATEFMT)) )

			params['entrycontent'] = ''.join(self.entry_template % self.get_post_params(p) for p in posts)

			body = self.feed_template % params

			Cache.set(self.cache_key, {'headers': headers, 'body': body}, time=900) # 15 minute cache
			return self._respond(headers, body)

	def get_post_params(self, post):
		post_timestamp = datetime.datetime.fromtimestamp(float(post[5])/1000)
		post_id = post[21]
		permalink = 'https://plus.google.com/%s' % post_id
		
		# post[4] is the full post text (with HTML).
		# not sure what post[47] is, but plusfeed uses it if it exists
		content = [post[47] or post[4] or '']

		if post[44]: # "originally shared by"
			content.append('<br/><br/>')
			content.append('<a href="https://plus.google.com/%s">%s</a>' % (post[44][1], post[44][0]))
			content.append(' originally shared this post: ')

		if post[66]: # attached content
			attach = post[66]
	
			if attach[0][1]: # attached link
				content.append('<br/><br/>')
				content.append('<a href="%s">%s</a>' % (attach[0][1], attach[0][3]))

			if attach[0][6]: #attached media
				media = attach[0][6][0]

				if media[1] and media[1].startswith('image'): # attached image
					content.append('<br/><br/>')
					content.append('<img src="http:%s" alt="attached image"/>' % media[2])
				elif len(media) >= 9: # some other attached media
					try:
						content.append('<br/><br/>')
						content.append('<a href="%s">%s</a>' % (media[8], media[8]))
					except:
						pass

		# If no actual parseable content was found, just link to the post
		post_content = ''.join(content) or permalink

		# Generate the post title out of just text [max: 100 characters]
		post_title = ' '.join(x.string for x in soup(post_content).findAll(text=True))
		post_title = self.space_compress_regex.sub(' ', post_title)
		if len(post_title) > 100:
			if post_title == permalink:
				post_title = "A public G+ post"
			else:
				candidate_title = post_title[:97]
				if '&' in candidate_title[-5:]: # Don't risk cutting off HTML entities
					candidate_title = candidate_title.rsplit('&', 1)[0]
				if ' ' in candidate_title[-5:]: # Reasonably avoid cutting off words
					candidate_title = candidate_title.rsplit(' ', 1)[0]
				post_title = "%s..." % candidate_title

		return {
			'title': post_title,
			'permalink': xhtml_escape(permalink),
			'postatomdate': post_timestamp.strftime(self.ATOM_DATEFMT),
			'postdate': post_timestamp.strftime('%Y-%m-%d'),
			'id': xhtml_escape(post_id),
			'summary': xhtml_escape(post_content),
		}

	entry_template = """
 <entry>
  <title>%(title)s</title>
  <link href="%(permalink)s" rel="alternate" />
  <updated>%(postatomdate)s</updated>
  <id>tag:plus.google.com,%(postdate)s:/%(id)s/</id>
  <summary type="html">%(summary)s</summary>
 </entry>
"""

	feed_template = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">
 <title>%(author)s - Google+ Public Posts</title>
 <link href="https://plus.google.com/%(userid)s" rel="alternate" />
 <link href="%(requesturi)s" rel="self" />
 <id>https://plus.google.com/%(userid)s</id>
 <updated>%(lastupdate)s</updated>
 <author>
  <name>%(author)s</name>
 </author>
%(entrycontent)s
</feed>
"""

	empty_feed_template = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>No Public Items Found</title>
  <link href="https://plus.google.com/%(userid)s" rel="alternate"></link>
  <link href="%(requesturi)s" rel="self"></link>
  <id>https://plus.google.com/%(userid)s</id>
  <updated>%(lastupdate)s</updated>
  <entry>
    <title>No Public Items Found</title>
    <link href="http://plus.google.com/%(userid)s"/>
    <id>https://plus.google.com/%(userid)s</id>
    <updated>%(lastupdate)s</updated>
    <summary>Google+ user %(userid)s  has not made any posts public.</summary>
  </entry>
</feed>
"""
