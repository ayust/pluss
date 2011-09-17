import tornado.web

from util.route import route

@route(r'/')
class MainHandler(tornado.web.RequestHandler):
	"""Display the homepage."""

	def get(self):
		gplus_id = self.get_cookie('gplus_id')
		if gplus_id:
			self.render('authed_main.html',
				gplus_id=gplus_id,
				feed_url="http://%s/atom/%s" % (self.request.host, gplus_id),
			)
		else:
			self.render('main.html')

@route(r'/clear')
class ClearHandler(tornado.web.RequestHandler):

	def get(self):
		self.clear_all_cookies()
		self.redirect('/')
