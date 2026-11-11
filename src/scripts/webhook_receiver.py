"""Маленький сервер, изображает сервер клиента: принимает webhook и печатает его"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        print(f"{self.path} {body.decode()}", flush=True)

        # на /fail ответ 500, так проверяются ретраи и DLQ
        self.send_response(500 if self.path.startswith("/fail") else 200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
