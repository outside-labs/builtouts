# Builtouts implementation plan

Status: selected v0.1.0 scope; publication requires a separate release decision.

## Purpose

Builtouts builds out Python's batteries: reusable interfaces, adapters, and
explicit conventions powered by builtins and the standard library. A feature
belongs here when it removes recurring application boilerplate, has a clear
contract, works independently, and does not silently change Python's behavior.

The source concept is `builtouts GIST01.md`. The package and distribution name
are `builtouts`; the repository is `outside-labs/builtouts`. Earlier names in the
gist are exploratory and are not compatibility commitments.

## Decisions for v0.1.0

- Preserve the existing Python 3.14+ baseline and `uv_build` backend.
- Require no third-party runtime dependencies. Use `unittest` for verification.
- Keep flat, independently importable feature namespaces: `builtouts.html`,
  `builtouts.concurrent`, and `builtouts.conventions`.
- Build an HTML extraction library, not a browser engine. Publish the exact
  parsing recovery rules and supported selector grammar.
- Offer bounded, synchronous thread concurrency for I/O tasks. Do not promise
  faster CPU-bound parsing or cancellation of an already running Python thread.
- Include a small naming-convention module as a second example of the broader
  library identity. Do not add a plugin registry or mandatory common base class.
- Ship type annotations and `py.typed`, examples, an MIT license, changelog,
  three-platform CI, and isolated distribution verification.
- Prepare `.github/workflows/release.yaml` for Trusted Publishing with the
  `pypi` environment. Creating a release tag or publishing is a separate action.

## Architecture

```text
src/builtouts/
    __init__.py           package version; no eager feature imports
    py.typed
    html/
        __init__.py       supported public HTML API
        nodes.py          read-only tree views and traversal
        parser.py         bounded HTMLParser event adapter and Document
        selectors.py      explicit, small CSS grammar and matching
        collectors.py     incremental link and visible-text extraction
    concurrent.py        bounded thread iteration and collection
    conventions.py       deterministic naming transformations
tests/                   synthetic offline fixtures and contract tests
examples/                executable, offline use cases
scripts/                 distribution verification
.github/workflows/
    checks.yaml
    release.yaml
```

HTML does not import concurrency, conventions, or a future HTTP client. Root
imports must not construct executors, access the network, modify environment
state, or monkey-patch builtins. No CLI is selected: remove the generated hello
world entry point rather than invent a command surface for a library.

### HTML tree and parsing contract

`Document.from_html(source)` parses Unicode strings. `DocumentParser` subclasses
`html.parser.HTMLParser` and supports incremental `feed()` followed by `close()`.
Its `document` exposes nodes with `kind`, `tag`, `attrs`, `data`, `parent`, and
`children`. Child and attribute collections are read-only to callers; all
mutation stays inside the parser. Documents remain live while fed and stable
after close. A parser is single-use; feeding after close or failure is an error.

Parsing rules:

- Normalize element and attribute names through HTMLParser's HTML handling.
- Preserve text, comments, declarations, processing instructions, and source
  order. Empty/boolean attribute values remain `None`; duplicate attributes use
  the last value. Text character references are decoded, except the standard
  library's raw script/style content handling.
- HTML void elements never become parents. XHTML self-closing syntax closes
  immediately. A matching end tag closes its element and intervening open
  elements. Unmatched end tags are ignored. Open elements close at EOF.
- Do not implement HTML5 tree construction, implied optional end tags, foster
  parenting, namespace-aware XML, DOM scripting, or browser layout.
- Bound total input characters, tree nodes, and open element depth; defaults
  are 10,000,000 characters, 100,000 nodes, and 256 levels. Positive integer
  overrides are explicit. Raise `ParseLimitError` on excess and reject reuse.
- Iterate rather than recurse for traversal and extraction. These limits are
  application guardrails, not an adversarial CPU/memory sandbox.

`find()` / `find_all()` search descendant elements, excluding the receiver.
They accept an optional tag, an `attrs` mapping, and keyword attributes. A
filter value of `True` means present, `False` means absent, `None` means a
present boolean attribute, and a string means exact value. Multiple filters
are ANDed. `class_` maps to `class` and matches whitespace-delimited tokens.

`text` joins descendant text without introducing whitespace, excluding comments,
script, and style. `get_text(separator='', strip=False, include_hidden=False)`
lets callers explicitly request separators, per-piece trimming, or raw script
and style text. Text is extraction data, never sanitized HTML. `Document.title`
is the stripped text of the first title or `None`.

### Query grammar

Support tag and universal selectors, `.class`, `#id`, `[attr]`, `[attr=value]`,
compound selectors, descendants, direct children (`>`), and comma groups.
Attribute values may be unquoted identifiers or quoted strings. Tags and
attribute names are normalized; IDs, classes, and values remain case-sensitive.
Results are deduplicated in document order. Matching is scoped to the receiver's
subtree; ancestor matching does not escape its element boundary. The receiver
may satisfy an ancestor part but is never itself returned.

Reject unsupported syntax with `SelectorSyntaxError`, including sibling
combinators, pseudo-classes/elements, escapes, namespace syntax, and substring
attribute operators. Empty selectors and malformed groups fail clearly, even
on empty documents. No silent partial matching. Add selector-length and part
limits and use iterative matching to avoid recursive overflow.

### Streaming collectors

`LinkCollector` and `TextCollector` share the parser's incremental lifecycle and
limits without retaining a document tree. Link results contain original `href`,
visible anchor text, and an optional resolved URL from an explicit `base_url`.
Keep relative URLs when no base is supplied; do not fetch or execute URLs.
Do not trust an input `<base>` tag to redirect resolution. Boolean/missing href
attributes produce no link; an empty-string href is valid. Void elements and
self-closing anchors must not leave dangling state. Collectors support a
callback-only mode so callers can process output without accumulating results.
Their working memory is bounded by input/depth/result limits; accumulated text
or link results necessarily use memory proportional to retained output.

### Concurrency contract

Public APIs:

```python
from builtouts.concurrent import thread_iter, thread_map

lengths = thread_map(len, ['one', 'three'], max_workers=4)
with thread_iter(len, ['one', 'three'], ordered=False) as results:
    for length in results:
        print(length)
```

`thread_map()` returns a list. `thread_iter()` is a context manager yielding a
single-pass result iterator; callers use `with` even if they stop early.
Both accept a function, an iterable, `max_workers`, `max_pending`, and `ordered`.
Default worker count follows ThreadPoolExecutor's Python 3.14 rule; the default
pending bound is twice that count. Positive integer validation excludes bool.
`ordered=True` returns input order; false yields ready work first, with no
promised ordering between simultaneous completions.

Only pull input as capacity becomes available. The pending bound includes
submitted work whose result has not yet been yielded, including completed work.
Do not create a future for the entire input in advance. Iterable and worker
exceptions preserve their original types. On exceptions or early context exit,
cancel queued work and join running workers. Calls may therefore wait for
already-running functions; users must provide I/O timeouts. No pool, global
queue, retry, or rate limit is implicit. Infinite inputs require `thread_iter()`
and a terminating caller. A `thread_map()` result list is intentionally unbounded.

Validate concurrency with events/barriers and finite safety timeouts rather than
performance thresholds: actual overlap, pending-input bounds, ordering, empty
inputs, iterator failures, worker exceptions, early exits, and thread cleanup.

### Naming conventions

Expose `words()`, `snake_case()`, `kebab_case()`, `camel_case()`, and
`pascal_case()`. Separate lowercase-to-uppercase boundaries and acronym-to-word
boundaries (`HTTPServer` becomes `http_server`); retain digit runs with adjacent
words (`version2ID` becomes `version2_id`). Treat punctuation/whitespace as
separators, support Unicode letters/digits, and normalize to NFC. Conversion
does not imply valid Python identifiers, path safety, slug uniqueness,
transliteration, locale-specific casing, or reversible original spelling.
Document collisions and empty-input behavior. Keep the module free of I/O.

## Delivery queue

Create GitHub issues and a linked organization Project before implementation.
The issues/Project are the canonical status and dependency queue; this plan
records architecture and milestone gates. Implement the selected five tasks as
focused PRs, building dependent work on the preceding local branch. Start CI
when each PR is ready and continue the next task. Squash merge in dependency
order after passing checks. Preserve parent branches while children target them,
reconcile children without rewriting shared history, verify focused diffs and
fresh checks after retargeting, and verify final main before cleanup.

| Task | Scope and acceptance | Dependencies |
| --- | --- | --- |
| HTML-01 | Read-only tree, traversal, find/text, bounded incremental parser, malformed markup fixtures, minimal three-platform CI | Bootstrap |
| HTML-02 | Strict selector subset, link/text collectors, callback mode, chunked and limit tests | HTML-01 |
| CONC-01 | Bounded thread map/iteration, ordered/ready results, exception and shutdown tests | HTML-01 foundation |
| CONV-01 | Unicode-aware word splitting and deterministic naming transformations, documented edge cases | HTML-01 foundation |
| REL-01 | Complete docs/examples, metadata/typing/license, artifact and installed-package checks, release workflow and release checklist | All selected features |

### Verification and release gate

1. Run focused tests with each implementation, then the relevant suite.
2. CI runs all tests on Linux, macOS, and Windows using Python 3.14. Treat resource
   warnings as errors. No live sites or production credentials in tests.
3. Build wheel and sdist from the reviewed source. Verify exact archive contents,
   original package bytes, license, metadata/version, Python floor, typing marker,
   empty runtime requirements, and absence of generated CLI entry points.
4. Rebuild a wheel from the sdist and compare package bytes and metadata. Install
   wheel and sdist separately into fresh virtual environments, with no runtime
   dependency installation. Run tests and offline examples outside the checkout.
5. Keep workflow actions pinned to reviewed commit SHAs. Only the publish job has
   OIDC permission; it consumes the distributions verified by the check jobs.
6. A release tag must match the package version, be the selected `v0.1.0`, and
   point at a commit on main. Ordinary PR/main CI never publishes. The publisher
   must match owner `outside-labs`, repository `builtouts`, workflow
   `release.yaml`, environment `pypi`, and PyPI project `builtouts`.
7. Before publication, confirm final-main CI, inspect final artifacts, and record
   the selected source and workflow run in REL-01. Stop at this preparation gate.
8. After explicit publication authorization: tag the verified commit, observe
   the workflow, create release notes, compare PyPI bytes/hashes with the verified
   workflow artifacts, and run a fresh uncached install from public PyPI.
   Release tags and uploaded versions are immutable; use a new patch for fixes.

## Future milestones and decision gates

These are planned opportunities, not v0.1.0 promises. Add features only after a
specific use case and a focused contract have been selected.

| Task | Opportunity | Gate and completion criteria |
| --- | --- | --- |
| HTTP-01 | `builtouts.http` over urllib.request | Select redirect, proxy, TLS, response-size, deadline, error, decoding, and ownership contracts; loopback-only tests; HTTP(S) only; no silent retries or SSRF-safety claim |
| HTML-03 | Mutation and serialization | Define parent ownership, detach/move/copy, cycle prevention, text/attribute escaping, raw-text behavior, and normalized versus lossless output; round-trip tests; never imply sanitization |
| HTML-04 | Structured extraction | Explicit required/optional fields and selector/cardinality/conversion errors; dataclass-friendly adapters; optional enforce-type integration without a core dependency |
| HTML-05 | Extended selectors | Add only requested grammar; reference fixtures, performance bounds, and explicit unsupported syntax; decide whether browser-grade querying belongs in an optional backend |
| HTML-06 | Recovery profiles | Demand and corpus needed before implied end tags or HTML5 behavior; document intentional divergences rather than claim Beautiful Soup equivalence |
| CONC-02 | Per-item outcomes and progress | Select error aggregation, indices/input retention, callback thread, cancellation ownership, and retry/idempotency policies |
| CONC-03 | Processes and interpreter pools | Separate pickling/start-method/isolation contracts and CPU workload evidence; never switch execution strategy silently |
| CONC-04 | Async helpers | Demonstrate a gap beyond asyncio.TaskGroup; define cancellation and bounded producer semantics without mixing Future types |
| CONV-02 | Shared conventions | Concrete downstream consumers before field aliases, serialization policies, or project templates; explicit opt-in policies, no global defaults |
| ITER-01 | Iterator conveniences | Real recurring use cases beyond itertools; define laziness, one-shot inputs, memory, and infinite-input behavior |
| PATH-01 | Filesystem helpers | Specify symlink, overwrite, atomicity, encoding, permissions, and sandbox boundaries; no implicit destructive operations |
| JSON-01 | JSON codecs | Select type/coercion/duplicate-key/non-finite/cycle contracts; preserve independent interoperability with validation packages |
| QA-02 | Corpus and performance work | License-cleared offline fixtures; memory/throughput baselines and adversarial cases; benchmark environment recorded; no unsupported speed claims |
| DOC-01 | Hosted documentation | Choose canonical host/URL and version policy before adding a docs service or dependencies |
| PORT-01 | Wider Python/platform support | Evidence and CI for each extra version or free-threaded build; concurrency is unavailable on WASI; no browser runtime promise |
| PACK-01 | Independent distribution extraction | Only split when usage, maintenance, or release cadence warrants it; avoid overlapping ordinary packages across distributions |

## Boundaries and risks

- HTMLParser tokenization differs from browser DOM construction. Synthetic
  fixtures and documentation must expose the exact recovery rules.
- Resource limits constrain retained work but cannot turn an in-process parser
  into a hard isolation boundary. Callers must bound network input separately.
- Thread concurrency is cooperative with respect to the worker function. A stuck
  function can delay shutdown; timeout and retry policy belongs to the operation.
- Selectors need strict grammar validation, predictable scoping, and bounded
  complexity; reject unsupported syntax instead of guessing intent.
- Naming conversions can collide and Unicode case mappings can expand strings.
  They are conventions, not validators or secure filename generators.
- Avoid a miscellaneous-helper collection: new modules need independent value,
  a maintained contract, examples, and the same zero-runtime-dependency gate.

## References

- [Python HTMLParser](https://docs.python.org/3.14/library/html.parser.html):
  event hooks, character references, incremental parsing, and recovery limits.
- [Python concurrent.futures](https://docs.python.org/3.14/library/concurrent.futures.html):
  worker defaults, buffering, shutdown, cancellation, and executor tradeoffs.
- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/adding-a-publisher/):
  exact repository, workflow, and environment identity for OIDC publishing.
