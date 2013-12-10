"""pluss, a feed proxy for G+"""
import logging

from pluss.app import app

@app.before_first_request
def setup_logging():
    if not app.debug:
        # In production mode, add log handler to sys.stderr.
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(process)d] [%(levelname)s] %(pathname)s:%(lineno)d %(message)s",
            "%Y-%m-%d %H:%M:%S",
        ))
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.WARNING)

if __name__ == '__main__':
    app.run(host='pluss.aiiane.com', port=54321, debug=True)

# vim: set ts=4 sts=4 sw=4 et:
