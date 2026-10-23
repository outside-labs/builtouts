"""Entirely offline HTTP -> HTML -> structured records -> thread outcomes."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from builtouts.concurrent import thread_outcomes
from builtouts.html import Document, ExtractionError, Field, extract_all
from builtouts.http import Client


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        number = self.path.removeprefix('/')
        count = 'invalid' if number == '2' else number
        body = f'<article data-count="{count}"><h2>Entry {number}</h2></article>'.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    client = Client(timeout=2, max_bytes=4096)
    fields = {'title': Field('h2'), 'count': Field(attribute='data-count', convert=int)}

    def fetch_record(url: str) -> dict[str, object]:
        response = client.get(url)
        response.raise_for_status()
        document = Document.from_html(response.text)
        return extract_all(document, 'article', fields)[0]

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            observed = []
            with thread_outcomes(fetch_record, [f'{base}/{n}' for n in range(1, 4)],
                                 max_workers=2, max_pending=2, on_result=observed.append) as results:
                outcomes = list(results)
            assert [row.index for row in outcomes] == [0, 1, 2]
            assert [row.ok for row in outcomes] == [True, False, True]
            assert outcomes[0].result() == {'title': 'Entry 1', 'count': 1}
            assert isinstance(outcomes[1].error, ExtractionError)
            assert outcomes[1].error.reason == 'conversion'
            assert outcomes[2].result() == {'title': 'Entry 3', 'count': 3}
            assert len(observed) == 3
        finally:
            server.shutdown()
            worker.join(timeout=5)
    print('Offline scrape pipeline passed: 2 successes, 1 explicit field failure')


if __name__ == '__main__':
    main()
