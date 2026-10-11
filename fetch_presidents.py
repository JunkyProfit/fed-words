#!/usr/bin/env python3
"""Fetch major U.S. presidential spoken addresses from the American Presidency Project.

NOT run by publish.sh. Texts are U.S. Government works (17 U.S.C. §105), so cleaned
transcripts are committed under transcripts/<slug>/ and get full-text treatment.

  python3 fetch_presidents.py                 # all eight (only fetches what's missing)
  python3 fetch_presidents.py --only obama    # one slug
  python3 fetch_presidents.py --refresh       # re-extract (raw HTML cached in raw/presidents/)

Source: https://www.presidency.ucsb.edu (The American Presidency Project, UC Santa Barbara).
Selection (~20 per president): inaugural addresses, State of the Union / addresses before
joint sessions of Congress, farewell addresses, and Addresses to the Nation; short weekly
addresses, proclamations, statements and press material are skipped. Bracketed stage
directions like [Applause] / [Laughter] are stripped.
Polite: ~1 request/s, identifying User-Agent, cached raw downloads.
"""
import argparse, html, json, re, time, urllib.parse, urllib.request, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw" / "presidents"
TDIR = ROOT / "transcripts"
UA = "Mozilla/5.0 (X11; Linux x86_64) FedWords/1.0 (+https://github.com/JunkyProfit/fed-words)"
BASE = "https://www.presidency.ucsb.edu"
TARGET_N = 20
MIN_WORDS = 400
_last = [0.0]

# slug -> (display name, APP person node id(s), date ranges MM-DD-YYYY, eyebrow years, party)
# Trump: both presidential terms combined under one speaker.
PRESIDENTS = {
    "trump": (
        "Donald J. Trump",
        [200301, 375125],
        [("01-20-2017", "01-20-2021"), ("01-20-2025", "01-20-2029")],
        "2017–2021, 2025–present",
        "R",
    ),
    "biden": (
        "Joseph R. Biden, Jr.",
        [200320],
        [("01-20-2021", "01-20-2025")],
        "2021–2025",
        "D",
    ),
    "obama": (
        "Barack Obama",
        [200300],
        [("01-20-2009", "01-20-2017")],
        "2009–2017",
        "D",
    ),
    "bush43": (
        "George W. Bush",
        [200299],
        [("01-20-2001", "01-20-2009")],
        "2001–2009",
        "R",
    ),
    "clinton": (
        "William J. Clinton",
        [200298],
        [("01-20-1993", "01-20-2001")],
        "1993–2001",
        "D",
    ),
    "bush41": (
        "George H. W. Bush",
        [200297],
        [("01-20-1989", "01-20-1993")],
        "1989–1993",
        "R",
    ),
    "reagan": (
        "Ronald Reagan",
        [200296],
        [("01-20-1981", "01-20-1989")],
        "1981–1989",
        "R",
    ),
    "carter": (
        "Jimmy Carter",
        [200295],
        [("01-20-1977", "01-20-1981")],
        "1977–1981",
        "D",
    ),
}

# APP category tids
CAT_SPOKEN = 8
CAT_SOTU = 45
CAT_INAUGURAL = 46
CAT_FAREWELL = 52

KEEP_TITLE = re.compile(
    r"(?i)^((?:Videotaped )?Inaugural Address|Farewell Address|"
    r"Address (?:to the Nation|Before (?:a )?Joint Session|to (?:the )?Congress|"
    r"Before the United Nations|to the United Nations|Before the UN|"
    r"on |at the |to the People)|"
    r"Radio Address to the Nation|"
    r"Televised Address|"
    r"(?:Videotaped )?Remarks (?:to the Nation|Addressing the Nation|"
    r"(?:to|at|before) the United Nations))"
)
SKIP_TITLE = re.compile(
    r"(?i)weekly address|saturday radio|event timeline|press briefing|digest of|"
    r"press release|statement from the press|photo opportunity|exchange with reporters|"
    r"toast |telephone |nomination acceptance|message to (?:the )?congress|"
    r"proclamation|executive order|memorandum|letter to|statement on the death|"
    r"remarks prior to|remarks following a meeting|swearing-in ceremony|"
    r"remarks on arrival|remarks on departure|bill signing|briefing following|commencement exercises|"
    r"^fact sheet\b|background press call|press call by|leaders.? reception|"
    r"state legislature|\breadout\b"
)


def get(url, cache, refresh=False):
    cache = Path(cache)
    if cache.exists() and cache.stat().st_size > 200 and not refresh:
        return cache.read_bytes()
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=90).read()
    _last[0] = time.time()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def clean_text(s):
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\u00a0", " ").replace("\u00ad", "")
    return " ".join(s.split())


def drop_stage(s):
    """Strip non-spoken bracketed/parenthetical stage directions."""
    s = re.sub(
        r"\((?:Laughter|Applause|Inaudible|Cheers|Crosstalk|Via interpreter|"
        r"In Spanish|Off-mike|Pause|Audience[^)]*)\)\.?",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"\[[^\]]*\]", "", s)
    return " ".join(s.split())


def parse_search_table(raw):
    out = []
    for m in re.finditer(
        r"(?is)<tr[^>]*>\s*<td[^>]*>\s*([A-Za-z]{3} \d{1,2}, \d{4})\s*</td>\s*"
        r"<td[^>]*>.*?</td>\s*"
        r'<td[^>]*>\s*<a href="(/documents/[^"]+)">([^<]+)</a>',
        raw,
    ):
        date_s = m.group(1)
        href = m.group(2)
        title = html.unescape(re.sub(r"\s+", " ", m.group(3))).strip()
        out.append((date_s, href, title))
    return out


def to_iso(date_s):
    date_s = " ".join(date_s.split())
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(date_s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"bad date: {date_s!r}")


def search(pid, dfrom, dto, cats=None, keywords="", pages=6, refresh=False):
    out = []
    cats = cats or []
    for page in range(pages):
        q = {
            "field-keywords": keywords,
            "field-keywords2": "",
            "field-keywords3": "",
            "from[date]": dfrom,
            "to[date]": dto,
            "person2": str(pid),
            "items_per_page": "100",
        }
        if page:
            q["page"] = str(page)
        parts = urllib.parse.urlencode(q)
        for c in cats:
            parts += f"&category2%5B%5D={c}"
        url = f"{BASE}/advanced-search?{parts}"
        key = f"search-{pid}-{'-'.join(map(str, cats)) or 'none'}-{keywords.replace(' ', '_')[:48] or 'all'}-p{page}.html"
        raw = get(url, RAW / "search" / key, refresh).decode("utf-8", "replace")
        rows = parse_search_table(raw)
        if not rows:
            break
        out.extend(rows)
        m = re.search(r"(\d+)\s*-\s*(\d+)\s*of\s*([\d,]+)\s*records", raw)
        if m and int(m.group(2)) >= int(m.group(3).replace(",", "")):
            break
    seen, uniq = set(), []
    for r in out:
        if r[1] in seen:
            continue
        seen.add(r[1])
        uniq.append(r)
    return uniq


def classify_type(title):
    t = title.lower()
    if "inaugural" in t:
        return "inaugural"
    if "farewell" in t:
        return "farewell"
    if "state of the union" in t:
        return "state of the union"
    if "joint session" in t:
        return "address to congress"
    if "address to the nation" in t:
        return "address to the nation"
    if "united nations" in t or re.search(r"\bun\b", t):
        return "address"
    if t.startswith("address"):
        return "address"
    return "remarks"


def priority(title):
    t = title.lower()
    if re.match(r"(?i)^(?:videotaped )?inaugural address\b", title):
        return 0
    if "farewell" in t and "fact sheet" not in t:
        return 1
    # Full televised SOTU before short radio SOTU
    if "state of the union" in t and "radio" not in t:
        return 2
    if "state of the union" in t:
        return 7
    if "joint session of the congress" in t or "joint session of congress" in t:
        return 3
    if "joint session" in t:  # state legislatures etc.
        return 8
    if "address to the nation" in t and "radio" not in t:
        return 4
    if "united nations general assembly" in t:
        return 5
    if t.startswith("address") and "radio" not in t:
        return 6
    if "radio address" in t:
        return 8
    return 9


def accept_title(title):
    """True for major spoken addresses we want to keep."""
    if SKIP_TITLE.search(title):
        return False
    tl = title.lower()
    # Prefer UN General Assembly addresses; skip short bilateral UN meeting remarks
    if "united nations" in tl or re.search(r"\bun\b", tl):
        if "general assembly" in tl:
            return True
        return False
    if KEEP_TITLE.search(title):
        return True
    if "state of the union" in tl or "farewell" in tl:
        return True
    # Exact inaugural title only (not "Remarks Following the Inaugural Ceremony")
    if re.match(r"(?i)^(?:videotaped )?inaugural address\b", title):
        return True
    if "address to the nation" in tl:
        return True
    if re.match(r"(?i)^address before (?:a )?joint session", title):
        return True
    return False


def collect_candidates(pids, ranges, refresh=False):
    """Gather major spoken-address candidates across person ids / date ranges."""
    found = {}  # href -> (date_iso, href, title)
    # Category searches plus keyword fallbacks (some recent docs are miscategorized).
    queries = [
        ([CAT_INAUGURAL], ""),
        ([CAT_SOTU], ""),
        ([CAT_FAREWELL], ""),
        ([CAT_SPOKEN], '"Address to the Nation"'),
        ([CAT_SPOKEN], "Address Before"),
        ([CAT_SPOKEN], "United Nations General Assembly"),
        ([CAT_SPOKEN], "Radio Address to the Nation"),
        ([CAT_SPOKEN], "Inaugural Address"),
        ([], "Inaugural Address"),
        ([], "Address Before a Joint Session"),
        ([], '"Address to the Nation"'),
        ([], "Farewell Address to the Nation"),
        ([], "United Nations General Assembly"),
    ]
    for pid in pids:
        for dfrom, dto in ranges:
            for cats, kw in queries:
                try:
                    rows = search(pid, dfrom, dto, cats, kw, pages=4, refresh=refresh)
                except Exception as e:
                    print(f"  search fail pid={pid} cats={cats} kw={kw!r}: {e}")
                    continue
                for date_s, href, title in rows:
                    if not accept_title(title):
                        continue
                    try:
                        iso = to_iso(date_s)
                    except ValueError:
                        continue
                    prev = found.get(href)
                    if prev is None or priority(title) < priority(prev[2]):
                        found[href] = (iso, href, title)
    items = list(found.values())
    items.sort(key=lambda r: (priority(r[2]), r[0]))
    return items


def extract_doc(href, refresh=False):
    url = BASE + href if href.startswith("/") else href
    slug = href.rstrip("/").rsplit("/", 1)[-1]
    raw = get(url, RAW / "docs" / f"{slug}.html", refresh).decode("utf-8", "replace")
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", raw, re.S)
    title = clean_text(title_m.group(1)) if title_m else slug
    date_m = re.search(r'class="date-display-single"[^>]*>([^<]+)', raw)
    if not date_m:
        raise ValueError("no date")
    date = to_iso(date_m.group(1).strip())
    # Main content
    m = re.search(
        r'(?is)<div[^>]*class="[^"]*field-docs-content[^"]*"[^>]*>(.*?)</div>\s*</div>',
        raw,
    )
    if not m:
        raise ValueError("no content")
    body = m.group(1)
    body = re.sub(r"(?is)<script.*?</script>", "", body)
    body = re.sub(r"(?is)<style.*?</style>", "", body)
    # Paragraphs: prefer <p> blocks; fall back to <br> splits
    paras = []
    ps = re.findall(r"(?is)<p[^>]*>(.*?)</p>", body)
    if ps:
        for p in ps:
            t = drop_stage(clean_text(p))
            if t:
                paras.append(t)
    else:
        body = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
        body = re.sub(r"</p>", "\n\n", body, flags=re.I)
        text = drop_stage(clean_text(re.sub(r"<[^>]+>", " ", body)))
        # re-split roughly into paragraphs by double spaces lost — use sentences batches
        if text:
            paras = [text]
    # Drop leading citation / APP note lines that sometimes appear
    while paras and re.match(
        r"(?i)^(note:|app note:|see app|\[keywords|online by gerhard)", paras[0]
    ):
        paras.pop(0)
    nwords = sum(len(p.split()) for p in paras)
    if nwords < MIN_WORDS:
        raise ValueError(f"too short ({nwords} words)")
    # location if present
    loc_m = re.search(
        r'(?is)class="[^"]*field-docs-location[^"]*".*?<div[^>]*>(.*?)</div>', raw
    )
    location = clean_text(loc_m.group(1)) if loc_m else ""
    return {
        "id": slug[:80],
        "url": url,
        "type": classify_type(title),
        "title": title,
        "date": date,
        "location": location,
        "source": "presidency.ucsb.edu",
        "paras": paras,
        "note": "Transcript from The American Presidency Project (UC Santa Barbara); "
        "bracketed stage directions removed",
    }


def write_person(slug, person, docs):
    out = TDIR / slug
    out.mkdir(parents=True, exist_ok=True)
    keep = set()
    for d in docs:
        paras = d.pop("paras")
        (out / f"{d['id']}.txt").write_text("\n\n".join(paras) + "\n", encoding="utf-8")
        keep.add(f"{d['id']}.txt")
    for f in out.glob("*.txt"):
        if f.name not in keep:
            f.unlink()
    idx = []
    for d in sorted(docs, key=lambda d: d["date"], reverse=True):
        idx.append(
            {
                "id": d["id"],
                "file": f"{d['id']}.txt",
                "person": person,
                "url": d["url"],
                "type": d["type"],
                "title": d["title"],
                "date": d["date"],
                "location": d.get("location", ""),
                "source": d["source"],
                "note": d.get("note", ""),
                "fetched": dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
    (out / "index.json").write_text(
        json.dumps(idx, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for d in idx:
        n = len((out / d["file"]).read_text(encoding="utf-8").split())
        print(f"  {slug:8s} {d['date']} {d['type']:22s} {n:6d} words | {d['title'][:80]}")
    return len(idx)


def fetch_one(slug, refresh=False):
    name, pids, ranges, years, party = PRESIDENTS[slug]
    idx_path = TDIR / slug / "index.json"
    if idx_path.exists() and not refresh:
        n = len(json.loads(idx_path.read_text(encoding="utf-8")))
        print(f"  {slug}: up to date ({n} docs)")
        return n
    print(f"== {name} ({slug}, {party})")
    cands = collect_candidates(pids, ranges, refresh=refresh)
    print(f"  candidates: {len(cands)}")
    docs, seen_ids, seen_keys = [], set(), {}
    for iso, href, title in cands:
        if len(docs) >= TARGET_N:
            break
        try:
            d = extract_doc(href, refresh=refresh)
        except Exception as e:
            print(f"  SKIP {href}: {e}")
            continue
        if d["id"] in seen_ids:
            continue
        key = (d["date"], re.sub(r"[^a-z0-9]+", " ", d["title"].lower()).strip()[:60])
        nwords = sum(len(p.split()) for p in d["paras"])
        if key in seen_keys:
            # keep the longer of two same-day near-duplicates
            i = seen_keys[key]
            old_n = sum(len(p.split()) for p in docs[i]["paras"])
            if nwords <= old_n:
                print(f"  SKIP dup {href}")
                continue
            print(f"  replace dup with longer: {d['title'][:60]}")
            docs[i] = d
            seen_ids.add(d["id"])
            continue
        seen_ids.add(d["id"])
        seen_keys[key] = len(docs)
        docs.append(d)
        print(f"  + {d['date']} {d['type']:22s} {nwords:6d} | {d['title'][:70]}")
    if len(docs) < 8:
        raise SystemExit(
            f"ERROR: only {len(docs)} usable speeches for {slug}; "
            f"refusing to substitute. Check APP access or filters."
        )
    return write_person(slug, name, docs)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", help="slug (trump, biden, obama, bush43, clinton, bush41, reagan, carter)")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    slugs = [args.only] if args.only else list(PRESIDENTS)
    if args.only and args.only not in PRESIDENTS:
        raise SystemExit(f"unknown slug {args.only}; choose from {', '.join(PRESIDENTS)}")
    for slug in slugs:
        fetch_one(slug, refresh=args.refresh)


if __name__ == "__main__":
    main()
