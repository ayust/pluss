from datetime import datetime

ATOM_DATEFMT = "%Y-%m-%dT%H:%M:%SZ"
HTTP_DATEFMT = "%a, %d %b %Y %H:%M:%S GMT"
ISO_DATEFMT = "%Y-%m-%dT%H:%M:%S.%fZ"

from_iso_format = lambda x: datetime.strptime(x, ISO_DATEFMT)
to_iso_format = lambda x: datetime.strftime(x, ISO_DATEFMT)

from_http_format = lambda x: datetime.strptime(x, HTTP_DATEFMT)
to_http_format = lambda x: datetime.strftime(x, HTTP_DATEFMT)

from_atom_format = lambda x: datetime.strptime(x, ATOM_DATEFMT)
to_atom_format = lambda x: datetime.strftime(x, ATOM_DATEFMT)
