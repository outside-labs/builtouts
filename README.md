# Builtouts

Building out Python's batteries.

Builtouts provides dependency-free interfaces and explicit conventions over
Python's builtins and standard library. Python 3.14+ is required. Modules are
independently usable and do not modify Python globals.

| Module | Standard-library foundation | Added interface |
| --- | --- | --- |
| `builtouts.html` | `html.parser` | Bounded trees, queries, visible text, streaming links |
| `builtouts.concurrent` | `concurrent.futures` | Bounded thread iteration and collection |
| `builtouts.conventions` | `str`, `unicodedata` | Explicit Unicode naming transformations |

Install builtouts:

```sh
python -m pip install builtouts
```

For a local development checkout, use `python -m pip install .`.
The published release is 0.1.0. This checkout develops unreleased 0.2.0;
sections marked 0.2 require installing the checkout until its release.

## HTTP retrieval (0.2)

```python
from builtouts.http import Client
from builtouts.html import Document

response = Client(timeout=10, max_bytes=2_000_000).get('https://example.com/')
response.raise_for_status()
document = Document.from_html(response.text)
```

`Client` performs independent GETs with verified TLS and closes each response
before returning an immutable `Response(url, status, headers, body)`. It is a
reusable configuration; each call owns its opener and connection. There are
no cookies, retries, connection pooling, global opener changes or decompression.
URLs must be absolute ASCII HTTP(S) URLs without credentials, whitespace or
controls; callers encode Unicode hosts/paths explicitly. Fragments are removed.
Local/private addresses are allowed: this is not an SSRF filter.

`timeout=10.0` bounds blocking socket operations, not DNS resolution or total
wall-clock time. `max_bytes=5_000_000` bounds response body bytes, including
responses without Content-Length; malformed/conflicting lengths and truncated
bodies fail explicitly. No-body 204/304 statuses have no representation payload.
Only identity Content-Encoding is accepted. `ResponseLimitError` rejects excess
bytes and `ContentEncodingError` rejects compressed content before reading it.
Standard-library transport, TLS, timeout and framing exceptions propagate.

`max_redirects=5` bounds redirects and cycles fail with `RedirectError`.
Redirect targets are validated before opening; HTTPS downgrade is forbidden.
Origin changes require `allow_cross_origin_redirects=True`, which permanently
drops all caller-supplied headers for the remainder of that request chain.
Environment proxies are disabled unless `trust_env=True`. Each flag is explicit;
no browser, session, authentication or network isolation is implied.

`get(url, headers={...})` accepts Latin-1 header values without controls. Framing,
Host, Connection, Proxy-Authorization and Accept-Encoding headers are reserved;
case-insensitive duplicates fail before I/O. Header results preserve duplicates:
`response.header(name)` returns the first value or None, while
`response.headers_all(name)` returns a tuple. HTTP statuses, including 4xx/5xx,
are ordinary responses; `raise_for_status()` explicitly raises `HTTPStatusError`
and retains its response. `text` uses the declared charset or UTF-8 with strict
decoding. `decode(encoding=None, errors='strict')` allows an explicit override;
there is no BOM or HTML-meta sniffing.

## HTML extraction

```python
from builtouts.html import Document

doc = Document.from_html('''
<title>Example</title>
<article class="card"><h2>First</h2><a href="/one">Read more</a></article>
''')
assert doc.title == 'Example'
article = doc.select_one('article.card')
assert article is not None
link = article.find('a', href=True)
assert link is not None
assert link.attrs['href'] == '/one'
assert article.get_text(' ', strip=True) == 'First Read more'
```

`DocumentParser` subclasses `HTMLParser`. Feed string chunks, call `close()`,
then use its `document`. The document is live during feeds. Parsers are single
use: closing twice is harmless, but feeding after close/failure or calling
`reset()` raises `RuntimeError`. Bytes must be decoded by the caller.

Nodes expose `kind`, `tag`, read-only `attrs` and `children`, `parent`, and
`data`. `descendants()` iterates in source order and excludes the receiver.
`find()` and `find_all()` search descendant elements by optional tag and ANDed
attribute filters, supplied through `attrs={...}` or keyword arguments:

- Strings match exact attribute values. `class_='card'` matches a class token.
- `True` means present; `False` means absent.
- `None` matches a present boolean attribute, distinct from absence or `''`.

`text` concatenates descendant text, omitting comments and script/style
subtrees. `get_text(separator='', strip=False, include_hidden=False)` controls
joining, per-piece trimming and script/style inclusion. No layout whitespace
is inferred around block or void elements. Hidden here refers only to script
and style; CSS visibility, the `hidden` attribute and browser layout are not
evaluated. `title` returns the first title's stripped text, or `None`.

Supported CSS selectors use ASCII identifiers (`-?[_a-zA-Z][_a-zA-Z0-9-]*`) for tags, IDs and classes,
`*`, `[attr]`, `[attr=value]`, compound selectors, descendants, `>` children,
and comma groups. Attribute strings can be quoted, including non-ASCII text;
unquoted values must be identifiers. Results are deduplicated in source order.
An element receiver can match an ancestor part but is excluded from results;
matching never climbs above it. Tags/attribute names are case-normalized;
IDs, classes and values are case-sensitive. Unsupported or malformed syntax
raises `SelectorSyntaxError`, including sibling combinators, pseudo-classes,
escapes and substring attribute operators. Selectors are limited to 4,096
characters and 64 compound parts across all groups.

Parsing preserves text, comments, declarations and processing instructions.
Names follow HTMLParser normalization; duplicate attributes use the last value.
Void elements never become parents; self-closing tags close immediately.
A matching end tag closes its element and intervening open elements; unmatched
end tags are ignored. EOF closes remaining elements. Optional end tags are not
inferred: `<li>a<li>b` produces nested elements. This is a documented extraction
tree, without HTML5 browser tree construction, XML namespaces or JavaScript.
Raw script/style text follows HTMLParser's handling. Parsed text and URLs are
untrusted data; extraction does not sanitize content or validate URLs for fetching.

All parsers accept positive integer `max_chars=10_000_000`,
`max_nodes=100_000`, and `max_depth=256`. Excess raises `ParseLimitError` and
invalidates the parser. Node counts exclude the document root and coalesce
adjacent text across feeds. Streaming collectors count structural/text events
without retaining nodes. Limits are in-process guardrails, not a hard CPU or
memory isolation boundary; downloaded input needs its own byte/deadline bounds.

## Streaming extraction

```python
from builtouts.html import LinkCollector, TextCollector

links = LinkCollector(base_url='https://example.test/notes/')
links.feed('<a href="../one">One &amp; ')
links.feed('<b>two</b></a>')
links.close()
assert links.links[0].url == 'https://example.test/one'
assert links.links[0].text == 'One & two'

pieces = []
text = TextCollector(on_text=pieces.append, collect=False)
text.feed('<p>Hello</p><script>ignored</script>')
text.close()
assert ''.join(pieces) == 'Hello'
assert text.text == ''
```

Collectors do not build trees. `Link` is an immutable `href`, `text`, `url`
record. Without `base_url`, `url` equals the original href. An input `<base>`
tag is ignored for resolution. Missing/boolean href attributes emit no link;
empty hrefs are retained. Links emit when anchors close, including EOF;
nested malformed anchors emit inner links first and include inner text in the
outer link. No URL is fetched. Resolution can still produce arbitrary schemes
or different hosts; apply an operation-specific URL policy before using them.

Set `collect=False` and `on_link=callback` or `on_text=callback` to avoid retaining
output. Callbacks run synchronously inside `feed()`/`close()` and must not reenter
the parser. Callback failures propagate and invalidate it. Text callback chunk
boundaries depend on input feeds/tokenization. Accumulated results, and text in
currently open anchors, consume memory proportional to retained output.

## Bounded thread concurrency

```python
from builtouts.concurrent import thread_iter, thread_map

assert thread_map(len, ['a', 'abcd'], max_workers=4) == [1, 4]

with thread_iter(len, ['a', 'abcd'], max_workers=4,
                 max_pending=8, ordered=False) as results:
    for length in results:
        print(length)
```

`thread_map()` returns a list; its input must terminate and the list grows with
all results. Always use `thread_iter()` in a `with` block, especially when
stopping early. Its result iterator is single-pass and intended for one consumer.
The caller owns input iterable resources. No input is consumed until iteration
starts; only `max_pending` submitted but unconsumed results are retained,
including already-completed results. A smaller bound than the worker count is
allowed and can reduce utilization.

`ordered=True` preserves input order and can wait behind a slow early item.
`ordered=False` yields ready results first, with no ordering guarantee between
simultaneous completions. The default worker count is
`min(32, (os.process_cpu_count() or 1) + 4)`; the default pending bound is twice
that count. Worker/pending values must be positive integers, excluding bool.

Input and worker exceptions propagate unchanged. Failure, caller exceptions,
or early context exit cancel queued calls and join running workers. Running
threads cannot be forcibly interrupted: each I/O operation needs its own
timeout. Never make worker functions wait on dependent work in an exhausted
pool. Use threads for overlapping I/O; CPU-bound Python parsing has no promised
speedup. There are no implicit retries, rate limits, process pools or asyncio
adapters. `concurrent.futures` is unavailable on WASI.

## Naming conventions

```python
from builtouts.conventions import words, snake_case, kebab_case, camel_case, pascal_case

assert words('HTTPServer version2ID') == ('http', 'server', 'version2', 'id')
assert snake_case('HTTPServer') == 'http_server'
assert kebab_case('a name') == 'a-name'
assert camel_case('HTTP_server') == 'httpServer'
assert pascal_case('HTTP_server') == 'HttpServer'
```

Words are lowercase and NFC-normalized. Punctuation/whitespace separates words;
acronyms split before a following title word; digit runs remain with adjacent
text. Unicode letters, numbers and attached combining marks are retained;
uncased scripts remain intact. Empty/separator-only input returns `()` from
`words()` and `''` from converters. Casing may expand characters.
These conventions do not validate identifiers, reserve keywords, transliterate,
ensure uniqueness or make filenames/URLs safe. Different spellings can collide.

## Development and release

```sh
uv sync --locked
uv run --frozen python -W error::ResourceWarning -m unittest discover -s tests -v
uv run --frozen python scripts/check_distribution.py --output-dir dist
```

CI checks Python 3.14 on Linux, macOS and Windows, then builds and verifies exact
wheel/sdist contents, source bytes, metadata, typing/license, RECORD hashes and
source rebuild parity. Both distributions are independently installed and
tested outside the checkout with offline examples. Build tooling is declared
in `pyproject.toml`; installed builtouts requires no third-party packages.
Rebuilds require identical package, license and METADATA bytes and compatibility
headers; only the build-tool Generator header may vary, with both RECORDs
independently verified.

The [implementation plan](IMPLEMENTATION_PLAN.md) describes future HTTP,
serialization/mutation, extraction models, additional executors and other
modules. [GitHub issues](https://github.com/outside-labs/builtouts/issues) and
the [Project](https://github.com/orgs/outside-labs/projects/17) hold the queue.

`release.yaml` uses PyPI Trusted Publishing through environment
`pypi`; only an authorized `v0.1.0` tag on main can publish. Before tagging,
verify final-main CI and the release checklist in the implementation plan.
Published versions and release tags must never be replaced. See
[CHANGELOG.md](CHANGELOG.md). MIT licensed.
