"""Inline SVG architecture diagrams for the case studies.

One vertical flow per case study, read top to bottom: sources, processing,
guardrails, human review, output. Vertical so it stays legible at phone width,
where a five-box row would shrink its text below reading size.

Colours are CSS custom properties, never literals, so a diagram follows the
page's light or dark theme with no script. Every diagram carries <title> and
<desc>, and the desc says the whole flow in words, so a screen reader gets the
same information as the picture.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from textwrap import wrap

WIDTH = 360
BOX_X, BOX_W = 20, 320
LINE_H = 19
PAD_Y = 12
ROLE_H = 20            # the small role label above each box
ARROW_H = 28
WRAP_AT = 38           # characters per line at 14px IBM Plex Sans in a 290px box
GROUP_PAD = 14

ROLES = {
    "source": "Source",
    "processing": "Processing",
    "model": "Model output",
    "guardrail": "Guardrail",
    "review": "Human review",
    "output": "Output",
}


@dataclass(frozen=True)
class Stage:
    role: str
    text: str
    strong: bool = False          # heavier border, for the step the diagram is about


@dataclass(frozen=True)
class Group:
    label: str
    stages: tuple[Stage, ...]


@dataclass(frozen=True)
class Diagram:
    title: str
    desc: str
    flow: tuple[Stage | Group, ...]
    footnote: str = ""


def _stage(s: Stage, y: float, x: float = BOX_X, w: float = BOX_W) -> tuple[list[str], float]:
    lines = wrap(s.text, WRAP_AT - (4 if w < BOX_W else 0))
    h = PAD_Y * 2 + LINE_H * len(lines) - 4
    out = [f'<g class="dg-stage dg-{s.role}">',
           f'<text class="dg-role" x="{x}" y="{y + 13}">{escape(ROLES[s.role])}</text>']
    top = y + ROLE_H
    cls = "dg-box dg-strong" if s.strong else "dg-box"
    out.append(f'<rect class="{cls}" x="{x}" y="{top}" width="{w}" height="{h}" rx="8"/>')
    out.append(f'<rect class="dg-bar" x="{x}" y="{top}" width="5" height="{h}" rx="2"/>')
    for i, line in enumerate(lines):
        out.append(f'<text class="dg-text" x="{x + 18}" y="{top + PAD_Y + 13 + i * LINE_H}">'
                   f'{escape(line)}</text>')
    out.append("</g>")
    return out, top + h


def _arrow(y: float) -> list[str]:
    cx = BOX_X + BOX_W / 2
    return [f'<path class="dg-arrow" d="M{cx} {y + 4} V{y + ARROW_H - 6}"/>',
            f'<path class="dg-head" d="M{cx - 5} {y + ARROW_H - 10} L{cx} {y + ARROW_H - 3} '
            f'L{cx + 5} {y + ARROW_H - 10} Z"/>']


def render(d: Diagram, ident: str) -> str:
    body: list[str] = []
    y = 4.0
    for i, item in enumerate(d.flow):
        if i:
            body += _arrow(y)
            y += ARROW_H
        if isinstance(item, Stage):
            part, y = _stage(item, y)
            body += part
            continue
        # A group: a dashed boundary around the stages it holds, labelled on top.
        top = y
        inner: list[str] = []
        yy = top + 26
        for j, s in enumerate(item.stages):
            if j:
                inner += _arrow(yy)
                yy += ARROW_H
            part, yy = _stage(s, yy, BOX_X + GROUP_PAD, BOX_W - GROUP_PAD * 2)
            inner += part
        bottom = yy + GROUP_PAD
        body.append(f'<rect class="dg-group" x="{BOX_X - 6}" y="{top}" width="{BOX_W + 12}" '
                    f'height="{bottom - top}" rx="12"/>')
        body.append(f'<text class="dg-group-label" x="{BOX_X + 8}" y="{top + 17}">'
                    f'{escape(item.label)}</text>')
        body += inner
        y = bottom
    if d.footnote:
        y += 10
        for k, line in enumerate(wrap(d.footnote, 46)):
            body.append(f'<text class="dg-note" x="{BOX_X}" y="{y + 14 + k * 18}">{escape(line)}</text>')
        y += 18 * len(wrap(d.footnote, 46)) + 4
    height = int(y + 8)
    head = (f'<svg class="diagram" viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" '
            f'role="img" aria-labelledby="{ident}-t {ident}-d">'
            f'<title id="{ident}-t">{escape(d.title)}</title>'
            f'<desc id="{ident}-d">{escape(d.desc)}</desc>')
    return head + "".join(body) + "</svg>"
