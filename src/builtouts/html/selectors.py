"""A deliberately small, strictly validated CSS selector subset."""

from dataclasses import dataclass
import re

from .nodes import Node

_IDENT = re.compile(r'-?[_a-zA-Z][_a-zA-Z0-9-]*')


class SelectorSyntaxError(ValueError):
    """A selector is malformed or uses syntax outside the supported subset."""


@dataclass(frozen=True, slots=True)
class _Compound:
    tag: str | None
    ids: tuple[str, ...]
    classes: tuple[str, ...]
    attrs: tuple[tuple[str, str | None], ...]

    def matches(self, node: Node) -> bool:
        if node.kind != 'element' or (self.tag is not None and node.tag != self.tag):
            return False
        classes = (node.attrs.get('class') or '').split()
        return (all(node.attrs.get('id') == value for value in self.ids)
                and all(value in classes for value in self.classes)
                and all(name in node.attrs and (value is None or node.attrs[name] == value)
                        for name, value in self.attrs))


class _Grammar:
    def __init__(self, source: str) -> None:
        if not isinstance(source, str):
            raise TypeError('selector must be a string')
        if len(source) > 4096:
            raise SelectorSyntaxError('selectors are limited to 4096 characters')
        if '\\' in source:
            raise SelectorSyntaxError('CSS escapes are not supported')
        self.source = source
        self.pos = 0

    def peek(self) -> str:
        return self.source[self.pos:self.pos + 1]

    def space(self) -> bool:
        start = self.pos
        while self.peek() and self.peek().isspace():
            self.pos += 1
        return self.pos > start

    def identifier(self) -> str:
        match = _IDENT.match(self.source, self.pos)
        if match is None:
            raise SelectorSyntaxError(f'expected an ASCII identifier at position {self.pos}')
        self.pos = match.end()
        return match.group()

    def attribute(self) -> tuple[str, str | None]:
        self.pos += 1
        self.space()
        name = self.identifier().lower()
        self.space()
        value = None
        if self.peek() == '=':
            self.pos += 1
            self.space()
            if self.peek() in {'"', "'"}:
                quote = self.peek()
                self.pos += 1
                end = self.source.find(quote, self.pos)
                if end == -1:
                    raise SelectorSyntaxError('unterminated attribute value')
                value = self.source[self.pos:end]
                self.pos = end + 1
                if any(char in value for char in '\n\r\f'):
                    raise SelectorSyntaxError('newlines in attribute strings are not supported')
            else:
                value = self.identifier()
            self.space()
        if self.peek() != ']':
            raise SelectorSyntaxError(f'expected ] at position {self.pos}')
        self.pos += 1
        return name, value

    def compound(self) -> _Compound:
        start = self.pos
        tag = None
        ids: list[str] = []
        classes: list[str] = []
        attrs: list[tuple[str, str | None]] = []
        if self.peek() == '*':
            self.pos += 1
        elif _IDENT.match(self.source, self.pos):
            tag = self.identifier().lower()
        while self.peek() in {'#', '.', '['}:
            prefix = self.peek()
            if prefix == '[':
                attrs.append(self.attribute())
            else:
                self.pos += 1
                (ids if prefix == '#' else classes).append(self.identifier())
        if self.pos == start:
            raise SelectorSyntaxError(f'expected a selector at position {self.pos}')
        return _Compound(tag, tuple(ids), tuple(classes), tuple(attrs))

    def parse(self) -> list[list[tuple[str, _Compound]]]:
        groups: list[list[tuple[str, _Compound]]] = []
        self.space()
        group = [('', self.compound())]
        count = 1
        while True:
            spaced = self.space()
            char = self.peek()
            if not char:
                groups.append(group)
                return groups
            if char == ',':
                groups.append(group)
                group = []
                relation = ''
                self.pos += 1
                self.space()
            elif char == '>':
                relation = 'child'
                self.pos += 1
                self.space()
            elif spaced:
                relation = 'descendant'
            else:
                raise SelectorSyntaxError(f'unsupported syntax at position {self.pos}')
            count += 1
            if count > 64:
                raise SelectorSyntaxError('selectors are limited to 64 compound parts')
            group.append((relation, self.compound()))


def _matches(node: Node, group: list[tuple[str, _Compound]], scope: Node) -> bool:
    # Backtrack descendant alternatives: the nearest matching ancestor may fail
    # an earlier child constraint. Memoization bounds repeated ancestor states.
    pending = [(node, len(group) - 1)]
    visited: set[tuple[Node, int]] = set()
    while pending:
        current, index = pending.pop()
        if (current, index) in visited:
            continue
        visited.add((current, index))
        relation, compound = group[index]
        if not compound.matches(current):
            continue
        if index == 0:
            return True
        if current is scope:
            continue
        parent = current.parent
        while parent is not None:
            pending.append((parent, index - 1))
            if relation == 'child' or parent is scope:
                break
            parent = parent.parent
    return False


def select(scope: Node, selector: str, *, first: bool = False) -> list[Node]:
    groups = _Grammar(selector).parse()
    result: list[Node] = []
    for node in scope.descendants():
        if node.kind == 'element' and any(_matches(node, group, scope) for group in groups):
            result.append(node)
            if first:
                break
    return result
