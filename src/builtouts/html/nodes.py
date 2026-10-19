"""Read-only HTML tree views and iterative extraction."""

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Literal

type NodeKind = Literal['document', 'element', 'text', 'comment', 'declaration', 'processing_instruction']
type AttributeFilter = str | bool | None


class Node:
    """A parser-owned node; public child and attribute collections are read-only."""

    __slots__ = ('_kind', '_tag', '_attrs', '_parts', '_parent', '_children')

    def __init__(
        self, kind: NodeKind, *, tag: str | None = None,
        attrs: Mapping[str, str | None] | None = None, data: str = '',
        parent: Node | None = None,
    ) -> None:
        self._kind = kind
        self._tag = tag
        self._attrs = MappingProxyType(dict(attrs or {}))
        self._parts = [data] if data else []
        self._parent = parent
        self._children: list[Node] = []

    @property
    def kind(self) -> NodeKind:
        return self._kind

    @property
    def tag(self) -> str | None:
        return self._tag

    @property
    def attrs(self) -> Mapping[str, str | None]:
        return self._attrs

    @property
    def data(self) -> str:
        return ''.join(self._parts)

    @property
    def parent(self) -> Node | None:
        return self._parent

    @property
    def children(self) -> tuple[Node, ...]:
        return tuple(self._children)

    def descendants(self) -> Iterator[Node]:
        """Visit every descendant in source order, excluding this node."""
        pending = list(reversed(self._children))
        while pending:
            node = pending.pop()
            yield node
            pending.extend(reversed(node._children))

    @staticmethod
    def _filters(
        tag: str | None, attrs: Mapping[str, AttributeFilter] | None,
        attributes: Mapping[str, AttributeFilter],
    ) -> tuple[str | None, dict[str, AttributeFilter]]:
        if tag is not None and not isinstance(tag, str):
            raise TypeError('tag must be a string or None')
        filters = dict(attrs or {})
        filters.update(attributes)
        for name, value in filters.items():
            if not isinstance(name, str) or not isinstance(value, (str, bool, type(None))):
                raise TypeError('attribute filters require string names and str, bool, or None values')
        return tag.lower() if tag is not None else None, filters

    @staticmethod
    def _matches(node: Node, tag: str | None, filters: Mapping[str, AttributeFilter]) -> bool:
        if node.kind != 'element' or (tag is not None and node.tag != tag):
            return False
        for name, expected in filters.items():
            token_match = name == 'class_'
            key = 'class' if token_match else name.lower()
            present = key in node.attrs
            if expected is True:
                if not present:
                    return False
            elif expected is False:
                if present:
                    return False
            elif not present:
                return False
            elif token_match and isinstance(expected, str):
                if expected not in (node.attrs[key] or '').split():
                    return False
            elif node.attrs[key] != expected:
                return False
        return True

    def find_all(
        self, tag: str | None = None, *, attrs: Mapping[str, AttributeFilter] | None = None,
        **attributes: AttributeFilter,
    ) -> list[Node]:
        """Find descendant elements using exact attributes or class_ token matching."""
        tag, filters = self._filters(tag, attrs, attributes)
        return [node for node in self.descendants() if self._matches(node, tag, filters)]

    def find(
        self, tag: str | None = None, *, attrs: Mapping[str, AttributeFilter] | None = None,
        **attributes: AttributeFilter,
    ) -> Node | None:
        """Return the first matching descendant element, or None."""
        tag, filters = self._filters(tag, attrs, attributes)
        return next((node for node in self.descendants() if self._matches(node, tag, filters)), None)

    def get_text(self, separator: str = '', *, strip: bool = False, include_hidden: bool = False) -> str:
        """Join text pieces, omitting script/style subtrees unless requested."""
        if not isinstance(separator, str):
            raise TypeError('separator must be a string')
        pieces: list[str] = []
        pending = [self]
        while pending:
            node = pending.pop()
            if node.kind == 'text':
                piece = node.data.strip() if strip else node.data
                if piece:
                    pieces.append(piece)
            elif include_hidden or node.tag not in {'script', 'style'}:
                pending.extend(reversed(node._children))
        return separator.join(pieces)

    @property
    def text(self) -> str:
        return self.get_text()

    def select(self, selector: str) -> list[Node]:
        """Select descendants with the documented CSS subset."""
        from .selectors import select
        return select(self, selector)

    def select_one(self, selector: str) -> Node | None:
        """Return the first selected descendant, or None."""
        from .selectors import select
        result = select(self, selector, first=True)
        return result[0] if result else None

    def __repr__(self) -> str:
        return f'Node(kind={self.kind!r}, tag={self.tag!r})'
