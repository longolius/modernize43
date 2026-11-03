"""Server bootstrap and command line flags."""

import argparse
from http.server import ThreadingHTTPServer

from .jobs import JobManager
from .web import Handler


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="modernize43")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--allow-private-hosts", action="store_true")
    parser.add_argument("--retention-minutes", type=int, default=60)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    manager = JobManager(args.allow_private_hosts, args.retention_minutes)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    server.manager = manager
    host, port = server.server_address[0], server.server_address[1]
    print("modernize43 läuft auf http://%s:%d" % (host, port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
