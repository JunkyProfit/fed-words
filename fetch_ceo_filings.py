#!/usr/bin/env python3
"""Former CEOs whose own words exist only in filings: SEC EDGAR and US government hearing records.

Used for Apple's past CEOs (Tim Cook, Steve Jobs). Apple publishes no earnings-call transcripts or prepared
remarks (investor.apple.com has the press release plus an audio webcast that comes down after about two weeks),
so these people are built ONLY from texts that Apple itself filed with the SEC, plus official congressional
hearing records:
  quote      "Press release quote": the quoted words attributed to the person in Apple press releases filed
             as 8-K exhibits (EX-99.x). Found through EDGAR full-text search, kept within the person's tenure
             (ceos.json since/until). Only the quoted spans attributed to the person are kept.
  letter     "Investor letter" / "Email to employees": a signed letter or email Apple filed with the SEC.
  conference "Conference transcript": a partial transcript Apple filed itself (the person's turns only).
  hearing    "Congressional hearing": the person's own spoken turns in the official hearing record on
             govinfo.gov (other speakers, inserted material and bracketed notes removed). Treated like
             company text (counts + capped excerpts), not as public-domain government text.
No third-party transcripts, keynotes, apple.com pages or archives.

Config: ceos.json companies with "fetcher": "fetch_ceo_filings.py" and a "filings" block. Raw downloads are
cached in local_sources/<slug>/raw/ and the cut text goes to local_sources/<slug>/ (gitignored), exactly like
fetch_ceo.py; build.py turns it into derived/<slug>.json. SEC asks automated clients to send a User-Agent with
a contact address (www.sec.gov/os/accessing-edgar-data) and to stay under 10 requests/s; we send one request
per second. Usage: python3 fetch_ceo_filings.py [--only cook,jobs] [--refresh]
"""
import argparse, html, json, os, re, sys, tempfile, time, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / "local_sources"
# SEC asks automated clients for a User-Agent with a contact address. It comes only from the environment (never stored in the repo):
#   SEC_CONTACT="you@example.com" python3 fetch_ceo_filings.py
CONTACT = os.environ.get("SEC_CONTACT", "").strip()
UA = f"MouthMath/1.0 (+https://mouthmath.com) {CONTACT}"
MIN_WORDS = 8
TYPES = {"quote": "Press release quote", "letter": "Investor letter", "email": "Email to employees",
         "conference": "Conference transcript", "hearing": "Congressional hearing"}

_last = [0.0]
def get(url):
    if not CONTACT:   # only network fetches need it; rebuilding from local_sources/ works without
        sys.exit("fetch_ceo_filings.py: set SEC_CONTACT (a contact email for SEC's User-Agent rule) to download from sec.gov")
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.read()
    finally: _last[0] = time.time()

def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "wb" if isinstance(data, bytes) else "w", **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as f:
        f.write(data)
    os.replace(tmp, path)

def cached(d, name, url, refresh):
    p = d / "raw" / name
    if p.exists() and not refresh: return p.read_bytes()
    raw = get(url); atomic_write(p, raw); return raw

def ws(s): return " ".join(html.unescape(s).replace("\u00a0", " ").split())

def html_paras(raw):
    """Block-level paragraphs of an EDGAR HTML exhibit."""
    t = raw.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", t)
    t = re.sub(r"(?i)<(br|/p|/div|/h\d|/li|/tr|/td|/table|p\b[^>]*|div\b[^>]*)>", "\n\n", t)
    return [p for p in (ws(re.sub(r"<[^>]+>", " ", x)) for x in re.split(r"\n\s*\n", t)) if p]

# ---------------- press-release quotes (EDGAR full-text search -> 8-K EX-99.x) ----------------
def efts(q, cik, forms):
    out, frm = [], 0
    while True:
        p = {"q": q, "ciks": cik, "forms": forms, "from": frm}
        d = json.loads(get("https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(p)))
        hits = d["hits"]["hits"]; out += hits
        if len(hits) < 100 or frm + 100 >= d["hits"]["total"]["value"]: return out
        frm += 100

def edgar_url(cik, hit_id):
    adsh, fn = hit_id.split(":")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{fn}"

QUOTE = re.compile(r"[\u201c\"]([^\u201c\u201d\"]{3,2000})[\u201d\"]")
VERB = r"(?:said|says|added|noted|commented)"
def quote_spans(paras, f):
    """Quoted spans attributed to the person: the quote right before 'said <name>' and the quote right after that
    attribution sentence (Apple's pattern: "A," said Tim Cook, Apple's CEO. "B."), or right after '<name> said'.
    Quotes from anyone else in the same release are not taken."""
    t = " ".join(paras)
    nm = r"(?:" + re.escape(f["speaker"]) + r"|" + re.escape(f["speaker"].split()[-1]) + r")\b"
    after_q = re.compile(r"^\s*" + VERB + r"\s+" + nm)                                      # "...," said Tim Cook
    before_q = re.compile(r"(?:" + VERB + r"\s+" + nm + r"[^\u201c\u201d\"]{0,90}[.,:]|" + nm +
                          r"(?:,[^,\u201c\u201d\"]{0,60},)?\s+" + VERB + r"[^\u201c\u201d\"]{0,12}[,:]?)\s*$")    # said Tim Cook, CEO. "..."
    out = []
    for m in QUOTE.finditer(t):
        if after_q.search(t[m.end():m.end() + 80]) or before_q.search(t[max(0, m.start() - 160):m.start()]):
            q = re.sub(r",$", ".", m.group(1).strip())
            if len(q.split()) >= 3: out.append(q)
    return out

def release_title(paras):
    """Headline: the first title-like block before the dateline."""
    for p in paras[:25]:
        if re.match(r"(?i)^(ex-?99|exhibit|quicklinks|\d+$|page|press release|apple (inc|computer)\.?$|contacts?:)", p): continue
        if re.search(r"(?i)cupertino", p): break
        if 3 <= len(p.split()) <= 20 and not p.endswith("."): return p
    return None

def release_date(paras, fallback):
    for p in paras[:30]:
        m = re.search(r"(?i)cupertino,?\s+calif\w*\W{1,4}((?:January|February|March|April|May|June|July|August|September|"
                      r"October|November|December)\s+\d{1,2},\s+(?:19|20)\d\d)", p)
        if m: return datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
    return fallback

def quotes_list(P, f, d, refresh):
    fq = f["quotes"]
    hits = efts(f'"{f["speaker"]}"', f["cik"], fq.get("forms", "8-K"))
    hits = [h for h in hits if re.match(r"EX-99", h["_source"].get("file_type") or "")]
    since, until = P["since"], P.get("until") or "9999"
    out, seen = [], set()
    listed = {x["url"] for x in f.get("docs", [])} | set(fq.get("exclude", []))      # letters etc. are their own documents
    for h in sorted(hits, key=lambda h: h["_source"]["file_date"]):
        fd = h["_source"]["file_date"]
        url = edgar_url(f["cik"], h["_id"])
        if not (since <= fd <= until) or url in seen or url in listed: continue
        seen.add(url)
        out.append({"kind": "quote", "url": url, "filed": fd, "form": h["_source"]["form"], "exhibit": h["_source"]["file_type"]})
    return out

# ---------------- letters, transcripts and hearings listed in ceos.json ----------------
def letter_paras(paras, doc):
    st = next((i for i, p in enumerate(paras) if re.match(doc["start"], p)), None)
    if st is None: raise ValueError("letter start not found")
    out = []
    for p in paras[st:]:
        if re.fullmatch(doc["signature"], p) or re.match(r"(?i)^(press contacts?|forward-looking|this (letter|document) contains)", p): break
        p = re.sub(doc["start"] + r"\s*", "", p) if p is paras[st] else p
        p = re.sub(r"\s+" + doc["signature"].strip("^$") + r"$", "", p)            # signature run into the last line
        if not p or not re.search(r"[A-Za-z]{2}", p): continue
        if len(p.split()) <= 8 and not re.search(r"[.!?:;,\u201d\"')]$", p): continue        # headings, bullet figures
        out.append(p)
    return out

def turns(paras, label, others, stop=None):
    """Text of every turn that starts with `label` (regex), up to the next speaker label."""
    out, on = [], False
    for p in paras:
        if stop and re.match(stop, p): on = False; continue
        m = re.match(label, p)
        if m: on = True; p = p[m.end():].strip()
        elif re.match(others, p): on = False; continue
        if on and p: out.append(p)
    return out

def hearing_paras(raw):
    """govinfo hearing HTML (<pre> text): paragraphs start with 4-space indents; headings are centred."""
    t = html.unescape(re.sub(r"<[^>]+>", "", raw.decode("utf-8", "replace")))
    paras, cur = [], []
    for line in t.split("\n"):
        if not line.strip():
            if cur: paras.append(" ".join(cur)); cur = []
            continue
        ind = len(line) - len(line.lstrip(" "))
        if ind >= 4 and cur: paras.append(" ".join(cur)); cur = []
        if ind >= 8 and not cur:                                 # centred heading / table line: own block
            paras.append("\x00" + line.strip()); continue
        cur.append(line.strip())
    if cur: paras.append(" ".join(cur))
    return [ws(p) if not p.startswith("\x00") else p for p in paras]

HEARING_OTHERS = (r"^(?:Mr|Ms|Mrs|Dr|Senator|Chairman|Chairwoman|Representative|Chair|Voice)\.?\s+[A-Z][A-Za-z'\-]+"
                  r"(?:\s(?:of\s)?[A-Z][A-Za-z'\-]+)*(?:\s\[[^\]]{0,30}\])?\.\s|^\x00|^\[|^The (?:Chairman|Clerk)\.|^STATEMENT OF|^TESTIMONY OF")
def clean_turn(p):
    if re.match(r"^\\\d+\\", p): return ""                         # footnote (\1\ The prepared statement ...)
    p = re.sub(r"-{8,}.*$", " ", p) if re.search(r"-{8,}\s*\\\d+\\", p) else re.sub(r"-{8,}", " ", p)
    p = re.sub(r"\[[^\]]{0,200}\]", " ", p)                      # [Laughter.], [inaudible], [The prepared statement ...]
    p = re.sub(r"(\w)- (\w)", r"\1\2", p) if re.search(r"\w- [a-z]", p) else p
    return ws(p)

def doc_items(P, f):
    return [dict(x, kind=x["type"]) for x in f.get("docs", [])]

def extract(P, f, item, d, refresh):
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", urllib.parse.urlparse(item["url"]).path.strip("/").replace("/", "_"))[-90:]
    raw = cached(d, name, item["url"], refresh)
    if item["kind"] == "quote":
        paras = html_paras(raw)
        q = quote_spans(paras, f)
        title = release_title(paras) or "Apple press release"
        date = release_date(paras, item["filed"])
        return {"title": f"{title}", "date": date, "note": f"Apple {item['form']} {item['exhibit']} (filed {item['filed']})"}, q
    if item["kind"] in ("letter", "email"):
        return {"title": item["title"], "date": item["date"], "note": item["note"]}, letter_paras(html_paras(raw), item)
    if item["kind"] == "conference":
        paras = html_paras(raw)
        t = turns(paras, item["label"], item["others"], item.get("stop"))
        return {"title": item["title"], "date": item["date"], "note": item["note"]}, [clean_turn(x) for x in t if clean_turn(x)]
    if item["kind"] == "hearing":
        paras = hearing_paras(raw)
        t = turns(paras, item["label"], HEARING_OTHERS)
        return {"title": item["title"], "date": item["date"], "note": item["note"]}, [x for x in (clean_turn(p) for p in t) if x]
    raise ValueError("unknown kind " + item["kind"])

def doc_id(P, item, date):
    if item.get("id"): return item["id"]
    tail = re.sub(r"[^a-z0-9]+", "-", item["url"].rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()).strip("-")[:40]
    return f"{P['ticker'].lower()}-{P['slug']}-{date}-{tail}"

def main():
    cfg = json.loads((ROOT / "ceos.json").read_text(encoding="utf-8"))
    people = {c["slug"]: c for c in cfg["companies"] if c.get("fetcher") == "fetch_ceo_filings.py"}
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(people))
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    for slug in a.only.split(","):
        P = people[slug]; f = P["filings"]; d = LOCAL / slug
        items = (quotes_list(P, f, d, a.refresh) if f.get("quotes") else []) + doc_items(P, f)
        metas = []
        for it in items:
            try:
                upd, paras = extract(P, f, it, d, a.refresh)
            except Exception as e:
                print(f"[{slug}] WARN skipping {it['url']}: {e}"); continue
            text = "\n\n".join(paras) + "\n"
            n = len(text.split())
            if n < MIN_WORDS:
                print(f"[{slug}] skip {it['url']}: {n} words attributed to {f['speaker']}"); continue
            m = {"id": doc_id(P, it, upd["date"]), "person": P["name"], "category": "CEOs", "role": P["role"], "org": P["org"],
                 "url": it["url"], "type": it["kind"], "source_type": it.get("source_type") or TYPES[it["kind"]],
                 "source": urllib.parse.urlparse(it["url"]).netloc.replace("www.", ""), "ticker": P["ticker"],
                 "fetched": datetime.now().isoformat(timespec="seconds")} | upd
            m["file"] = m["id"] + ".txt"
            atomic_write(d / m["file"], text)
            metas.append(m)
            print(f"[{slug}] {m['date']} {m['source_type']:22s} {n:5d} words  {m['title'][:70]}")
        ids = [m["id"] for m in metas]
        assert len(ids) == len(set(ids)), "duplicate document ids"
        for old in d.glob("*.txt"):                                  # documents no longer selected
            if old.name not in {m["file"] for m in metas}: old.unlink()
        metas.sort(key=lambda m: (m["date"], m["id"]), reverse=True)
        atomic_write(d / "index.json", json.dumps(metas, indent=2, ensure_ascii=False) + "\n")
        print(f"[{slug}] {len(metas)} document(s), {sum(len((d / m['file']).read_text().split()) for m in metas)} words -> {(d / 'index.json').relative_to(ROOT)}")

if __name__ == "__main__":
    main()
