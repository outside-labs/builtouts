"""Offline HTML querying and callback-based link extraction."""

from builtouts.html import Document, LinkCollector, TextCollector

source = '<title>Reading</title><article class=card><h2>A &amp; B</h2><a href="/one">Read</a></article>'
doc = Document.from_html(source)
assert doc.title == 'Reading'
assert doc.select_one('.card > h2').text == 'A & B'
assert doc.select_one('article').get_text(' ', strip=True) == 'A & B Read'
links = []
parser = LinkCollector(base_url='https://example.test/', collect=False, on_link=links.append)
for offset in range(0, len(source), 7):
    parser.feed(source[offset:offset + 7])
parser.close()
assert links[0].url == 'https://example.test/one'
assert links[0].text == 'Read'
collector = TextCollector()
collector.feed('<p>Visible</p><style>hidden</style>')
collector.close()
assert collector.text == 'Visible'
print('HTML extraction passed')
