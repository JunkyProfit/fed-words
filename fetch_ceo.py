#!/usr/bin/env python3
"""Fetch CEO shareholder letters from each company's OWN public website and save the
extracted text LOCALLY ONLY (local_sources/<slug>/, which is gitignored).

The full letter text is never committed or published. build.py turns these local
texts into derived data (word counts + a limited set of excerpt sentences) in
derived/<slug>.json, which is what gets committed.

Manual script (not part of publish.sh). Safe to rerun: existing documents are kept
and not re-downloaded unless --refresh is given. ~1 request/second, declared UA.

Usage: python3 fetch_ceo.py [--only karp,jassy,abel,pichai,ternus] [--refresh]

Source types (shown as a label on each document in the site):
  karp / jassy / abel  "Shareholder letter"            (signed annual/quarterly letters)
  pichai               "Earnings call prepared remarks" (only the CEO's own prepared section of the
                       call transcript Alphabet publishes on abc.xyz; operator, other executives and
                       the analyst Q&A are discarded)
  ternus               "Earnings call prepared remarks" -- Apple publishes only a press release and an
                       audio webcast on investor.apple.com (no transcript or prepared-remarks text), so
                       this lists Apple's earnings events after Sept 1, 2026 and saves text ONLY if Apple
                       itself attaches a transcript/remarks document. Until then it saves nothing.
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
    "pichai": {"name": "Sundar Pichai", "display": "Sundar Pichai", "category": "CEOs",
               "role": "CEO, Alphabet and Google", "org": "Alphabet", "max": 8,
               "type": "remarks", "source_type": "Earnings call prepared remarks"},
    "ternus": {"name": "John Ternus", "display": "John Ternus", "category": "CEOs",
               "role": "CEO, Apple", "org": "Apple", "since": "2026-09-01",
               "type": "remarks", "source_type": "Earnings call prepared remarks"},
}
SOURCE_TYPE = {"letter": "Shareholder letter", "remarks": "Earnings call prepared remarks"}

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

# ---------------- Alphabet (abc.xyz: company-published earnings call transcripts) -------------
ABC = "https://abc.xyz"
def pichai_list():
    feed = json.loads(get(ABC + "/feed/FinancialReport.svc/GetFinancialReportList?LanguageId=1&reportTypes="
                          "First%20Quarter|Second%20Quarter|Third%20Quarter|Fourth%20Quarter&pageSize=-1&pageNumber=0"
                          "&tagList=&includeTags=true&year=-1&excludeSelection=1"))
    out, seen = [], set()
    for r in feed["GetFinancialReportListResult"]:
        q = {"First Quarter": 1, "Second Quarter": 2, "Third Quarter": 3, "Fourth Quarter": 4}.get(r.get("ReportSubType"))
        for x in r.get("Documents", []):
            if "Transcript" not in (x.get("DocumentTitle") or "") or not q: continue
            key = (int(r["ReportYear"]), q)
            if key in seen: continue
            seen.add(key); url = x["DocumentPath"]
            if url.startswith("/"): url = ABC + url
            out.append({"id": f"goog-q{q}-{key[0]}", "url": url, "title": f"Q{q} {key[0]} Earnings Call: Prepared Remarks"})
    return sorted(out, key=lambda c: c["id"][-4:] + c["id"][6], reverse=True)

def _speaker_label(t):
    m = re.match(r"^([A-Z][\w.\- ]{2,40}),\s*[^:]{2,80}:\s*(.*)$", t)
    return m

def pichai_extract(raw):
    """Keep only Sundar Pichai's prepared section: from his first speaker label up to the next
    speaker label (another executive). The operator, IR safe-harbor text and the Q&A are dropped."""
    m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2}), (20\d\d)", raw)
    date = datetime.strptime(m.group(0), "%B %d, %Y").strftime("%Y-%m-%d") if m else None
    paras, on = [], False
    for p in re.findall(r"<p[^>]*>(.*?)</p>", raw, re.S):
        p = re.sub(r"</?(?:span|em)\b[^>]*>", "", p)          # older pages wrap text and labels in styled spans
        p = re.sub(r"<(/?)b\b[^>]*>", r"<\1strong>", p)        # ...and some use <b> for speaker labels
        lab = re.match(r"\s*<strong>(.*?)</strong>(.*)$", p, re.S)
        if lab and re.search(r":\s*$", clean(re.sub(r"<[^>]+>", " ", lab.group(1)))):
            who = clean(re.sub(r"<[^>]+>", " ", lab.group(1)))
            if on: break                                   # next speaker -> end of Sundar's prepared remarks
            if who.startswith("Sundar Pichai"):
                on = True; p = lab.group(2)
            else: continue
        if not on: continue
        t = clean(re.sub(r"<[^>]+>", " ", p)).replace("\u2011", "-")
        if t: paras.append(t)
    if not paras: raise ValueError("Sundar Pichai's prepared remarks not found on the page")
    return date, paras

# ---------------- Apple (investor.apple.com) -------------------------------------------------
def ternus_list():
    """Apple's earnings events since the CEO transition. Apple has so far published only a press
    release and an audio webcast per call; we save text only when Apple attaches a transcript or
    prepared-remarks document of its own (never third-party transcripts)."""
    feed = json.loads(get("https://investor.apple.com/feed/Event.svc/GetEventList?LanguageId=1&eventSelection=3"
                          "&eventDateFilter=3&includeFinancialReports=true&includePresentations=true&includePressReleases=true"
                          "&sortOperator=1&pageSize=12&pageNumber=0&tagList=&includeTags=true&year=-1&excludeSelection=1"))
    out = []
    for e in feed.get("GetEventListResult") or []:
        d = datetime.strptime(e["StartDate"][:10], "%m/%d/%Y").strftime("%Y-%m-%d")
        if d < PEOPLE["ternus"]["since"]: continue
        docs = [a for a in (e.get("Attachments") or []) if re.search(r"(?i)transcript|remarks", a.get("Title") or "")]
        print(f"[ternus] {d} {e.get('Title')}: {'company transcript/remarks found' if docs else 'no Apple-published transcript or remarks (webcast/press release only)'}")
        for a in docs:
            out.append({"id": "aapl-" + d, "url": a.get("Url") or a.get("DocumentPath"), "date": d, "title": clean(e["Title"]) + ": Prepared Remarks"})
    return out

def ternus_extract(raw):
    """Apple has not published one yet, so the format is unknown: keep the CEO's section between his
    speaker label and the next speaker label (same rule as Alphabet)."""
    txt = clean(re.sub(r"<[^>]+>", "\n", raw)) if "<" in raw[:2000] else raw
    m = re.search(r"John Ternus[^:\n]{0,40}:(.*?)(?=\n?[A-Z][a-z]+ [A-Z][a-z]+[^:\n]{0,40}:|$)", txt, re.S)
    if not m: raise ValueError("John Ternus's remarks not found")
    return [clean(x) for x in re.split(r"\n\s*\n", m.group(1)) if clean(x)]

# ---------------- Data-driven companies (ceos.json) -------------------------------------------
import zipfile, io
from ceo_extract import transcript_section, letter_body
CONFIG = json.loads((ROOT / "ceos.json").read_text(encoding="utf-8"))["companies"]
CONFIG = [_c for _c in CONFIG if not _c.get("fetcher")]       # e.g. past CEOs built by fetch_ceo_filings.py
for _c in CONFIG:
    PEOPLE.setdefault(_c["slug"], {"name": _c["name"], "display": _c["name"], "category": "CEOs", "role": _c["role"],
                                   "org": _c["org"], "max": _c.get("max", 4), "cfg": _c,
                                   "type": "letter" if _c["kind"] == "letter" else "remarks",
                                   "source_type": SOURCE_TYPE["letter" if _c["kind"] == "letter" else "remarks"]})
MON = "January|February|March|April|May|June|July|August|September|October|November|December"
MON3 = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"

def find_date(*texts):
    for t in texts:
        t = urllib.parse.unquote(t or "").replace("+", " ")
        for rx, fmt in [(r"(20\d\d)-(\d\d)-(\d\d)", None), (r"\b(\d{1,2})[- ](" + MON + r")[- ](20\d\d)\b", "%d %B %Y"),
                        (r"\b(\d{1,2})-(" + MON3 + r")-(20\d\d)\b", "%d %b %Y"), (r"\b(" + MON + r")\.? (\d{1,2})(?:st|nd|rd|th)?,? (20\d\d)\b", "%B %d %Y"),
                        (r"_(\d{1,2})-(\d{1,2})-(\d\d)_", "mdy")]:
            m = re.search(rx, t)
            if not m: continue
            try:
                if fmt is None: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                if fmt == "mdy": return datetime(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2))).strftime("%Y-%m-%d")
                return datetime.strptime(" ".join(m.groups()), fmt).strftime("%Y-%m-%d")
            except ValueError: continue
    return None

def pdf_date(raw):
    """CreationDate from the PDF metadata (fallback when the text carries no date)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(raw); f.flush()
        info = subprocess.run(["pdfinfo", "-isodates", f.name], capture_output=True, text=True).stdout
    m = re.search(r"CreationDate:\s+(20\d\d-\d\d-\d\d)", info)
    return m.group(1) if m else None

def doc_text(raw):
    if raw[:4] == b"%PDF":
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(raw); f.flush()
            return subprocess.run(["pdftotext", f.name, "-"], capture_output=True, text=True, check=True).stdout
    if raw[:2] == b"PK":
        x = zipfile.ZipFile(io.BytesIO(raw)).read("word/document.xml").decode("utf-8", "replace")
        return "\n\n".join(html.unescape(re.sub(r"<[^>]+>", "", p)) for p in re.findall(r"<w:p[ >].*?</w:p>", x, re.S))
    t = raw.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?i)<(br|/p|/div|/h\d|/li)[^>]*>", "\n\n", t)
    return html.unescape(re.sub(r"<[^>]+>", " ", t))

def q4_list(cfg):
    d = cfg["discover"]
    feed = json.loads(get(f"https://{d['host']}/feed/FinancialReport.svc/GetFinancialReportList?LanguageId=1&reportTypes="
                          "&pageSize=-1&pageNumber=0&tagList=&includeTags=true&year=-1&excludeSelection=1"))
    out = []
    for r in feed.get("GetFinancialReportListResult") or []:
        q = {"First Quarter": 1, "Second Quarter": 2, "Third Quarter": 3, "Fourth Quarter": 4}.get(r.get("ReportSubType"))
        for x in r.get("Documents", []):
            if not re.search(d["title"], x.get("DocumentTitle") or ""): continue
            u = x["DocumentPath"]; u = ("https:" + u) if u.startswith("//") else (f"https://{d['host']}" + u if u.startswith("/") else u)
            out.append({"url": u, "period": f"Q{q} {r['ReportYear']}" if q else str(r.get("ReportYear", "")),
                        "hint": (r.get("ReportDate") or "") + " " + u})
    return out

def links_list(cfg):
    d = cfg["discover"]; pages = [d["page"]]
    if "{year}" in d["page"]:
        pages = [d["page"].format(year=datetime.now().year - k) for k in range(d.get("years", 2))]
    out, seen = [], set()
    for pg in pages:
        try: page = get(pg)
        except Exception as e: print(f"[{cfg['slug']}] WARN {pg}: {e}"); continue
        for h in re.findall(r'href="([^"]+)"', page):
            h = html.unescape(h)
            if not re.search(d["href"], h): continue
            u = urllib.parse.urljoin(pg, h)
            if u in seen: continue
            seen.add(u); out.append({"url": u, "period": "", "hint": u})
    return out

def pattern_list(cfg):
    d = cfg["discover"]; now = datetime.now(); out = []
    fy = now.year + (1 if now.month > d.get("fiscal_end_month", 12) else 0)
    q = ((now.month - d.get("fiscal_end_month", 12) - 1) % 12) // 3 + 1      # current fiscal quarter
    for _ in range(d.get("quarters", 8)):
        q -= 1
        if q == 0: q, fy = 4, fy - 1
        out.append({"url": d["template"].format(yy=f"{fy % 100:02d}", q=q, yyyy=fy), "period": f"Q{q} FY{fy}", "hint": ""})
    return out

def order_key(c):
    """(year, quarter) guessed from the period label or URL, for newest-first ordering."""
    t = (c.get("period") or "") + " " + urllib.parse.unquote(c["url"]).replace("+", " ")
    dt = find_date(c.get("hint"), c["url"])
    if dt: return (int(dt[:4]), (int(dt[5:7]) - 1) // 3 + 1, dt)
    m = re.search(r"Q([1-4]) (?:FY)?(20\d\d)", t) or re.search(r"(?i)FY(\d\d)\s*Q([1-4])", t)
    if m and m.re.pattern.startswith("Q"): return (int(m.group(2)), int(m.group(1)), "")
    if m: return (2000 + int(m.group(1)), int(m.group(2)), "")
    t2 = re.sub(r"[_+]", " ", t)
    m = re.search(r"(?i)(?<![0-9a-z])([1-4])\s?q\s?(?:20)?(\d\d)(?!\d)", t2) or re.search(r"(?i)(20\d\d)psqtr([1-4])", t2)
    if m and m.group(1).startswith("20"): return (int(m.group(1)), int(m.group(2)), "")
    if m: return (2000 + int(m.group(2)), int(m.group(1)), "")
    m = re.search(r"(?i)\b(first|second|third|fourth)\s+quarter\b.{0,30}?(20\d\d)", t2)
    if m: return (int(m.group(2)), ["first", "second", "third", "fourth"].index(m.group(1).lower()) + 1, "")
    m = re.search(r"(20\d\d)", t)
    return (int(m.group(1)), 0, "") if m else (0, 0, "")

def pages_list(cfg):
    d = cfg["discover"]; out = []
    for c in pattern_list({"discover": {"template": d["page"], "fiscal_end_month": d.get("fiscal_end_month", 12)}}):
        try: page = get(c["url"])
        except Exception as e: continue
        for h in re.findall(r'(?:href|src)="([^"]+)"', page):
            h = html.unescape(h)
            m = re.search(d["href"], h)
            if m:
                u = m.group(0) if m.group(0).startswith("http") else urllib.parse.urljoin(c["url"], m.group(0))
                out.append({"url": u, "period": c["period"], "hint": ""}); break
    return out

def generic_list(slug):
    cfg = PEOPLE[slug]["cfg"]
    return sorted({"q4": q4_list, "links": links_list, "pattern": pattern_list, "pages": pages_list,
            "urls": lambda c: [{"url": u, "period": "", "hint": u} for u in c["discover"]["urls"]]}[cfg["discover"]["type"]](cfg),
                  key=order_key, reverse=True)

def generic_fetch(slug, c, d):
    """Download one candidate, cut the CEO's own words; returns (meta updates, paragraphs) or raises."""
    cfg = PEOPLE[slug]["cfg"]
    raw = get(c["url"], binary=True)
    ext = ".pdf" if raw[:4] == b"%PDF" else ".docx" if raw[:2] == b"PK" else ".html"
    text = doc_text(raw)
    date = find_date(c.get("hint"), text[:6000])
    if not date and raw[:4] == b"%PDF":
        date = pdf_date(raw)
        k = order_key(c)                                   # sanity: within ~100 days after the quarter it covers
        if date and k[1]:
            qend = datetime(k[0], 3 * k[1], 28)
            if not (0 <= (datetime.strptime(date, "%Y-%m-%d") - qend).days <= 100): date = None
        if date: print(f"[{slug}] {c['id']}: date taken from PDF metadata ({date})"); c["date_basis"] = "pdf"
    if cfg["kind"] == "letter" and raw[:4] == b"%PDF" and date and date[5:] == "12-31":   # fiscal year-end, not the letter's date
        date = pdf_date(raw) or date
    if not date: raise ValueError("no date found")
    if date < cfg["since"]: raise ValueError(f"{date} is before {cfg['name']} became CEO ({cfg['since']})")
    if cfg["kind"] == "letter":
        paras = letter_body(text, cfg["signer"])
        if not re.search(re.escape(cfg["signer"].split()[-1]), text): raise ValueError("not signed by " + cfg["signer"])
        ym = re.search(r"(20\d\d)", urllib.parse.unquote(c["url"]).rsplit("/", 1)[-1])
        title = f"{int(ym.group(1)) if ym else int(date[:4]) - 1} Letter to Shareholders"
    else:
        paras = transcript_section(text, cfg["ceo"])
        per = c.get("period") or ""
        k = order_key(c)
        if not per and k[1] and not k[2]:
            per = f"Q{k[1]} FY{k[0]}" if re.search(r"(?i)FY\s?\d\d", urllib.parse.unquote(c["url"])) else f"Q{k[1]} {k[0]}"
        if not per:
            m = re.search(r"(?i)\b([1-4])q\s?(20)?(\d\d)\b|qtr([1-4])|\bQ([1-4])[ +_-]*(FY)?\s?(20)?(\d\d)", urllib.parse.unquote(c["url"]).replace("+", " "))
            if m:
                qn = m.group(1) or m.group(4) or m.group(5)
                yy = m.group(3) or m.group(8)
                per = f"Q{qn} " + (("FY" if m.group(6) else "") + "20" + yy if yy else date[:4])
        if per and cfg.get("fiscal") and "FY" not in per: per = re.sub(r"^Q([1-4]) (20\d\d)$", r"Q\1 FY\2", per)
        if not per and not cfg.get("fiscal") and cfg["discover"].get("fiscal_end_month", 12) == 12:   # calendar-year reporter: call date -> prior quarter
            cm, cy = int(date[5:7]), int(date[:4]); qn = (cm - 1) // 3
            per = f"Q{qn} {cy}" if qn else f"Q4 {cy - 1}"
        title = (f"{per} Earnings Call" if per else f"Earnings Call, {datetime.strptime(date, '%Y-%m-%d'):%b %-d, %Y}") + ": CEO Prepared Remarks"
    atomic_write(d / "raw" / (c["id"] + ext), raw)
    return {"title": title, "date": date} | ({"date_basis": "transcript file date (call date not printed)"} if c.get("date_basis") else {}), paras

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
            fn = {"karp": karp_list, "jassy": jassy_list, "abel": abel_list,
                  "pichai": pichai_list, "ternus": ternus_list}.get(slug)
            cands = fn() if fn else generic_list(slug)
            if not fn:
                tk = P["cfg"]["ticker"].lower()
                for k, cnd in enumerate(cands):
                    cnd["id"] = f"{tk}-" + re.sub(r"[^a-z0-9]+", "-", (urllib.parse.unquote(cnd["url"]).rsplit("/", 1)[-1].rsplit(".", 1)[0]).lower()).strip("-")[:60]
                from collections import Counter as _C
                dup = _C(c["id"] for c in cands)
                for cnd in cands:            # same file name every quarter (e.g. .../2026/q1/Transcript.pdf): add the period
                    if dup[cnd["id"]] > 1:
                        k = order_key(cnd); cnd["id"] += f"-{k[0]}q{k[1]}" if k[1] else "-" + re.sub(r"[^a-z0-9]+", "-", cnd.get("period", "").lower())
        except Exception as e:
            print(f"[{slug}] WARN could not list documents: {e}; keeping {len(have)} saved"); cands = []
        if P.get("max") and "cfg" not in P: cands = cands[:P["max"]]
        if "cfg" in P: cands = cands[:16]                     # newest first; old/invalid ones are skipped below
        got_new = 0
        for c in cands:
            if c["id"] in have and not a.refresh: continue
            try:
                meta = {"id": c["id"], "file": c["id"] + ".txt", "person": P["name"], "category": P["category"],
                        "role": P["role"], "org": P["org"], "url": c["url"], "type": P.get("type", "letter"),
                        "source_type": P.get("source_type", SOURCE_TYPE["letter"]),
                        "source": urllib.parse.urlparse(c["url"]).netloc.replace("www.", ""),
                        "fetched": datetime.now().isoformat(timespec="seconds")}
                if slug == "karp":
                    raw = get(c["url"]); atomic_write(d / "raw" / (c["id"] + ".html"), raw)
                    date, paras = karp_extract(raw); meta.update(title=c["title"], date=date)
                elif slug == "jassy":
                    raw = get(c["url"]); atomic_write(d / "raw" / (c["id"] + ".html"), raw)
                    title, date, paras = jassy_extract(raw)
                    meta.update(title=title.replace("Amazon CEO Andy Jassy’s ", "").replace("Amazon CEO Andy Jassy's ", ""), date=date)
                elif "cfg" in P:
                    if len([m for m in have.values()]) >= P["max"]: break
                    upd, paras = generic_fetch(slug, c, d); meta.update(upd)
                    meta["ticker"] = P["cfg"]["ticker"]
                elif slug == "pichai":
                    raw = get(c["url"]); atomic_write(d / "raw" / (c["id"] + ".html"), raw)
                    date, paras = pichai_extract(raw); meta.update(title=c["title"], date=date)
                elif slug == "ternus":
                    raw = get(c["url"], binary=True)
                    if raw[:4] == b"%PDF":
                        rp = d / "raw" / (c["id"] + ".pdf"); atomic_write(rp, raw)
                        raw = subprocess.run(["pdftotext", str(rp), "-"], capture_output=True, text=True, check=True).stdout
                    else: raw = raw.decode("utf-8", "replace")
                    paras = ternus_extract(raw); meta.update(title=c["title"], date=c["date"])
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
