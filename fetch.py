#!/usr/bin/env python3
"""Fetch Fed Chair speeches/testimony from federalreserve.gov and save clean
body text to transcripts/<slug>/ (default: the current Chair, Kevin Warsh).
Past Chairs use the same pipeline (same extraction, same index.json format);
only the speaker pattern and output folder differ (see CHAIRS below).

Safe to rerun (e.g., weekly): items already listed in transcripts/index.json
with an existing .txt file are kept as-is and not re-downloaded; only new
items are added. Nothing is ever deleted. index.json is written atomically.

Usage:
  python3 fetch.py                      # add any new chair speeches/testimony
  python3 fetch.py --refresh            # re-download existing items too
  python3 fetch.py --speaker "^Chair Jerome H\\. Powell$"   # different speaker (regex)
  python3 fetch.py --slug powell --max 20   # a past Chair: the 20 most recent items as Chair
  python3 fetch.py --slug greenspan --max 20  # pre-2006: read from the yearly archive pages
"""
import argparse, html, json, os, re, sys, tempfile, time, urllib.request
from datetime import datetime
from pathlib import Path

BASE = "https://www.federalreserve.gov"
FEEDS = {"speech": "/json/ne-speeches.json", "testimony": "/json/ne-testimony.json"}
UA = {"User-Agent": "Mozilla/5.0 (compatible; MouthMath/1.0; +https://mouthmath.com)"}
TDIR = Path(__file__).resolve().parent / "transcripts"   # transcripts/<person slug>/ (see people.json)
DEFAULT_SPEAKER = r"^Chair(man)?\s+Kevin\s+(M\.\s+)?Warsh$"   # as Chair only, not Governor
MIN_WORDS = 50   # sanity check: refuse to save a "speech" shorter than this
DELAY = 1.5      # seconds between page requests (be polite to federalreserve.gov)
# Every Chair is matched only by the title they held as Chair (never Governor / Vice Chair),
# exactly as the speaker appears in the Board's own listings (typos in the listings included).
# "archive" = years whose speeches/testimony are listed only on the yearly archive pages
# (/newsevents/speech/<year>speech.htm, /newsevents/testimony/<year>testimony.htm), not in the JSON feeds.
CHAIRS = {
    "warsh":     {"speaker": DEFAULT_SPEAKER},
    "powell":    {"speaker": r"^Chair(man)?(\s+Pro\s+Tempore)?\s+Jerome\s+H\.\s+Powell$"},
    "yellen":    {"speaker": r"^Chair(man)?\s+Janet\s+L\.\s+Yellen$"},
    "bernanke":  {"speaker": r"^Ch(ai|ia)rman\s+Ben\s+S\.\s+Bernanke$"},
    "greenspan": {"speaker": r"^Chairman\s+Alan\s+Greenspan$", "archive": range(2006, 1995, -1)},
}

_last = [0.0]
def get(url):
    wait = _last[0] + DELAY - time.time()     # sequential requests with a small delay
    if wait > 0:
        time.sleep(wait)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            raw = r.read()
    finally:
        _last[0] = time.time()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:                # some pre-2006 pages are Windows-1252
        return raw.decode("cp1252", errors="replace")

# A "References" or "Appendix..." heading starts the bibliography / technical appendix (not part of the remarks).
REFS_RE = re.compile(r"(?:<p\b[^>]*>\s*)?<(?:strong|b)>\s*(?:References\s*(?:<br\s*/?>|</strong>|</b>)|Appendix\b)"
                     r"|<h\d\b[^>]*>\s*(?:<(?:strong|b)>\s*)?(?:References\s*(?:</(?:strong|b)>\s*)?</h\d>|Appendix\b)", re.I)
# A paragraph that is only a media link ("Watch live", "Watch Video", "Audio", "Watch on-demand: <url>").
MEDIA_P_RE = re.compile(r"<p\b[^>]*>\s*(?:(?:Watch|View)[^<]{0,40})?<a\b[^>]*>\s*(?:(?:Watch|View)\b[^<]{0,60}|Audio|https?://[^<]+)\s*</a>\s*</p>", re.I)

def clean_text(seg):
    """HTML fragment -> plain text (shared by both page layouts)."""
    seg = re.sub(r"<(script|style)\b.*?</\1>|<!--.*?-->", "", seg, flags=re.S | re.I)
    seg = re.sub(r'<div class="(?:sr-only|hidden)">.*?</div>', "", seg, flags=re.S)   # video-player key help, hidden slide links
    seg = MEDIA_P_RE.sub("", seg)
    seg = re.sub(r"<sup>.*?</sup>", "", seg, flags=re.S | re.I)            # footnote markers
    seg = re.sub(r"<a\b[^>]*href=\"#fn\d+\"[^>]*>.*?</a>", "", seg, flags=re.S | re.I)  # footnote links
    seg = re.sub(r"<p>\s*<em>\s*<strong>.*?</strong>\s*</em>\s*</p>", "", seg, flags=re.S)  # editorial notes
    seg = re.sub(r"</p>|<br\s*/?>", "\n\n", seg, flags=re.I)
    seg = re.sub(r"<p\b[^>]*>", "\n\n", seg, flags=re.I)
    seg = re.sub(r"<[^>]+>", "", seg)
    seg = html.unescape(seg)
    # a few archive pages carry U+FFFD where a curly apostrophe was lost (world\ufffds -> world's)
    seg = re.sub(r"(?<=[A-Za-z])\ufffd(?=[A-Za-z])", "\u2019", seg).replace("\ufffd", " ")
    seg = re.sub(r"[ \t\r\f\v]+", " ", seg)
    seg = re.sub(r"\n\s*\n+", "\n\n", seg)
    seg = seg.replace("Return to text", "").strip()
    for junk in ("<", "Related Content", "Back to Top", "Last Update", "Return to top"):   # page chrome leaked in?
        if junk in seg:
            raise ValueError(f"extracted text contains page chrome {junk!r}")
    return seg

def body_text(page):
    art = page.find('id="article"')
    if art == -1:
        raise ValueError("no article element found")
    start = page.find('col-xs-12 col-sm-8 col-md-8"', art + 200)  # 2nd column = body
    if start == -1:
        raise ValueError("no body column found")
    seg = page[start:]
    ends = [i for i in (seg.find("<hr"),                                  # footnotes rule
                        seg.find('<div class="col-xs-12 col-sm-4 col-md-4'),  # right sidebar
                        seg.find('id="lastUpdate"'), seg.find('<a name="fn1"'),
                        (lambda m: m.start() if m else -1)(REFS_RE.search(seg))) if i != -1]
    seg = seg[seg.find(">") + 1:min(ends) if ends else len(seg)]
    return clean_text(seg)

def archive_body_text(page, date):
    """Pre-2006 archive layout (/boarddocs/...): a title block in bold that ends with the date,
    then the body paragraphs, then footnotes / 'Return to top'."""
    low = page.lower()
    m = re.compile(re.escape(date.strftime("%B ") + str(date.day) + date.strftime(", %Y"))).search(page, max(low.find("<body"), 0))
    if not m:
        raise ValueError("date line not found")
    start = low.find("</b>", m.end())
    if start == -1 or start - m.end() > 300:
        raise ValueError("title block not found")
    seg_low = low[start:]
    ends = [m.start() for m in (re.search(r, seg_low) for r in (
        r"<hr",                               # rule before footnotes / page footer
        r"<a\s[^>]*name=\"fn1\"",              # first footnote
        r"<a\s[^>]*href=\"#pagetop\"",          # 'Return to top' link
        r"<p>\s*<b>\s*footnotes", REFS_RE.pattern.lower())) if m]
    seg = page[start + 4:start + min(ends) if ends else len(page)]
    seg = re.sub(r"^(?:\s|</?(?:td|tr|table|p)\b[^>]*>)*<p>\s*<(em|i)>[^<]{0,400}</\1>\s*</p>", "", seg, flags=re.I)  # editorial note
    seg = re.sub(r"^((?:\s|</?(?:td|tr|table|p)\b[^>]*>)*)<(strong|b)>[^<]{0,200}</\2>\s*<br\s*/?>", r"\1", seg, flags=re.I)  # title repeated atop the body
    return clean_text(seg)

def archive_items(spk, years):
    """Speech/testimony listings from the yearly archive pages (same fields as the JSON feeds)."""
    items = []
    for y in years:
        for kind, path in (("speech", f"/newsevents/speech/{y}speech.htm"), ("testimony", f"/newsevents/testimony/{y}testimony.htm")):
            try:
                page = get(BASE + path)
            except Exception as e:
                print(f"  WARN could not read {path}: {e}"); continue
            for li in re.findall(r"<li>(.*?)</li>", page, re.S):
                d = re.match(r"\s*([A-Z][a-z]+ \d{1,2}, \d{4})", li)
                a = re.search(r'<a href="([^"]+)"[^>]*>(.*?)</a>', li, re.S)
                sp = re.search(r'class="speaker">(.*?)</div>', li, re.S)
                lo = re.search(r'class="location">(.*?)</div>', li, re.S)
                if not (d and a and sp):
                    continue
                s = " ".join(html.unescape(sp.group(1)).split())
                if spk.search(s):
                    items.append((datetime.strptime(d.group(1), "%B %d, %Y"), kind,
                                  {"l": a.group(1), "t": " ".join(re.sub(r"<[^>]+>", "", a.group(2)).split()), "s": s,
                                   "lo": " ".join(html.unescape(lo.group(1)).split()) if lo else ""}))
    return items

def file_slug(link, slug, date):
    """transcripts file name: the page's own name (warsh20260828a.htm -> warsh20260828a); archive
    pages are all called default.htm, so use <slug><yyyymmdd><a|b|...> like the newer pages."""
    stem = Path(link).stem
    return stem if stem not in ("default", "testimony", "index") else slug + date.strftime("%Y%m%d")

def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="warsh", choices=sorted(CHAIRS), help="person slug (transcripts/<slug>/)")
    ap.add_argument("--speaker", help="regex matched against the feed's speaker field (default: the slug's)")
    ap.add_argument("--max", type=int, default=0, help="keep at most this many of the most recent items (0 = all)")
    ap.add_argument("--refresh", action="store_true", help="re-download items already saved")
    a = ap.parse_args()
    cfg = CHAIRS[a.slug]
    spk = re.compile(a.speaker or cfg["speaker"])
    out = TDIR / a.slug
    index = out / "index.json"
    out.mkdir(parents=True, exist_ok=True)

    existing = json.loads(index.read_text(encoding="utf-8")) if index.exists() else []
    by_url = {m["url"]: m for m in existing}

    items = []
    for kind, path in FEEDS.items():
        try:
            feed = json.loads(get(BASE + path))
        except Exception as e:
            sys.exit(f"ERROR: could not read {kind} feed ({e}); nothing changed.")
        for x in feed:
            if spk.search(x.get("s", "").strip()):
                d = datetime.strptime(x["d"].split()[0], "%m/%d/%Y")
                items.append((d, kind, x))
    if cfg.get("archive"):
        need = a.max or 10**9
        for y in cfg["archive"]:                       # newest year first; stop once we have enough
            if len(items) >= need + 5:                 # (+5 spare in case a page cannot be parsed)
                break
            items += archive_items(spk, [y])
    items.sort(key=lambda t: (t[0], t[2]["l"]), reverse=True)
    print(f"Listings have {len(items)} matching item(s); {len(existing)} already saved.")

    added = refreshed = failed = 0
    used = set()
    keep = []
    for d, kind, x in items:
        if a.max and len(keep) >= a.max:
            break
        url = BASE + x["l"]
        old = by_url.get(url)
        if old and (out / old["file"]).exists() and not a.refresh:
            keep.append(url); used.add(Path(old["file"]).stem); continue
        slug = file_slug(x["l"], a.slug, d)
        if slug != Path(x["l"]).stem:                  # archive page: add a/b/c for same-day items
            base, n = slug, 0
            while (slug := base + "abcdefghij"[n]) in used or any(
                    m["file"] == slug + ".txt" and m["url"] != url for m in by_url.values()):
                n += 1
        txt = out / f"{slug}.txt"
        try:
            page = get(url)
            text = body_text(page) if 'id="article"' in page else archive_body_text(page, d)
            if len(text.split()) < MIN_WORDS:
                raise ValueError(f"only {len(text.split())} words extracted")
        except Exception as e:
            failed += 1
            print(f"  WARN skipping {url}: {e}")
            continue
        used.add(slug)
        atomic_write(txt, text + "\n")
        by_url[url] = {"file": txt.name, "date": d.strftime("%Y-%m-%d"), "type": kind,
                       "title": html.unescape(x["t"]).strip(), "speaker": html.unescape(x["s"]).strip(),
                       "location": html.unescape(x.get("lo", "")), "url": url,
                       "fetched": datetime.now().isoformat(timespec="seconds")}
        keep.append(url)
        if old: refreshed += 1
        else: added += 1
        print(f"  {'refreshed' if old else 'added':9s} {by_url[url]['date']} {kind:9s} {by_url[url]['title']}")

    if a.max:   # with a cap, list only the kept items (older .txt files stay on disk; nothing is deleted)
        by_url = {u: by_url[u] for u in keep}
    meta = sorted(by_url.values(), key=lambda m: (m["date"], m["url"]), reverse=True)
    atomic_write(index, json.dumps(meta, indent=2) + "\n")
    print(f"Done: {added} added, {refreshed} refreshed, {failed} failed, {len(meta)} total in {index}")

if __name__ == "__main__":
    main()
