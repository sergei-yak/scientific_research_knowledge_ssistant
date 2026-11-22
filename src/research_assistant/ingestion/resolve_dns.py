"""Bounded child-process DNS resolution; HTTPS connects only to checked returned addresses."""

import json
import socket
import sys


def main() -> None:
    """Return numeric stream addresses only, without fetching a URL or reading local data."""
    host = sys.argv[1]
    addresses = sorted({row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    print(json.dumps(addresses))


if __name__ == '__main__':
    main()
