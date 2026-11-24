from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

from . import codec, routes
from .errors import Problem

WEB = Path(__file__).resolve().parent.parent / 'web'
MAX_BODY = 65536


class Handler(BaseHTTPRequestHandler):
    def response(self, status, data, media, filename=None):
        self.send_response(status)
        self.send_header('Content-Type', media)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        if self.headers.get_content_type() != 'application/json' or self.headers.get('Transfer-Encoding'):
            raise Problem('请求须为定长 application/json', 415)
        size = self.headers.get('Content-Length', '')
        if not size.isascii() or not size.isdecimal() or len(size) > 9:
            raise Problem('请求长度无效', 400)
        size = int(size)
        if size > MAX_BODY:
            raise Problem('请求超过 64 KiB', 413)
        try:
            return codec.decode(self.rfile.read(size))
        except (ValueError, RecursionError) as exc:
            raise Problem('请求不是有效的 UTF-8 JSON', 400) from exc

    def serve_static(self, path):
        target = (WEB / (path.lstrip('/') or 'index.html')).resolve()
        if not target.is_relative_to(WEB) or target.suffix not in {'.html', '.js', '.css'} or not target.is_file():
            raise Problem('页面或资源不存在', 404)
        mime = 'text/javascript' if target.suffix == '.js' else mimetypes.guess_type(target)[0]
        self.response(200, target.read_bytes(), f'{mime}; charset=utf-8')

    def handle_request(self):
        try:
            host, port = self.server.server_address
            allowed = {f'{host}:{port}', f'localhost:{port}'}
            origin = self.headers.get('Origin')
            if self.headers.get('Host') not in allowed or origin and origin not in {'http://' + name for name in allowed}:
                raise Problem('只接受本机同源访问', 403)
            path = urlsplit(self.path).path
            if path.startswith('/api/'):
                parts = path.removeprefix('/api/').split('/')
                post = self.command == 'POST'
                body = self.read_body() if post else None
                with self.server.database.transaction(write=post and parts[-1] != 'preview') as db:
                    result = routes.dispatch(db, self.command, parts, body)
                name = '-'.join(parts[1:4]) if len(parts) >= 4 and parts[2] == 'releases' else None
                if isinstance(result, bytes):
                    self.response(200, result, 'text/csv; charset=utf-8', f'{name}.csv')
                else:
                    download = f'{name}.json' if name and len(parts) == 4 and urlsplit(self.path).query == 'download' else None
                    self.response(200, codec.encode(result), 'application/json; charset=utf-8', download)
            elif self.command == 'GET':
                self.serve_static(path)
            else:
                raise Problem('没有此接口', 404)
        except Problem as exc:
            self.response(exc.status, codec.encode({'error': str(exc)}), 'application/json; charset=utf-8')
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise
            self.response(503, codec.encode({'error': '工作库繁忙，请稍后重试'}), 'application/json; charset=utf-8')

    do_GET = handle_request
    do_POST = handle_request


def server(database, port):
    http = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    http.database = database
    return http
