#!/usr/bin/env python

import os
import time

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
import tornado.web

from util.config import Config
from util import db
from util import pid
from util.route import route

import handlers # See handlers/__init__.py for all the magic
_hush_pyflakes = [handlers]
del _hush_pyflakes

def _expand_path(path):
	return os.path.expanduser(os.path.expandvars(path))

application = tornado.web.Application(
	route.get_routes(),
	gzip = True,
	static_path = 'static',
)	
	
if __name__ == '__main__':

	pid_path = _expand_path(Config.get('system', 'pid-path'))

	pid.check(pid_path)
	time.sleep(1) # Give a little time for ports to be recognized as unbound

	pid.write(pid_path)
	try:
		db.init(_expand_path(Config.get('database', 'path')))

		http_server = HTTPServer(application, xheaders=True)
		http_server.bind(Config.getint('network', 'port'))
		http_server.start()
		IOLoop.instance().start()
	finally:
		pid.remove(pid_path)
