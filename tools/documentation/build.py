"""Builds Incipit_Documentation.docx in three passes: (A) collect headings, captions and index entries, (B) build
with the contents in place and render it with LibreOffice to find the pages, (C) build with the page numbers."""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pymupdf  # noqa: E402

from doclib import Doc  # noqa: E402
import part1, part2, part3, appendix  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "Incipit_Documentation.docx")
SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
cat = json.load(open(os.path.join(HERE, "catalogue.json"), encoding="utf-8"))
facts = json.load(open(os.path.join(HERE, "facts.json"), encoding="utf-8"))

code_files = [m for m in cat if not m.startswith("tools/")]
INFO = {
    "version": "1.0.102", "commit": "5541f83", "date": "2026-11-15", "files": len(code_files),
    "lines": sum(cat[m]["lines"] for m in code_files),
    "funcs": sum(len(cat[m]["functions"]) + sum(len(c["methods"]) for c in cat[m]["classes"]) for m in code_files),
    "tests": sum(t[1] for t in facts["tests"]),
}


def build(path, pages=None):
    D = Doc()
    D.pages = pages
    part1.title_page(D, INFO)
    D.header_footer("Incipit · Integrated documentation · version " + INFO["version"])
    part1.about(D)
    part1.part1(D, INFO)
    part1.part2(D)
    part2.part3(D, facts)
    part3.part4(D, cat, facts)
    part3.part5(D, cat, facts)
    appendix.catalogue(D, cat)
    appendix.back_matter(D)
    D.save(path)
    return D


def to_pdf(docx):
    folder = os.path.dirname(docx)
    subprocess.run([SOFFICE, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", folder, docx],
                   check=True, capture_output=True, timeout=900)
    return os.path.splitext(docx)[0] + ".pdf"


def norm(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def find_pages(pdf, D):
    doc = pymupdf.open(pdf)
    texts = [doc[i].get_text() for i in range(len(doc))]
    lines = [[norm(l) for l in t.splitlines() if l.strip()] for t in texts]
    flat = [norm(t) for t in texts]
    h_pages, cursor = {}, 0
    for n, (level, text) in enumerate(D.headings):
        key = norm(text)[:40]
        for page in range(cursor, len(doc)):
            if any(l.startswith(key) and "....." not in l for l in lines[page]):
                h_pages[n] = page + 1
                cursor = page
                break
    c_pages = {}
    for kind, num, text in D.captions:
        key = norm(f"{kind} {num}:")
        for page in range(len(doc)):
            if any(l.startswith(key) and "....." not in l for l in lines[page]):
                c_pages[f"{kind} {num}"] = page + 1
                break
    index = {}
    for entry, shown, heading in D.xe_log:
        start = h_pages.get(heading, 1)
        found = start
        key = norm(shown)[:50]
        for page in range(start - 1, min(len(doc), start + 5)):
            if key and key in flat[page]:
                found = page + 1
                break
        index.setdefault(entry, set()).add(found)
    index = {k: sorted(v) for k, v in index.items()}
    missing_h = [D.headings[n][1] for n in range(len(D.headings)) if n not in h_pages]
    missing_c = [f"{k} {n}" for k, n, _t in D.captions if f"{k} {n}" not in c_pages]
    return {"h": h_pages, "c": c_pages, "index": index, "pages": len(doc)}, missing_h, missing_c


if __name__ == "__main__":
    work = os.path.join(HERE, "work")
    os.makedirs(work, exist_ok=True)
    A = build(os.path.join(work, "a.docx"))
    pages = {"headings": A.headings, "captions": A.captions, "h": {}, "c": {},
             "index": {e: [0] for e, _s, _h in A.xe_log}}
    build(os.path.join(work, "b.docx"), pages)
    found, mh, mc = find_pages(to_pdf(os.path.join(work, "b.docx")), A)
    print("pass B:", found["pages"], "pages; headings not found:", mh[:8], "captions not found:", mc[:8])
    pages.update(h=found["h"], c=found["c"], index=found["index"])
    C = build(OUT, pages)
    final, mh, mc = find_pages(to_pdf(OUT), C)
    moved = [n for n in final["h"] if final["h"][n] != found["h"].get(n)]
    print("final:", final["pages"], "pages; headings whose page moved after pass C:", len(moved),
          "; figures", C.fig, "tables", C.tab, "index entries", len(final["index"]))
