"""The case study model shared by the Ortho case studies (sitegen.py) and the products (productgen.py)."""

from __future__ import annotations

from dataclasses import dataclass

from diagram import Diagram


@dataclass(frozen=True)
class Result:
    value: str
    label: str
    numeric: bool = True        # IBM Plex Mono is for numbers only


@dataclass(frozen=True)
class Case:
    slug: str
    name: str
    kind: str
    dek: str
    description: str
    problem: tuple[str, ...]
    did: tuple[str, ...]
    how: str
    diagram: Diagram
    results: tuple[Result, ...]
    nxt: str
    stack: tuple[str, ...]
