#!/usr/bin/env python3
"""Fetch a past Fed Chair's speeches/testimony from FRASER (fraser.stlouisfed.org, the St. Louis
Fed's public digital library) and save clean body text to transcripts/<slug>/, in the same
index.json + .txt format fetch.py writes for federalreserve.gov (build.py counts both the same way).

Used for Paul A. Volcker (Chair Aug 6, 1979 - Aug 11, 1987), whose statements predate
federalreserve.gov. The documents are typed originals scanned to PDF, so the text comes from
OCR (tesseract on 300 dpi page images); the PDFs' own text layer is only used to find where the
remarks end (appendices, charts, tables, footnote pages are dropped, like for the other Chairs).

Listing: the collection's public title page; metadata (date, title, venue, PDF) from FRASER's
OAI-PMH endpoint (no API key needed). Each saved document links to its FRASER item page.
Only remarks given as Chair; transcripts of press conferences / interviews (other speakers)
and speaking notes are skipped. Each text is scored by the share of its words found in an
English dictionary; documents below MIN_DICT are rejected (OCR too poor).

Downloads are cached in raw/<slug>/ (gitignored). Sequential requests, DELAY seconds apart.
Needs: pdftotext, pdftoppm (poppler-utils), tesseract, /usr/share/dict/american-english.

Usage:
  python3 fetch_fraser.py                 # Volcker: the 20 most recent documents that pass
  python3 fetch_fraser.py --max 20 --refresh
"""
import argparse, html, json, os, re, subprocess, sys, tempfile, time, urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (compatible; MouthMath/1.0; +https://mouthmath.com)"}
SITE = "https://fraser.stlouisfed.org"
DELAY = 1.5
MIN_WORDS = 300       # skip fragments
MIN_DICT = 0.97       # reject a document if fewer than 97% of its words are dictionary words
MAX_PAGES = 60        # very long filings (statement + appendices + charts) are skipped
PEOPLE = {
    "volcker": {"title": "/title/statements-speeches-paul-a-volcker-451", "decades": ["1970s", "1980s"],
                "since": "1979-08-06", "until": "1987-08-11", "speaker": "Chairman Paul A. Volcker"},
}
SKIP_RE = re.compile(r"transcript|interview|press conference|macneil|meet the press|face the nation|"
                     r"questions and answers|notes for", re.I)   # other speakers' words / not a full text
NS = {"m": "http://www.loc.gov/mods/v3"}

_last = [0.0]
def get(url, binary=False):
    wait = _last[0] + DELAY - time.time()
    if wait > 0:
        time.sleep(wait)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
            data = r.read()
    finally:
        _last[0] = time.time()
    return data if binary else data.decode("utf-8", "replace")

def cached(path, url, binary=False, refresh=False):
    if path.exists() and path.stat().st_size and not refresh:
        return path.read_bytes() if binary else path.read_text(encoding="utf-8")
    data = get(url, binary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data) if binary else path.write_text(data, encoding="utf-8")
    return data

def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)

# ---------- dictionary score ----------
def load_dict():
    words = set()
    for f in ("/usr/share/dict/american-english", "/usr/share/dict/words"):
        if os.path.exists(f):
            words |= {w.strip().lower() for w in open(f, encoding="utf-8", errors="ignore") if w.strip()}
    words = {w[:-2] if w.endswith("'s") else w for w in words}
    return words
DICT = load_dict()

def in_dict(w):
    w = w.lower().replace("\u2019", "'")
    if w.endswith("'s"):
        w = w[:-2]
    return w in DICT or (w.endswith("s") and w[:-1] in DICT)

def dict_rate(text):
    toks = re.findall(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)?", text)
    toks = [t for t in toks if len(t) > 1 or t in ("a", "A", "I")]
    return (sum(map(in_dict, toks)) / len(toks) if toks else 0.0), len(toks)

# ---------- page structure from the PDF's text layer ----------
END_HEAD_RE = re.compile(r"^\s*(appendix|appendices|attachments?|footnotes|notes|charts?|tables?|exhibits?|"
                         r"references|bibliography|statistical)\b[\s\w.:-]{0,40}$", re.I)

def body_pages(pdf):
    """1-based page numbers holding the remarks: from page 1 to the last prose page before an
    appendix / attachment / chart / table / footnotes section."""
    n = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout).group(1))
    keep = []
    for p in range(1, n + 1):
        t = subprocess.run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(pdf), "-"], capture_output=True, text=True).stdout
        lines = [l.strip() for l in t.splitlines() if l.strip() and not FOOTER_RE.match(l.strip())]
        if p > 2 and lines and any(END_HEAD_RE.match(l) for l in lines[:3]):
            break
        toks = re.findall(r"\S+", " ".join(lines))
        digits = sum(bool(re.search(r"\d", x)) for x in toks)
        prose = sum(1 for l in lines if len(l.split()) >= 5)
        if p > 2 and (prose < 3 or digits > 0.25 * max(len(toks), 1)):
            if keep and p - keep[-1] > 1:
                break
            continue          # a chart/table page; stop if two in a row
        keep.append(p)
    while keep and keep[-1] > 2 and keep[-1] - (keep[-2] if len(keep) > 1 else 0) > 1:
        keep.pop()
    return keep, n

# ---------- OCR ----------
FOOTER_RE = re.compile(r"^(digitized for fraser|https?://fraser\.stlouisfed\.org/?|federal reserve bank of st\.? ?louis)\s*$", re.I)
PAGENO_RE = re.compile(r"^[-\u2014\u2013 ]*\(?\d{1,3}\)?[-\u2014\u2013 .]*$|^[-\u2014\u2013~]\s*[\dlIiO|!]{1,3}\s*[-\u2014\u2013~]$")   # 7 / -7- / -ll-

def ocr_page_lines(png):
    """[(left, text)] per line, from tesseract's TSV (so indentation marks paragraph starts)."""
    out = subprocess.run(["tesseract", str(png), "-", "--psm", "4", "tsv"], capture_output=True, text=True).stdout
    lines, cur = [], {}
    for row in out.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        key = (int(f[2]), int(f[3]), int(f[4]))
        if key not in cur:
            cur[key] = [int(f[6]), []]
            lines.append(cur[key])
        cur[key][1].append(f[11])
    return [(l, " ".join(ws)) for l, ws in lines]

COVER_RE = re.compile(r"for release|remarks by|statement by|testimony by|address by|chairman,? board of governors|"
                      r"^before the$|^of the$|^paul a\.? volcker$", re.I)

def ocr_document(pdf, pages, work):
    paras, first = [], True
    for p in pages:
        subprocess.run(["pdftoppm", "-r", "300", "-gray", "-f", str(p), "-l", str(p), "-png", str(pdf), str(work / "pg")], check=True)
        png = sorted(work.glob("pg-*.png"))[-1]
        lines = ocr_page_lines(png)
        png.unlink()
        lines = [(x, t.strip()) for x, t in lines if t.strip() and not FOOTER_RE.match(t.strip()) and not PAGENO_RE.match(t.strip())]
        if first:      # the typed cover page: release time, "Remarks by Paul A. Volcker", venue, date
            first = False
            if any(COVER_RE.search(t) for _, t in lines) and sum(len(t.split()) >= 8 for _, t in lines) < 3:
                continue
        if not lines:
            continue
        xs = sorted(x for x, t in lines if len(t.split()) >= 5) or sorted(x for x, _ in lines)
        margin = xs[len(xs) // 5]                     # left margin of the body text
        for x, t in lines:
            new = x > margin + 80 or not paras        # indented first line (or a centered heading) starts a paragraph
            if new:
                paras.append([t])
            else:
                paras[-1].append(t)
    return paras

def join_lines(lines):
    out = ""
    for t in lines:
        if not out:
            out = t; continue
        m = re.search(r"([A-Za-z]+)-$", out)
        if m and re.match(r"[a-z]", t):              # hyphen at a line break
            nxt = re.match(r"[A-Za-z]+", t).group(0)
            out = out[:-1] + t if in_dict(m.group(1) + nxt) else out + t     # "inter-" "nationally" -> internationally; "long-" "term" stays
        else:
            out += " " + t
    return out

def tidy(text):
    text = re.sub(r"\s*(?:-~-|~-|-~|--+|\u2014)\s*", " \u2014 ", text)    # typed dashes
    text = re.sub(r"(?<=[A-Za-z])11(?=[\s.,;:)]|$)", "\u201d", text)      # OCR'd closing quote
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def clean_paragraphs(paras):
    out = []
    for lines in paras:
        t = tidy(join_lines(lines))
        if not t:
            continue
        words = t.split()
        if END_HEAD_RE.match(t) and out:              # appendix / footnotes heading: the remarks are over
            break
        if len(words) <= 3 and dict_rate(t)[0] < 0.5:  # stamps, stray marks
            continue
        if re.fullmatch(r"[\W\d_]+", t):              # rules, page numbers, asterisks
            continue
        out.append(t)
    return "\n\n".join(out)

# ---------- listing / metadata ----------
def list_items(cfg, raw, refresh):
    ids = []
    for dec in cfg["decades"]:
        page = cached(raw / f"title-{dec}.html", f"{SITE}{cfg['title']}?browse={dec}", refresh=refresh)
        for m in re.finditer(r'data-id="(\d+)"\s+data-type="item"\s+href="(' + re.escape(cfg["title"]) + r'/[^"]+)"', page):
            if m.group(1) not in {i for i, _ in ids}:
                ids.append((m.group(1), m.group(2)))
    return ids

def item_meta(iid, raw, refresh):
    xml = cached(raw / "oai" / f"{iid}.xml", f"{SITE}/oai?verb=GetRecord&metadataPrefix=mods&identifier=oai:fraser.stlouisfed.org:item:{iid}", refresh=refresh)
    mods = ET.fromstring(xml).find(".//m:mods", NS)
    g = lambda p: " ".join((mods.find(p, NS).text or "").split()) if mods.find(p, NS) is not None else ""
    pdf = [u.text for u in mods.findall("m:location/m:url", NS) if u.get("access") == "raw object"]
    return {"title": html.unescape(g("m:titleInfo/m:title")), "sub": html.unescape(g("m:titleInfo/m:subTitle")),
            "date": g("m:originInfo/m:sortDate"), "pdf": pdf[0] if pdf else ""}

def title_venue(m):
    """FRASER titles are either 'Topic' + subtitle 'Remarks before X' or 'Statement before X'."""
    t, s = m["title"].strip(" :"), m["sub"].strip()
    kind = "testimony" if re.search(r"\b(statement|testimony)\s+before\b|report to the congress", t + " " + s, re.I) else "speech"
    mt = re.match(r"(Statement|Testimony|Remarks|Address)\s+(before|at)\s+(.*)", t, re.I)
    if mt and not s:
        return mt.group(1).capitalize(), mt.group(2).capitalize() + " " + mt.group(3), kind
    if s:
        return t, s[0].upper() + s[1:], kind
    return t, "", kind

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="volcker", choices=sorted(PEOPLE))
    ap.add_argument("--max", type=int, default=20, help="keep the N most recent documents that pass the checks")
    ap.add_argument("--refresh", action="store_true", help="re-run OCR (and re-download) for saved items")
    a = ap.parse_args()
    cfg = PEOPLE[a.slug]
    raw, out = ROOT / "raw" / a.slug, ROOT / "transcripts" / a.slug
    out.mkdir(parents=True, exist_ok=True)
    report = []

    items = []
    for iid, href in list_items(cfg, raw, False):
        m = item_meta(iid, raw, False) | {"id": iid, "href": href}
        if cfg["since"] <= m["date"] <= cfg["until"] and m["pdf"]:
            items.append(m)
    items.sort(key=lambda m: (m["date"], m["id"]), reverse=True)
    print(f"{len(items)} items dated within the chairmanship")

    keep, used = [], set()
    for m in items:
        if len(keep) >= a.max:
            break
        label = f"{m['date']} {m['title'][:70]}"
        if SKIP_RE.search(m["title"] + " " + m["sub"]):
            report.append(("skipped (not a full text of his own remarks)", label, None)); continue
        pdf = raw / "pdf" / Path(m["pdf"]).name
        cached(pdf, SITE + "/files" + m["pdf"], binary=True)
        pages, n = body_pages(pdf)
        if n > MAX_PAGES:
            report.append((f"skipped ({n}-page filing with appendices and charts)", label, None)); continue
        base = a.slug + m["date"].replace("-", "")
        k = 0
        while (fname := base + "abcdefgh"[k]) in used:
            k += 1
        txt = out / f"{fname}.txt"
        if txt.exists() and not a.refresh:
            text = txt.read_text(encoding="utf-8").strip()
        else:
            with tempfile.TemporaryDirectory() as td:
                text = clean_paragraphs(ocr_document(pdf, pages, Path(td)))
        rate, ntok = dict_rate(text)
        words = len(text.split())
        if words < MIN_WORDS:
            report.append((f"rejected (only {words} words)", label, rate)); continue
        if rate < MIN_DICT:
            report.append((f"rejected (OCR quality {100*rate:.1f}% dictionary words < {100*MIN_DICT:.0f}%)", label, rate)); continue
        used.add(fname)
        atomic_write(txt, text + "\n")
        title, venue, kind = title_venue(m)
        keep.append({"file": txt.name, "date": m["date"], "type": kind, "title": title, "speaker": cfg["speaker"],
                     "location": venue, "url": SITE + m["href"],
                     "note": "", "pages": f"{pages[0]}-{pages[-1]} of {n}" if pages else "",
                     "dict_rate": round(rate, 4), "fetched": datetime.now().isoformat(timespec="seconds")})
        report.append(("kept", label, rate))
        print(f"  kept {m['date']} {kind:9s} {words:6d} words  {100*rate:5.1f}% dictionary  {title[:60]}", flush=True)

    meta = sorted(keep, key=lambda d: (d["date"], d["url"]), reverse=True)
    for d in meta:
        d.pop("note")
    atomic_write(out / "index.json", json.dumps(meta, indent=2) + "\n")
    print("\n".join(f"  {r[0]:60s} {r[1]}" + (f"  [{100*r[2]:.1f}%]" if r[2] is not None else "") for r in report if r[0] != "kept"))
    print(f"Done: {len(meta)} documents in {out / 'index.json'}")

if __name__ == "__main__":
    main()
