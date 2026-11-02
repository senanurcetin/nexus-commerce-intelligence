"""Serve the built static portfolio with reliable cross-platform module MIME types."""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY=Path(__file__).resolve().parent if (Path(__file__).resolve().parent/'index.html').is_file() else ROOT/'target/showcase'


class PortfolioHandler(SimpleHTTPRequestHandler):
    # Windows registry MIME associations can map .mjs to text/plain. Browsers
    # reject those ES modules even though an HTTP request returns status 200.
    extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.mjs':'text/javascript',
                    '.js':'text/javascript','.json':'application/json','.css':'text/css',
                    '.html':'text/html','.svg':'image/svg+xml','.png':'image/png','.zip':'application/zip'}


def create_server(directory:Path,port:int=8787):
    directory=directory.resolve()
    if not directory.is_dir():raise FileNotFoundError('Build the static portfolio first: python -m scripts.build_demo')
    return ThreadingHTTPServer(('127.0.0.1',port),partial(PortfolioHandler,directory=str(directory)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=DEFAULT_DIRECTORY)
    p.add_argument('--port',type=int,default=8787);args=p.parse_args()
    with create_server(args.directory,args.port) as server:
        print(f'Portfolio: http://127.0.0.1:{server.server_port}/\nResearch: http://127.0.0.1:{server.server_port}/research/index.html',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
