"""Dependency-free HTML trees and extraction powered by html.parser."""

from .nodes import Node
from .parser import Document, DocumentParser, ParseLimitError
from .selectors import SelectorSyntaxError
from .collectors import Link, LinkCollector, TextCollector

__all__ = ['Document', 'DocumentParser', 'Node', 'ParseLimitError',
           'SelectorSyntaxError', 'Link', 'LinkCollector', 'TextCollector']
