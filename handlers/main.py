import tornado.web

from util.route import route

@route(r'/')
class MainHandler(tornado.web.RequestHandler):
	"""Allow people to fetch the root / to make sure the server is okay."""

	def get(self):
		self.write("OK\n")

