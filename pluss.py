#!/usr/bin/env python

import os
import time

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
import tornado.web

import handlers # See handlers/__init__.py for all the magic
from util import pid
from util.route import route

application = tornado.web.Application(
	route.get_routes(),
	gzip = True,
	static_path = 'static',
)	
	
if __name__ == '__main__':

	pid_path = os.path.join(os.path.dirname(__file__), 'app.pid')

	pid.check(pid_path)
	time.sleep(1) # Give a little time for ports to be recognized as unbound

	pid.write(pid_path)
	try:
		http_server = HTTPServer(application, xheaders=True)
		http_server.bind(7587) # "PLUS" on a phone keypad
		http_server.start() # Pre-fork equal to available CPUs
		IOLoop.instance().start()
	finally:
		pid.remove(pid_path)
