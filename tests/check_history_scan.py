"""The history scan finds personal information wherever it hides, and the old byte search did not.

A throwaway git repo is built with an invented identity planted once in each
place it can hide: plain text, a commit's author, a file name, an xlsx's
document properties, a docx, a zip inside a zip, the Flate-compressed text of a
PDF, a gzip, upper case with an accent, UTF-16, a name split across a
document's text runs, and an email split across two lines of a PDF. Each
compressed fixture is first shown not to contain the identity as raw bytes, so
finding it proves the file was opened. Then:

    the scan finds every plant, and names where and how
    the old search misses what it should (its rules are kept below as old_hit)
    the same files without the identity scan clean (the passing case)
    a blob at two paths is judged per path, so allowing one hides nothing else
    an allow rule needs a reason
    a broken PDF and a zip nested past the limit are UNREADABLE, never clean
    a malformed needles line stops the scan, a missing needles file is NOT RUN

Last, the control on real artifacts: when the owner's local needles file exists,
this repo's résumé must be found with the allow file ignored, and must not be
found by the old raw search. If it is not, the scan is blind to the very file
that made it necessary.

    py tests/check_history_scan.py
"""

from __future__ import annotations

import gzip
import io
import os
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

from sitekit import ROOT, Report

sys.path.insert(0, str(ROOT / "tools"))
import scan_history  # noqa: E402

EMAIL = "jane.example@example.org"                  # invented, never a real person
NAME = "José Example"
NEEDLES = [scan_history.needle("email", EMAIL), scan_history.needle("name", NAME)]
COMPRESSED = ["book.xlsx", "letter.docx", "nested.zip", "resume.pdf", "notes.txt.gz", "split.docx", "spaced.pdf"]
OLD_MISSES = COMPRESSED + ["upper.txt", "utf16.txt"]


def old_hit(value: str, data: bytes) -> bool:
    """The search this replaces: ASCII lower case, UTF-8 only, raw bytes, one contiguous run."""
    return value.lower().encode("utf-8") in data.lower()


def pdf_with(lines: list[str]) -> bytes:
    """A one-page PDF whose only text sits in a Flate stream, one line per entry."""
    body = " ".join(f"({line}) Tj 0 -14 Td" for line in lines)
    content = zlib.compress(f"BT /F1 12 Tf 72 720 Td {body} ET".encode())
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(content) + content + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for n, obj in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % n + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    out.write(b"".join(b"%010d 00000 n \n" % o for o in offsets))
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def zipped(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def fixtures(email: str, name: str) -> dict[str, bytes]:
    pad = b"Prairie Ridge Builders (fictional) " * 20         # gives deflate something to compress
    first, rest = name[:2], name[2:]
    local, domain = email.split("@")
    return {
        "plain.txt": f"contact {email}\n".encode(),
        "book.xlsx": zipped({"docProps/core.xml": f"<cp:lastModifiedBy>{email}</cp:lastModifiedBy>".encode() + pad}),
        "letter.docx": zipped({"word/document.xml": f"<w:t>{email}</w:t>".encode() + pad}),
        "nested.zip": zipped({"inner.zip": zipped({"deep.txt": email.encode() + pad})}),
        "resume.pdf": pdf_with([email]),
        "notes.txt.gz": gzip.compress(email.encode() + pad),
        "upper.txt": f"by {name.upper()}\n".encode("utf-8"),
        "utf16.txt": f"by {name}\n".encode("utf-16"),
        "split.docx": zipped({"word/document.xml": f"<w:r><w:t>{first}</w:t></w:r><w:r><w:t>{rest}</w:t></w:r>"
                              .encode() + pad}),
        "spaced.pdf": pdf_with([f"{local}@", domain]),
        f"{name} CV.txt": b"a file whose name is the identity\n",
    }


def git(repo: Path, *args: str, author: str = "fixture@example.invalid") -> None:
    subprocess.run(["git", "-c", "user.name=Fixture", "-c", f"user.email={author}", "-c", "commit.gpgsign=false",
                    "-c", "core.quotepath=false", *args], cwd=repo, check=True, capture_output=True)


def make_repo(root: Path, files: dict[str, bytes], author: str = "fixture@example.invalid") -> Path:
    root.mkdir()
    git(root, "init", "-q")
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixtures", author=author)
    return root


def found(res: scan_history.Result) -> set[str]:
    return {where for _, where, _ in res.findings}


def check_fixtures(rep: Report, planted: dict[str, bytes]) -> None:
    for name in COMPRESSED:
        rep.check(f"fixture {name} hides the identity from the old search",
                  not old_hit(EMAIL, planted[name]) and not old_hit(NAME, planted[name]))
    for name in ("upper.txt", "utf16.txt"):
        rep.check(f"fixture {name} is missed by the old search's matching", not old_hit(NAME, planted[name]))
    text = dict(scan_history.pdf_views(planted["resume.pdf"]))["pdf text"].decode()
    rep.check("pypdf's text view itself holds the PDF's email", EMAIL in text, repr(text[:60]))


def check_finds(rep: Report, tmp: Path, planted: dict[str, bytes]) -> Path:
    dirty = make_repo(tmp / "dirty", planted, author=EMAIL)
    res = scan_history.scan(dirty, NEEDLES)
    hits, how = found(res), {where: h for _, where, h in res.findings}
    for name in planted:
        rep.check(f"scan finds the identity in {name}", name in hits, how.get(name, ""))
    rep.check("scan finds the identity in the commit's author", any(h.startswith("commit ") for h in hits))
    rep.check("the file name is found as a file name", how.get(f"{NAME} CV.txt") == "file name")
    rep.check("the nested zip is found two levels down", "zip:inner.zip zip:deep.txt" in how.get("nested.zip", ""),
              how.get("nested.zip", ""))
    rep.check("the split docx is found through the squeezed view", "split" in how.get("split.docx", ""),
              how.get("split.docx", ""))
    rep.check("nothing in the fixtures is unreadable", res.unreadable == [], str(res.unreadable))
    old = {name for name, data in planted.items() if old_hit(EMAIL, data) or old_hit(NAME, data)}
    for name in OLD_MISSES:
        rep.check(f"the old search misses {name} (what this change fixes)", name not in old)
    rep.check("the old search still finds plain text", "plain.txt" in old)
    raw = found(scan_history.scan(dirty, NEEDLES, raw_only=True))
    rep.check("raw_only (no opening) misses every compressed plant", not raw & set(COMPRESSED), str(raw & set(COMPRESSED)))
    return dirty


def check_clean(rep: Report, tmp: Path) -> None:
    clean = make_repo(tmp / "clean", fixtures("someone.else@example.net", "Pat Other"))
    res = scan_history.scan(clean, NEEDLES)
    rep.check("the same files without the identity scan clean", res.findings == [] and res.unreadable == [],
              str(res.findings + res.unreadable))
    rep.check("the clean scan opened the compressed files", res.opened["zip"] == 4 and res.opened["pdf"] == 2
              and res.opened["gzip"] == 1, str(dict(res.opened)))


def check_allow(rep: Report, dirty: Path, planted: dict[str, bytes]) -> None:
    (dirty / "copies").mkdir()
    (dirty / "copies" / "cv.pdf").write_bytes(planted["resume.pdf"])          # the same blob at a second path
    git(dirty, "add", "-A")
    git(dirty, "commit", "-q", "-m", "copy")
    (dirty / scan_history.ALLOW_FILE).write_text("email resume.pdf  # a test reason\n", encoding="utf-8")
    res = scan_history.scan(dirty, NEEDLES)
    rep.check("an allow rule hides its own path", "resume.pdf" not in found(res)
              and any(w == "resume.pdf" for _, w, _ in res.allowed))
    rep.check("the same blob at another path is still found", "copies/cv.pdf" in found(res), str(sorted(found(res))))
    rep.check("an allow rule hides nothing else", "letter.docx" in found(res))
    rep.check("allow rules are ignored when asked (the control)",
              "resume.pdf" in found(scan_history.scan(dirty, NEEDLES, use_allow=False)))
    (dirty / scan_history.ALLOW_FILE).write_text("email resume.pdf\n", encoding="utf-8")
    try:
        scan_history.scan(dirty, NEEDLES)
        rep.check("an allow rule without a reason is refused", False)
    except ValueError:
        rep.check("an allow rule without a reason is refused", True)
    (dirty / scan_history.ALLOW_FILE).unlink()


def check_unreadable(rep: Report, tmp: Path) -> None:
    deep = b"nothing here"
    for k in range(scan_history.MAX_DEPTH + 1):
        deep = zipped({f"level{k}.zip" if k else "leaf.txt": deep})
    repo = make_repo(tmp / "broken", {"broken.pdf": b"%PDF-1.4\nnot a pdf at all", "deep.zip": deep})
    res = scan_history.scan(repo, NEEDLES)
    bad = sorted(w for w, _ in res.unreadable)
    rep.check("a broken PDF is UNREADABLE, never clean", "broken.pdf" in bad, str(res.unreadable))
    rep.check("a zip nested past the limit is UNREADABLE, never clean", "deep.zip" in bad, str(res.unreadable))


def check_needles(rep: Report, tmp: Path) -> None:
    bad = tmp / "bad_needles.txt"
    bad.write_text("email = someone@example.net\nname: Pat Other\n", encoding="utf-8")
    try:
        scan_history.load_needles(bad)
        rep.check("a malformed needles line stops the scan", False)
    except ValueError:
        rep.check("a malformed needles line stops the scan", True)
    env = {**os.environ, "HISTORY_SCAN_NEEDLES": str(tmp / "missing.txt")}
    run = subprocess.run([sys.executable, str(ROOT / "tools" / "scan_history.py"), str(tmp)], env=env,
                         capture_output=True, text=True)
    rep.check("without needles the scan reports NOT RUN, exit 2", run.returncode == 2 and "NOT RUN" in run.stdout,
              run.stdout.strip()[:80])


def check_real(rep: Report) -> None:
    real = scan_history.load_needles()
    name = "real resume.pdf found with the allow file ignored, missed by raw_only (control on a real artifact)"
    if not real:
        rep.not_run(name, f"no local needles at {scan_history.NEEDLES_FILE}")
        return
    full = found(scan_history.scan(ROOT, real, use_allow=False))
    raw = found(scan_history.scan(ROOT, real, raw_only=True, use_allow=False))
    rep.check(name, "resume.pdf" in full and "resume.pdf" not in raw)


def main() -> int:
    rep = Report("History scan: inside compressed files, case, encodings and split text")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        planted = fixtures(EMAIL, NAME)
        check_fixtures(rep, planted)
        dirty = check_finds(rep, tmp, planted)
        check_clean(rep, tmp)
        check_allow(rep, dirty, planted)
        check_unreadable(rep, tmp)
        check_needles(rep, tmp)
    check_real(rep)
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
