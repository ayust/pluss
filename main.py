"""pluss, a feed proxy for G+"""

from pluss.app import app

if __name__ == '__main__':
    app.run(host='pluss.aiiane.com', port=54321, debug=True)

# vim: set ts=4 sts=4 sw=4 et:
