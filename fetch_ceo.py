#!/usr/bin/env python3
"""Fetch CEO shareholder letters from each company's OWN public website and save the
extracted text LOCALLY ONLY (local_sources/<slug>/, which is gitignored).

The full letter text is never committed or published. build.py turns these local
texts into derived data (word counts + a limited set of excerpt sentences) in
derived/<slug>.json, which is what gets committed.

Manual script (not part of publish.sh). Safe to rerun: existing documents are kept
and not re-downloaded unless --refresh is given. ~1 request/second, declared UA.

Usage: python3 fetch_ceo.py [--only karp,jassy,abel] [--refresh]
"""
import argparse, html, json, os, re, subprocess, sys, tempfile, time, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / "local_sources"
UA = "Mozilla/5.0 (X11; Linux x86_64) FedWords/1.0 (+https://github.com/JunkyProfit/fed-words)"
MIN_WORDS = 300

PEOPLE = {
    "karp": {"name": "Alex Karp", "display": "Alex Karp", "category": "CEOs",
             "role": "Co-Founder & CEO, Palantir Technologies", "org": "Palantir", "max": 4},
    "jassy": {"name": "Andy Jassy", "display": "Andy Jassy", "category": "CEOs",
              "role": "President & CEO, Amazon", "org": "Amazon"},
    "abel": {"name": "Greg Abel", "display": "Greg Abel", "category": "CEOs",
             "role": "CEO, Berkshire Hathaway", "org": "Berkshire Hathaway"},
}

_last = [0.0]
def get(url, binary=False):
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read()
    finally:
        _last[0] = time.time()
    return data if binary else data.decode("utf-8", "replace")

def clean(s):
    s = html.unescape(s).replace("\u00a0", " ")
    return " ".join(s.split())

def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "wb" if isinstance(data, bytes) else "w", **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as f:
        f.write(data)
    os.replace(tmp, path)

# ---------------- Palantir (palantir.com, Next.js page with Contentful rich text) -------------
def karp_list():
    page = get("https://www.palantir.com/newsroom/letters/")
    qs = sorted({(int(y), int(q)) for q, y in re.findall(r"/q([1-4])-(20\d\d)-letter", page)}, reverse=True)
    return [{"id": f"pltr-q{q}-{y}", "url": f"https://www.palantir.com/q{q}-{y}-letter/en/",
             "title": f"Q{q} {y} Letter to Shareholders"} for y, q in qs]

def karp_extract(raw):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', raw, re.S)
    data = json.loads(m.group(1))
    def text(n):
        if n.get("nodeType") == "text": return n.get("value", "")
        return "".join(text(c) for c in n.get("content", []) if isinstance(c, dict))
    docs = []
    def walk(n):
        if isinstance(n, dict):
            if n.get("nodeType") == "document":
                docs.append([(c.get("nodeType"), text(c)) for c in n.get("content", [])]); return
            for v in n.values(): walk(v)
        elif isinstance(n, list):
            for v in n: walk(v)
    walk(data["props"]["pageProps"]["page"])
    body = next(d for d in docs if any(clean(t).startswith("Sincerely") for _, t in d))  # the signed letter
    date, paras = None, []
    for kind, t in body:
        t = clean(t)
        if not t or kind == "embedded-asset-block": continue
        if date is None and re.fullmatch(r"[A-Z][a-z]+ \d{1,2}, 20\d\d", t):
            date = datetime.strptime(t, "%B %d, %Y").strftime("%Y-%m-%d"); continue
        if t.startswith("Sincerely"): break                       # stop before signature block
        if re.fullmatch(r"[IVXLC]+\.", t): continue                # section numerals
        paras.append(t)
    # Drop a leading epigraph (quotation by someone else + "— Author, Work" attribution line).
    for i, t in enumerate(paras[:8]):
        if re.match(r"^[\u2014\u2015]\s*\S", t):
            paras = paras[i + 1:]; break
    return date, paras

# ---------------- Amazon (aboutamazon.com article) -------------------------------------------
JASSY = [("amzn-2025-letter", "https://www.aboutamazon.com/news/company-news/amazon-ceo-andy-jassy-2025-letter-to-shareholders"),
         ("amzn-2024-letter", "https://www.aboutamazon.com/news/company-news/amazon-ceo-andy-jassy-2024-letter-to-shareholders")]
def jassy_list():
    return [{"id": i, "url": u} for i, u in JASSY]

def jassy_extract(raw):
    title = clean(re.search(r"<title>(.*?)</title>", raw, re.S).group(1))
    date = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d\d-\d\d)', raw).group(1)
    start = raw.find("Dear Shareholders")
    end = raw.find("Sincerely,", start)          # stop before signature, P.S. and the reprinted 1997 Bezos letter
    seg = raw[raw.rfind('<div class="contentContainer block">', 0, start):end]
    paras = []
    for block in seg.split('<div class="contentContainer block">'):
        if "contentItem-role-text" not in block: continue          # skip images/embeds
        for p in re.split(r"<br\s*/?>|</div>", block):
            t = clean(re.sub(r"<[^>]+>", " ", p))
            if t: paras.append(t)
    return title, date, paras

# ---------------- Berkshire (berkshirehathaway.com PDF) --------------------------------------
def abel_list():
    out = []
    for y in range(2025, datetime.now().year + 1):            # Abel became CEO Jan 1, 2026 -> letters for FY2025+
        out.append({"id": f"brk-{y}-letter", "url": f"https://www.berkshirehathaway.com/letters/{y}ltr.pdf",
                    "title": f"{y} Letter to Berkshire Shareholders"})
    return out

def abel_extract(pdf_path):
    """pdftotext -layout keeps blank lines between paragraphs and column gaps in tables.
    Keep prose paragraphs and bullet items; drop headings, tables, page numbers, separators."""
    txt = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"], capture_output=True, text=True, check=True).stdout
    if "Gregory E. Abel" not in txt:
        raise ValueError("not signed by Gregory E. Abel")
    m = re.search(r"([A-Z][a-z]+ \d{1,2}, 20\d\d)", txt[txt.find("Gregory E. Abel"):][:300])
    date = datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
    END = re.compile(r"[.!?:;\u201d\"')]$")
    paras, pages, dropped = [], [], []
    for pno, page in enumerate(txt.split("\f"), 1):
        stop = "Gregory E. Abel" in page
        if stop: page = page[:page.find("Gregory E. Abel")]
        for block in re.split(r"\n[ \t]*\n", page):
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            if not lines: continue
            lines = [re.sub(r"^(?:\u2022|\d{1,2}\.)\s{2,}", "", l) for l in lines]      # bullets / numbered items
            tab = [i for i, l in enumerate(lines) if re.search(r"\S {3,}\S", l)]  # table rows have column gaps
            if tab:
                dropped.append(" | ".join(lines[tab[0]:]))                         # drop the table (and its header rows)
                lines = lines[:tab[0]]                                              # keep prose right above it
                if not lines: continue
            t = ""
            for l in lines:                                                          # join lines; keep real hyphens
                t = t + l if t.endswith("-") else (t + " " + l if t else l)
            t = clean(t)
            words = t.split()
            if (not re.search(r"[A-Za-z]{2}", t) or t == "Berkshire Hathaway Inc."                 # letterhead
                    or (len(lines) == 1 and len(words) <= 8 and not re.search(r"[.!?:;,\u201d\"')]$", t))):
                dropped.append(t); continue                                          # page numbers, separators, headings
            if paras and not END.search(paras[-1]) and t[:1].islower():
                paras[-1] += " " + t                                                  # paragraph continued across a page break
            else:
                paras.append(t); pages.append(pno)
        if stop: break
    return date, paras, pages, dropped

# ---------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(PEOPLE))
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    for slug in a.only.split(","):
        P = PEOPLE[slug]; d = LOCAL / slug; idx_path = d / "index.json"
        idx = json.loads(idx_path.read_text()) if idx_path.exists() else []
        have = {m["id"]: m for m in idx if (d / m["file"]).exists()}
        try:
            cands = {"karp": karp_list, "jassy": jassy_list, "abel": abel_list}[slug]()
        except Exception as e:
            print(f"[{slug}] WARN could not list documents: {e}; keeping {len(have)} saved"); cands = []
        if slug == "karp": cands = cands[:P["max"]]
        for c in cands:
            if c["id"] in have and not a.refresh: continue
            try:
                meta = {"id": c["id"], "file": c["id"] + ".txt", "person": P["name"], "category": P["category"],
                        "role": P["role"], "org": P["org"], "url": c["url"], "type": "letter",
                        "source": urllib.parse.urlparse(c["url"]).netloc.replace("www.", ""),
                        "fetched": datetime.now().isoformat(timespec="seconds")}
                if slug == "karp":
                    raw = get(c["url"]); atomic_write(d / "raw" / (c["id"] + ".html"), raw)
                    date, paras = karp_extract(raw); meta.update(title=c["title"], date=date)
                elif slug == "jassy":
                    raw = get(c["url"]); atomic_write(d / "raw" / (c["id"] + ".html"), raw)
                    title, date, paras = jassy_extract(raw)
                    meta.update(title=title.replace("Amazon CEO Andy Jassy’s ", "").replace("Amazon CEO Andy Jassy's ", ""), date=date)
                else:
                    try: pdf = get(c["url"], binary=True)
                    except urllib.error.HTTPError as e:
                        if e.code == 404: continue                 # that year's letter not published (yet)
                        raise
                    raw_path = d / "raw" / (c["id"] + ".pdf"); atomic_write(raw_path, pdf)
                    date, paras, pages, dropped = abel_extract(raw_path)
                    meta.update(title=c["title"], date=date, para_pages=pages, pdf=True)
                    print(f"[{slug}] {c['id']}: dropped {len(dropped)} non-prose blocks (tables/page numbers)")
                text = "\n\n".join(paras) + "\n"
                if len(text.split()) < MIN_WORDS: raise ValueError(f"only {len(text.split())} words extracted")
                if not meta.get("date"): raise ValueError("no date found")
                atomic_write(d / meta["file"], text)
                have[c["id"]] = meta
                print(f"[{slug}] saved {meta['date']} {meta['title']} ({len(text.split())} words, {len(paras)} paragraphs)")
            except Exception as e:
                print(f"[{slug}] WARN skipping {c['url']}: {e}")
        meta_all = sorted(have.values(), key=lambda m: m["date"], reverse=True)
        atomic_write(idx_path, json.dumps(meta_all, indent=2, ensure_ascii=False) + "\n")
        print(f"[{slug}] {len(meta_all)} document(s) in {idx_path.relative_to(ROOT)}")

if __name__ == "__main__":
    import urllib.parse, urllib.error
    main()
