"""Incremental extraction without retaining an HTML document tree."""

from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin

from .parser import _BoundedParser, ParseLimitError, VOID_ELEMENTS


@dataclass(frozen=True, slots=True)
class Link:
    """An anchor's original href, visible text, and explicitly resolved URL."""

    href: str
    text: str
    url: str


@dataclass(eq=False, slots=True)
class _Frame:
    tag: str
    href: str | None = None
    pieces: list[str] = field(default_factory=list)


class _StreamParser(_BoundedParser):
    def __init__(self, *, max_chars: int, max_nodes: int, max_depth: int) -> None:
        super().__init__(max_chars=max_chars, max_nodes=max_nodes, max_depth=max_depth)
        self._stack: list[_Frame] = []
        self._last_was_data = False

    def _open(self, tag: str, attrs: list[tuple[str, str | None]], *, closed: bool) -> None:
        if len(self._stack) >= self.max_depth:
            raise ParseLimitError('max_depth exceeded')
        self._count()
        self._last_was_data = False
        frame = _Frame(tag, dict(attrs).get('href') if tag == 'a' else None)
        if closed or tag in VOID_ELEMENTS:
            self._end(frame)
        else:
            self._stack.append(frame)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs, closed=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs, closed=True)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index].tag == tag:
                frames = self._stack[index:]
                del self._stack[index:]
                for frame in reversed(frames):
                    self._end(frame)
                self._last_was_data = False
                break

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if not self._last_was_data:
            self._count()
        self._last_was_data = True
        if not any(frame.tag in {'script', 'style'} for frame in self._stack):
            self._data(data)

    def handle_comment(self, data: str) -> None:
        self._count()
        self._last_was_data = False

    handle_decl = handle_comment
    handle_pi = handle_comment
    unknown_decl = handle_comment

    def _data(self, data: str) -> None:
        pass

    def _end(self, frame: _Frame) -> None:
        pass

    def _finish(self) -> None:
        frames, self._stack = self._stack, []
        for frame in reversed(frames):
            self._end(frame)


class LinkCollector(_StreamParser):
    """Emit links when anchors close, including implicit closure at EOF.

    Set collect=False with on_link to process output without retaining results.
    URL resolution does not validate schemes or make URLs safe to fetch.
    """

    def __init__(self, *, base_url: str | None = None,
                 on_link: Callable[[Link], None] | None = None, collect: bool = True,
                 max_chars: int = 10_000_000, max_nodes: int = 100_000,
                 max_depth: int = 256) -> None:
        if base_url is not None and not isinstance(base_url, str):
            raise TypeError('base_url must be a string or None')
        if on_link is not None and not callable(on_link):
            raise TypeError('on_link must be callable or None')
        if not isinstance(collect, bool):
            raise TypeError('collect must be a bool')
        super().__init__(max_chars=max_chars, max_nodes=max_nodes, max_depth=max_depth)
        self._base_url = base_url
        self._on_link = on_link
        self._collect = collect
        self._links: list[Link] = []

    @property
    def links(self) -> tuple[Link, ...]:
        return tuple(self._links)

    def _data(self, data: str) -> None:
        for frame in self._stack:
            if frame.href is not None:
                frame.pieces.append(data)

    def _end(self, frame: _Frame) -> None:
        if frame.href is None:
            return
        url = urljoin(self._base_url, frame.href) if self._base_url is not None else frame.href
        link = Link(frame.href, ''.join(frame.pieces), url)
        if self._collect:
            self._links.append(link)
        if self._on_link is not None:
            self._on_link(link)


class TextCollector(_StreamParser):
    """Collect visible text or call on_text with incremental decoded chunks."""

    def __init__(self, *, on_text: Callable[[str], None] | None = None,
                 collect: bool = True, max_chars: int = 10_000_000,
                 max_nodes: int = 100_000, max_depth: int = 256) -> None:
        if on_text is not None and not callable(on_text):
            raise TypeError('on_text must be callable or None')
        if not isinstance(collect, bool):
            raise TypeError('collect must be a bool')
        super().__init__(max_chars=max_chars, max_nodes=max_nodes, max_depth=max_depth)
        self._on_text = on_text
        self._collect = collect
        self._pieces: list[str] = []

    @property
    def text(self) -> str:
        return ''.join(self._pieces)

    def _data(self, data: str) -> None:
        if self._collect:
            self._pieces.append(data)
        if self._on_text is not None:
            self._on_text(data)
