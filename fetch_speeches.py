#!/usr/bin/env python3
"""Manual fetcher for speeches/texts of heads of state and religious leaders (not run by publish.sh).

  trump  U.S. President. Public domain (U.S. government works) -> transcripts/trump/ (committed, full text).
         Source: the Daily Compilation of Presidential Documents (DCPD) on govinfo.gov, the official
         U.S. government record of the President's remarks. (In 2026 whitehouse.gov posts videos and
         highlights, not full transcripts, except the 2025 Inaugural Address.) Only the President's
         words are kept: other speakers' turns, audience lines, [bracketed] notes, GPO subheadings
         (class "s1") and the closing NOTE/Categories block are removed; speaker labels are set in italics.
  leo    Pope Leo XIV. (c) Dicastery for Communication - Libreria Editrice Vaticana -> local_sources/leo/
         (gitignored, raw text never committed). build.py writes derived/leo.json (counts + limited excerpts).
         Source: vatican.va English texts. Kept: the text between the first "____" rule and the next rule
         (drops page headers, footnotes, and the "Summary of the Holy Father's words" read by others).

Polite: identifying User-Agent, ~1 request/second, only fetches documents not already saved.
Usage: python3 fetch_speeches.py [--only trump|leo] [--refresh]
"""
import argparse, html, json, re, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (X11; Linux x86_64) FedWords/1.0 (+https://github.com/JunkyProfit/fed-words)"
MIN_WORDS = 300

# DCPD package ids of recent major prepared addresses (see the DCPD collection on govinfo.gov).
TRUMP = [("DCPD-202600469", "address"),   # Address to the Nation on Election Reforms
         ("DCPD-202600443", "speech"),    # Remarks at an Independence Day Celebration
         ("DCPD-202600354", "address"),   # Commencement Address, U.S. Coast Guard Academy
         ("DCPD-202600220", "address"),   # Address to the Nation on U.S. Military Operations in Iran
         ("DCPD-202600136", "address")]   # Address Before a Joint Session of the Congress on the State of the Union
VAT = "https://www.vatican.va/content/leo-xiv/en/"
LEO = [("20260930-udienza-generale", VAT + "audiences/2026/documents/20260930-udienza-generale.html", "general audience"),
       ("20260927-francia-messa-lourdes", VAT + "homilies/2026/documents/20260927-francia-messa-lourdes.html", "homily"),
       ("20260926-francia-messa-parigi", VAT + "homilies/2026/documents/20260926-francia-messa-parigi.html", "homily"),
       ("20260925-francia-sede-unesco", VAT + "speeches/2026/september/documents/20260925-francia-sede-unesco.html", "address"),
       ("20260925-francia-autorita", VAT + "speeches/2026/september/documents/20260925-francia-autorita.html", "address")]

_last = [0.0]
def get(url):
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")

def lines_of(fragment):
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", fragment, flags=re.S)
    t = re.sub(r"</p>|<br\s*/?>|</h\d>|</div>|</li>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\u00a0", " ")
    return [" ".join(l.split()) for l in t.split("\n") if l.strip()]

def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp"); tmp.write_text(data, encoding="utf-8"); tmp.replace(path)

MONTHS = "January February March April May June July August September October November December".split()
def leo_extract(raw):
    i = raw.find('class="documento"'); seg = raw[i:]
    seg = seg[:seg.find("Copyright ©")] if "Copyright ©" in seg else seg
    L = lines_of(seg)
    rules = [k for k, l in enumerate(L) if re.fullmatch(r"_{5,}", l)]
    if not rules: raise ValueError("no ____ rule found; layout changed?")
    head = L[:rules[0]]
    body = L[rules[0] + 1: rules[1] if len(rules) > 1 else len(L)]
    title = " ".join(l for l in head if l.isupper() and not re.fullmatch(r"[A-Z]{2}|- [A-Z_]{2,5}", l))
    dline = next((l for l in head if re.search(r"\d{1,2} (%s) 20\d\d" % "|".join(MONTHS), l)), "")
    m = re.search(r"(\d{1,2}) (%s) (20\d\d)" % "|".join(MONTHS), dline)
    date = f"{m.group(3)}-{MONTHS.index(m.group(2)) + 1:02d}-{int(m.group(1)):02d}"
    loc = head[head.index(dline) - 1] if dline in head and head.index(dline) > 0 else ""
    out = []
    for l in body:
        if not re.search(r"[.!?,:;\u201d\"\u2019)\]]$", l) and len(l.split()) < 12:
            continue                                            # headings: "Special greetings", section titles
        l = re.sub(r"\[\d+\]", "", l)                         # footnote markers
        l = re.sub(r"\s*\((?:cf\.|Cf\.)[^)]*\)", "", l)        # (cf. ...) references
        l = re.sub(r"\s*\((?:[1-3] )?[A-Z][a-z]{0,3}\.? \d+:\d+[^)]*\)", "", l)   # (Jn 7:37) scripture refs
        out.append(" ".join(l.split()))
    return "\n\n".join(out) + "\n", date, loc

def fetch_leo(args):
    out = ROOT / "local_sources" / "leo"; (out / "raw").mkdir(parents=True, exist_ok=True)
    ipath = out / "index.json"
    index = {m["id"]: m for m in json.loads(ipath.read_text())} if ipath.exists() else {}
    for did, url, typ in LEO:
        if did in index and not args.refresh: continue
        raw = get(url); (out / "raw" / f"{did}.html").write_text(raw, encoding="utf-8")
        text, date, loc = leo_extract(raw)
        n = len(text.split())
        if n < MIN_WORDS: print(f"SKIP {did}: only {n} words"); continue
        t = re.search(r"<title>(.*?)</title>", raw, re.S)
        title = html.unescape(t.group(1)).split("|")[0].strip() if t else did
        title = re.sub(r"\s*\((?:[^()]*\d{4})\)$", "", re.sub(r"^Apostolic Journey to [^:]+:\s*", "", title))  # short title
        title = re.sub(r"\s+-\s+", ": ", title)
        atomic_write(out / f"{did}.txt", text)
        index[did] = {"id": did, "file": f"{did}.txt", "person": "Pope Leo XIV", "url": url, "type": typ,
                      "title": title, "date": date, "location": loc, "source": "vatican.va",
                      "note": "English text as published by the Holy See (vatican.va)",
                      "fetched": datetime.now().isoformat(timespec="seconds")}
        print(f"OK {did}: {date} {typ} {n} words | {title}")
    atomic_write(ipath, json.dumps(sorted(index.values(), key=lambda m: m["date"], reverse=True), indent=2, ensure_ascii=False) + "\n")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--only"); ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    if a.only in (None, "leo"): fetch_leo(a)
    if a.only in (None, "trump"): fetch_trump(a)

from html.parser import HTMLParser
class _Runs(HTMLParser):
    """Split a DCPD paragraph into (italic, text) runs. In class="s2" paragraphs the base style is italic and
    <span class="p"> is roman; elsewhere <i> is italic. GPO sets speaker labels ("The President.") in italics."""
    def __init__(self, base_italic):
        super().__init__(convert_charrefs=True); self.stack = [base_italic]; self.runs = []
    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "")
        self.stack.append(True if tag == "i" else False if (tag == "span" and cls == "p") else self.stack[-1])
    def handle_endtag(self, tag):
        if len(self.stack) > 1: self.stack.pop()
    def handle_data(self, d):
        if self.runs and self.runs[-1][0] == self.stack[-1]: self.runs[-1][1] += d
        else: self.runs.append([self.stack[-1], d])

def turns(attrs, inner):
    """[(speaker or None, text)] for one paragraph; speaker None = continues the previous speaker."""
    r = _Runs('class="s2"' in attrs); r.feed(inner); r.close()
    runs = [[it, t.replace("\u00a0", " ")] for it, t in r.runs]
    flat, depth = [], 0
    for it, t in runs:                                  # drop [bracketed] notes, which may span runs
        keep = ""
        for ch in t:
            if ch == "[": depth += 1
            elif ch == "]": depth = max(0, depth - 1)
            elif depth == 0: keep += ch
        flat.append([it, keep])
    out, cur, buf = [], None, ""
    for k, (it, t) in enumerate(flat):
        nxt = flat[k + 1][1] if k + 1 < len(flat) else ""
        lab = t.strip()
        at_start = not buf.strip() or re.search(r"[.!?\u201d\"')]\s*$", buf)   # labels begin a turn
        if it and at_start and lab and len(lab.split()) <= 8 and re.fullmatch(r"[A-Z][A-Za-z.,'\- ]*", lab) and \
                (lab.endswith(".") or nxt.lstrip().startswith(".")):
            if buf.strip(): out.append((cur, buf))
            cur, buf = lab.rstrip("."), ""
            if not lab.endswith("."): flat[k + 1][1] = nxt.lstrip()[1:]   # period was set in roman type
            continue
        buf += t
    if buf.strip(): out.append((cur, buf))
    return out

def trump_extract(raw):
    body = raw[raw.find("<body"):]
    paras = re.findall(r"<(p|h1)([^>]*)>(.*?)</\1>", body, re.S)
    title = next(html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for t, a, c in paras if t == "h1")
    plain = [" ".join(html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\u00a0", " ").split()) for _, _, c in paras]
    date = datetime.strptime(next(x for x in plain[:4] if re.fullmatch(r"[A-Z][a-z]+ \d{1,2}, 20\d\d", x)), "%B %d, %Y").strftime("%Y-%m-%d")
    loc = next((x[len("Locations:"):].strip().rstrip(".") for x in plain if x.startswith("Locations:")), "")
    start = next(i for i, (t, a, c) in enumerate(paras) if t == "h1") + 2       # after title + date
    speaker, out, labels = "The President", [], {}
    for (t, a, c), txt in zip(paras[start:], plain[start:]):
        if re.match(r"(NOTE|Categories|Locations|Names|Subjects|DCPD Number):", txt):
            break
        if 'class="s1"' in a:
            continue                                           # GPO-inserted subheadings (not spoken)
        kept = []
        for who, piece in turns(a, c):
            if who is not None:
                speaker = who; labels[who] = labels.get(who, 0) + 1
            if speaker == "The President":                     # other speakers / audience are dropped
                kept.append(" ".join(piece.split()))
        para = " ".join(x for x in kept if x)
        if para and out and not re.search(r"[.!?\"\u201d\u2019)\u2014:-]$", out[-1]):
            out[-1] += " " + para                              # paragraph split by a GPO page break
        elif para:
            out.append(para)
    return "\n\n".join(out) + "\n", title, date, loc, labels

def fetch_trump(args):
    out = ROOT / "transcripts" / "trump"; raw_dir = ROOT / "raw" / "dcpd"; raw_dir.mkdir(parents=True, exist_ok=True)
    ipath = out / "index.json"
    index = {m["id"]: m for m in json.loads(ipath.read_text())} if ipath.exists() else {}
    for pkg, typ in TRUMP:
        if pkg in index and not args.refresh: continue
        url = f"https://www.govinfo.gov/content/pkg/{pkg}/html/{pkg}.htm"
        raw = get(url); (raw_dir / f"{pkg}.htm").write_text(raw, encoding="utf-8")
        text, title, date, loc, labels = trump_extract(raw)
        n = len(text.split())
        if n < MIN_WORDS: print(f"SKIP {pkg}: only {n} words"); continue
        atomic_write(out / f"{pkg}.txt", text)
        index[pkg] = {"id": pkg, "file": f"{pkg}.txt", "person": "Donald J. Trump", "url": url, "type": typ,
                      "title": title, "date": date, "location": loc, "source": "govinfo.gov",
                      "note": "Daily Compilation of Presidential Documents",
                      "fetched": datetime.now().isoformat(timespec="seconds")}
        print(f"OK {pkg}: {date} {typ} {n} words | {title} | speakers seen: {labels}")
    atomic_write(ipath, json.dumps(sorted(index.values(), key=lambda m: m["date"], reverse=True), indent=2, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
