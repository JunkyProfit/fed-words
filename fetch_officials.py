#!/usr/bin/env python3
"""Manual fetcher for U.S. federal officials (NOT run by publish.sh).

All texts here are works of the U.S. Government (17 U.S.C. §105: works prepared by federal officers
or employees as part of their official duties are not subject to copyright), so the cleaned text is
committed under transcripts/<slug>/ and gets the full-text treatment (like the Fed and the President).

  python3 fetch_officials.py                 # everything (only fetches what's missing)
  python3 fetch_officials.py --only cabinet  # cabinet | congress | scotus | <slug>
  python3 fetch_officials.py --refresh       # re-extract (raw downloads are cached in raw/officials/)

Sources (all official .gov):
  Cabinet   treasury.gov remarks; state.gov remarks/testimony (Secretary's own turns only); prepared
            testimony + hearing transcript PDFs from appropriations.senate.gov / armed-services.senate.gov
            (commerce.gov and war.gov block automated access, so congressional testimony is used).
  Congress  Congressional Record (daily edition) on govinfo.gov: only the leader's own labelled turns;
            inserted material, procedural sections and unspoken "additional statements" are excluded.
  Court     supremecourt.gov opinions (OT2025 list). Each PDF is split by running head into the
            opinion of the Court, concurrences and dissents, attributed to their authors. The
            syllabus (by the Reporter), footnotes, captions and running heads are excluded.
            Needs PyMuPDF for the Court (pip install pymupdf); everything else is standard library.
Polite: ~1 request/s, identifying User-Agent, cached raw downloads.
"""
import argparse, html, json, re, subprocess, sys, time, urllib.request, zipfile, datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw" / "officials"
TDIR = ROOT / "transcripts"
UA = "Mozilla/5.0 (X11; Linux x86_64) FedWords/1.0 (+https://github.com/JunkyProfit/fed-words)"
_last = [0.0]

def get(url, cache, refresh=False):
    cache = Path(cache)
    if cache.exists() and cache.stat().st_size > 0 and not refresh:
        return cache.read_bytes()
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = urllib.request.urlopen(req, timeout=60).read()
    _last[0] = time.time()
    cache.parent.mkdir(parents=True, exist_ok=True); cache.write_bytes(data)
    return data

def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\u00a0", " ").replace("\u00ad", "")
    return " ".join(s.split())

def drop_parens(s):   # stage directions like (Laughter.) (Applause.) [Inaudible]
    s = re.sub(r"\((?:Laughter|Applause|Inaudible|Cheers|Crosstalk|Via interpreter|In Spanish|Off-mike)[^)]*\)\.?", "", s, flags=re.I)
    s = re.sub(r"\[[^\]]*\]", "", s)
    return " ".join(s.split())

def write_person(slug, person, docs):
    out = TDIR / slug; out.mkdir(parents=True, exist_ok=True)
    keep = set()
    for d in docs:
        (out / f"{d['id']}.txt").write_text("\n\n".join(d.pop("paras")) + "\n", encoding="utf-8"); keep.add(f"{d['id']}.txt")
    for f in out.glob("*.txt"):
        if f.name not in keep: f.unlink()
    idx = [{"id": d["id"], "file": f"{d['id']}.txt", "person": person, "url": d["url"], "type": d["type"], "title": d["title"],
            "date": d["date"], "location": d.get("location", ""), "source": d["source"], "note": d.get("note", ""),
            "fetched": dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")} for d in sorted(docs, key=lambda d: d["date"], reverse=True)]
    (out / "index.json").write_text(json.dumps(idx, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for d in idx:
        n = len((out / d["file"]).read_text().split())
        print(f"  {slug:9s} {d['date']} {d['type']:22s} {n:6d} words | {d['title'][:80]}")

# ------------------------------------------------------------------ cabinet
TREAS = "https://home.treasury.gov/news/press-releases/"
# Bessent: his full archive, discovered from Treasury's own press-release index (yearly JSON shards behind
# home.treasury.gov/news/press-releases). Kept: his speeches/remarks (as prepared for delivery) and his written
# testimony ("Statement ... Before the ... Committee"). Not kept: readouts, joint statements, interviews,
# travel notices and short press statements on votes/sanctions (not speeches).
BESSENT_SINCE = "2025-01-28"            # sworn in as the 79th Secretary of the Treasury
BESSENT_EXCLUDE = {"sb0511": "press release about his Reagan Forum speech (the remarks themselves are sb0514)",
                   "sb0197": "short press statement on the GENIUS Act, not a speech",
                   "sb0280": "written statement for the World Bank/IMF committees, not a speech or testimony",
                   "sb0095": "IMFC written statement", "sb0442": "IMFC written statement"}
BESSENT_WHO = re.compile(r"(?i)bessent|secretary of the treasury|treasury secretary")
BESSENT_NOT_HIM = re.compile(r"(?i)deputy|under secretary|assistant secretary|acting|former")
BESSENT_KIND = re.compile(r"(?i)\bremarks\b|statement (?:from|before)|\bstatement before\b|testimony|\baddress\b|\bdelivers\b|\bspeech\b|opening statement")
BESSENT_SKIP = re.compile(r"(?i)readout|joint statement|interview|icymi|to travel|statement by secretary|issues statement|statement from u\.s\. secretary of the treasury scott bessent (?:on|for)")

def bessent_list(refresh):
    """[(press-release id, date, title)] for every Bessent speech/testimony since he took office, oldest first."""
    man = json.loads(get("https://home.treasury.gov/news-data/press-releases/manifest.json", RAW / "treasury" / "manifest.json", True))
    out, seen = [], set()
    for sh in man.get("searchShards", []):
        if int(sh.get("endYear", 0)) < int(BESSENT_SINCE[:4]): continue
        cur = int(sh["endYear"]) >= dt.date.today().year            # current year's shard: always re-read
        items = json.loads(get("https://home.treasury.gov" + sh["path"], RAW / "treasury" / f"index-{sh['name']}.json", refresh or cur))["items"]
        for x in items:
            t, pid = x["title"], x["url"].rstrip("/").split("/")[-1]
            if x["date"] < BESSENT_SINCE or pid in seen or pid in BESSENT_EXCLUDE: continue
            if not BESSENT_WHO.search(t) or (BESSENT_NOT_HIM.search(t) and "bessent" not in t.lower()): continue
            if not BESSENT_KIND.search(t) or BESSENT_SKIP.search(t): continue
            seen.add(pid); out.append((pid, x["date"], clean(t)))
    return sorted(out, key=lambda r: r[1])
ST = "https://www.state.gov/releases/office-of-the-spokesman/"
RUBIO = [("munich-2026", ST + "2026/02/secretary-of-state-marco-rubio-at-the-munich-security-conference/", "speech"),
         ("caricom-2026", ST + "2026/02/secretary-of-state-marco-rubio-at-the-50th-regular-meeting-of-the-conference-of-caricom-heads-of-government/", "address"),
         ("sfrc-fy27", ST + "2026/06/secretary-of-state-marco-rubio-before-the-senate-foreign-relations-committee-on-the-fy27-department-of-state-budget-request/", "testimony"),
         ("hfac-fy27", ST + "2026/06/secretary-of-state-marco-rubio-before-the-house-foreign-affairs-committee-on-the-fy27-department-of-state-budget-request/", "testimony"),
         ("foundry-2026", ST + "2026/09/secretary-of-state-marco-rubio-at-the-trump-administrations-foundry-school-launch/", "remarks")]
SAC = "https://www.appropriations.senate.gov/download/"
LUTNICK = [("sac-fy27", SAC + "lutnick-testimony-fy27", "2026-04-22", "Senate Appropriations (CJS) hearing on the FY2027 Commerce budget request", "docx"),
           ("sac-broadband", SAC + "secretary-howard-lutnick-testimony-21026", "2026-02-10", "Senate Appropriations (CJS) hearing on broadband deployment funding", "pdf"),
           ("sac-fy26", SAC + "secretary-howard-lutnick-testimony", "2025-06-04", "Senate Appropriations (CJS) hearing on the FY2026 Commerce budget request", "pdf")]
HEGSETH = [("sasc-fy27", "https://www.armed-services.senate.gov/download/testimony/04/29/2026/hegseth-testimony", "2026-04-30",
            "Statement before the Senate Armed Services Committee on the FY2027 Department of War budget request", "testimony"),
           ("sasc-fy27-hearing", "https://www.armed-services.senate.gov/imo/media/doc/04-30-2026_transcript-full.pdf", "2026-04-30",
            "Senate Armed Services Committee hearing on the FY2027 budget (his spoken remarks)", "hearing remarks"),
           ("sac-fy26", SAC + "secretary-peter-b-hegseth-testimony", "2025-06-11",
            "Statement before Senate Appropriations (Defense) on the FY2026 budget request", "testimony")]

MARKER = re.compile(r"(?i)^\(?\s*(?:remarks )?as (?:prepared for delivery|prepared|delivered)\s*\)?[:.\s]*")
def treasury_doc(pid, date, refresh, title=None):
    raw = get(TREAS + pid + "/", RAW / "treasury" / f"{pid}.htm").decode("utf-8", "replace")   # pages are immutable
    title = title or clean(re.search(r"<title>(.*?)</title>", raw, re.S).group(1)).split(" | ")[0]
    i = raw.find("field--name-field-news-body")
    paras = [clean(p) for p in re.findall(r"(?s)<p[^>]*>(.*?)</p>", raw[i:])]
    out, n = [], 0
    for p in paras:
        if p.startswith("###"): break                  # end of the release
        if not p: continue
        n += 1
        m = MARKER.match(p)
        if m:
            if n <= 6: out = []                        # drop any staff-written lead before the marker
            p = p[m.end():].strip()
            if not p: continue
        p = re.sub(r"(?i)^(?:introductory|opening|closing) remarks:\s*", "", p)
        if not p or re.match(r"(?i)^(?:updated )?transcript of (?:the )?remarks", p): continue
        if p.startswith("WASHINGTON") or re.search(r"\b(?:Secretary|Treasury Secretary) (?:Scott )?(?:K\. ?H\. )?Bessent\b|\bBessent (?:said|delivered|announced|will)\b", p):
            continue                                   # third-person press-office text
        if not re.search(r"[.!?:;\u201d\"\u2019)\u2014\u2026-]$", p) and len(p.split()) <= 14:
            continue                                   # headings, title blocks, datelines
        p = drop_parens(p)
        if p: out.append(p)
    testimony = bool(re.search(r"(?i)statement (?:from .*)?before .*(committee|subcommittee)", title))
    return dict(id=pid, url=TREAS + pid + "/", type="testimony" if testimony else "speech", title=title, date=date,
                source="treasury.gov", paras=out,
                note="Written testimony (statement before the committee), U.S. Department of the Treasury" if testimony
                     else "Remarks as prepared for delivery, U.S. Department of the Treasury")

def dedupe(docs):
    """Drop a document whose sentences (>=85%) repeat an earlier-kept one: the same prepared statement given
    to a second committee, or the same speech posted twice. Each of his words is then counted once."""
    keep, sets = [], []
    for d in sorted(docs, key=lambda d: d["date"]):
        ss = {s.strip().lower() for p in d["paras"] for s in re.split(r"(?<=[.!?])\s+", p) if len(s.split()) >= 6}
        dup = next((k for k, t in zip(keep, sets) if ss and len(ss & t) / len(ss) >= 0.85), None)
        if dup: print(f"  DEDUPE bessent {d['id']} repeats {dup['id']}"); continue
        keep.append(d); sets.append(ss)
    return keep

LABEL_STATE = re.compile(r"^([A-Z][A-Z .'’\-]{2,40}):\s*")
def state_doc(sid, url, typ, refresh):
    raw = get(url, RAW / "state" / f"{sid}.htm").decode("utf-8", "replace")
    title = clean(re.search(r"<title>(.*?)</title>", raw, re.S).group(1)).split(" - United States Department of State")[0]
    paras = [clean(p) for p in re.findall(r"(?s)<p[^>]*>(.*?)</p>", raw[raw.find("Marco Rubio, Secretary of State"):])]
    di = next(i for i, p in enumerate(paras) if re.fullmatch(r"[A-Z][a-z]+ \d{1,2}, 20\d\d", p))
    date = dt.datetime.strptime(paras[di], "%B %d, %Y").strftime("%Y-%m-%d")
    loc = ", ".join(p for p in paras[1:di] if p)
    out, spk = [], None
    for p in paras[di + 1:]:
        if p == "Tags" or p.startswith("Facebook X"): break
        m = LABEL_STATE.match(p)
        if m: spk, p = m.group(1).strip(), p[m.end():]
        if spk == "SECRETARY RUBIO":
            p = drop_parens(p)
            if p: out.append(p)
    return dict(id=sid, url=url, type=typ, title=title, date=date, location=loc, source="state.gov", paras=out,
                note="U.S. Department of State transcript; only the Secretary's own words")

def pdf_text(path):
    return subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True).stdout

def statement_paras(text):
    """Prepared-statement PDF/docx text -> paragraphs. Drops the cover page (all-caps lines), page numbers,
    running headers (lines repeated on several pages), and standalone headings; joins paragraphs split by page breaks."""
    text = text.replace("\u00a0", " ").replace("\f", "\n\n")
    lines = [" ".join(l.split()) for l in text.split("\n")]
    rep = Counter(l for l in lines if l)
    chunks, cur = [], []
    for l in lines + [""]:
        if not l:
            if cur: chunks.append(cur); cur = []
            continue
        if re.fullmatch(r"\d{1,3}", l) or (rep[l] >= 3 and len(l.split()) < 12): continue
        if l.upper() == l and re.search(r"[A-Z]{3}", l): continue
        cur.append(l)
    END = re.compile(r"[.!?:”\"’)]$")
    paras, p = [], ""
    for ch in chunks:
        if not p and len(ch) <= 3 and not END.search(ch[-1]) and sum(len(x.split()) for x in ch) <= 20:
            continue                                                    # heading / title block
        for l in ch:
            if not p and len(l.split()) <= 6 and not END.search(l): continue   # heading line before a paragraph
            p = (p[:-1] + l) if p.endswith("-") and not p.endswith(" -") else (p + " " + l if p else l)
        if END.search(p): paras.append(p); p = ""
    if p: paras.append(p)
    out = []
    for p in paras:
        p = re.sub(r"^.*?(?=(?:Chairman|Chairwoman|Chair|Mr\. Chairman|Madam Chair) [A-Z])", "", p, count=1) if re.search(r"(?:Opening Statement|Subcommittee Hearing|Remarks as Prepared)", p[:300]) else p
        if len(p.split()) >= 6: out.append(drop_parens(p))
    return out

def lutnick_doc(lid, url, date, title, kind, refresh):
    raw_path = RAW / "cmte" / f"lutnick-{lid}.{kind}"
    get(url + "&download=1", raw_path)
    if kind == "docx":
        x = zipfile.ZipFile(raw_path).read("word/document.xml").decode()
        text = "\n\n".join(html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))) for p in re.findall(r"<w:p[ >].*?</w:p>", x, re.S))
    else:
        text = pdf_text(raw_path)
    paras = [p for p in statement_paras(text) if not re.match(r"(?i)(opening statement|remarks as prepared|united states secretary of commerce)", p)]
    return dict(id=lid, url=url, type="testimony", title="Prepared testimony: " + title, date=date, source="appropriations.senate.gov",
                paras=paras, note="Remarks as prepared, as posted by the committee")

SPK_T = re.compile(r"^((?:Chairman|Chairwoman|Chair|Senator|Secretary|General|Admiral|Mr\.|Ms\.|Mrs\.|Dr\.|Ranking Member) [A-Z][A-Za-z'\-]+):\s*")
def hearing_transcript_paras(text, who):
    lines = []
    for ln in text.split("\n"):
        m = re.match(r"^\s*(\d{1,2})\s{2,}(.*)$", ln)
        if not m: continue
        s = m.group(2).rstrip()
        lines.append(s)
    out, spk, cur = [], None, []
    def flush():
        if cur and spk == who:
            p = drop_parens(" ".join(cur))
            if p: out.append(p)
        cur.clear()
    for s in lines:
        t = s.strip()
        if not t: continue
        if t.upper() == t and re.search(r"[A-Z]{4}", t): flush(); continue   # section headings
        m = SPK_T.match(t)
        if m: flush(); spk = m.group(1); t = t[m.end():]
        elif s.startswith("    ") and cur: flush()                           # indented = new paragraph
        cur.append(t)
    flush()
    return out

def hegseth_doc(hid, url, date, title, typ, refresh):
    if typ == "hearing remarks":
        raw_path = RAW / "cmte" / f"hegseth-{hid}.pdf"; get(url, raw_path)
        text = subprocess.run(["pdftotext", "-layout", str(raw_path), "-"], capture_output=True, text=True).stdout
        paras = hearing_transcript_paras(text, "Secretary Hegseth")
        src, note = "armed-services.senate.gov", "Official hearing transcript; only the Secretary's own spoken turns"
    else:
        raw_path = RAW / "cmte" / f"hegseth-{hid}.pdf"; get(url + "&download=1", raw_path)
        paras = statement_paras(pdf_text(raw_path))
        src = url.split("/")[2].replace("www.", ""); note = "Prepared statement (record version), as posted by the committee"
    return dict(id=hid, url=url, type=typ, title=title, date=date, source=src, paras=paras, note=note)

def fetch_cabinet(args):
    plan = {"bessent": ("Scott Bessent", lambda: dedupe([treasury_doc(i, d, args.refresh, t) for i, d, t in bessent_list(args.refresh)])),
            "rubio": ("Marco Rubio", lambda: [state_doc(*r, args.refresh) for r in RUBIO]),
            "lutnick": ("Howard Lutnick", lambda: [lutnick_doc(*r, args.refresh) for r in LUTNICK]),
            "hegseth": ("Pete Hegseth", lambda: [hegseth_doc(*r, args.refresh) for r in HEGSETH])}
    for slug, (person, fn) in plan.items():
        if args.only not in (None, "cabinet", slug): continue
        if slug != "bessent" and (TDIR / slug / "index.json").exists() and not args.refresh: print(f"  {slug}: up to date"); continue
        lo = 150 if slug == "bessent" else 300         # Bessent: every speech, incl. short ceremonial remarks
        docs = [d for d in fn() if sum(len(p.split()) for p in d["paras"]) >= lo or print(f"  SKIP {slug} {d['id']}: too short")]
        write_person(slug, person, docs)

# ------------------------------------------------------------------ congress
LEADERS = {"johnson": ("Mike Johnson", "Speaker of the House", "Mr. JOHNSON of Louisiana", "House"),
           "jeffries": ("Hakeem S. Jeffries", "House Democratic Leader", "Mr. JEFFRIES", "House"),
           "thune": ("John Thune", "Senate Majority Leader", "Mr. THUNE", "Senate"),
           "schumer": ("Charles E. Schumer", "Senate Democratic Leader", "Mr. SCHUMER", "Senate")}
CREC_FROM, CREC_TO, CREC_MAX, CREC_MIN = dt.date(2026, 1, 3), dt.date(2026, 10, 1), 5, 250
SKIP_TITLE = re.compile(r"(?i)^(tribute|recogniz|remember|congratulat|commemorat|honoring|celebrat|additional statements|introductory statement|statements on|submitted resolutions|resolutions submitted|amendments submitted|executive calendar|orders? for|unanimous consent|measures|.*authority$|morning business|legislative session|executive session|cloture|adjournment|waiving|privileges of the floor|appointment|executive reports|nominations|messages|petitions|quorum|recess|schedule|calendar|prayer|pledge of allegiance|reservation of leader time|recognition of the|conclusion of|house of representatives|senate$|daily digest|program)")
LABEL_C = re.compile(r"^  ((?:Mr|Ms|Mrs|Miss|Dr)\. [A-Z][A-Z'\-]+(?: [A-Z][A-Z'\-]+)*(?: of [A-Z][a-z]+(?: [A-Z][a-z]+)*)?|The (?:ACTING |VICE )?(?:PRESIDENT|PRESIDING OFFICER|SPEAKER|CHAIR|CHAIRMAN|CLERK)(?: pro tempore)?)\.\s")
CLERKISH = re.compile(r"^(There (being|was) no objection|The (legislative|assistant|senior|bill|motion|resolution|amendment|question|yeas|clerk|Clerk|nomination|preamble|concurrent|joint|result|vote)|Thereupon|Accordingly|Pursuant to|Without objection|\(|\[)")

def crec_turns(raw, label):
    pre = html.unescape(re.search(r"(?s)<pre>(.*)</pre>", raw).group(1))
    pre = re.sub(r"<[^>]+>", "", pre)
    paras, cur = [], None
    for ln in pre.split("\n"):
        if re.match(r"^\[(Congressional Record|Senate|House|Page|\[Page)", ln.strip()) or ln.startswith("From the Congressional Record") or "{time}" in ln:
            continue
        if not ln.strip(): continue
        lead = len(ln) - len(ln.lstrip(" "))
        if lead >= 4: cur = None; continue                         # headings and inserted (printed) material
        if lead == 2: cur = [ln.strip()]; paras.append(cur)
        elif cur is not None: cur.append(ln.strip())
    out, spk = [], None
    for p in paras:
        t = " ".join(p); t = re.sub(r"(\w)-- ", r"\1--", t)
        t = re.sub(r"``\s*", "\u201c", t).replace("''", "\u201d")
        m = LABEL_C.match("  " + t)
        if m: spk = m.group(1); t = t[m.end() - 2:]
        elif CLERKISH.match(t): continue
        if spk == label and "<bullet>" not in t and not t.startswith("By "):
            t = drop_parens(t)
            if t: out.append(t)
    return out

def crec_mods(day):
    f = RAW / "crec" / f"CREC-{day}.mods.xml"; miss = f.with_suffix(".none")
    if miss.exists(): return None
    try: return get(f"https://www.govinfo.gov/metadata/pkg/CREC-{day}/mods.xml", f).decode("utf-8")
    except Exception: miss.parent.mkdir(parents=True, exist_ok=True); miss.write_text("none"); return None

def smart_title(t):
    t = html.unescape(t)
    t = re.sub(r"\s*\((executive session|legislative session)\)|--continued$", "", t, flags=re.I)
    small = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "with", "from"}
    t = t.replace("--", " -- ")
    ws = t.lower().split()
    out = " ".join(w if (i and w in small) else (w.upper() if re.fullmatch(r"(h\.r\.|s\.|u\.s\.|[ivx]+|fy\d+|ice|gop|nato|ai|agoa|ndaa|irs|va|dhs|fbi|cia|usda|snap)", w) else w[:1].upper() + w[1:]) for i, w in enumerate(ws))
    return re.sub(r" -- (\w)", lambda m: ": " + m.group(1).upper(), out)

def fetch_congress(args):
    todo = [k for k in LEADERS if args.only in (None, "congress", k) and (args.refresh or not (TDIR / k / "index.json").exists())]
    if not todo:
        if args.only in (None, "congress") or args.only in LEADERS: print("  congress: up to date")
        return
    days = []
    d = CREC_TO
    while d >= CREC_FROM:
        days.append(d); d -= dt.timedelta(days=1)
    mods = {}
    for day in days:
        m = crec_mods(day)
        if m: mods[day] = m
    for slug, (name, role, label, chamber) in LEADERS.items():
        if slug not in todo: continue
        docs = []
        for day in days:
            if day not in mods: continue
            for r in re.split(r'(?=<relatedItem type="constituent")', mods[day])[1:]:
                title = re.search(r"<title>(.*?)</title>", r, re.S).group(1)
                part = (re.search(r"<partName>(.*?)</partName>", r) or [None, ""])[1]
                spk = [n for n, role_ in re.findall(r'<name type="personal">\s*<namePart>(.*?)</namePart>.*?<roleTerm type="text">(.*?)</roleTerm>', r, re.S) if role_ == "speaking"]
                h = re.search(r'href="(https://www.govinfo.gov/content/pkg/[^"]+\.htm)"', r)
                if name not in spk or part != chamber or not h or SKIP_TITLE.match(html.unescape(title)): continue
                if any(x["date"] == str(day) for x in docs): continue        # at most one speech per day
                gid = h.group(1).rsplit("/", 1)[1][:-4]
                raw = get(h.group(1), RAW / "crec_htm" / f"{gid}.htm").decode("utf-8", "replace")
                paras = crec_turns(raw, label)
                if sum(len(p.split()) for p in paras) < CREC_MIN: continue
                if len(re.findall(r"unanimous consent", " ".join(paras), re.I)) >= 2: continue   # procedural (UC requests)
                docs.append(dict(id=gid, url=h.group(1), type="floor remarks", title=smart_title(title), date=str(day),
                                 location=f"{chamber} floor", source="govinfo.gov", paras=paras,
                                 note="Congressional Record (daily edition); only his own spoken remarks"))
                if len(docs) >= CREC_MAX: break
            if len(docs) >= CREC_MAX: break
        if docs: write_person(slug, name, docs)
        else: print(f"  SKIP {slug}: no floor remarks of >= {CREC_MIN} words between {CREC_FROM} and {CREC_TO}")

# ------------------------------------------------------------------ supreme court
JUSTICES = {"roberts": "John G. Roberts, Jr.", "thomas": "Clarence Thomas", "alito": "Samuel A. Alito, Jr.",
            "sotomayor": "Sonia Sotomayor", "kagan": "Elena Kagan", "gorsuch": "Neil M. Gorsuch",
            "kavanaugh": "Brett M. Kavanaugh", "barrett": "Amy Coney Barrett", "jackson": "Ketanji Brown Jackson"}
SC_TERM, SC_PER_JUSTICE, SC_MIN = "25", 3, 300
KIND_ID = {"opinion of the Court": "court", "plurality opinion": "plurality"}
KIND_NAME = {"court": "opinion of the Court", "plurality": "plurality opinion", "dissent": "dissent", "concurrence": "concurrence"}

def vocabulary():
    """Words seen in clean text elsewhere in the project, used only to choose fi vs fl for broken ligatures."""
    v = Counter()
    for f in list(TDIR.glob("*/*.txt")) + list((ROOT / "local_sources").glob("*/*.txt")):
        v.update(re.findall(r"[a-z]+", f.read_text(encoding="utf-8", errors="ignore").lower()))
    return v

def fix_word(w, vocab):
    """w contains '\x00' where a wide (ligature) f glyph lost its 'i' or 'l'."""
    if "\x00" not in w: return w
    a, b = w.replace("\x00", "i", 1), w.replace("\x00", "l", 1)
    a, b = fix_word(a, vocab), fix_word(b, vocab)
    return b if vocab[b.lower().strip(".,;:()“”\"'’[]-—")] > vocab[a.lower().strip(".,;:()“”\"'’[]-—")] else a

def opinion_sections(pdf_path, vocab):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    sizes = Counter()
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]: sizes[round(s["size"], 1)] += len(s["text"])
    body = sizes.most_common(1)[0][0]
    fwidth = defaultdict(list)
    pages = []
    for page in doc:
        H = page.rect.height; head, lines = [], []
        for b in page.get_text("rawdict")["blocks"]:
            for l in b.get("lines", []):
                spans = l["spans"]
                if not spans: continue
                n = Counter(); txt = ""
                for s in spans: n[round(s["size"], 1)] += len(s["chars"])
                dom = n.most_common(1)[0][0]
                y = l["bbox"][1]
                for s in spans:
                    if dom == body and round(s["size"], 1) < body - 1.2 and re.fullmatch(r"[\d*†‡§]+", "".join(c["c"] for c in s["chars"]).strip()):
                        continue                                  # footnote reference marks
                    for c in s["chars"]:
                        ch = c["c"]
                        if ch == "f":
                            w = c["bbox"][2] - c["bbox"][0]
                            if w > 0.45 * s["size"]: ch = "f\x00"      # ligature glyph (fi / fl) whose 2nd letter was lost
                        txt += ch
                txt = txt.replace("\u00ad", "\u00ad")
                rec = (y, l["bbox"][0], dom, txt)
                if y < 0.19 * H and dom != body or (y < 0.19 * H and re.fullmatch(r"\s*\d+\s*", txt)): head.append(rec)
                elif dom == body or abs(dom - body) < 0.6 or any(abs(round(s_["size"], 1) - body) < 0.6 and s_["chars"] and "".join(c["c"] for c in s_["chars"]).strip() for s_ in spans):
                    lines.append(rec)                             # body text (incl. lines mixing small caps)
        lines.sort(); head.sort()
        pages.append((" | ".join(h[3].strip() for h in head), lines))
    # keep pages whose running head marks an opinion (not the syllabus / cover); then split the stream at start sentences
    paras, cur = [], []
    for hd, lines in pages:
        h = hd.replace("\x00", "")
        if not re.search(r"(?i)opinion of the court|opinion of [A-Z][a-zA-Z]+, (?:C\. )?J\.|\b[A-Z][a-zA-Z]+, (?:C\. )?J\., (?:concurring|dissenting)", h):
            continue
        xs = [l[1] for l in lines] or [0]; left = min(xs)
        for y, x, dom, t in lines:
            t = t.strip()
            if not t or "Page Proof Pending Publication" in t or re.fullmatch(r"[*\s]+", t): continue
            letters = re.sub(r"[^A-Za-z]", "", t.replace("\x00", ""))
            if t in ("v.", "and") or re.fullmatch(r"(?:Nos?\. )?[\d–\-, and]+", t) or re.fullmatch(r"\[[^\]]*\]", t) or (len(letters) >= 3 and sum(c.isupper() for c in letters) >= 0.8 * len(letters)):
                if cur: paras.append(cur); cur = []
                continue                                          # captions, docket lines, dates between opinions
            if x > left + 6 and cur: paras.append(cur); cur = []
            cur.append(t)
    if cur: paras.append(cur)
    text_paras = []
    for p in paras:
        s_ = ""
        for t in p:
            if s_.endswith("\u00ad"): s_ = s_[:-1] + t
            elif s_.endswith("-") and not s_.endswith(" -"): s_ += t
            else: s_ = (s_ + " " + t) if s_ else t
        text_paras.append(s_)
    START = re.compile(r"^(?:Chief )?Justice ([A-Z][a-z]+)(?:, with whom [^.]*?,|,)? ?"
                       r"(delivered the opinion of the Court|announced the judgment of the Court|concurring|dissenting)[^.]*\.\s*", re.I)
    starts = [(i, m) for i, p in enumerate(text_paras) for m in [START.match(p.replace("\x00", ""))] if m]
    out = []
    for k, (i, m) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(text_paras)
        st = m.group(0).lower()
        kind = ("court" if "delivered the opinion" in st else "plurality" if "announced the judgment" in st
                else "dissent" if "dissenting" in st else "concurrence")
        first = text_paras[i].replace("\x00", "")[m.end():]
        body_paras = ([first] if first.strip() else []) + text_paras[i + 1:end]
        ps = []
        for p in body_paras:
            p = " ".join(fix_word(w, vocab) for w in p.split(" "))
            p = " ".join(p.split())
            while True:                                           # Court style "U. S." -> "U.S." (like other sources)
                q = re.sub(r"\b([A-Z])\. (?=[A-Z]\.)", r"\1.", p)
                if q == p: break
                p = q
            if p: ps.append(p)
        out.append(dict(kind=KIND_NAME.get(kind, kind), author=m.group(1).lower(), paras=ps))
    return out

def fetch_scotus(args):
    want = [j for j in JUSTICES if args.only in (None, "scotus", j)]
    if not want: return
    if all((TDIR / j / "index.json").exists() for j in want) and not args.refresh:
        print("  scotus: up to date"); return
    listing = get(f"https://www.supremecourt.gov/opinions/slipopinion/{SC_TERM}", RAW / "scotus" / f"slipopinion{SC_TERM}.htm").decode("utf-8", "replace")
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", listing, re.S):
        tds = [clean(t) for t in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        a = re.search(r"href='([^']+\.pdf)'", r)
        if a and len(tds) >= 6 and tds[4] not in ("PC", "D"):
            rows.append(dict(date=dt.datetime.strptime(tds[1], "%m/%d/%y").strftime("%Y-%m-%d"), docket=tds[2],
                             name=re.sub(r"\s*Revisions?\s*:.*$", "", tds[3]).strip(), pdf="https://www.supremecourt.gov" + a.group(1)))
    vocab = vocabulary()
    writings = defaultdict(list)
    for row in sorted(rows, key=lambda r: r["date"], reverse=True):
        path = RAW / "scotus" / row["pdf"].rsplit("/", 1)[1]
        get(row["pdf"], path)
        for sec in opinion_sections(path, vocab):
            n = sum(len(p.split()) for p in sec["paras"])
            if sec["author"] in JUSTICES and n >= SC_MIN:
                writings[sec["author"]].append(dict(row, **sec, n=n))
    for j in want:
        ws = writings[j][:SC_PER_JUSTICE]
        if not ws: print(f"  SKIP {j}: no writings found"); continue
        docs = [dict(id=f"{w['docket'].replace(' ', '')}-{KIND_ID.get(w['kind'], w['kind'])}", url=w["pdf"], type=w["kind"],
                     title=f"{w['name']} ({w['kind']})", date=w["date"], location=f"No. {w['docket']}", source="supremecourt.gov",
                     paras=w["paras"], note="Supreme Court opinion; syllabus, footnotes and headings excluded") for w in ws]
        write_person(j, JUSTICES[j], docs)

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only"); ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    for fn in (fetch_cabinet, fetch_congress, fetch_scotus):
        fn(args)

if __name__ == "__main__":
    main()
