#!/usr/bin/env python3
"""Fetch the current Fed Chair's speeches/testimony from federalreserve.gov
and save clean body text to transcripts/.

Safe to rerun (e.g., weekly): items already listed in transcripts/index.json
with an existing .txt file are kept as-is and not re-downloaded; only new
items are added. Nothing is ever deleted. index.json is written atomically.

Usage:
  python3 fetch.py                      # add any new chair speeches/testimony
  python3 fetch.py --refresh            # re-download existing items too
  python3 fetch.py --speaker "^Chair Jerome H\\. Powell$"   # different speaker (regex)
"""
import argparse, html, json, os, re, sys, tempfile, urllib.request
from datetime import datetime
from pathlib import Path

BASE = "https://www.federalreserve.gov"
FEEDS = {"speech": "/json/ne-speeches.json", "testimony": "/json/ne-testimony.json"}
UA = {"User-Agent": "Mozilla/5.0 (fed-words prototype)"}
OUT = Path(__file__).resolve().parent / "transcripts"
INDEX = OUT / "index.json"
DEFAULT_SPEAKER = r"^Chair(man)?\s+Kevin\s+(M\.\s+)?Warsh$"   # as Chair only, not Governor
MIN_WORDS = 50   # sanity check: refuse to save a "speech" shorter than this

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8-sig")

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
                        seg.find('id="lastUpdate"'), seg.find('<a name="fn1"')) if i != -1]
    seg = seg[seg.find(">") + 1:min(ends) if ends else len(seg)]
    seg = re.sub(r"<sup>.*?</sup>", "", seg, flags=re.S)            # footnote markers
    seg = re.sub(r"<p>\s*<em>\s*<strong>.*?</strong>\s*</em>\s*</p>", "", seg, flags=re.S)  # editorial notes
    seg = re.sub(r"</p>|<br\s*/?>", "\n\n", seg)
    seg = re.sub(r"<[^>]+>", "", seg)
    seg = html.unescape(seg)
    seg = re.sub(r"[ \t\r\f\v]+", " ", seg)
    seg = re.sub(r"\n\s*\n+", "\n\n", seg)
    seg = seg.replace("Return to text", "").strip()
    for junk in ("<", "Related Content", "Back to Top", "Last Update"):   # page chrome leaked in?
        if junk in seg:
            raise ValueError(f"extracted text contains page chrome {junk!r}")
    return seg

def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speaker", default=DEFAULT_SPEAKER, help="regex matched against the feed's speaker field")
    ap.add_argument("--refresh", action="store_true", help="re-download items already saved")
    a = ap.parse_args()
    spk = re.compile(a.speaker)
    OUT.mkdir(exist_ok=True)

    existing = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else []
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
    items.sort(key=lambda t: t[0], reverse=True)
    print(f"Feed has {len(items)} matching item(s); {len(existing)} already saved.")

    added = refreshed = failed = 0
    for d, kind, x in items:
        url = BASE + x["l"]
        slug = Path(x["l"]).stem
        txt = OUT / f"{slug}.txt"
        old = by_url.get(url)
        if old and (OUT / old["file"]).exists() and not a.refresh:
            continue
        try:
            text = body_text(get(url))
            if len(text.split()) < MIN_WORDS:
                raise ValueError(f"only {len(text.split())} words extracted")
        except Exception as e:
            failed += 1
            print(f"  WARN skipping {url}: {e}")
            continue
        atomic_write(txt, text + "\n")
        by_url[url] = {"file": txt.name, "date": d.strftime("%Y-%m-%d"), "type": kind,
                       "title": html.unescape(x["t"]).strip(), "speaker": html.unescape(x["s"]).strip(),
                       "location": html.unescape(x.get("lo", "")), "url": url,
                       "fetched": datetime.now().isoformat(timespec="seconds")}
        if old: refreshed += 1
        else: added += 1
        print(f"  {'refreshed' if old else 'added':9s} {by_url[url]['date']} {kind:9s} {by_url[url]['title']}")

    meta = sorted(by_url.values(), key=lambda m: (m["date"], m["url"]), reverse=True)
    atomic_write(INDEX, json.dumps(meta, indent=2) + "\n")
    print(f"Done: {added} added, {refreshed} refreshed, {failed} failed, {len(meta)} total in {INDEX}")

if __name__ == "__main__":
    main()
