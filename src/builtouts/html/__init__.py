"""Dependency-free HTML trees and extraction powered by html.parser."""

from .nodes import Node
from .parser import Document, DocumentParser, ParseLimitError

__all__ = ['Document', 'DocumentParser', 'Node', 'ParseLimitError']
