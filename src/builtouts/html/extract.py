"""Explicit, scoped HTML fields returning ordinary Python records."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field as dataclass_field
from typing import Literal

from .nodes import Node
from .selectors import _Grammar

__all__ = ['Field', 'ExtractionError', 'extract', 'extract_all']
_UNSET = object()
type ErrorReason = Literal['missing', 'multiple', 'attribute', 'conversion', 'default']


class ExtractionError(ValueError):
    """A field failed; messages do not contain extracted source values."""

    def __init__(self, field: str, reason: ErrorReason, *, record: int | None = None,
                 item: int | None = None) -> None:
        self.field = field
        self.reason = reason
        self.record = record
        self.item = item
        context = f'record {record}, ' if record is not None else ''
        super().__init__(f'{context}field {field!r}: {reason}')


@dataclass(frozen=True, slots=True)
class Field:
    """Read the receiver (selector=None) or scoped descendant elements.

    Exactly one match is required unless many=True. Optional missing selections
    use a default, a per-use factory, None for a scalar, or [] for a collection.
    Optional missing/boolean attributes use the scalar fallback for that item.
    Constants are returned by reference; use a factory for fresh mutable defaults.
    """

    selector: str | None = None
    attribute: str | None = None
    many: bool = False
    required: bool = True
    strip: bool = True
    convert: Callable[[str], object] | None = None
    default: object = dataclass_field(default=_UNSET, repr=False)
    default_factory: Callable[[], object] | None = None

    def __post_init__(self) -> None:
        if self.selector is not None:
            _Grammar(self.selector).parse()
        if self.attribute is not None:
            if not isinstance(self.attribute, str):
                raise TypeError('attribute must be a string or None')
            if not self.attribute:
                raise ValueError('attribute must not be empty')
            object.__setattr__(self, 'attribute', self.attribute.lower())
        if any(not isinstance(getattr(self, name), bool) for name in ('many', 'required', 'strip')):
            raise TypeError('many, required and strip must be bools')
        for name in ('convert', 'default_factory'):
            value = getattr(self, name)
            if value is not None and not callable(value):
                raise TypeError(f'{name} must be callable or None')
        if self.default is not _UNSET and self.default_factory is not None:
            raise ValueError('choose default or default_factory')
        if self.required and (self.default is not _UNSET or self.default_factory is not None):
            raise ValueError('defaults require required=False')


def _schema(fields: Mapping[str, Field]) -> dict[str, Field]:
    if not isinstance(fields, Mapping):
        raise TypeError('fields must be a mapping')
    result = dict(fields)
    if any(not isinstance(name, str) or not name or not isinstance(spec, Field)
           for name, spec in result.items()):
        raise TypeError('fields require nonempty string names and Field values')
    return result


def _fallback(spec: Field, name: str, record: int | None, *, collection: bool = False) -> object:
    if spec.default_factory is not None:
        try:
            return spec.default_factory()
        except Exception as error:
            raise ExtractionError(name, 'default', record=record) from error
    if spec.default is not _UNSET:
        return spec.default
    return [] if collection else None


def _record(node: Node, fields: dict[str, Field], record: int | None) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, spec in fields.items():
        nodes = [node] if spec.selector is None else node.select(spec.selector)
        if not nodes:
            if spec.required:
                raise ExtractionError(name, 'missing', record=record)
            result[name] = _fallback(spec, name, record, collection=spec.many)
            continue
        if not spec.many and len(nodes) != 1:
            raise ExtractionError(name, 'multiple', record=record)
        values: list[object] = []
        for index, target in enumerate(nodes):
            item = index if spec.many else None
            value = target.attrs.get(spec.attribute) if spec.attribute is not None else target.text
            if value is None:
                if spec.required:
                    raise ExtractionError(name, 'attribute', record=record, item=item)
                values.append(_fallback(spec, name, record))
                continue
            if spec.strip:
                value = value.strip()
            if spec.convert is not None:
                try:
                    values.append(spec.convert(value))
                except Exception as error:
                    raise ExtractionError(name, 'conversion', record=record, item=item) from error
            else:
                values.append(value)
        result[name] = values if spec.many else values[0]
    return result


def extract(node: Node, fields: Mapping[str, Field]) -> dict[str, object]:
    """Extract one record; no coercion occurs without a conversion callback."""
    if not isinstance(node, Node):
        raise TypeError('node must be a Node')
    return _record(node, _schema(fields), None)


def extract_all(node: Node, selector: str, fields: Mapping[str, Field]) -> list[dict[str, object]]:
    """Extract records from selected descendants; error.record is zero-based.

    This collects every record into a list. Use explicit iteration and extract()
    when the caller needs incremental consumption or custom error handling.
    """
    if not isinstance(node, Node):
        raise TypeError('node must be a Node')
    schema = _schema(fields)
    return [_record(target, schema, index) for index, target in enumerate(node.select(selector))]
