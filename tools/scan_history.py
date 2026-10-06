"""Scan every object in a repo's history for personal information, inside compressed files too.

    py tools/scan_history.py <repo> [<repo> ...]

A plain byte search is blind to anything compressed: the text of a PDF sits in
Flate streams and an .xlsx or .docx is a zip, so a name in a workbook's
properties or an email in a résumé reads as clean. This scan opens each object
before searching it:

    zip (xlsx, docx, pptx, any zip)   every member, recursively
    pdf                               extracted text, metadata, every inflated stream
    gzip                              decompressed

Every form is searched as text, decoded as UTF-8 and, when it looks like it,
UTF-16, with case folded, and again with markup removed and whitespace
squeezed out, so a name split across a document's text runs or an email spaced
out by a PDF's layout still matches. File names are searched too, every path a
blob ever had is judged on its own, and commit and tag objects (identities and
messages) are searched like files.

Formats it cannot open (fonts, images) are searched as raw bytes and listed by
extension, so that blind spot is printed, not hidden. Anything that fails to
open, nests deeper than the limit or inflates past it is reported UNREADABLE,
never passed. Only objects reachable from refs are scanned, which is what a
clone receives.

What to look for comes from a local file outside every repo, never from the
code: HISTORY_SCAN_NEEDLES, or ~/.config/history-scan/needles.txt, one
`label = value` per line. Only labels are printed. Without that file the scan
reports NOT RUN, and a malformed line stops it.

A repo may allow a label on some paths in `.history-scan-allow`, one
`label path-glob  # reason` per line. The reason is required. Commit and tag
objects have no path and match `(commit)` and `(tag)`. Globs follow fnmatch,
where `*` also crosses `/`.

Exit codes: 0 clean, 1 findings or unreadable objects, 2 not run.
"""

from __future__ import annotations

import fnmatch
import gzip
import io
import os
import re
import subprocess
import sys
import zipfile
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

NEEDLES_FILE = Path(os.environ.get("HISTORY_SCAN_NEEDLES")
                    or Path.home() / ".config" / "history-scan" / "needles.txt")
ALLOW_FILE = ".history-scan-allow"
MAX_INFLATED = 64 * 1024 * 1024        # per member or stream: past it the object is UNREADABLE
MAX_DEPTH = 4                          # containers inside containers: past it the object is UNREADABLE
STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
MARKUP = re.compile(r"<[^>]*>")
SPACE = re.compile(r"\s+")


@dataclass
class Result:
    findings: list[tuple[str, str, str]] = field(default_factory=list)    # label, where, how
    allowed: list[tuple[str, str, str]] = field(default_factory=list)     # label, where, reason
    unreadable: list[tuple[str, str]] = field(default_factory=list)       # where, why
    opened: Counter = field(default_factory=Counter)                      # how each object was read
    raw_only: Counter = field(default_factory=Counter)                    # binary extensions searched raw
    objects: int = 0


@dataclass(frozen=True)
class Needle:
    label: str
    text: str            # case folded
    squeezed: str        # case folded, whitespace removed


def needle(label: str, value: str) -> Needle:
    folded = value.casefold()
    return Needle(label, folded, SPACE.sub("", folded))


def load_needles(path: Path = NEEDLES_FILE) -> list[Needle]:
    if not path.is_file():
        return []
    needles = []
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        label, eq, value = (s.strip() for s in line.partition("="))
        if not eq or not label or not value:
            raise ValueError(f"{path} line {n}: expected 'label = value'")
        needles.append(needle(label, value))
    return needles


def load_allow(repo: Path) -> list[tuple[str, str, str]]:
    path = repo / ALLOW_FILE
    if not path.is_file():
        return []
    rules = []
    for n, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        rule, _, reason = line.partition("#")
        parts = rule.split()
        if len(parts) != 2 or not reason.strip():
            raise ValueError(f"{path.name} line {n}: expected 'label path-glob  # reason'")
        rules.append((parts[0], parts[1], reason.strip()))
    return rules


# --------------------------------------------------------------------------- opening objects

def kind(data: bytes) -> str:
    if data[:4] == b"PK\x03\x04":
        return "zip"
    if data[:5] == b"%PDF-":
        return "pdf"
    return "gzip" if data[:2] == b"\x1f\x8b" else ""


def inflate(raw: bytes) -> bytes:
    d = zlib.decompressobj()
    out = d.decompress(raw, MAX_INFLATED)
    if d.unconsumed_tail:
        raise ValueError("a PDF stream inflates past the limit")
    return out


def pdf_views(data: bytes) -> list[tuple[str, bytes]]:
    import pypdf                                    # only needed when a PDF is present
    reader = pypdf.PdfReader(io.BytesIO(data))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    meta = "\n".join(str(v) for v in (reader.metadata or {}).values())
    views = [("pdf text", text.encode("utf-8")), ("pdf metadata", meta.encode("utf-8"))]
    for k, raw in enumerate(STREAM.findall(data)):
        try:
            views.append((f"pdf stream {k}", inflate(raw)))
        except zlib.error:
            pass        # not Flate (or another filter first): the text view and the raw view cover it
    return views


def views(data: bytes, depth: int = 0) -> list[tuple[str, bytes]]:
    """Every readable form of an object: the raw bytes, then whatever it contains."""
    out = [("raw", data)]
    what = kind(data)
    if what and depth >= MAX_DEPTH:
        raise ValueError(f"a {what} nested more than {MAX_DEPTH} deep")
    if what == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if info.file_size > MAX_INFLATED:
                    raise ValueError(f"member {info.filename} inflates past the limit")
                for how, inner in views(z.read(info), depth + 1):
                    out.append((f"zip:{info.filename} {how}", inner))
    elif what == "pdf":
        out += pdf_views(data)
    elif what == "gzip":
        inner = gzip.GzipFile(fileobj=io.BytesIO(data)).read(MAX_INFLATED + 1)
        if len(inner) > MAX_INFLATED:
            raise ValueError("a gzip inflates past the limit")
        out += [(f"gzip {how}", form) for how, form in views(inner, depth + 1)]
    return out


def texts(form: bytes) -> list[str]:
    """The ways a form can read as text: UTF-8, and UTF-16 when it has the BOM or the zero bytes for it."""
    decoded = [form.decode("utf-8", "replace")]
    sample = form[:4096]
    if form[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(sample) > 8 and sample.count(0) > len(sample) // 4):
        for enc in ("utf-16-le", "utf-16-be"):
            decoded.append(form.decode(enc, "replace"))
    return [t.casefold() for t in decoded]


def matches(n: Needle, forms: list[tuple[str, bytes]]) -> str | None:
    """How the needle was found, or None."""
    for how, form in forms:
        for text in texts(form):
            if n.text in text:
                return how
            if n.squeezed and n.squeezed in SPACE.sub("", MARKUP.sub("", text)):
                return f"{how}, split by markup or spacing"
    return None


# --------------------------------------------------------------------------- walking history

def run(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True).stdout


def objects(repo: Path) -> dict[str, set[str]]:
    """Every commit, tag and blob reachable from a ref, with every path each blob ever had."""
    found: dict[str, set[str]] = defaultdict(set)
    commits = run(repo, "rev-list", "--all").decode().split()
    for commit in commits:
        found[commit]
        for entry in run(repo, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
            if entry:
                meta, path = entry.split(b"\t", 1)
                mode, otype, oid = meta.decode().split()
                if otype == "blob":
                    found[oid].add(path.decode("utf-8", "replace"))
    for line in run(repo, "for-each-ref", "--format=%(objectname) %(objecttype)", "refs/tags").decode().splitlines():
        oid, otype = line.split()
        if otype == "tag":
            found[oid]
    return found


def read_all(repo: Path, oids: list[str]) -> dict[str, tuple[str, bytes] | None]:
    """All objects through one `git cat-file --batch` call. None for an object git reports missing."""
    out = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, input="\n".join(oids).encode() + b"\n",
                         capture_output=True, check=True).stdout
    found: dict[str, tuple[str, bytes] | None] = {}
    pos = 0
    while pos < len(out):
        header_end = out.index(b"\n", pos)
        header = out[pos:header_end].decode().split()
        if header[-1] == "missing":
            found[header[0]] = None
            pos = header_end + 1
            continue
        oid, otype, size = header
        start = header_end + 1
        found[oid] = (otype, out[start:start + int(size)])
        pos = start + int(size) + 1
    return found


def scan(repo: Path, needles: list[Needle], raw_only: bool = False, use_allow: bool = True) -> Result:
    """`raw_only` is the old byte search, kept so the tests can show what it missed.
    `use_allow=False` ignores the allow file, the control that shows allowed paths are really found."""
    allow = load_allow(repo) if use_allow else []
    listed = objects(repo)
    content = read_all(repo, list(listed))
    res = Result()

    def judge(label: str, where: str, glob_target: str, how: str) -> None:
        rule = next((r for r in allow if r[0] == label and fnmatch.fnmatch(glob_target, r[1])), None)
        if rule:
            res.allowed.append((label, where, rule[2]))
        else:
            res.findings.append((label, where, how))

    for oid, paths in listed.items():
        if content.get(oid) is None:
            res.unreadable.append((f"object {oid[:10]}", "git reports it missing"))
            continue
        otype, data = content[oid]
        res.objects += 1
        targets = sorted(paths) or [f"({otype})"]
        name = sorted(paths)[0] if paths else f"{otype} {oid[:10]}"
        try:
            forms = [("raw", data)] if raw_only else views(data)
            res.opened[kind(data) or ("text" if b"\0" not in data[:8000] else "binary")] += 1
        except Exception as e:  # noqa: BLE001  any failure to open is reported, never skipped
            res.unreadable.append((name, f"{type(e).__name__}: {e}"[:160]))
            res.opened["unreadable"] += 1
            forms = [("raw", data)]
        if not raw_only and not kind(data) and b"\0" in data[:8000]:
            for path in paths or {""}:
                res.raw_only[Path(path).suffix.lower() or "(none)"] += 1
        for n in needles:
            how = matches(n, forms)
            if how:
                for target in targets:
                    judge(n.label, target if paths else name, target, how)
            if not raw_only:
                for path in paths:
                    if matches(n, [("file name", path.encode("utf-8"))]):
                        judge(n.label, path, path, "file name")
    return res


def report(repo: Path, res: Result) -> None:
    print(f"== {repo}")
    print(f"  {res.objects} objects: " + ", ".join(f"{n} {k}" for k, n in sorted(res.opened.items())))
    if res.raw_only:
        print("  searched as raw bytes only (format not opened): "
              + ", ".join(f"{n} {ext}" for ext, n in sorted(res.raw_only.items())))
    for (label, reason), n in sorted(Counter((label, reason) for label, _, reason in set(res.allowed)).items()):
        print(f"  allowed  {label:<12} {n} objects: {reason}")
    for where, why in res.unreadable:
        print(f"  UNREADABLE {where}: {why}")
    for label, where, how in sorted(set(res.findings)):
        print(f"  FOUND    {label:<12} {where}  [{how}]")
    verdict = "FAIL" if res.findings or res.unreadable else "clean"
    print(f"  {verdict}: {len(set(res.findings))} findings, {len(set(res.allowed))} allowed, "
          f"{len(res.unreadable)} unreadable")


def main(argv: list[str]) -> int:
    needles = load_needles()
    if not needles:
        print(f"NOT RUN: no needles in {NEEDLES_FILE} (one 'label = value' per line)")
        return 2
    if not argv:
        print(__doc__)
        return 2
    failed = False
    for arg in argv:
        res = scan(Path(arg), needles)
        report(Path(arg), res)
        failed |= bool(res.findings or res.unreadable)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
