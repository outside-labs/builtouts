"""Bounded, incremental HTMLParser adapters."""

from html.parser import HTMLParser

from .nodes import Node

VOID_ELEMENTS = frozenset({'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                           'link', 'meta', 'param', 'source', 'track', 'wbr'})


class ParseLimitError(ValueError):
    """An explicit parsing resource limit was exceeded."""


def _positive(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f'{name} must be a positive integer')
    if value <= 0:
        raise ValueError(f'{name} must be a positive integer')
    return value


class _BoundedParser(HTMLParser):
    """Shared single-use parser lifecycle; subclasses retain their own output."""

    def __init__(self, *, max_chars: int = 10_000_000, max_nodes: int = 100_000,
                 max_depth: int = 256) -> None:
        self.max_chars = _positive('max_chars', max_chars)
        self.max_nodes = _positive('max_nodes', max_nodes)
        self.max_depth = _positive('max_depth', max_depth)
        self._chars = 0
        self._events = 0
        self._closed = False
        self._failed = False
        super().__init__(convert_charrefs=True)

    def reset(self) -> None:
        # HTMLParser calls reset during construction. Reuse would desynchronize
        # subclass output and input buffers, so it is deliberately unsupported.
        if hasattr(self, 'rawdata'):
            raise RuntimeError('parsers are single-use; construct a new parser')
        super().reset()

    def _available(self) -> None:
        if self._closed or self._failed:
            raise RuntimeError('parser is closed or failed')

    def _count(self) -> None:
        self._events += 1
        if self._events > self.max_nodes:
            raise ParseLimitError('max_nodes exceeded')

    def feed(self, data: str) -> None:
        self._available()
        if not isinstance(data, str):
            raise TypeError('HTML input must be a string')
        try:
            if self._chars + len(data) > self.max_chars:
                raise ParseLimitError('max_chars exceeded')
            self._chars += len(data)
            super().feed(data)
        except BaseException:
            self._failed = True
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._available()
        try:
            super().close()
            self._finish()
        except BaseException:
            self._failed = True
            raise
        self._closed = True

    def _finish(self) -> None:
        pass


class Document(Node):
    """A document tree that never performs network I/O or executes markup."""

    def __init__(self) -> None:
        super().__init__('document')

    @classmethod
    def from_html(cls, source: str, *, max_chars: int = 10_000_000,
                  max_nodes: int = 100_000, max_depth: int = 256) -> Document:
        parser = DocumentParser(max_chars=max_chars, max_nodes=max_nodes, max_depth=max_depth)
        parser.feed(source)
        parser.close()
        return parser.document

    @property
    def title(self) -> str | None:
        node = self.find('title')
        return node.text.strip() if node is not None else None


class DocumentParser(_BoundedParser):
    """Incrementally build a read-only tree; inspect document after close()."""

    def __init__(self, *, max_chars: int = 10_000_000, max_nodes: int = 100_000,
                 max_depth: int = 256) -> None:
        super().__init__(max_chars=max_chars, max_nodes=max_nodes, max_depth=max_depth)
        self.document = Document()
        self._stack: list[Node] = [self.document]

    def _append(self, kind, *, tag=None, attrs=None, data='') -> Node:
        self._count()
        parent = self._stack[-1]
        node = Node(kind, tag=tag, attrs=attrs, data=data, parent=parent)
        parent._children.append(node)
        return node

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if len(self._stack) > self.max_depth:
            raise ParseLimitError('max_depth exceeded')
        node = self._append('element', tag=tag, attrs=dict(attrs))
        if tag not in VOID_ELEMENTS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if len(self._stack) > self.max_depth:
            raise ParseLimitError('max_depth exceeded')
        self._append('element', tag=tag, attrs=dict(attrs))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if not data:
            return
        children = self._stack[-1]._children
        if children and children[-1].kind == 'text':
            children[-1]._parts.append(data)
        else:
            self._append('text', data=data)

    def handle_comment(self, data: str) -> None:
        self._append('comment', data=data)

    def handle_decl(self, decl: str) -> None:
        self._append('declaration', data=decl)

    def handle_pi(self, data: str) -> None:
        self._append('processing_instruction', data=data)

    def unknown_decl(self, data: str) -> None:
        self._append('declaration', data=data)

    def _finish(self) -> None:
        self._stack = [self.document]
