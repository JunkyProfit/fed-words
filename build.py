#!/usr/bin/env python3
"""Count every word each person said and write a single self-contained index.html.

People are listed in people.json.
  policy "full"    (Fed Chairman; public domain): full transcripts in transcripts/<slug>/ (fetch.py);
                    every sentence is embedded for the hover popover.
  policy "excerpt" (CEO letters; copyrighted): the full text lives ONLY in the gitignored
                    local_sources/<slug>/ (fetch_ceo.py). From it we write derived/<slug>.json,
                    which is committed: word counts plus a limited excerpt set (<= EXCERPT_BUDGET of
                    each letter's words; <= 10 excerpt sentences shown per word). If local_sources is
                    absent (e.g. another machine), build.py uses the committed derived/<slug>.json.

Usage: python3 build.py [--keep-numbers] [--top 10] [--split]
"""
import argparse, html, json, os, re, sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TDIR = ROOT / "transcripts"
LOCAL = ROOT / "local_sources"
DERIVED = ROOT / "derived"
DATA_DIR = ROOT / "data"
EXCERPT_BUDGET = 0.25        # max share of a letter's words that may be embedded as excerpts
SOURCE_TYPE = {"letter": "Shareholder letter", "remarks": "Earnings call prepared remarks"}   # CEO doc label
EXCERPTS_PER_WORD = 10       # max excerpt sentences listed per word per letter
SPLIT_BYTES = 1_500_000      # above this, per-person data goes to data/<slug>.json (loaded on demand)

# Contractions ending in 's that should NOT be treated as possessives.
S_CONTRACTIONS = {"it's", "that's", "there's", "here's", "what's", "let's", "he's",
                  "she's", "who's", "where's", "how's", "when's", "why's"}

STOPWORDS = set("""
a about above after again against all also am an and any are aren't as at be because been
before being below between both but by can can't cannot could couldn't did didn't do does
doesn't doing don't down during each even ever every few for from further had hadn't has
hasn't have haven't having he he'd he'll he's her here here's hers herself him himself his
how how's however i i'd i'll i'm i've if in into is isn't it it's its itself just let's
like many may me might more most much must mustn't my myself no nor not now of off on once
one only or other ought our ours ourselves out over own per rather same shall shan't she
she'd she'll she's should shouldn't since so some such than that that's the their theirs
them themselves then there there's these they they'd they'll they're they've this those
though through to too under until up upon us very was wasn't we we'd we'll we're we've
were weren't what what's when when's where where's whether which while who who's whom
whose why why's will with within without won't would wouldn't yet you you'd you'll you're
you've your yours yourself yourselves e.g. i.e.
""".split())

# Dotted initialisms (U.S., U.K., E.U., e.g., i.e.) are ONE token, normalized to a trailing
# dot: "U.S." / "U.S" / "U.S.'s" -> "u.s."; "U.S.-based" -> "u.s." + "based".
# Everything else: letters/digits with inner apostrophes; other punctuation splits words.
# (Keep in sync with TOK in the page JS below.)
TOKEN_RE = re.compile(r"[a-z](?:\.[a-z])+\.?(?:'s)?(?![a-z0-9])|[a-z0-9]+(?:'[a-z]+)*")

def norm_token(t):
    if "." in t:                               # dotted initialism
        if t.endswith("'s"):
            t = t[:-2]
        return t if t.endswith(".") else t + "."
    if t.endswith("'s") and t not in S_CONTRACTIONS:
        t = t[:-2]                             # possessive: fed's -> fed
    return t

def tokenize(text, keep_numbers=False):
    text = text.lower().replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")
    out = []
    for t in TOKEN_RE.findall(text):          # hyphens/dashes/punctuation split words
        t = norm_token(t)
        if not keep_numbers and t.isdigit():
            continue
        out.append(t)
    return out

# Words ending in "." that usually do NOT end a sentence.
ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "no", "nos", "vol", "pp", "p",
                 "inc", "corp", "co", "ltd", "gov", "sen", "rep", "gen", "rev", "fig", "ed", "eds",
                 "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
                 "approx", "est", "cf", "al"}
# Candidate break: sentence punctuation (+ closing quotes/brackets), whitespace, then a likely sentence start.
BREAK_RE = re.compile("[.!?][\"'\u201d\u2019)\\]]*\\s+(?=[\"'\u201c\u2018(\\[]*[A-Z0-9])")

def split_sentences(text, with_para=False):
    """Split into sentences. Breaks only at whitespace, so tokens are never cut and
    per-sentence token counts always add up to the whole-transcript count.
    with_para=True returns (paragraph_index, sentence) pairs."""
    out = []
    for pi, para in enumerate(re.split(r"\n\s*\n", text)):
        para = " ".join(para.split())
        start = 0
        for m in BREAK_RE.finditer(para):
            before = para[start:m.start() + 1]
            last = before.split()[-1] if before.split() else ""
            core = last.rstrip(".!?").lstrip("\"'(\u201c\u2018[")
            if m.group(0)[0] == "." and (
                core.lower() in ABBREVIATIONS                      # Mr. Dr. vol. Jan.
                or re.fullmatch(r"(?:[A-Za-z]\.)*[A-Za-z]", core)  # U.S. e.g. i.e. N. (initials)
                or (core == "" and before.endswith(". ."))):       # ". . ." ellipsis
                continue
            out.append((pi, para[start:m.end()].strip()))
            start = m.end()
        if para[start:].strip():
            out.append((pi, para[start:].strip()))
    return out if with_para else [s for _, s in out]

def write_if_changed(path, text):
    """Atomic write; leaves the file (and its mtime) untouched if content is identical."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)

def word_index(sent_toks, embed):
    """{word: [n, m, entries]}: n = occurrences, m = distinct sentences containing it,
    entries = embedded-sentence positions (one per occurrence) for <= EXCERPTS_PER_WORD sentences
    (all sentences when embed is None, i.e. full-text people)."""
    pos = {si: k for k, si in enumerate(sorted(embed))} if embed is not None else None
    idx = {}
    for si, toks in enumerate(sent_toks):
        c = Counter(toks)
        for w, k in c.items():
            e = idx.setdefault(w, [0, 0, []])
            e[0] += k; e[1] += 1
            if pos is None:
                e[2] += [si] * k
            elif si in pos and len(set(e[2])) < EXCERPTS_PER_WORD:
                e[2] += [pos[si]] * k
    return idx

def choose_excerpts(sent_toks, total_words):
    """Greedy: pick sentences that cover the most not-yet-covered content words per word of
    text, until EXCERPT_BUDGET of the letter's words is used. Deterministic."""
    budget = int(total_words * EXCERPT_BUDGET)
    chosen, covered, used = set(), set(), 0
    types = [set(t) - STOPWORDS for t in sent_toks]
    while True:
        best, best_score = None, 0.0
        for si, toks in enumerate(sent_toks):
            if si in chosen or not toks or used + len(toks) > budget:
                continue
            gain = len(types[si] - covered)
            score = gain / len(toks)
            if gain and score > best_score:
                best, best_score = si, score
        if best is None:
            return chosen
        chosen.add(best); covered |= types[best]; used += len(sent_toks[best])

def build_excerpt_derived(P, keep_numbers):
    """local_sources/<slug>/ (full text, never committed) -> derived/<slug>.json (committed)."""
    src = LOCAL / P["slug"]
    meta = json.loads((src / "index.json").read_text(encoding="utf-8"))
    docs = []
    for m in sorted(meta, key=lambda m: (m["date"], m["id"]), reverse=True):
        text = (src / m["file"]).read_text(encoding="utf-8")
        pairs = split_sentences(text, with_para=True)
        sents = [s for _, s in pairs]
        toks = [tokenize(s, keep_numbers) for s in sents]
        assert Counter(t for ts in toks for t in ts) == Counter(tokenize(text, keep_numbers)), m["file"]
        total = sum(len(t) for t in toks)
        emb = choose_excerpts(toks, total)
        idx = word_index(toks, emb)
        d = {k: m[k] for k in ("id", "date", "title", "url", "type", "source")}
        d.update({k: m[k] for k in ("location", "note") if m.get(k)})
        d["source_type"] = m.get("source_type") or SOURCE_TYPE.get(m["type"], m["type"].capitalize())
        d.update(words=total, n_sentences=len(sents),
                 excerpts=[sents[i] for i in sorted(emb)],
                 counts={w: e[0] for w, e in sorted(idx.items())},
                 msent={w: e[1] for w, e in sorted(idx.items())},
                 entries={w: e[2] for w, e in sorted(idx.items()) if e[2]})
        if m.get("para_pages"):
            d["pages"] = [m["para_pages"][pairs[i][0]] for i in sorted(emb)]
        docs.append(d)
    out = {"slug": P["slug"], "note": "Derived data only: word counts and a limited excerpt set. "
           "Full text is not included; see each document's url.", "keep_numbers": keep_numbers,
           "excerpt_budget": EXCERPT_BUDGET, "excerpts_per_word": EXCERPTS_PER_WORD, "docs": docs}
    write_if_changed(DERIVED / f"{P['slug']}.json", json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True) + "\n")

def load_person(P, keep_numbers):
    """Return a list of uniform doc dicts: meta + s (sentences shown) + sp (pages) + idx {w: [n, m, entries]}."""
    docs = []
    if P["policy"] == "full":
        if not (TDIR / P["slug"] / "index.json").exists():
            print(f"WARN: no transcripts for {P['slug']} (run fetch.py / fetch_speeches.py); skipped"); return []
        for m in json.loads((TDIR / P["slug"] / "index.json").read_text(encoding="utf-8")):
            path = TDIR / P["slug"] / m["file"]
            if not path.exists():
                print(f"WARN: {path} missing; skipped"); continue
            text = path.read_text(encoding="utf-8")
            sents = split_sentences(text)
            toks = [tokenize(s, keep_numbers) for s in sents]
            assert Counter(t for ts in toks for t in ts) == Counter(tokenize(text, keep_numbers)), m["file"]
            docs.append({"id": Path(m["file"]).stem, "date": m["date"], "type": m["type"], "title": m["title"],
                         "location": m.get("location", ""), "note": m.get("note", ""), "url": m["url"], "words": sum(map(len, toks)),
                         "n_sentences": len(sents), "s": sents, "sp": None, "idx": word_index(toks, None)})
    else:
        li = LOCAL / P["slug"] / "index.json"
        if li.exists() and json.loads(li.read_text(encoding="utf-8")):
            build_excerpt_derived(P, keep_numbers)          # refresh committed derived data from local text
        dpath = DERIVED / f"{P['slug']}.json"
        if not dpath.exists():
            print(f"WARN: no data for {P['slug']} (run fetch_ceo.py / fetch_speeches.py); skipped"); return []
        der = json.loads(dpath.read_text(encoding="utf-8"))
        if der.get("keep_numbers", False) != keep_numbers:
            print(f"WARN: derived/{P['slug']}.json was built with keep_numbers={der.get('keep_numbers')}")
        for d in der["docs"]:
            idx = {w: [n, d["msent"][w], d["entries"].get(w, [])] for w, n in d["counts"].items()}
            docs.append({"id": d["id"], "date": d["date"], "type": d["type"], "title": d["title"],
                         "location": d.get("location") or d["source"], "note": d.get("note", ""), "url": d["url"], "words": d["words"],
                         "stype": d.get("source_type") or SOURCE_TYPE.get(d["type"], ""),
                         "n_sentences": d["n_sentences"], "s": d["excerpts"], "sp": d.get("pages"), "idx": idx})
    docs.sort(key=lambda d: (d["date"], d["url"]), reverse=True)
    return docs

def load_people():
    """people.json plus the data-driven CEO list in ceos.json (adding a company there is enough)."""
    people = json.loads((ROOT / "people.json").read_text(encoding="utf-8"))
    cpath = ROOT / "ceos.json"
    if not cpath.exists(): return people
    cfg = json.loads(cpath.read_text(encoding="utf-8"))
    have = {p["slug"] for p in people}
    for p in people:
        if p["slug"] in cfg.get("existing_indices", {}): p["indices"] = cfg["existing_indices"][p["slug"]]
        if p["slug"] in cfg.get("existing_tickers", {}): p["ticker"] = cfg["existing_tickers"][p["slug"]]
    for c in cfg["companies"]:
        if c["slug"] in have: continue
        letter, filings = c["kind"] == "letter", c["kind"] == "filings"   # filings: past CEOs (fetch_ceo_filings.py), mixed doc types
        people.append({"slug": c["slug"], "name": c["name"], "display": c["name"], "category": "CEOs", "role": c["role"],
                       "org": c["org"], "policy": "excerpt", "source": c["source"], "mode": "ceo", "eyebrow": c.get("eyebrow") or "CEO · " + c["org"],
                       "doc_noun": "documents" if filings else "shareholder letters" if letter else "earnings call prepared remarks",
                       "doc_noun1": "document" if filings else "shareholder letter" if letter else "earnings call prepared remarks",
                       "unit": "document" if filings else "letter" if letter else "call",
                       "unit_pl": "documents" if filings else "letters" if letter else "calls",
                       "indices": c.get("indices", []), "ticker": c.get("ticker")})
    tvx = cfg.get("tv_exchange", {})
    for p in people:   # TradingView symbol for the price-chart popup (EXCHANGE:TICKER), only when the exchange is known
        if p.get("ticker") and tvx.get(p["ticker"]): p["tv"] = tvx[p["ticker"]] + ":" + p["ticker"]
    order = {s: i for i, s in enumerate(cfg.get("order", []))}
    ceos = sorted([p for p in people if p["category"] == "CEOs"], key=lambda p: order.get(p["slug"], 999))
    it = iter(ceos)
    return [next(it) if p["category"] == "CEOs" else p for p in people]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-numbers", action="store_true", help="count digit-only tokens like 2026")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--split", action="store_true", help="force per-person data files in data/")
    a = ap.parse_args()

    people_out, report = [], []
    for P in load_people():
        docs = load_person(P, a.keep_numbers)
        if not docs:
            continue
        total = Counter()
        for d in docs:
            total.update({w: e[0] for w, e in d["idx"].items()})
        rows = sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))
        vocab = [w for w, _ in rows]
        vidx = {w: i for i, w in enumerate(vocab)}
        jdocs = []
        for d in docs:
            x = []
            for w in sorted(d["idx"], key=vidx.get):
                n, m, ent = d["idx"][w]
                x += [vidx[w], n, m, len(ent)] + ent
            jd = {k: d[k] for k in ("id", "date", "type", "title", "location", "url", "words", "n_sentences")}
            jd.update(year=d["date"][:4], s=d["s"], x=x)
            if d.get("note"):
                jd["note"] = d["note"]
            if d.get("stype"):
                jd["stype"] = d["stype"]
            if d["sp"]:
                jd["sp"] = d["sp"]
            jdocs.append(jd)
        people_out.append({k: P[k] for k in ("slug", "name", "display", "category", "role", "org", "policy",
                                             "source", "doc_noun")}
                          | {k: P[k] for k in ("group", "mode", "eyebrow", "doc_noun1", "unit", "unit_pl", "credit", "indices", "ticker", "tv", "bio") if P.get(k)}
                          | {"vocab": vocab, "docs": jdocs})

        # ---- console report (all numbers come from here) ----
        ns = [(w, c) for w, c in rows if w not in STOPWORDS]
        print(f"== {P['display']} ({P['category']}; {P['policy']}): {len(docs)} document(s), "
              f"{docs[-1]['date']} to {docs[0]['date']}")
        for d in docs:
            dn = {w: e[0] for w, e in d["idx"].items() if w not in STOPWORDS}
            line = (f"  {d['date']} {d['type']:9s} {d['words']:5d} words {len(d['idx']):5d} unique | "
                    f"stopwords hidden: {sum(dn.values()):5d} words {len(dn):5d} unique | "
                    f"{d['n_sentences']:4d} sentences | {d['title']}")
            print(line)
            if P["policy"] == "excerpt":
                ew = sum(len(tokenize(s, a.keep_numbers)) for s in d["s"])
                cov = sum(1 for e in d["idx"].values() if e[2]) / len(d["idx"])
                print(f"      embedded excerpts: {len(d['s'])}/{d['n_sentences']} sentences "
                      f"({100 * len(d['s']) / d['n_sentences']:.1f}%), {ew}/{d['words']} words "
                      f"({100 * ew / d['words']:.1f}%); words with >=1 excerpt: {100 * cov:.1f}%")
                if len(d["s"]) > 0.5 * d["n_sentences"]:
                    sys.exit(f"ERROR: {d['id']} would embed {len(d['s'])}/{d['n_sentences']} sentences (>50%); "
                             f"lower EXCERPT_BUDGET / EXCERPTS_PER_WORD")
        for y in sorted({d["date"][:4] for d in docs}, reverse=True):
            yc = Counter()
            for d in docs:
                if d["date"][:4] == y:
                    yc.update({w: e[0] for w, e in d["idx"].items()})
            print(f"  Year {y}: {sum(yc.values())} words, {len(yc)} unique")
        print(f"  All: total words: {sum(total.values())}   Unique words: {len(total)}")
        print(f"  All, stopwords hidden: {sum(c for _, c in ns)} words, {len(ns)} unique")
        print(f"  Top {a.top} (all words): " + ", ".join(f"{w} {c}" for w, c in rows[:a.top]))
        print(f"  Top {a.top} (stopwords hidden): " + ", ".join(f"{w} {c}" for w, c in ns[:a.top]))

    import content
    content.compose_bios(people_out, STOPWORDS | S_CONTRACTIONS)
    common = {"stop": sorted(STOPWORDS), "sc": sorted(S_CONTRACTIONS), "keepNum": a.keep_numbers}
    def render(inline_people):
        data = dict(common, people=inline_people)
        return TEMPLATE.replace("__DEFAULT_FT__", '<span class="ft">From the mouth of</span>').replace("__LOGO__", (ROOT / "assets" / "logo-inline.svg").read_text(encoding="utf-8").strip()).replace("__DEFAULT_TITLE__", html.escape(people_out[0]["display"])).replace(
            "__NUMNOTE__", "included" if a.keep_numbers else "excluded").replace(
            "__DATA__", json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/"))
    page = render(people_out)
    split = a.split or len(page.encode("utf-8")) > SPLIT_BYTES
    if split:   # keep the first (default) person inline; load the others on demand
        inline = [people_out[0]]
        for p in people_out[1:]:
            write_if_changed(DATA_DIR / f"{p['slug']}.json", json.dumps(p, separators=(",", ":"), ensure_ascii=False) + "\n")
            inline.append({k: p[k] for k in p if k not in ("vocab", "docs")} | {"external": f"data/{p['slug']}.json",
                                                                               "ndocs": len(p["docs"])})
        page = render(inline)
        keep = {f"{p['slug']}.json" for p in people_out[1:]}
        for f in DATA_DIR.glob("*.json"):       # people no longer listed in people.json
            if f.name not in keep:
                f.unlink()
    else:       # remove stale generated per-person files from a previous split build
        for p in people_out:
            f = DATA_DIR / f"{p['slug']}.json"
            if f.exists():
                f.unlink()
        if DATA_DIR.exists() and not any(DATA_DIR.iterdir()):
            DATA_DIR.rmdir()
    write_if_changed(ROOT / "index.html", page)
    write_if_changed(ROOT / "privacy.html", PRIVACY)
    write_if_changed(ROOT / "contact.html", contact_page())
    write_if_changed(ROOT / "robots.txt", "User-agent: *\nAllow: /\n\nSitemap: https://mouthmath.com/sitemap.xml\n")
    lastmod = datetime.now().strftime("%Y-%m-%d")
    extra = content.build_all(people_out, STOPWORDS | S_CONTRACTIONS, PRIVACY, write_if_changed)
    write_if_changed(ROOT / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                     f'  <url><loc>https://mouthmath.com/</loc><lastmod>{lastmod}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>\n'
                     f'  <url><loc>https://mouthmath.com/contact.html</loc><lastmod>{lastmod}</lastmod><changefreq>yearly</changefreq><priority>0.4</priority></url>\n'
                     f'  <url><loc>https://mouthmath.com/privacy.html</loc><lastmod>{lastmod}</lastmod><changefreq>yearly</changefreq><priority>0.3</priority></url>\n'
                     + "".join(f'  <url><loc>https://mouthmath.com/{u}</loc><lastmod>{lastmod}</lastmod><changefreq>monthly</changefreq><priority>{"0.3" if u == "terms.html" else "0.6"}</priority></url>\n' for u in extra)
                     + '</urlset>\n')
    print(f"\nWrote {ROOT / 'index.html'} ({len(page.encode('utf-8')) / 1024:.0f} KB"
          f"{', per-person data in data/' if split else ', all data inline'})")


# ---- contact.html: same look as privacy.html, built from it (mm43) ----
def contact_page():
    head, rest = PRIVACY.split("<main>", 1)
    tail = rest.split("</main>", 1)[1]
    head = (head.replace("<title>Privacy Policy — MouthMath</title>", "<title>Contact — MouthMath</title>")
                .replace("https://mouthmath.com/privacy.html", "https://mouthmath.com/contact.html")
                .replace('content="Privacy Policy — MouthMath"', 'content="Contact — MouthMath"'))
    import re as _re
    head = _re.sub(r'<meta name="description" content="[^"]*">', '<meta name="description" content="Contact MouthMath: questions, corrections or ideas for speakers to add.">', head, 1)
    tail = tail.replace('<a href="contact.html">Contact</a> · <a href="privacy.html" aria-current="page">Privacy Policy</a>',
                        '<a href="contact.html" aria-current="page">Contact</a> · <a href="privacy.html">Privacy Policy</a>')
    head = _re.sub(r'<script async src="https://pagead2\.googlesyndication\.com/[^"]*" crossorigin="anonymous"></script>\n?', '', head)   # adsense-content: no ads on the form-only Contact page
    body = ('<main>\n<h1>Contact</h1>\n<p>Questions, corrections or a speaker you want counted? Send a message.</p>\n'
            '<form class="mmform" id="kform" action="https://api.web3forms.com/submit" method="POST"><input type="hidden" name="access_key" value="a7f0f3e1-21eb-42b6-af4b-7d083c91c1b4"><input type="hidden" name="subject" value="MouthMath contact page"><input type="hidden" name="from_name" value="MouthMath website"><input type="checkbox" name="botcheck" class="mmhp" tabindex="-1" autocomplete="off" aria-hidden="true"><label for="kformN">Name <span class="opt">(optional)</span></label><input id="kformN" name="name" autocomplete="name" maxlength="100"><label for="kformE">Email</label><input id="kformE" type="email" name="email" required autocomplete="email" maxlength="200" inputmode="email"><label for="kformM">Message</label><textarea id="kformM" name="message" required rows="5" maxlength="5000"></textarea><button type="submit">Send</button><p class="fmsg" role="status" aria-live="polite"></p></form>\n'
            '</main>')
    tail = tail.replace("document.getElementById('toTop').onclick", "(document.getElementById('toTop')||{}).onclick")
    return head + body + tail

# ---- privacy.html: static Privacy Policy page (same black / cream / Arial look); contact address assembled in JS ----
PRIVACY = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5930727143587260" crossorigin="anonymous"></script>
<link rel="icon" type="image/png" sizes="32x32" href="assets/favicon.png?v=mm205">
<link rel="icon" type="image/svg+xml" href="assets/favicon.svg?v=mm205">
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png?v=mm205">
<title>Privacy Policy — MouthMath</title>
<meta name="description" content="MouthMath privacy policy: no accounts or logins, no personal data collected by the site itself; Google AdSense cookies and personalized ads; TradingView chart embed.">
<link rel="canonical" href="https://mouthmath.com/privacy.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="MouthMath">
<meta property="og:title" content="Privacy Policy — MouthMath">
<meta property="og:url" content="https://mouthmath.com/privacy.html">
<meta property="og:image" content="https://mouthmath.com/assets/og-image.png?v=mm205">
<style>
:root{--ink:#f3eee4;--muted:#a49e93;--rule:#2c2a27;--red:#ff5449;color-scheme:dark}
*{box-sizing:border-box}
html,body{margin:0;background:#000;color:var(--ink);font-family:Arial,"Helvetica Neue",Helvetica,sans-serif}
body{font-size:16px;line-height:1.6;-webkit-text-size-adjust:100%}
a{color:var(--ink);text-decoration-color:rgba(243,238,228,.4);text-underline-offset:2px}
a:hover{color:var(--red);text-decoration-color:var(--red)}
a:focus-visible{outline:2px solid var(--red);outline-offset:2px;border-radius:2px}
header{border-bottom:1px solid var(--rule);padding:14px 20px}
header .in{max-width:780px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:16px}
header .logo{display:block;line-height:0}header .logo img{height:48px;width:auto;aspect-ratio:925/144;display:block}
header .back{font-size:15px;font-weight:700;white-space:nowrap}
main{max-width:780px;margin:0 auto;padding:28px 20px 40px}
h1{font-size:32px;line-height:1.15;letter-spacing:-.025em;margin:0 0 6px}
.upd{color:var(--muted);font-size:14px;margin:0 0 26px}
h2{font-size:20px;letter-spacing:-.015em;margin:30px 0 8px}
p,li{color:#e4dfd5}ul{padding-left:22px}li{margin:4px 0}
.sum{border:1px solid var(--rule);border-left:3px solid var(--red);border-radius:6px;padding:12px 16px;margin:0 0 8px;background:#0b0b0b}
.sum p{margin:0}
footer{border-top:1px solid var(--rule);color:var(--muted);font-size:14px;padding:18px 20px 28px;text-align:center}
footer a{color:var(--muted)}
.mmcopy{margin-top:8px;font:400 12px/1.4 Arial,Helvetica,sans-serif;color:#7d776d;text-align:center;letter-spacing:0}
@media (max-width:640px){header{padding:12px 16px}header .logo img{height:38px}main{padding:22px 16px 32px}h1{font-size:26px}h2{font-size:18px}body{font-size:15.5px}}
@media (max-width:420px){header .in{flex-wrap:wrap;row-gap:6px}}
.mmform{display:grid;gap:4px;max-width:520px;margin:6px 0 12px;font-family:Arial,Helvetica,sans-serif}.mmform label{font-size:13px;font-weight:700;color:#f3eee4;margin-top:6px}.mmform .opt{font-weight:400;color:var(--muted)}.mmform input:not([type=checkbox]),.mmform textarea{font:16px/1.35 Arial,Helvetica,sans-serif;color:#f3eee4;background:#0b0b0b;border:1px solid #3a3733;border-radius:6px;padding:9px 11px;width:100%;box-sizing:border-box}.mmform textarea{resize:vertical;min-height:96px}.mmform input:focus,.mmform textarea:focus{outline:2px solid #ff5449;outline-offset:1px;border-color:#ff5449}.mmform button{justify-self:start;margin-top:10px;min-height:44px;padding:0 24px;border:0;border-radius:8px;background:#ff5449;color:#fff;font:700 16px Arial,Helvetica,sans-serif;cursor:pointer}.mmform button:hover{background:#ff6b61}.mmform button:disabled{opacity:.6;cursor:default}.mmform button:focus-visible{outline:2px solid #fff;outline-offset:2px}.mmform .mmhp{position:absolute!important;left:-9999px!important;width:1px;height:1px;opacity:0}.mmform .fmsg{margin:6px 0 0;min-height:1.2em;font-size:14px;color:#f3eee4}.mmform .fmsg.ok{color:#85bb65}.mmform .fmsg.err{color:#ff5449}@media (max-width:640px){.mmform button{width:100%}}
/* mm33: Back to top (same as the main page's) */
.abtop{margin:28px 0 0}
.totop{display:inline-flex;align-items:center;gap:8px;min-height:44px;min-width:44px;padding:0 16px;font:700 15px/1 Arial,Helvetica,sans-serif;color:#f3eee4;background:transparent;border:1px solid #6f6a62;border-radius:4px;cursor:pointer;-webkit-tap-highlight-color:transparent;touch-action:manipulation}
.totop .tri{font-size:24px;line-height:0;color:#fff}.totop:hover{border-color:#f3eee4}.totop:active{background:rgba(243,238,228,.08)}.totop:focus-visible{outline:2px solid #fff;outline-offset:2px}
html body p.abtop{text-align:right!important;display:flex!important;justify-content:flex-end!important}
</style></head>
<body>
<header><div class="in"><a class="logo" href="./" aria-label="MouthMath home"><img src="assets/logo.svg?v=mm205" alt="MouthMath"></a><a class="back" href="./">&larr; Back to MouthMath</a></div></header>
<main>
<h1>Privacy Policy</h1>
<p class="upd">Last updated: October 4, 2026</p>
<div class="sum"><p><strong>In short:</strong> MouthMath (mouthmath.com) has no accounts, no login and no sign-up. The site itself does not collect,
store or sell personal data and does not set its own cookies; the only exception is what you choose to send through the contact form. Ads on the site are served by Google AdSense, and
Google and other third-party vendors may use cookies to show those ads, including personalized ads.</p></div>

<h2>Information the site collects</h2>
<p>None that identifies you. MouthMath is a static website: the word counts are computed in your browser, and your
choices (person, documents, view) are kept only in the page address so you can share a link. We don't use analytics,
tracking pixels, or our own cookies, and the site itself stores nothing in your browser (no cookies, local storage or similar). We don't ask for personal information except in the optional contact form.</p>
<h2>Contact form</h2>
<p>If you use the contact form (in About and below), the name (optional), email address and message you enter are sent to us through
<a href="https://web3forms.com/">Web3Forms</a>, a form-delivery service, which forwards them by email. We use them only to read and answer your message,
and we don't sell or share them. Web3Forms processes the submission under its <a href="https://web3forms.com/privacy">privacy policy</a>.</p>

<h2>Advertising and cookies (Google AdSense)</h2>
<p>MouthMath uses Google AdSense, an advertising service from Google, to show ads. When ads are shown:</p>
<ul>
<li>Third-party vendors, including Google, use cookies to serve ads based on your prior visits to this website or other websites.</li>
<li>Google's use of advertising cookies enables it and its partners to serve ads to you based on your visit to this site and/or other sites on the Internet.</li>
<li>Google and its partners may place and read cookies in your browser, or use web beacons, IP addresses and similar identifiers, to show ads,
measure them and prevent fraud. Your browser automatically sends Google information such as the address of the page you're viewing and your IP address.</li>
<li>Learn more in Google's
<a href="https://policies.google.com/technologies/partner-sites">How Google uses information from sites or apps that use our services</a>.</li>
</ul>
<p><strong>Personalized ads and your choices.</strong> You can opt out of personalized advertising from Google at
<a href="https://adssettings.google.com">Ads Settings (adssettings.google.com)</a>. If you opt out you'll still see ads, but they won't be
based on your interests or browsing history. You can also opt out of some other third-party vendors' use of cookies for personalized
advertising at <a href="https://www.aboutads.info/choices/">www.aboutads.info</a> (US) or
<a href="https://www.youronlinechoices.eu/">www.youronlinechoices.eu</a> (Europe), and you can block or delete cookies in your browser settings.</p>
<p>If ads from other ad networks or vendors are shown through AdSense, those vendors may also use cookies as described above; you can
opt out of their personalized advertising through the links above. Where the law requires it (for example in the European Economic Area,
the UK and Switzerland), cookies for personalized ads are only used with your consent, and you can change your choice at any time.</p>

<h2>TradingView stock charts</h2>
<p>On CEO pages, clicking a stock ticker opens a price chart embedded from <a href="https://www.tradingview.com/">TradingView</a>. The chart
is loaded only when you click, directly from TradingView's servers, so TradingView receives your IP address and browser information and may
set its own cookies. That is governed by the <a href="https://www.tradingview.com/privacy-policy/">TradingView Privacy Policy</a>.</p>

<h2>Other services</h2>
<ul>
<li><strong>Hosting:</strong> the site is hosted on GitHub Pages. Like any web host, GitHub may log technical information such as IP addresses
for security and operations; see the <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement">GitHub Privacy Statement</a>.</li>
<li><strong>Animated word cloud:</strong> when the Word Cloud first scrolls into view (unless your device asks for reduced motion), the p5.js library is loaded from the jsDelivr CDN (cdn.jsdelivr.net), which receives
standard request information such as your IP address; see the <a href="https://www.jsdelivr.com/terms/privacy-policy-jsdelivr-net">jsDelivr privacy policy</a>.</li>
<li><strong>Links to sources:</strong> links to official documents open the publisher's own website, which has its own privacy policy.</li>
</ul>

<h2>Children</h2>
<p>MouthMath is not directed to children under 13, and we don't knowingly collect personal information from children.</p>

<h2>Changes</h2>
<p>If this policy changes, the updated version will be posted on this page with a new "Last updated" date.</p>

<h2>Contact</h2>
<p>Questions about this policy? Send us a message:</p>
<form class="mmform" id="pform" action="https://api.web3forms.com/submit" method="POST"><input type="hidden" name="access_key" value="a7f0f3e1-21eb-42b6-af4b-7d083c91c1b4"><input type="hidden" name="subject" value="MouthMath privacy question"><input type="hidden" name="from_name" value="MouthMath website"><input type="checkbox" name="botcheck" class="mmhp" tabindex="-1" autocomplete="off" aria-hidden="true"><label for="pformN">Name <span class="opt">(optional)</span></label><input id="pformN" name="name" autocomplete="name" maxlength="100"><label for="pformE">Email</label><input id="pformE" type="email" name="email" required autocomplete="email" maxlength="200" inputmode="email"><label for="pformM">Message</label><textarea id="pformM" name="message" required rows="4" maxlength="5000"></textarea><button type="submit">Send</button><p class="fmsg" role="status" aria-live="polite"></p></form>
<p class="abtop"><button type="button" class="totop" id="toTop"><span class="tri" aria-hidden="true">&#9652;</span>Back to top</button></p>
</main>
<footer><a href="./">Home</a> · <a href="findings.html">Findings</a> · <a href="articles/">Articles</a> · <a href="contact.html">Contact</a> · <a href="privacy.html" aria-current="page">Privacy Policy</a> · <a href="terms.html">Terms of Use</a><div class="mmcopy">&copy; 2026 MouthMath</div></footer>
<script>document.querySelectorAll('form.mmform').forEach(f=>f.addEventListener('submit',async e=>{e.preventDefault();const m=f.querySelector('.fmsg'),b=f.querySelector('button');if(f.botcheck.checked)return;if(!f.reportValidity())return;b.disabled=true;m.className='fmsg';m.textContent='Sending…';try{const r=await fetch(f.action,{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(f)))});const j=await r.json().catch(()=>({}));if(r.ok&&j.success){f.reset();m.className='fmsg ok';m.textContent='Thanks! Your message was sent.'}else{m.className='fmsg err';m.textContent='Sorry, the message could not be sent'+(j.message?': '+j.message:'')+'. Please try again later.'}}catch(err){m.className='fmsg err';m.textContent='Sorry, the message could not be sent (network error). Please try again later.'}finally{b.disabled=false}}))</script>
<script>document.getElementById('toTop').onclick=()=>{scrollTo({top:0,left:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});const L=document.querySelector('header .logo');if(L)L.focus({preventScroll:true})}</script>
<script>document.querySelectorAll('a[href^="http"]').forEach(a=>{a.target='_blank';a.rel='noopener noreferrer'})</script>
</body></html>
"""

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5930727143587260" crossorigin="anonymous"></script>
<link rel="icon" type="image/png" sizes="32x32" href="assets/favicon.png?v=mm205">
<link rel="icon" type="image/svg+xml" href="assets/favicon.svg?v=mm205">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png?v=mm205">
<title>MouthMath — Word Counts from Fed Chairman Speeches &amp; CEO Earnings Calls</title>
<meta name="description" content="Word counts from Fed Chairman Kevin Warsh&#39;s speeches and testimony, CEO earnings calls and shareholder letters (JPMorgan&#39;s Jamie Dimon and more) and US government officials. See which words lead: inflation, interest rates, banks.">
<meta name="keywords" content="Federal Reserve, Fed Chairman, Kevin Warsh, Jerome Powell, Janet Yellen, Ben Bernanke, Alan Greenspan, FOMC, interest rates, inflation, monetary policy, banks, banking, CEO earnings calls, shareholder letters, JPMorgan, Jamie Dimon, US Treasury, Scott Bessent, Congress, Senate, Senators, Governors, Supreme Court, word frequency, word count, speech analysis, text analysis">
<link rel="canonical" href="https://mouthmath.com/">
<meta name="robots" content="index, follow">
<meta name="application-name" content="MouthMath">
<meta name="apple-mobile-web-app-title" content="MouthMath">
<meta property="og:type" content="website">
<meta property="og:site_name" content="MouthMath">
<meta property="og:title" content="MouthMath — Word Counts from Fed Chairman Speeches &amp; CEO Earnings Calls">
<meta property="og:description" content="Every word, counted: Fed Chairman speeches, CEO earnings calls and shareholder letters, and US government remarks, ranked by word frequency in Word Cloud and the sortable Mouth Math table.">
<meta property="og:url" content="https://mouthmath.com/">
<meta property="og:image" content="https://mouthmath.com/assets/og-image.png?v=mm205">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="MouthMath logo">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="MouthMath — Word Counts from Fed Chairman Speeches &amp; CEO Earnings Calls">
<meta name="twitter:description" content="Every word, counted: Fed Chairman speeches, CEO earnings calls and shareholder letters, and US government remarks, ranked by word frequency in Word Cloud and the sortable Mouth Math table.">
<meta name="twitter:image" content="https://mouthmath.com/assets/og-image.png?v=mm205">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"WebSite","@id":"https://mouthmath.com/#website","name":"MouthMath","url":"https://mouthmath.com/","inLanguage":"en","description":"Word counts from official Federal Reserve Chair speeches, CEO earnings calls and shareholder letters, and US government remarks."},{"@type":"WebApplication","@id":"https://mouthmath.com/#app","name":"MouthMath","url":"https://mouthmath.com/","applicationCategory":"ReferenceApplication","operatingSystem":"Any (web browser)","isAccessibleForFree":true,"offers":{"@type":"Offer","price":"0","priceCurrency":"USD"},"description":"Free word-frequency and speech analysis tool: pick a speaker and documents, then see every word counted and ranked in Word Cloud (words sized by count) or Mouth Math (a sortable ranked table), with the sentences behind each count.","isPartOf":{"@id":"https://mouthmath.com/#website"}},{"@type":"Dataset","@id":"https://mouthmath.com/#dataset","name":"MouthMath word counts","description":"Word frequency counts computed from official, publicly available texts: Federal Reserve Chair speeches and congressional testimony (federalreserve.gov), CEO earnings call prepared remarks and shareholder letters from company investor-relations sites, and remarks, testimony and opinions by US Cabinet secretaries, US senators, House leaders, state governors and Supreme Court Justices.","url":"https://mouthmath.com/","isAccessibleForFree":true,"keywords":["Federal Reserve","Fed Chairman","monetary policy","inflation","interest rates","banks","CEO earnings calls","shareholder letters","US government","word frequency","speech analysis"],"variableMeasured":"Word frequency (count of each word per selected speaker and documents)","creator":{"@type":"Organization","name":"MouthMath","url":"https://mouthmath.com/"}}]}</script>
<style>
:root{--num-red:#9e1b24;--bg:#f5f0e6;--card:#fffdf8;--ink:#2b2a26;--muted:#6e6658;--accent:#3f6250;--line:#e6dccb;--header:#4f6656;--green:#7fa98b;--sage:#9cc7ad;--green-soft:#edf5f0;--chip-on:#dcebdf;--chip-ink:#2f4f3b}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 Arial,"Helvetica Neue",Helvetica,sans-serif;background:var(--bg);color:var(--ink)}
html{scroll-behavior:smooth}
header{background:var(--header);color:#fff;padding:22px 28px;position:relative;box-shadow:inset 0 -4px 0 #b9d3bf}
header a.about-link{position:absolute;top:22px;right:28px;color:#fff;font-size:14px;opacity:.9;text-decoration:none;border:1px solid rgba(255,255,255,.5);border-radius:999px;padding:3px 12px}
header a.about-link:hover{opacity:1;background:rgba(255,255,255,.12)}
header .brand{display:flex;align-items:center;gap:18px;padding-right:90px}
header .logo{flex:none;display:block;background:var(--card);border-radius:10px;padding:7px 12px;box-shadow:0 1px 3px rgba(0,0,0,.25);line-height:0}
header .logo img{height:46px;width:auto;display:block}
header .titles{min-width:0}
@media (max-width:640px){header{padding:16px}header a.about-link{top:16px;right:16px}
 header .brand{flex-direction:column;align-items:flex-start;gap:10px;padding-right:0}
 header .logo img{height:38px}header h1{font-size:20px}}
#about{scroll-margin-top:16px}#about ul.sources{margin:0 0 10px;padding-left:20px;max-width:72ch}#about ul.sources li{margin:3px 0}#about h2{font-size:18px}#about p{margin:0 0 10px;max-width:72ch}
.notice{border:1px solid #e0b252;background:#fff8e6;border-left:5px solid #d99a1e;border-radius:8px;padding:10px 14px;margin-top:12px;max-width:72ch}
.notice strong{color:#7a4d00}header h1{margin:0;font-size:24px}header p{margin:4px 0 0;opacity:.85}
main{max-width:960px;margin:0 auto;padding:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin-bottom:16px}
h2{font-size:16px;margin:0 0 10px}.muted{color:var(--muted);font-size:13px}
.tf-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.tf-row .lbl{font-weight:700;font-size:13px;color:var(--muted);min-width:70px}
button.chip,label.chip{border:1px solid var(--line);background:var(--bg);border-radius:999px;padding:4px 12px;font:inherit;font-size:13px;cursor:pointer;display:inline-flex;gap:6px;align-items:center}
button.chip.on,label.chip.on{background:var(--chip-on);color:var(--chip-ink);border-color:var(--sage)}label.chip.on .muted{color:#47604f}
label.chip input{margin:0}
ul.speeches{list-style:none;margin:0;padding:0;font-size:14px}
ul.speeches li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:0 10px;align-items:start;padding:8px 8px;border-top:1px solid var(--line);border-radius:6px}
ul.speeches li.sel{background:var(--green-soft)}ul.speeches input{margin:3px 0 0}
.dl1{display:grid;grid-template-columns:7.4em minmax(0,1fr) auto;gap:2px 12px;align-items:baseline;cursor:pointer}
.dl1 .dt{font-weight:400;line-height:1.35}.dl1 .dw{color:var(--muted);font-size:13px;white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}
.dl2{margin:3px 0 0 calc(7.4em + 12px);font-size:12.5px;line-height:1.45}.dl2>*+*::before{content:"\00b7";display:inline-block;padding:0 6px;color:#b3a891;text-decoration:none}
.dl2 a{white-space:nowrap}
.dl2 .stype{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink,#111);border:1px solid var(--ink,#111);border-radius:3px;padding:0 5px;line-height:1.55;vertical-align:1px}
.dl2>.stype+*::before{padding-left:7px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
button.only{border:1px solid var(--line);background:var(--bg);color:var(--accent);border-radius:999px;font:inherit;font-size:12px;line-height:1.5;padding:0 9px;cursor:pointer}
button.only:hover{border-color:var(--sage)}
@media (max-width:600px){.dl1{grid-template-columns:minmax(0,1fr) auto}.dl1 .dw{grid-row:1;grid-column:2}.dl1 .dt{grid-column:1/-1}.dl2{margin-left:0}
 ul.speeches li{padding:8px 4px}}
.date{font-variant-numeric:tabular-nums;font-weight:700;white-space:nowrap}
#selSummary{margin-top:8px;font-size:14px}
.stats{display:flex;gap:14px;flex-wrap:wrap}.stat{flex:1;min-width:150px;background:var(--bg);border-radius:8px;padding:10px 14px}
.stat b{display:block;font-size:24px;color:var(--num-red)}
@media (max-width:640px){.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;padding:10px}.stat{min-width:0;padding:6px 6px;font-size:11.5px;line-height:1.25}
 .stat b{font-size:17px}}
.controls{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
input[type=search]{flex:1;min-width:220px;padding:9px 12px;border:1px solid var(--line);border-radius:8px;font-size:15px}
input[type=search]:focus{outline:none;border-color:var(--sage);box-shadow:0 0 0 3px rgba(127,169,139,.25)}
input[type=checkbox]{accent-color:#6b9477}:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}
th{cursor:pointer;user-select:none;background:var(--bg);position:sticky;top:0;border-bottom-color:var(--sage)}th:hover{color:var(--accent)}
td.num,th.num{text-align:right}.bar{height:8px;background:#a9c9b2;border-radius:4px}
tr.stop td.w{color:var(--muted)}td.cnt{color:var(--num-red);font-weight:700} /* word-count numbers: one variable, easy to revert */
tr[data-w]{cursor:help}tr[data-w]:hover td{background:#f0f7f2}tr.active td{background:#e2f0e7}
#pop{position:absolute;z-index:50;background:var(--card);border:1px solid #d9cdb6;border-radius:10px;box-shadow:0 10px 30px rgba(60,45,20,.18);
 padding:10px 12px;font-size:12px;max-height:60vh;overflow:auto;line-height:1.4}
#pop[hidden]{display:none}#pop.expanded{max-height:75vh}
#pop .ph{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;position:sticky;top:-10px;background:var(--card);padding:2px 0 6px;border-bottom:1px solid var(--line);margin-bottom:5px}
#pop .ph .t{font-size:11px;color:var(--muted)}#pop .ph b{font-size:13.5px;color:var(--ink)}
#pop .x{border:0;background:none;font-size:20px;line-height:1;cursor:pointer;color:var(--muted)}
#pop .doc{margin:8px 0 3px;font-size:9.5px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
#pop ol{margin:0;padding-left:18px}#pop li{margin:4px 0}
#pop mark{background:#ffe27a;padding:0 1px;border-radius:2px}
#pop .src{font-size:10.5px;margin-left:5px;white-space:nowrap}#pop .twice{font-size:10px;color:#8a5a00;background:#fff3cd;border-radius:4px;padding:0 4px;margin-left:4px}
#pop .more{margin-top:8px;border:1px solid var(--accent);color:var(--accent);background:var(--card);border-radius:8px;padding:5px 10px;cursor:pointer;font:inherit;font-size:11.5px}
#pop .hint{font-size:10.5px;color:var(--muted);margin-top:6px}a{color:var(--accent)}.empty{padding:20px;text-align:center;color:var(--muted)}
#picker .tf-row:last-of-type{margin-bottom:4px}#personInfo{margin-top:2px}
body.mode-ceo header{background:#6a5f4e;box-shadow:inset 0 -4px 0 #d8c8a4}
#personInfo .eyebrow{display:inline-block;font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;background:var(--chip-on);color:var(--chip-ink);border-radius:999px;padding:1px 10px;margin:2px 6px 2px 0;vertical-align:1px}
#words h1#personTitle{margin:0 0 10px;font-size:18px}
header p#siteSub{max-width:640px}
.seg{display:inline-flex;gap:4px;background:#efe7d8;border:1px solid #d9cdb6;border-radius:12px;padding:4px;margin:0 0 12px}
.seg button{border:0;background:transparent;color:#5c5548;font:inherit;font-size:15px;font-weight:700;padding:7px 22px;border-radius:9px;cursor:pointer}
.seg button:hover{color:var(--ink);background:rgba(255,253,248,.6)}
.seg button.on{background:var(--chip-on);color:var(--chip-ink);box-shadow:inset 0 0 0 2px var(--accent),0 1px 2px rgba(60,45,20,.15)}.seg button.on::before{content:"\2713\00a0"}
#persons button.chip.on{font-weight:700;box-shadow:inset 0 0 0 1px var(--accent)}
body.mode-cab header{background:#56604a;box-shadow:inset 0 -4px 0 #c9d0b5}
body.mode-cong header{background:#6b5148;box-shadow:inset 0 -4px 0 #d9bfb3}
body.mode-scotus header{background:#3f4a45;box-shadow:inset 0 -4px 0 #c2cbc5}
body.mode-gov header{background:#5b5040;box-shadow:inset 0 -4px 0 #d6c7ab}
.only-fed,.only-ceo,.only-cab,.only-cong,.only-scotus,.only-gov{display:none}
body.mode-fed .only-fed,body.mode-ceo .only-ceo,body.mode-cab .only-cab,body.mode-cong .only-cong,body.mode-scotus .only-scotus,body.mode-gov .only-gov{display:inline}
#cats{flex-wrap:wrap}#pop .credit{font-size:10px;color:var(--muted);margin-top:4px}
#pop .cap{font-size:10.5px;color:var(--muted);margin-top:6px;padding-top:5px;border-top:1px dashed var(--line)}
.viewbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 14px}
.viewbar .lbl{font-weight:700;font-size:13px;color:var(--muted)}
.vcards{display:flex;gap:10px}
.vcard{position:relative;display:flex;align-items:center;gap:10px;width:200px;padding:7px 12px 7px 8px;border:1px solid #d9cdb6;border-radius:12px;
 background:var(--card);color:var(--ink);font:inherit;text-align:left;cursor:pointer;transition:border-color .12s,background-color .12s,box-shadow .12s}
.vcard svg{flex:none;width:76px;height:50px;display:block}
.vcard .vt{display:flex;flex-direction:column;line-height:1.2;min-width:0}.vcard .vt b{font-size:15px}.vcard .vt small{font-size:12px;color:var(--muted)}
.vcard:hover{border-color:var(--sage);background:#fbf8f0}
.vcard[aria-pressed="true"]{background:var(--chip-on);border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent),0 1px 3px rgba(60,45,20,.15)}
.vcard[aria-pressed="true"] .vt b{color:var(--chip-ink)}.vcard[aria-pressed="true"] .vt small{color:#47604f}
.vcard[aria-pressed="true"]::after{content:"\2713";position:absolute;top:-7px;right:-7px;width:20px;height:20px;border-radius:50%;background:var(--accent);color:#fff;
 font-size:12px;font-weight:700;line-height:20px;text-align:center;box-shadow:0 0 0 2px var(--bg)}
@media (max-width:640px){.viewbar{gap:6px 10px}.viewbar .lbl{width:100%}#viewHint{display:none}.vcards{width:100%}
 .vcard{flex:1;width:auto;gap:8px;padding:6px 8px 6px 6px}.vcard svg{width:58px;height:40px}.vcard .vt b{font-size:14px}.vcard .vt small{font-size:11.5px}}
.topgrid{display:block}
@media (min-width:900px){.topgrid{display:grid;grid-template-columns:1.2fr 1fr;gap:16px;align-items:start}}
#cats button{font-size:14px;padding:6px 14px}#picker .seg{margin-bottom:10px}
#persons.grouped{display:block}#persons .pg{display:flex;gap:6px 8px;flex-wrap:wrap;align-items:center;padding:6px 0;border-top:1px dashed var(--line)}
#persons .pg:first-child{border-top:0;padding-top:0}#persons .pg .lbl{min-width:96px}
#timeframe .tf-row{margin-bottom:8px}
#timeframe .tf-years{flex-wrap:nowrap;align-items:center}
#timeframe .tf-row .lbl{min-width:52px}#years label.chip{padding:4px 10px}
@media (min-width:900px){#timeframe .tf-years{flex-direction:column;align-items:stretch;gap:5px}.yrs{gap:5px}}
.yrs{display:flex;flex-wrap:nowrap;gap:6px;overflow-x:auto;min-width:0;scrollbar-width:thin;padding-bottom:1px}
.yrs>*{flex:none}
#docPick{margin-top:8px;border-top:1px solid var(--line);padding-top:8px}
#docPick>summary{cursor:pointer;font-weight:700;font-size:14px;color:var(--accent);list-style:none;display:inline-flex;align-items:center;gap:6px;padding:3px 0}
#docPick>summary::-webkit-details-marker{display:none}
#docPick>summary::before{content:"";width:7px;height:7px;border-right:2px solid currentColor;border-bottom:2px solid currentColor;transform:rotate(-45deg);transition:transform .15s;margin:0 3px 0 1px}
#docPick[open]>summary::before{transform:rotate(45deg)}#docPick>summary .muted{font-weight:400}
#docPick .hint{margin:4px 0 6px}
#timeframe{container-type:inline-size}
@container (max-width:520px){.dl1{grid-template-columns:minmax(0,1fr) auto}.dl1 .dw{grid-row:1;grid-column:2}.dl1 .dt{grid-column:1/-1}.dl2{margin-left:0}ul.speeches li{padding:8px 4px}}
/* Wide screens (both views): Who + Timeframe in a sidebar; beside it the words card = person name, red stats, then table/cloud */
@media (min-width:900px){
 body main{display:grid;grid-template-columns:300px minmax(0,1fr);column-gap:16px;max-width:1280px;align-items:start}
 body main>*{grid-column:1/-1}
 body .topgrid{grid-column:1;grid-row:1/span 2;display:block}
 body #words{grid-column:2;grid-row:1/span 2}
 body .stat{min-width:110px}}
@media (min-width:1100px){body main{grid-template-columns:340px minmax(0,1fr)}}
/* Word Cloud, narrow screens: results right after the compact Who + Timeframe area; stats and filters below the cloud */
@media (max-width:899px){
 body.view-visual main{display:flex;flex-direction:column}body.view-visual main>*{order:2}
 body.view-visual .viewbar,body.view-visual .topgrid{order:0}body.view-visual #words{order:1}}
@media (max-width:640px){
 header{padding:12px 14px}header a.about-link{top:12px;right:14px;font-size:13px;padding:2px 10px}header .brand{gap:8px}
 header .logo{padding:5px 9px}header .logo img{height:28px}header h1{font-size:19px}header p#siteSub{font-size:13px;line-height:1.35}
 main{padding:12px}.card{padding:12px 14px;margin-bottom:10px}h2{font-size:15px;margin-bottom:8px}
 .viewbar{margin-bottom:10px}.viewbar .lbl{display:none}
 #cats,#persons:not(.grouped),#persons .pg{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;margin-right:-14px;padding-right:14px;
  -webkit-mask-image:linear-gradient(90deg,#000 88%,transparent);mask-image:linear-gradient(90deg,#000 88%,transparent)}
 #cats::-webkit-scrollbar,#persons::-webkit-scrollbar,#persons .pg::-webkit-scrollbar{display:none}
 #persons.grouped{overflow:visible;margin-right:0;padding-right:0;-webkit-mask-image:none;mask-image:none}
 #persons .pg .lbl{position:sticky;left:0;z-index:1;width:auto;height:auto;clip:auto;overflow:visible;min-width:0;flex:none;font-size:12px;
  background:var(--card);padding:4px 6px 4px 0;box-shadow:6px 0 6px -2px var(--card)}
 #timeframe h2{float:left;margin:5px 12px 0 0}#timeframe .tf-row .lbl{display:none}#selSummary{clear:both;font-size:13.5px}
 body.view-visual #personInfo{display:none}body.view-visual #persons{margin-bottom:0}
 #cats{display:flex;background:none;border:0;padding:0;gap:6px;margin-bottom:8px}
 #cats button{flex:none;font-size:13.5px;padding:5px 12px;border:1px solid #d9cdb6;background:#efe7d8}
 #persons{margin-bottom:6px}#persons .chip{flex:none}#persons .lbl{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
 #personInfo{font-size:12.5px;line-height:1.4}#timeframe .tf-row .lbl{min-width:0}
 #words h1#personTitle{font-size:16px}
 body.view-visual #words{display:flex;flex-direction:column}body.view-visual #words>*{order:2}
 body.view-visual #personTitle{order:0}body.view-visual #words>.only-visual{order:1;display:flex;flex-direction:column}
 body.view-visual #cloud{order:0}body.view-visual .cloud-bar{order:2;margin-top:6px}body.view-visual #words .controls{margin:8px 0 0}}
/* (stacked layout: Mouth Math and Word Cloud are both always shown) */
.cloud-bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:2px 0 6px;font-size:14px}
.cloud-bar select{font:inherit;font-size:14px;padding:3px 6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
#cloud{position:relative;width:100%;min-height:120px;overflow:hidden;margin:4px 0 2px}
#cloud span{position:absolute;white-space:nowrap;cursor:help;border-radius:5px;letter-spacing:-.01em;transition:background-color .12s}
#cloud span:hover,#cloud span.active{background:#e2f0e7}#cloud .empty{position:static}


#cloud canvas.cloudcv{position:absolute;left:0;top:0;pointer-events:none;z-index:0}
#cloud.live span{color:transparent!important;background:transparent!important;font-size:0!important;padding:0!important;z-index:1}
#cloud.live span:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
/* ---- Black line-art theme (matches the logo's thin black strokes); delete this block to revert ---- */
:root{--ink:#141413;--cream:#f5efe2;--rule:#1c1b19;--hl:#ece3cf;--ink:#141413}
body{color:var(--ink)}a{color:var(--ink);text-decoration-color:rgba(20,20,19,.45);text-underline-offset:2px}a:hover{text-decoration-color:var(--ink)}
body[class] header{background:var(--ink);color:var(--cream)}
body.mode-fed header{box-shadow:inset 0 -3px 0 #9cc7ad}body.mode-ceo header{box-shadow:inset 0 -3px 0 #d8c8a4}
body.mode-cab header{box-shadow:inset 0 -3px 0 #c9d0b5}body.mode-cong header{box-shadow:inset 0 -3px 0 #d9bfb3}body.mode-scotus header{box-shadow:inset 0 -3px 0 #c2cbc5}body.mode-gov header{box-shadow:inset 0 -3px 0 #d6c7ab}
header a.about-link{color:var(--cream);border-color:rgba(245,239,226,.55)}header a.about-link:hover{background:rgba(245,239,226,.1)}
header p{opacity:.82}header .logo{box-shadow:0 0 0 1px rgba(245,239,226,.25)}
.card{border:1px solid var(--rule);box-shadow:none}h2{color:var(--ink)}
.viewbar .lbl,.tf-row .lbl{color:var(--ink)}
.vcard{border:1px solid var(--rule);background:var(--card)}.vcard:hover{background:#fbf7ee;border-color:var(--rule)}
.vcard[aria-pressed="true"]{background:var(--ink);border-color:var(--ink);box-shadow:0 1px 3px rgba(20,20,19,.25)}
.vcard[aria-pressed="true"] .vt b{color:var(--cream)}.vcard[aria-pressed="true"] .vt small{color:#d9d2c3}
.vcard[aria-pressed="true"]::after{background:var(--num-red);box-shadow:0 0 0 2px var(--bg)}
.seg,#cats{background:transparent;border:1px solid var(--rule)}.seg button{color:var(--ink)}
.seg button:hover{background:#efe7d8}
.seg button.on{background:var(--ink);color:var(--cream);box-shadow:none}
button.chip,label.chip{border:1px solid var(--rule);background:var(--card);color:var(--ink)}
button.chip:hover,label.chip:hover{background:#efe7d8}
button.chip.on,label.chip.on{background:var(--ink);color:var(--cream);border-color:var(--ink)}label.chip.on .muted{color:#d9d2c3}
#persons button.chip.on{box-shadow:none}
label.chip.on input{accent-color:var(--cream)}
#persons .pg{border-top:1px solid rgba(20,20,19,.16)}
#personInfo .eyebrow{background:transparent;color:var(--ink);border:1px solid var(--rule)}
#docPick{border-top:1px solid var(--rule)}#docPick>summary{color:var(--ink)}
ul.speeches li{border-top:1px solid rgba(20,20,19,.16)}ul.speeches li.sel{background:#f3ecdc}
button.only{border-color:var(--rule);color:var(--ink);background:var(--card)}button.only:hover{background:var(--ink);color:var(--cream)}
input[type=checkbox]{accent-color:var(--ink)}
.stat{background:var(--card);border:1px solid var(--rule)}
input[type=search]{border:1px solid var(--rule)}input[type=search]:focus{border-color:var(--ink);box-shadow:0 0 0 3px rgba(20,20,19,.12)}
th{border-bottom:1px solid var(--rule);color:var(--ink)}td{border-bottom-color:rgba(20,20,19,.12)}
.bar{background:#2b2a26;opacity:.82}
tr[data-w]:hover td{background:#f6efe0}tr.active td{background:var(--hl)}
#cloud span:hover,#cloud span.active{background:var(--hl)}
#pop{border:1px solid var(--rule);box-shadow:0 10px 30px rgba(20,20,19,.18)}#pop .ph{border-bottom:1px solid var(--rule)}
#pop .more{border-color:var(--ink);color:var(--ink)}#pop .more:hover{background:var(--ink);color:var(--cream)}

:focus-visible{outline-color:var(--ink)}
@media (max-width:640px){#cats{border:0}#cats button{border:1px solid var(--rule);background:var(--card);padding:5px 11px;font-size:13px}#cats button.on{background:var(--ink);color:var(--cream)}}
/* ---- A-Z last-name index (CEOs, US Government) ---- */
#picker{container-type:inline-size}
.pk.has-az{display:grid;grid-template-columns:minmax(0,1fr) auto;column-gap:12px;align-items:start}
@media (min-width:900px){.pk.has-az #persons .pg{display:block}.pk.has-az #persons .pg .lbl{display:block;margin:0 0 4px}.pk.has-az #persons .pg .chip{margin:0 4px 5px 0}
 .pk.has-az #persons:not(.grouped) .chip{margin:0 0 2px}}
.pk.has-az>*{grid-column:1/-1}.pk.has-az>#persons{grid-column:1;grid-row:3}.pk.has-az>#az{grid-column:2;grid-row:3;align-self:start}
@media (min-width:900px){#picker #cats button{padding:6px 11px;font-size:13.5px}}
@media (min-width:1100px){#picker #cats{display:flex;flex-wrap:nowrap}#picker #cats button{flex:auto;padding:6px 7px;white-space:nowrap}}
#az{display:grid;grid-template-columns:repeat(2,22px);gap:2px 3px;padding-left:10px;border-left:1px solid var(--rule)}
#az button{font:inherit;font-size:12px;font-weight:700;height:20px;line-height:1;padding:0;border:1px solid transparent;border-radius:4px;background:transparent;color:var(--ink);cursor:pointer}
#az button.all{grid-column:1/-1;font-size:12px;letter-spacing:.04em;border-color:var(--rule)}
#az button:hover:not(:disabled){border-color:var(--rule)}
#az button[aria-pressed="true"]{background:var(--ink);color:var(--cream);border-color:var(--ink)}
#az button:disabled{color:#b9b09d;cursor:default;font-weight:400}
#az[hidden]{display:none!important}
@container (max-width:285px){
 .pk.has-az{display:block}
 #az{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none;border-left:0;padding:0 0 2px;margin:0 0 8px}
 #az::-webkit-scrollbar{display:none}
 #az button{flex:none;width:22px;height:24px;font-size:12px}#az button.all{width:auto;padding:0 8px;margin-right:4px}}
.tftog,.abtog{display:none}
#words .stats{margin:0 0 12px}
.sl{display:block}
/* ---- Desktop/tablet: a shorter header and slimmer View cards so the name, red stats and results sit higher ---- */
@media (min-width:641px){
 header{padding:12px 28px}header a.about-link{top:14px}header .logo{padding:5px 10px}header .logo img{height:36px}
 header h1{font-size:21px}header p#siteSub{max-width:820px;font-size:13.5px;line-height:1.4;margin-top:2px}
 .viewbar{margin-bottom:10px}.vcard{padding:4px 10px 4px 6px;width:auto;min-width:170px}.vcard svg{width:54px;height:36px}
 .vcard .vt b{font-size:14px}.vcard .vt small{font-size:11.5px}main{padding-top:14px}}
/* ---- Word Cloud card in the stat red (default view) ---- */
.vcard[data-view="visual"]{border-color:var(--num-red);box-shadow:inset 0 0 0 1px var(--num-red)}
.vcard[data-view="visual"] .vt b{color:var(--num-red)}
.vcard[data-view="visual"]:hover{background:#fbf1ef}
.vcard[data-view="visual"][aria-pressed="true"]{background:var(--num-red);border-color:var(--num-red);box-shadow:0 1px 3px rgba(158,27,36,.35)}
.vcard[data-view="visual"][aria-pressed="true"] .vt b{color:#fff}.vcard[data-view="visual"][aria-pressed="true"] .vt small{color:#f6dcdc}
.vcard[data-view="visual"][aria-pressed="true"]::after{background:var(--ink)}
/* ---- Typography: one family (Arial), hierarchy from size/weight/spacing; tight tracking on big type ---- */
:root{--font:Arial,"Helvetica Neue",Helvetica,sans-serif}
html,body,button,input,select,textarea,#pop,#cloud{font-family:var(--font)}
body{letter-spacing:0;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
header h1{font-size:23px;font-weight:700;letter-spacing:-.03em;line-height:1.15}
header p#siteSub{letter-spacing:0}
h2{font-weight:700;letter-spacing:-.01em}
#words h1#personTitle{font-size:21px;letter-spacing:-.025em;line-height:1.2}
#about h2{letter-spacing:-.02em}
#about h3.ablead{font-family:Arial,"Helvetica Neue",Helvetica,sans-serif;font-weight:700;font-size:24px;line-height:1.2;letter-spacing:-.02em;color:var(--num-red);margin:2px 0 10px}
@media (max-width:640px){#about h3.ablead{font-size:20px;margin:4px 0 8px}}
.stat{font-size:12.5px;line-height:1.3;color:var(--muted)}
.stat b{font-size:28px;font-weight:700;letter-spacing:-.035em;line-height:1.1;font-variant-numeric:tabular-nums;margin-bottom:2px}
td.cnt,td.num,.dl1 .dw,#sDocs,#sTotal,#sUnique,#sShown,.date{font-variant-numeric:tabular-nums}
td.cnt{font-weight:700;letter-spacing:-.01em}
table{font-size:14px}th{font-size:12px;font-weight:700;letter-spacing:0}
button.chip,label.chip,#cats button,.seg button{letter-spacing:0}
#personInfo .eyebrow,.dl2 .stype,#persons .pg .lbl,#pop .doc{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}#pop .doc{font-size:9.5px}
.vcard .vt b{letter-spacing:-.015em}
#cloud span{letter-spacing:-.02em}
.muted{letter-spacing:0}
/* ---- Phones: compress vertically; order = person, red stats, then cloud/table ---- */
@media (max-width:640px){
 body{font-size:14px;line-height:1.4}
 header{padding:7px 12px}header .brand{flex-direction:row;align-items:center;gap:8px;padding-right:62px}
 header .logo{padding:3px 6px;border-radius:7px}header .logo img{height:21px}
 header h1{font-size:15px;letter-spacing:-.03em;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 header .titles{flex:1}header p#siteSub{display:none}
 header a.about-link{top:50%;transform:translateY(-50%);right:12px;font-size:12px;padding:1px 9px}
 main{padding:8px;display:flex;flex-direction:column}body[class] main>*{order:5}.topgrid{display:contents}
 body[class] main #picker{order:0}body[class] main .viewbar{order:2}body[class] main #timeframe{order:3}body[class] main #words{order:4}
 .card{padding:8px 10px;margin-bottom:8px;border-radius:8px}
 #picker h2{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
 #cats{margin-bottom:6px}#cats button{padding:3px 10px;font-size:12.5px}
 #persons,#persons.grouped{display:flex;flex-wrap:nowrap;overflow-x:auto;gap:6px;margin:0 -10px 4px 0;padding-right:10px;scrollbar-width:none;
  -webkit-mask-image:linear-gradient(90deg,#000 88%,transparent);mask-image:linear-gradient(90deg,#000 88%,transparent)}
 #persons .pg{display:contents}#persons .pg .lbl{position:static;box-shadow:none;background:none;flex:none;align-self:center;font-size:10.5px;
  text-transform:uppercase;letter-spacing:.05em;padding:0 0 0 6px;border-left:1px solid var(--rule);margin-left:2px;width:auto;height:auto;clip:auto;overflow:visible}
 #persons .pg:first-child .lbl{border-left:0;padding-left:0;margin-left:0}
 #persons .chip{padding:3px 10px;font-size:12.5px}
 #personInfo{font-size:11.5px;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0}
 #personInfo .eyebrow{font-size:9.5px;padding:0 6px;margin:0 4px 0 0}
 body.view-visual #personInfo{display:block}
 .viewbar{margin:0 0 8px;gap:6px}.viewbar .lbl{display:inline;width:auto;font-size:12px}.vcards{width:auto;gap:4px}
 .vcard{flex:none;padding:3px 12px;border-radius:999px;gap:0}.vcard svg,.vcard .vt small,.vcard[aria-pressed="true"]::after{display:none}
 .vcard .vt b{font-size:12.5px}
 #timeframe{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px}
 #timeframe>*{order:3;width:100%}#timeframe h2{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);float:none;margin:0}
 #selSummary{order:0;flex:1;width:auto;min-width:0;margin:0;font-size:12.5px;line-height:1.35}
 #timeframe>.tftog{display:inline-block;order:1;width:auto;font:inherit;font-size:12px;font-weight:700;border:1px solid var(--rule);border-radius:999px;background:var(--card);color:var(--ink);padding:2px 10px;cursor:pointer}
 .pk.has-az{display:block}
 #az{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none;border-left:0;padding:0 0 2px;margin:0 0 6px}
 #az::-webkit-scrollbar{display:none}#az button{flex:none;width:22px;height:24px;font-size:12px}#az button.all{width:auto;padding:0 8px;margin-right:4px}
 .tftog::after{content:" \25BE"}#timeframe.open .tftog::after{content:" \25B4"}
 #timeframe:not(.open)>.tf-row,#timeframe:not(.open)>#docPick{display:none}
 #docPick{margin-top:4px}
 #timeframe .tf-row .lbl{display:inline;min-width:44px;font-size:11.5px}#timeframe .tf-row{margin-bottom:6px}
 .yrs{scrollbar-width:none;-webkit-mask-image:linear-gradient(90deg,#000 90%,transparent);mask-image:linear-gradient(90deg,#000 90%,transparent);padding-right:12px}
 .yrs::-webkit-scrollbar{display:none}
 #words h1#personTitle{font-size:16px;margin:0 0 6px;line-height:1.2;letter-spacing:-.02em}
 #words .stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;padding:0;margin:0 0 8px}
 .stat{padding:4px 6px;border-radius:6px;font-size:11px;line-height:1.2;min-width:0}.stat b{font-size:19px;line-height:1.15;letter-spacing:-.035em;margin:0}
 .sl{font-size:0;white-space:nowrap}.sl::after{content:attr(data-s);font-size:11px}
 .controls{gap:6px 10px;margin-bottom:6px}.controls label{font-size:12.5px}
 input[type=search]{min-width:0;padding:6px 10px;font-size:16px}
 th,td{padding:4px 8px}th{white-space:nowrap}
 body.view-visual #words>*{order:3}body.view-visual #personTitle,body.view-visual #words .stats{order:0}
 body.view-visual #words>.only-visual{order:1}
 #method{font-size:12px;line-height:1.4}
 .abtog{display:inline;font:inherit;font-weight:700;border:0;background:none;color:var(--ink);padding:0;cursor:pointer}
 .abtog::after{content:" \25BE";font-size:12px}#about.open .abtog::after{content:" \25B4"}
 #about:not(.open)>:not(h2){display:none}#about h2{font-size:15px;margin:0}#about.open h2{margin-bottom:8px}}
/* tablets (641-899): Word Cloud keeps controls first, then the words card (stats sit inside it, above the cloud) */

/* ==== v4 "black" theme: black page, black panels, cream type, hairline rules, red for numbers. Delete this block to revert ==== */
:root{--num-red:#ff5449;--money:#85bb65;--bg:#070707;--card:#111111;--panel2:#171717;--ink:#f3eee4;--cream:#0b0b0b;--muted:#a49e93;--rule:#2c2a27;--line:#232120;
 --hair:rgba(243,238,228,.14);--hl:#3b1715;--chip-on:#f3eee4;--chip-ink:#0b0b0b;color-scheme:dark}
html,body{background:var(--bg);color:var(--ink)}
a{color:var(--ink);text-decoration-color:rgba(243,238,228,.4)}a:hover{text-decoration-color:var(--num-red)}
body[class] header{background:#000;color:var(--ink);box-shadow:inset 0 -1px 0 var(--hair)!important;border-bottom:0}
header .logo{background:#f4efe6!important;box-shadow:none!important;border-radius:4px}
header p,header p#siteSub{color:#bdb6aa;opacity:1}
.hact{position:absolute;top:50%;right:28px;transform:translateY(-50%);display:flex;gap:8px;align-items:center}
header .hact a.about-link{position:static;transform:none;color:var(--ink);border:1px solid var(--hair);border-radius:3px;padding:4px 11px;font-size:13px;opacity:1}
.hbtn{font:inherit;font-size:13px;font-weight:700;color:var(--ink);background:transparent;border:1px solid var(--hair);border-radius:3px;padding:4px 11px;cursor:pointer;line-height:1.2}
.hbtn:hover,header .hact a.about-link:hover{border-color:var(--num-red);background:transparent}
header .titles{padding-right:150px}
main{max-width:1280px}
.card{background:var(--card);border:1px solid var(--line);border-radius:4px;box-shadow:none}
h2,#words h1#personTitle,#about h2{color:var(--ink)}
.muted,#personMeta,.stat,.hint,#method,#selSummary,.dl2,.dl2 a{color:var(--muted)}
#method{border-top:1px solid var(--line);padding-top:10px}
.stat{background:var(--panel2);border:1px solid var(--line);border-radius:3px}
.stat b,td.cnt{color:var(--num-red)}
.stat b{text-shadow:0 0 18px rgba(255,84,73,.18)}
th{color:var(--muted);border-bottom:1px solid var(--rule);text-transform:uppercase;font-size:10.5px!important;letter-spacing:.06em!important}
td{border-bottom:1px solid var(--line)!important}tr[data-w]:hover td{background:#1a1919}tr.active td{background:var(--hl)}
.bar{background:linear-gradient(90deg,rgba(255,84,73,.75),rgba(255,84,73,.35));opacity:1;border-radius:0}
input[type=search],.cloud-bar select{background:#0b0b0b;color:var(--ink);border:1px solid var(--rule);border-radius:3px}
input[type=search]::placeholder{color:#8a8479}
input[type=search]:focus{border-color:var(--ink);box-shadow:0 0 0 2px rgba(243,238,228,.12);outline:0}
input[type=checkbox]{accent-color:var(--num-red)}
button.chip,label.chip,.seg button{background:transparent;color:var(--ink);border:1px solid var(--rule);border-radius:3px}
button.chip:hover,label.chip:hover,.seg button:hover{background:#1c1b1a;border-color:#4a4743}
button.chip.on,label.chip.on,.seg button.on{background:var(--ink);color:#0b0b0b;border-color:var(--ink)}
label.chip.on .muted{color:#4a463f}label.chip.on input{accent-color:#0b0b0b}
#persons .chip .tk{font-size:10.5px;font-weight:700;letter-spacing:.04em;color:var(--muted)}#persons .chip.on .tk{color:#5a554d}
#persons .pg{border-top:1px solid var(--line)}#persons .pg .lbl{color:var(--muted);background:var(--card)}
#personInfo .eyebrow{background:transparent;color:var(--ink);border:1px solid var(--rule);border-radius:2px}
.dl2 .stype{color:var(--ink);border-color:var(--rule);border-radius:2px}
#docPick{border-top:1px solid var(--line)}#docPick>summary{color:var(--ink)}
ul.speeches li{border-top:1px solid var(--line)}ul.speeches li.sel{background:#181716}
button.only{background:transparent;color:var(--ink);border:1px solid var(--rule)}button.only:hover{background:var(--ink);color:#0b0b0b}
#pop{background:#141414;color:var(--ink);border:1px solid var(--rule);box-shadow:0 18px 50px rgba(0,0,0,.6)}
#pop mark{background:rgba(255,84,73,.28);color:#fff}#pop .twice{background:#2a2414;color:#e9c46a}
#pop .more{border-color:var(--ink);color:var(--ink)}#pop .more:hover{background:var(--ink);color:#0b0b0b}
#cloud{background:#0b0b0b;border:1px solid var(--line);border-radius:3px;
}   /* mm30: plain background, the grid lines are gone */
#cloud span:hover,#cloud span.active{background:var(--hl)}
.notice{background:#1b160c;border-color:#5a4520;color:var(--ink)}.notice strong{color:#e9c46a}
:focus-visible{outline:2px solid var(--num-red);outline-offset:2px}
.tftog,.abtog{color:var(--ink)}#timeframe>.tftog{background:transparent;border-color:var(--rule)}
/* View cards: hairline panels; Word Cloud card framed in the stat red */
.vcard{background:var(--card);border:1px solid var(--rule);border-radius:3px;box-shadow:none}
.vcard:hover{background:#181818;border-color:#4a4743}
.vcard svg{filter:invert(1) hue-rotate(180deg);opacity:.9}
.vcard .vt b{color:var(--ink)}.vcard .vt small{color:var(--muted)}
.vcard[aria-pressed="true"]{background:#1a1a1a;border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}
.vcard[aria-pressed="true"] .vt b{color:var(--ink)}.vcard[aria-pressed="true"] .vt small{color:var(--muted)}
.vcard[data-view="visual"]{border-color:var(--num-red);box-shadow:inset 0 0 0 1px rgba(255,84,73,.5)}
.vcard[data-view="visual"] .vt b{color:var(--num-red)}
.vcard[data-view="visual"]:hover{background:#1d1110}
.vcard[data-view="visual"][aria-pressed="true"]{background:linear-gradient(180deg,#2a0f0d,#1a0a09);border-color:var(--num-red);box-shadow:inset 0 0 0 1px var(--num-red),0 0 24px rgba(255,84,73,.18)}
.vcard[data-view="visual"][aria-pressed="true"] .vt b{color:#fff}.vcard[data-view="visual"][aria-pressed="true"] .vt small{color:#ffb3ad}
/* Mouth Math card: dollar-bill green, ONE variable (--money in :root above; set it to e.g. #a49e93 for gray) */
.vcard[data-view="standard"]{border-color:var(--money);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--money) 50%,transparent)}
.vcard[data-view="standard"] .vt b{color:var(--money)}
.vcard[data-view="standard"]:hover{background:color-mix(in srgb,var(--money) 9%,#111)}
.vcard[data-view="standard"][aria-pressed="true"]{background:linear-gradient(180deg,color-mix(in srgb,var(--money) 22%,#0b0b0b),color-mix(in srgb,var(--money) 12%,#0b0b0b));border-color:var(--money);box-shadow:inset 0 0 0 1px var(--money),0 0 24px color-mix(in srgb,var(--money) 18%,transparent)}
.vcard[data-view="standard"][aria-pressed="true"] .vt b{color:#fff}.vcard[data-view="standard"][aria-pressed="true"] .vt small{color:color-mix(in srgb,var(--money) 55%,#fff)}
.vcard[aria-pressed="true"]::after{display:none}
/* Category tiles: the first thing to click */
.topbar{display:flex;align-items:stretch;gap:16px;margin:0 0 14px}
.catbar{flex:1;min-width:0}
#cats.seg{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;background:none;border:0;padding:0;margin:0;border-radius:0;overflow:visible;-webkit-mask-image:none;mask-image:none}
#cats button.cat{display:flex;align-items:center;gap:12px;text-align:left;padding:12px 16px;min-height:62px;background:var(--card);color:var(--ink);
 border:1px solid var(--rule);border-radius:4px;cursor:pointer;font:inherit;white-space:normal;flex:auto;transition:border-color .15s,background-color .15s}
#cats button.cat:hover{border-color:#5a5650;background:#171717}
#cats .ci svg{width:28px;height:28px;fill:none;stroke:currentColor;stroke-width:1.2;stroke-linecap:round;stroke-linejoin:round;display:block}
#cats .ct{display:flex;flex-direction:column;min-width:0}
#cats .ct b{font-size:17px;font-weight:700;letter-spacing:-.025em;line-height:1.15}
#cats .ct small{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;margin-top:2px}
#cats button.cat.on{background:var(--ink);color:#0b0b0b;border-color:var(--ink);box-shadow:inset 0 -3px 0 var(--num-red)}
#cats button.cat.on .ct small{color:#4f4a43}
/* mm29: the selected category tab (e.g. 'Fed Chairman' on the default load) softened from bright cream to a medium warm gray; dark text keeps ~6.6:1 contrast, the count ~5:1; the red underline stays */
#cats button.cat.on{background:#a8807a;border-color:#a8807a}#cats button.cat.on .ct small{color:#24191a}   /* mm35: warm red-gray (was #9a958c); text #0b0b0b 5.7:1, count #24191a 4.9:1 */
.topbar .viewbar{margin:0;flex:none;align-items:center}.topbar #viewHint{display:none}#cats .ct b{white-space:nowrap}
@media (min-width:900px){body main>.topbar{grid-column:1/-1;grid-row:1}}
@media (max-width:899px){.topbar{display:contents}.catbar{margin:0 0 10px}}
/* people search + index chips (CEOs, US Government) */
#pfilter{margin:0 0 10px}#pfilter[hidden],#idx[hidden]{display:none!important}
#psearch{width:100%;min-width:0;box-sizing:border-box;padding:7px 10px;font-size:14px}
#idx{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
#idx .chip.ix{font-size:12.5px;padding:3px 9px}#idx .chip .n{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;margin-left:2px}
#idx .chip[aria-pressed="true"]{background:var(--ink);color:#0b0b0b;border-color:var(--ink)}#idx .chip[aria-pressed="true"] .n{color:#5a554d}
#idx .chip:disabled{opacity:.4;cursor:default}
.nomatch{font-size:13px}.linkbtn{font:inherit;background:none;border:0;color:var(--ink);text-decoration:underline;cursor:pointer;padding:0}
#az button{color:var(--ink)}#az button:disabled{color:#4d4943}#az{border-left-color:var(--line)}
#az button[aria-pressed="true"]{background:var(--ink);color:#0b0b0b;border-color:var(--ink)}#az button.all{border-color:var(--rule)}
/* Ad placeholders: faint mock units, kept clear of the stats and controls */
aside.ad{display:block;margin:28px auto;width:min(100%,var(--aw));position:relative;clear:both}
aside.ad .adl{display:block;font-size:9.5px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#77726a;margin:0 0 4px}
aside.ad .adbox,aside.ad ins{height:var(--ah);box-sizing:border-box}
aside.ad .adbox{border:1px solid #242220;border-radius:2px;display:flex;align-items:center;justify-content:center;gap:12px;
 background:repeating-linear-gradient(135deg,transparent 0 9px,rgba(243,238,228,.018) 9px 10px);opacity:.75}
/* Mock ad blocks (until AdSense units go live): no text, just a faint decorative tile of math marks (+ = ± × in cream, one red minus) */
aside.ad .adbox.adfaint{display:block;border:1px solid #1d1b19;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='72' height='72' fill='none' stroke-width='1.2' stroke-linecap='round'%3E%3Cg stroke='rgba%28243,238,228,.085%29'%3E%3Cpath d='M10 14h8M14 10v8'/%3E%3Cpath d='M46 16h8M46 20h8'/%3E%3Cpath d='M28 44h8M32 40v8M28 51h8'/%3E%3Cpath d='M8 56l5 5M13 56l-5 5'/%3E%3C/g%3E%3Cpath stroke='rgba%28255,84,73,.10%29' d='M56 57h8'/%3E%3C/svg%3E") repeat 0 0/72px 72px;opacity:1}
aside.ad[data-slot="side"]{margin:16px 0 0;width:100%;max-width:200px}
aside.ad[data-slot="incontent"]{margin:24px auto}
aside.ad[data-slot="leader"]{margin:24px auto 18px}
@media (max-width:899px){aside.ad[data-slot="side"]{display:none}}
@media (max-width:640px){aside.ad{width:min(100%,var(--amw))}aside.ad .adbox,aside.ad ins{height:var(--amh)}aside.ad{margin:18px auto}}
@media (min-width:900px){body main>aside.ad{grid-column:1/-1}}
/* toast + shortcut hint */
#toast{position:fixed;left:50%;bottom:22px;transform:translate(-50%,20px);background:var(--ink);color:#0b0b0b;font-size:13.5px;font-weight:700;padding:9px 16px;
 border-radius:3px;opacity:0;pointer-events:none;transition:opacity .2s,transform .2s;z-index:100;max-width:90vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#toast.on{opacity:1;transform:translate(-50%,0)}
.kbd-hint{display:block;margin-top:6px;transition:color .3s}.kbd-hint.flash{color:var(--ink)}
kbd{font:inherit;font-size:11px;font-weight:700;border:1px solid var(--rule);border-bottom-width:2px;border-radius:3px;padding:0 5px;color:var(--ink)}
@media (pointer:coarse){.kbd-hint{display:none}}
@media (prefers-reduced-motion:reduce){#toast{transition:none}}
/* phones: tiles keep 16px from the screen edges, never clipped */
@media (max-width:640px){
 header{padding:8px 16px}.hact{right:16px;gap:6px}header .titles{padding-right:118px}
 .hbtn,header .hact a.about-link{font-size:12px;padding:3px 9px}
 main{padding:10px 16px}
 #cats.seg{gap:8px;margin:0}
 #cats button.cat{flex-direction:column;align-items:flex-start;gap:4px;padding:8px 10px;min-height:0}
 #cats .ci svg{width:20px;height:20px}#cats .ct b{font-size:14px;letter-spacing:-.02em}#cats .ct small{font-size:11px}
 .catbar{margin:0 0 8px}
 #pfilter{margin:0 0 6px}#psearch{font-size:16px;padding:5px 9px}#idx{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;margin-top:6px}#idx::-webkit-scrollbar{display:none}
 #idx .chip.ix{flex:none;font-size:12px;padding:2px 8px}
 body[class] main>.catbar,body[class] main .catbar{order:-1}
 #cats button.cat{display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;column-gap:5px;row-gap:2px;padding:7px 9px;align-items:center}
 #cats .ct{display:contents}#cats .ct b{grid-column:1/-1;grid-row:1;white-space:nowrap;font-size:13.5px}
 #cats .ci{grid-column:1;grid-row:2}#cats .ci svg{width:14px;height:14px}#cats .ct small{grid-column:2;grid-row:2;margin:0;white-space:nowrap}
 #words h1#personTitle{font-size:16px}}
#cats button.cat.on::before{content:none;display:none}
/* Mouth Math: rank, word and count columns shrink to their content so the count sits a short, fixed gap after the
   longest word (numbers right-aligned in their column); the frequency bar takes the rest of the row */
table.only-standard th[data-k="rank"],table.only-standard td.num:first-child{width:1%;white-space:nowrap}
table.only-standard th[data-k="word"],table.only-standard td.w{width:1%;padding-right:22px}
table.only-standard th[data-k="count"],table.only-standard td.cnt{width:1%;white-space:nowrap;padding-right:16px}
table.only-standard th.barc{width:auto}
@media (max-width:640px){table.only-standard th[data-k="rank"],table.only-standard td.num:first-child{padding-left:2px;padding-right:12px}table.only-standard th[data-k="word"],table.only-standard td.w{padding-right:6px}table.only-standard th[data-k="count"],table.only-standard td.cnt{padding-left:0;padding-right:12px}table.only-standard th[data-k="count"]{letter-spacing:.02em}}
tr.top td.w{color:var(--num-red);font-weight:700}#cloud span.top{color:var(--num-red)}
/* the #1 word in the Word Cloud is solid red (no pulse, Oct 2026); it floats a little more than the others instead (physics) */
/* ---- The #1 word as an inviting button (Oct 2026): a pill with two faint, static white rings (inner ~40%, outer further out ~15%,
   like the header buttons' double ring); the rings travel with the word as it floats. Tap = the word's excerpts popover. ---- */
#cloud span.top{cursor:pointer;overflow:visible}
#cloud span.top::before,#cloud span.top::after{content:"";position:absolute;pointer-events:none;border-radius:999px}
#cloud span.top::before{inset:-3px -6px;box-shadow:0 0 0 1.5px rgba(255,255,255,.4)}
#cloud span.top::after{inset:-9px -13px;border:1px solid rgba(255,255,255,.15)}
#cloud span.top:hover,#cloud span.top.active{background:transparent}
#cloud span.top:hover::before,#cloud span.top.active::before{background:rgba(255,255,255,.06)}
/* Mouth Math #1 row: the rings are an overlay laid over the row (pseudo-elements on a <tr> break the table layout in Chrome) */
#tb tr.top{cursor:pointer}#tb tr.top:focus-visible{outline:none}
.tbwrap{position:relative}
.topring{position:absolute;pointer-events:none;z-index:1}
.topring::before,.topring::after{content:"";position:absolute;pointer-events:none}
.topring::before{inset:3px 1px;border-radius:9px;box-shadow:0 0 0 1.5px rgba(255,255,255,.4)}
.topring::after{inset:-1px -3px;border-radius:12px;border:1px solid rgba(255,255,255,.15)}
.tbwrap:has(tr.top:focus-visible) .topring::before{box-shadow:0 0 0 2px #fff}
/* Phones: A-Z as a wrapping grid of ~40px tap targets (9 x 3; 14 x 2 from 560px), 17px letters; the cells touch (every pixel
   is tappable) and the visible rounded box is drawn 2px inside each one; empty letters stay grayed and disabled */
@media (max-width:640px){
 .pk.has-az #az{display:grid;grid-template-columns:repeat(9,minmax(0,1fr));gap:0;overflow:visible;padding:0;margin:-2px -2px 6px;border-left:0}
 .pk.has-az #az button{position:relative;isolation:isolate;width:auto;height:40px;margin:0;padding:0;font-size:17px;border:0;border-radius:8px;
  background:transparent!important;touch-action:manipulation;outline-offset:-2px}
 .pk.has-az #az button::before{content:"";position:absolute;inset:2px;z-index:-1;border:1px solid #2a2925;border-radius:6px}
 .pk.has-az #az button.all{grid-column:auto;width:auto;margin:0;padding:0;font-size:15px;letter-spacing:.02em}
 .pk.has-az #az button.all::before{border-color:var(--rule)}
 .pk.has-az #az button:disabled{font-weight:400}.pk.has-az #az button:disabled::before{border-color:transparent}
 .pk.has-az #az button[aria-pressed="true"]{color:#0b0b0b}.pk.has-az #az button[aria-pressed="true"]::before{background:var(--ink);border-color:var(--ink)}}
@media (min-width:560px) and (max-width:640px){.pk.has-az #az{grid-template-columns:repeat(14,minmax(0,1fr))}}
@media (min-width:900px){.pk.has-az #persons:not(.grouped){display:flex;flex-wrap:wrap;gap:5px;align-content:flex-start}
 .pk.has-az #persons:not(.grouped)>.lbl{width:100%;margin:0 0 2px}.pk.has-az #persons:not(.grouped) .chip{margin:0}}
/* ---- Logo: red-outline mouth straight on the black header (no cream tile) ---- */
header .logo{background:none!important;padding:0!important;box-shadow:none!important;border-radius:0!important}
header .logo img{height:44px!important;width:auto}
@media (max-width:640px){header .logo img{height:26px!important}header .brand{padding-right:0!important}header .titles{padding-right:122px!important}}  /* phones: reserve the Share/About width once */
/* ---- Header: logo | compact headline block | red Word Cloud + green Mouth Math buttons | Share/About ---- */
header .brand{flex-wrap:nowrap;align-items:center;gap:20px;padding-right:150px!important}
header .titles{flex:0 1 auto;max-width:470px;padding-right:0!important}
header h1{line-height:1.12;margin:0}
header p#siteSub{max-width:470px!important;font-size:12.5px!important;line-height:1.3!important;margin:3px 0 0!important}
header .hact{top:50%!important;transform:translateY(-50%)!important}
header .viewbar.hview{flex:none;margin:0;gap:0}header .hview .lbl,header .hview #viewHint{display:none}
header .hview .vcards{display:flex;gap:10px}
header .hview .vcard{--vc:var(--num-red);min-width:0;width:auto;padding:7px 16px 7px 9px;gap:11px;border:2px solid var(--vc)!important;border-radius:6px;
 background:#0b0b0b;box-shadow:none;transition:background .15s,box-shadow .15s}
header .hview .vcard[data-view="visual"]{--vc:var(--money)}
header .hview .vcard svg{width:58px;height:38px}
header .hview .vcard .vt b{font-size:17px;color:var(--vc);white-space:nowrap}header .hview .vcard .vt small{font-size:12px;color:#a49e93;white-space:nowrap}
header .hview .vcard:hover{background:color-mix(in srgb,var(--vc) 12%,#0b0b0b)}
header .hview .vcard[aria-pressed="true"]{background:color-mix(in srgb,var(--vc) 34%,#0b0b0b);box-shadow:0 0 0 1px var(--vc),0 0 22px color-mix(in srgb,var(--vc) 28%,transparent)}
header .hview .vcard[aria-pressed="true"] .vt b{color:#fff}header .hview .vcard[aria-pressed="true"] .vt small{color:color-mix(in srgb,var(--vc) 45%,#fff)}
header .hview .vcard:focus-visible{outline:2px solid #fff;outline-offset:2px}
@media (max-width:1239px) and (min-width:641px){header .hview .vcard svg{display:none}header .hview .vcard{padding:7px 14px}header .titles,header p#siteSub{max-width:330px!important}}
@media (max-width:839px) and (min-width:641px){header .brand{flex-wrap:wrap;row-gap:10px}header .viewbar.hview{flex-basis:100%}header .hact{top:25px!important;transform:none!important}}   /* mm24: no headline, so logo + jump buttons share one row from 840px */
@media (max-width:640px){
 header .brand{flex-wrap:wrap;gap:8px;row-gap:8px;padding-right:0!important}
 header .titles{flex:1;max-width:none;padding-right:122px!important}
 header .hact{top:7px!important;transform:none!important}
 header .viewbar.hview{flex-basis:100%;width:100%;margin:0 0 1px}header .hview .vcards{width:100%;gap:8px}
 header .hview .vcard{flex:1;width:auto;justify-content:center;padding:7px 8px;border-radius:5px;gap:0}
 header .hview .vcard svg,header .hview .vcard .vt small{display:none}
 header .hview .vcard .vt{align-items:center}header .hview .vcard .vt b{font-size:15.5px}}
#tfbar{position:relative}#tfbar #selSummary{width:1px!important;height:1px!important;flex:none!important;margin:0!important;overflow:hidden!important}.sr-only{position:absolute!important;left:0;top:0;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
/* ---- Categories live at the top of the Who panel (no separate tile row, no "Who" heading) ---- */
#picker .catbar{margin:0 0 12px}
#picker #cats.seg{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0}
#picker #cats button.cat{display:flex;flex-direction:row;align-items:center;gap:9px;min-height:0;padding:8px 11px;border-radius:4px;white-space:nowrap}
#picker #cats .ci svg{width:20px;height:20px}
#picker #cats .ct{display:flex;flex-direction:column;min-width:0}
#picker #cats .ct b{font-size:14.5px;line-height:1.15}#picker #cats .ct small{font-size:11.5px;margin:1px 0 0}
@media (min-width:900px){   /* narrow left column: a compact vertical list */
 #picker #cats.seg{grid-template-columns:1fr;gap:6px}
 #picker #cats button.cat{padding:7px 11px}
 #picker #cats .ct{flex-direction:row;align-items:baseline;justify-content:space-between;flex:1;gap:8px}
 #picker #cats .ct small{margin:0}}
@media (max-width:640px){
 #picker{padding-left:12px;padding-right:12px}
 #picker .catbar{margin:0 0 8px}
 #picker #cats.seg{gap:6px}
 #picker #cats button.cat{display:grid;grid-template-columns:auto 1fr;column-gap:5px;row-gap:2px;padding:6px 8px}
 #picker #cats .ct{display:contents}#picker #cats .ct b{grid-column:1/-1;grid-row:1;font-size:13px;letter-spacing:-.02em}
 #picker #cats .ci{grid-column:1;grid-row:2}#picker #cats .ci svg{width:13px;height:13px}#picker #cats .ct small{grid-column:2;grid-row:2;font-size:11px}}
@media (max-width:379px){#picker #cats .ct b{font-size:12px}#picker #cats button.cat{padding:6px 6px}}
/* ---- Timeframe: one slim row right under the red stats (All/None, years, Choose documents) ---- */
#tfbar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:-2px 0 12px;font-size:13px;line-height:1.2}
#tfbar .tfl{font-size:13px;font-weight:700;color:var(--muted);margin-right:2px}
#tfbar .chip,#tfbar label.chip{font-size:13px;padding:4px 10px;min-height:28px;margin:0;display:inline-flex;align-items:center;gap:4px}
#tfbar .tfsep{width:1px;height:18px;background:var(--rule);margin:0 2px}
#tfbar .yrs{display:flex;flex:0 1 auto;min-width:0;gap:6px;overflow-x:auto;scrollbar-width:none;padding:0}
#tfbar .yrs::-webkit-scrollbar{display:none}
#tfbar #years label.chip{padding:4px 10px}#tfbar #years label.chip .muted{font-size:12px}
#tfbar #docPick{margin:0 0 0 auto;padding:0;border:0}
#tfbar #docPick>summary{font-size:13px;font-weight:700;padding:4px 11px;min-height:28px;border:1px solid var(--rule);border-radius:999px;color:var(--ink);cursor:pointer}
#tfbar #docPick>summary:hover{border-color:#5a5650}
#tfbar #docPick[open]{flex-basis:100%;margin-left:0}
#tfbar #docPick[open]>summary{margin-bottom:4px}
#tfbar #docPick .speeches{max-height:340px;overflow:auto}
@media (max-width:640px){
 #tfbar{gap:6px;margin:0 0 8px}#tfbar .tfl,#tfbar .tfsep{display:none}
 #tfbar .chip,#tfbar label.chip,#tfbar #docPick>summary{min-height:36px;padding:6px 11px}
 #tfbar .yrs{flex:1 1 0;min-width:60px;-webkit-mask-image:linear-gradient(90deg,#000 88%,transparent);mask-image:linear-gradient(90deg,#000 88%,transparent);padding-right:10px}
 #tfbar{flex-wrap:nowrap}#tfbar:has(#docPick[open]){flex-wrap:wrap}
 #tfbar #docPick{margin-left:0;flex:none}#tfbar #docPick>summary{white-space:nowrap}
 #tfbar #docPick>summary::before{display:none}#tfbar #docPick>summary::after{content:" \25BE";font-size:11px}#tfbar #docPick[open]>summary::after{content:" \25B4"}
 #tfbar .chip{flex:none}#tfbar #years label.chip{position:relative}
 #tfbar #years input{position:absolute;opacity:0;width:1px;height:1px;margin:0}   /* chip fill shows on/off; still focusable */
 #tfbar #years label.chip:focus-within{outline:2px solid var(--ink);outline-offset:1px}
 body.view-visual #words>#tfbar{order:0}}
@media (max-width:379px){#tfbar{flex-wrap:wrap}#tfbar .yrs{flex-basis:100%;order:5}}   /* very narrow phones: years on their own line */
/* ---- Choose documents + document list in the accent red (--num-red); checked vs unchecked stay distinct ---- */
#tfbar #docPick>summary{color:var(--num-red);border-color:var(--num-red)}
#tfbar #docPick>summary .muted{color:color-mix(in srgb,var(--num-red) 65%,#fff)}
#tfbar #docPick>summary:hover{background:color-mix(in srgb,var(--num-red) 12%,transparent);border-color:var(--num-red)}
#tfbar #docPick[open]>summary{background:color-mix(in srgb,var(--num-red) 30%,#0b0b0b);color:#fff}
#tfbar #docPick[open]>summary .muted{color:#ffd0cc}
#docPick .hint{color:color-mix(in srgb,var(--num-red) 45%,#bdb6aa)}
#tfbar #docPick>summary .dpc{color:#fff;margin-right:-2px}   /* only "Choose" is white; "documents", the red border, the white triangle and the open red list are unchanged */
#docList li{border:1px solid color-mix(in srgb,var(--num-red) 30%,transparent);border-radius:4px;margin:0 0 6px;background:transparent}
#docList li .date,#docList li .dt{color:#a49e93}#docList li .dw{color:#8f897f}
#docList li.sel{background:color-mix(in srgb,var(--num-red) 15%,#0f0f0f);border-color:var(--num-red)}
#docList li.sel .date{color:var(--num-red)}#docList li.sel .dt{color:#fff}#docList li.sel .dw{color:#ffc4be}
#docList li.sel .dl2,#docList li.sel .dl2 a{color:#d9c9c6}
#docList li .dl2 .stype{color:color-mix(in srgb,var(--num-red) 70%,#fff);border-color:color-mix(in srgb,var(--num-red) 60%,transparent)}
#docList input{accent-color:var(--num-red)}
#docList button.only{color:var(--num-red);border-color:color-mix(in srgb,var(--num-red) 60%,transparent);background:transparent}
#docList button.only:hover{background:color-mix(in srgb,var(--num-red) 18%,transparent);border-color:var(--num-red)}
/* ---- Headline: ALL CAPS, Arial, tight tracking; one line on phones (own row under the logo, sized to the width) ---- */
header h1#siteTitle{text-transform:none;letter-spacing:-.02em;font-size:21px;line-height:1.15;font-family:Arial,Helvetica,sans-serif}
@media (max-width:640px){
 header .titles{flex-basis:100%;order:2;padding-right:0!important}header .viewbar.hview{order:3}
 header h1#siteTitle{font-size:clamp(12px,4.3vw,19px);white-space:nowrap;overflow:visible;text-overflow:clip;letter-spacing:-.025em}}
/* ---- Stock ticker pill (CEOs only): Arial caps, money-green outline; people list + selected speaker title ---- */
.tk{display:inline-block;font-family:Arial,Helvetica,sans-serif;text-transform:uppercase;font-weight:700;letter-spacing:.03em;line-height:1;white-space:nowrap;
 color:var(--money);border:1.5px solid var(--money);background:color-mix(in srgb,var(--money) 14%,transparent);border-radius:4px;vertical-align:.12em}
#persons .chip .tk{font-size:11px;padding:2px 4px 1px;margin-left:3px;color:var(--money)}
#persons .chip.on .tk{color:#1f4d12;border-color:#2f6b1f;background:#cfe6c0}
#words h1#personTitle .ft{font-weight:500;color:#c9c2b5;font-size:.86em;letter-spacing:-.01em}#words h1#personTitle .pn{font-weight:700;color:var(--ink)}
#words h1#personTitle .tk{font-size:max(11px,.62em);padding:3px 6px 2px;margin:0 2px;letter-spacing:.04em}
/* ---- "Show N words" chips: one shared control for Word Cloud and Mouth Math, right under the Timeframe row ---- */
#nbar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:-4px 0 12px;font-family:Arial,Helvetica,sans-serif}
#nbar .nbl{font-size:14px;font-weight:700;color:var(--ink);text-transform:uppercase;letter-spacing:.04em}
#nbar .nbl:first-child{margin-right:2px}#nbar .nbl:last-child{margin-left:2px;color:var(--muted);text-transform:none;letter-spacing:0;font-weight:400}
#nbar .nchip{font:700 13px/1 Arial,Helvetica,sans-serif;min-width:40px;min-height:32px;padding:0 11px;border-radius:6px;cursor:pointer;
 color:var(--num-red);background:transparent;border:1.5px solid var(--num-red);font-variant-numeric:tabular-nums}
#nbar .nchip:hover{background:color-mix(in srgb,var(--num-red) 16%,transparent)}
#nbar .nchip[aria-pressed="true"]{background:var(--num-red);color:#fff;border-color:var(--num-red)}
#nbar .nchip:focus-visible{outline:2px solid #fff;outline-offset:2px}
@media (max-width:640px){#nbar{gap:6px;margin:0 0 10px;flex-wrap:nowrap}#nbar .nchip{flex:none;min-width:40px;min-height:36px;padding:0 10px;font-size:14px}
 #nbar .nbl:last-child{display:none}body.view-visual #words>#nbar{order:0}}
/* ---- "Choose documents" arrow: 1.5x and white (label text stays red) ---- */
#tfbar #docPick>summary::before{width:10.5px;height:10.5px;border-right-width:3px;border-bottom-width:3px;border-color:#fff;margin:0 5px 0 2px}
#tfbar #docPick>summary::after{color:#fff;font-size:16.5px;line-height:1;vertical-align:-1px}
/* ---- every disclosure / sort arrow on the page is white (labels keep their colors) ---- */
#aboutToggle::after{color:#fff!important;font-size:16.5px!important;line-height:1;vertical-align:-1px}
th[data-k] .sarr{color:#fff;font-size:1.15em}
/* ---- Ticker pills open a 1-year TradingView chart in a modal ---- */
.tk.tkc{cursor:pointer}button.tk.tkc{font-family:Arial,Helvetica,sans-serif;font-weight:700;text-transform:uppercase}
.tk.tkc:hover,.tk.tkc:focus-visible{background:var(--money);color:#0b0b0b!important;border-color:var(--money)!important;outline:none}
#persons .chip.on .tk.tkc:hover{background:#2f6b1f;color:#fff!important}
html.tvopen{overflow:hidden}
.tvm{position:fixed;inset:0;z-index:2000;display:flex;align-items:center;justify-content:center;font-family:Arial,Helvetica,sans-serif}
.tvm[hidden]{display:none}
.tvm-back{position:absolute;inset:0;background:rgba(0,0,0,.74)}
.tvm-panel{position:relative;display:flex;flex-direction:column;width:min(1000px,94vw);height:min(700px,88vh);background:#0b0b0b;border:1.5px solid var(--money);border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,.6);overflow:hidden}
.tvm-head{display:flex;align-items:center;gap:10px;padding:8px 8px 8px 16px;border-bottom:1px solid #222}
.tvm-head h3{margin:0;font-size:17px;font-weight:700;color:var(--money);letter-spacing:.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.tvm-sub{font-size:13px;color:var(--muted);white-space:nowrap}
.tvm-x{margin-left:auto;flex:none;width:44px;height:44px;border-radius:8px;border:1px solid #3a3a3a;background:#151515;color:#fff;font:400 30px/1 Arial,Helvetica,sans-serif;cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0 0 3px}
.tvm-x:hover,.tvm-x:focus-visible{background:#fff;color:#000;outline:none}
.tvm-body{flex:1;min-height:0;padding:6px 8px 0}
.tvm-body .tradingview-widget-copyright{font-size:13px;line-height:32px;text-align:center;color:#9aa0a6}
.tvm-body .tradingview-widget-copyright .blue-text{color:#2962ff}
.tvm-note{margin:0;padding:4px 14px 8px;font-size:12px;color:var(--muted);text-align:center}
@media (max-width:640px){.tvm-panel{width:calc(100vw - 12px);height:calc(100dvh - 12px);border-radius:10px}.tvm-sub{display:none}.tvm-head{padding-left:12px}.tvm-body{padding:4px 2px 0}}
/* ---- Buttons: a bit more space between them and slightly fatter (proportionate; phones get smaller increases to keep the red stats high) ---- */
body header .viewbar.hview,body header #views{gap:16px!important}
body header .hview .vcard{padding:10px 20px 10px 12px!important;min-height:62px}
body #cats{gap:9px!important}body #cats button{padding:9px 13px!important}
body #persons{gap:8px!important;column-gap:8px!important;row-gap:8px!important}body #persons button.chip{padding:6px 14px!important}
body #idx{gap:8px!important}body #idx button{padding:5px 11px!important}
body #tfbar{gap:9px!important}body #tfbar .chip,body #tfbar label.chip,body #tfbar #docPick>summary{min-height:32px!important;padding:6px 12px!important}
body #nbar{gap:7px!important}body #nbar .nchip{min-height:32px!important;padding:0 11px!important}
body header .hact{gap:10px!important}body header .hact button,body header .hact a{padding:6px 13px!important}
@media (max-width:640px){
 body header .viewbar.hview,body header #views{gap:12px!important}body header .hview .vcard{padding:9px 10px!important;min-height:42px}
 body #cats{gap:8px!important}body #cats button{padding:6px 9px!important}
 body #persons{gap:8px!important}body #persons button.chip{padding:4px 12px!important}
 body #idx{gap:8px!important}body #idx button{padding:3px 10px!important}
 body #tfbar{gap:8px!important}body #tfbar .chip,body #tfbar label.chip,body #tfbar #docPick>summary{min-height:40px!important;padding:7px 12px!important}
 body #nbar{gap:6px!important}body #nbar .nchip{min-height:36px!important;padding:0 10px!important}
 body header .hact{gap:8px!important}body header .hact button,body header .hact a{padding:5px 11px!important}}
/* Show chips, smaller (Oct 2026): content-sized, 36px tall on phones; tighter padding on narrow phones keeps one row at 320 */
@media (max-width:374px){body #nbar{gap:5px!important}body #nbar .nchip{min-width:34px;padding:0 7px!important}}
@media (max-width:330px){body #nbar .nchip{padding:0 6px!important}#nbar .nbl:first-child{font-size:13px;margin-right:0}}
/* Show 5 / 50 / 100 / Max as stair steps (Oct 2026; 5/50 added mm35): bottom-aligned, each chip a little taller than the last so the tops rise like stairs */
body #nbar{align-items:flex-end!important}body #nbar .nbl{align-self:center}
body #nbar .nchip[data-n="5"]{min-height:28px!important}body #nbar .nchip[data-n="20"]{min-height:31px!important}body #nbar .nchip[data-n="50"]{min-height:34px!important}body #nbar .nchip[data-n="100"]{min-height:37px!important}body #nbar .nchip[data-n="all"]{min-height:40px!important}
@media (max-width:640px){body #nbar .nchip{min-width:48px}body #nbar .nchip[data-n="5"]{min-height:34px!important}body #nbar .nchip[data-n="20"]{min-height:37px!important}body #nbar .nchip[data-n="50"]{min-height:41px!important}body #nbar .nchip[data-n="100"]{min-height:44px!important}body #nbar .nchip[data-n="all"]{min-height:48px!important}}
/* ---- Phones: collapsible people list for every multi-person category (CEOs, US Government). Closed = selected name (red, + ticker) + white arrow ---- */
#pdisc{display:none}
@media (max-width:640px){
 .pk.pcoll #pdisc{display:flex;align-items:center;gap:10px;width:100%;min-height:52px;margin:2px 0 8px;padding:8px 14px;box-sizing:border-box;border:1.5px solid var(--rule);border-radius:10px;
  background:transparent;color:var(--ink);font:inherit;text-align:left;cursor:pointer}
 .pk.pcoll #pdisc:focus-visible{outline:2px solid #fff;outline-offset:2px}
 .pk.pcoll #pdisc .pdg{flex:none;font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
 .pk.pcoll #pdisc .pdn{flex:0 1 auto;min-width:0;font-size:20px;font-weight:700;line-height:1.15;letter-spacing:-.01em;color:var(--num-red);overflow-wrap:anywhere}
 .pk.pcoll #pdisc .pda::after{content:"\25BE";color:#fff;font-size:16.5px;line-height:1}
 .pk.pcoll #pdisc .tk{flex:none;font-size:12px;padding:3px 6px 2px;color:var(--money)}
 @media (max-width:360px){.pk.pcoll #pdisc{gap:8px;padding:8px 12px}.pk.pcoll #pdisc .pdn{font-size:19px}.pk.pcoll #pdisc .pdg{display:none}}
 .pk.pcoll #pdisc .pda{margin-left:auto;flex:none}
 .pk.pcoll.popen #pdisc .pda::after{content:"\25B4"}
 .pk.pgrp #az{display:none!important}
 .pk.pcoll:not(.popen) #pfilter,.pk.pcoll:not(.popen) #az,.pk.pcoll:not(.popen) #persons{display:none!important}
 .pk.pcoll.popen:not(.pgrp) #persons{display:flex!important;flex-wrap:wrap!important;gap:8px!important;overflow:visible!important;margin:0 0 8px!important;padding:0!important;-webkit-mask-image:none!important;mask-image:none!important}
 .pk.pcoll.popen:not(.pgrp) #persons>.lbl{display:none}
 .pk.pcoll.popen #persons,.pk.pcoll.popen #persons.grouped{display:block!important;overflow:visible!important;margin:0 0 6px!important;padding:0!important;-webkit-mask-image:none!important;mask-image:none!important}
 .pk.pcoll.popen #persons .pg{display:flex!important;flex-wrap:wrap!important;gap:8px!important;overflow:visible!important;margin:0!important;padding:8px 0!important;-webkit-mask-image:none!important;mask-image:none!important;border-top:1px dashed var(--line)}
 .pk.pcoll.popen #persons .pg:first-child{border-top:0;padding-top:2px!important}
 .pk.pcoll.popen #persons .pg .lbl{position:static!important;width:100%!important;flex:0 0 100%!important;border:0!important;padding:0!important;margin:0!important;box-shadow:none!important;background:none!important;font-size:10.5px}
 .pk.pcoll.popen #persons .chip{min-height:40px}
 /* single-person category (Fed Chairman): the selected name looks like the CEO / US Government collapse row (red name, dark row), not a cream chip */
 body .pk.psolo #persons{display:block!important;margin:0!important;padding:0!important;-webkit-mask-image:none!important;mask-image:none!important}
 body .pk.psolo #persons>.lbl{display:none!important}
 body .pk.psolo #persons button.chip.on,body .pk.psolo #persons button.chip.on:hover{display:flex;align-items:center;gap:10px;width:100%;min-height:52px;margin:2px 0 8px;padding:8px 14px!important;box-sizing:border-box;
  border:1.5px solid var(--rule)!important;border-radius:10px;background:transparent!important;box-shadow:none!important;color:var(--num-red)!important;font-size:20px;font-weight:700;line-height:1.15;letter-spacing:-.01em;text-align:left;cursor:default}
 body .pk.psolo #persons button.chip.on::before{content:attr(data-glabel);flex:none;font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
 @media (max-width:360px){body .pk.psolo #persons button.chip.on{gap:8px;padding:8px 12px!important;font-size:19px}body .pk.psolo #persons button.chip.on::before{display:none}}}
/* ---- View buttons: second outer ring (outline + offset, no layout cost) and a raised 3D look; pressed-in on :active ---- */
body header .hview .vcard{outline:2px solid color-mix(in srgb,var(--vc) 50%,transparent);outline-offset:3px;
 background-image:linear-gradient(180deg,rgba(255,255,255,.10),rgba(255,255,255,0) 48%,rgba(0,0,0,.24));
 box-shadow:inset 0 1px 0 rgba(255,255,255,.16),0 3px 0 color-mix(in srgb,var(--vc) 38%,#000),0 7px 16px rgba(0,0,0,.65);
 transition:transform .08s ease,box-shadow .08s ease,background-color .15s}
body header .hview .vcard[aria-pressed="true"]{outline:2px solid var(--vc);outline-offset:3px;
 box-shadow:inset 0 1px 0 rgba(255,255,255,.22),0 3px 0 color-mix(in srgb,var(--vc) 45%,#000),0 7px 16px rgba(0,0,0,.65),0 0 24px color-mix(in srgb,var(--vc) 30%,transparent)}
body header .hview .vcard:active{transform:translateY(2px);background-image:linear-gradient(180deg,rgba(0,0,0,.28),rgba(0,0,0,0) 55%);
 box-shadow:inset 0 2px 7px rgba(0,0,0,.6),0 1px 0 color-mix(in srgb,var(--vc) 38%,#000),0 2px 4px rgba(0,0,0,.6)}
body header .hview .vcard:focus-visible{outline:2px solid #fff;outline-offset:3px}
body header .viewbar.hview,body header #views{gap:24px!important}
@media (max-width:640px){body header .viewbar.hview,body header #views{gap:18px!important}body header .viewbar.hview{padding:3px 5px 0}}
/* ---- Stacked layout (Oct 2026): stats -> Mouth Math table -> ad -> Word Cloud on one page; header buttons are jump links ---- */
body header .hview a.vcard{text-decoration:none;color:inherit;cursor:pointer}
.secth{margin:22px 0 10px;font:700 19px/1.2 Arial,Helvetica,sans-serif;color:#f3eee4;letter-spacing:-.005em;scroll-margin-top:12px}
#superMath{margin-top:18px}
#cloud{scroll-margin-top:42px}   /* a plain #cloud link shows the Word Cloud heading too */
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
#more{margin:8px 0 0}
aside.ad[data-slot="between"]{margin:26px auto 4px}
.cloudwrap .cloud-bar{margin:6px 0 0}
@media (max-width:640px){.secth{font-size:17px;margin:18px 0 8px}#superMath{margin-top:14px}aside.ad[data-slot="between"]{margin:20px auto 2px}}
@media (prefers-reduced-motion:reduce){body header .hview .vcard{transition:none}}
/* ---- Logo v3: inline SVG (profile -> waves -> = ± -> animated red number -> MouthMath), no layout jump (fixed-width number) ---- */
/* ---- mm45: Latest / All combined segmented toggle (right above the red stats) ---- */
 font:600 14px/1.2 Arial,Helvetica,sans-serif;letter-spacing:-.01em;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;box-sizing:border-box}
/* ---- mm45: desktop people list scrolls inside itself so the selected chip stays in view ---- */
@media (min-width:900px){
 #persons{max-height:min(58vh,560px);overflow-y:auto;overflow-x:hidden;scrollbar-width:thin;padding-right:2px;margin-bottom:6px;scroll-behavior:auto}
 #persons.grouped{max-height:min(58vh,560px);overflow-y:auto}
 .pk.has-az>#persons{max-height:min(58vh,560px)}
}
.sitefoot{max-width:1240px;margin:0 auto;padding:18px 16px 30px;border-top:1px solid var(--rule);text-align:center;font-size:14px;color:var(--muted)}.sitefoot a{color:var(--muted)}.sitefoot a:hover{color:var(--num-red)}
.mmcopy{margin-top:8px;font:400 12px/1.4 Arial,Helvetica,sans-serif;color:#7d776d;text-align:center;letter-spacing:0}
header .logo svg.mmlogo{height:49px;width:auto;aspect-ratio:925/144;display:block;overflow:visible}   /* mm24: +25% (the header headline moved to About) */
@media (max-width:1239px) and (min-width:641px){header .logo svg.mmlogo{height:42px}}
/* phones: as big as fits next to Share/About (one row down to 320px): 50px from ~375px, ~41px at 320px */
@media (max-width:640px){body header{--lh:min(36px,calc((100vw - 132px) / 6.42));padding-left:12px!important;padding-right:12px!important}
 header .logo svg.mmlogo{height:var(--lh)}
 body header .hact{right:12px!important;gap:5px!important;top:calc(8px + (var(--lh) - 27px) / 2)!important}   /* centered on the logo */
 body header .hact button,body header .hact a{padding:4px 7px!important;font-size:12px!important}}
/* ---- Person names in the people list: red (#ff5449) on dark, darker red on the light selected chip; ticker pills keep their green ---- */
body #persons button.chip{color:#ff5449!important}
body #persons button.chip:hover{color:#ff7a70!important}
body #persons button.chip.on,body #persons button.chip.on:hover{color:#a8201a!important}
/* slim About (mm23): short text, contact + privacy on one line, fine print last */
#about p{margin:0 0 10px;line-height:1.5}#about .abnote{color:var(--muted)}
#about .abfoot{display:flex;flex-wrap:wrap;gap:4px 8px;align-items:center;margin:12px 0 6px;font-size:15px}#about .abfoot a{color:var(--ink);text-decoration-color:var(--rule);text-underline-offset:3px}
#about .abtitle{font-size:19px;font-weight:700;letter-spacing:-.02em;line-height:1.2;color:var(--ink);margin:0 0 4px}#about .absub{color:var(--muted);margin:0 0 12px}
#method:has(#kbdHint){border-top:0;padding-top:0}
@media (max-width:640px){#about p{font-size:15px;line-height:1.5}#about .abfoot{font-size:15px}#about .abfoot{margin:2px 0 0}#about .abfoot a{display:inline-flex;align-items:center;min-height:44px}
 #more,.cloudwrap .cloud-bar{display:none}   /* phones: the stats row already says how many words are shown */
 #method{font-size:12px;margin:6px 0 10px}}
@media (pointer:coarse){#pop .hint{display:none}}
/* mm24: people lists easier to read (all categories): unselected names cream, +2px; the selected person stays dark red on its light pill */
body #persons button.chip:not(.on){color:var(--ink)!important}body #persons button.chip:not(.on):hover{color:#ff7a70!important}
body .pk:not(.psolo) #persons button.chip{font-size:15px}
@media (max-width:640px){body .pk:not(.psolo) #persons button.chip{font-size:14.5px;padding:4px 9px!important}body .pk:not(.psolo) #persons button.chip .tk{margin-left:2px}body .pk:not(.psolo) #persons,body .pk:not(.psolo) #persons .pg{gap:6px!important;column-gap:6px!important;row-gap:7px!important}}
/* mm24: role label under the name (e.g. "CEO · JPMorgan Chase") white and a size up */
body #personInfo .eyebrow{color:#fff;font-size:11.5px;border-color:color-mix(in srgb,#fff 35%,transparent)}
@media (max-width:640px){body #personInfo .eyebrow{font-size:10.5px;line-height:1.35}}
/* mm24: Change speaker. Phones' collapsed row = one big button: name + ticker + 2x white triangle right next to it + cream "Change", faint ring */
@media (max-width:640px){
 body .pk.pcoll #pdisc{gap:8px;border-color:color-mix(in srgb,#fff 26%,transparent);box-shadow:0 0 0 4px color-mix(in srgb,#fff 6%,transparent);min-height:56px}
 body .pk.pcoll #pdisc .pda{margin-left:0;display:inline-flex;align-items:center}
 body .pk.pcoll #pdisc .pda::after{font-size:33px;line-height:.7}
 body .pk.pcoll #pdisc:active{background:color-mix(in srgb,#fff 5%,transparent)}
 @media (max-width:360px){body .pk.pcoll #pdisc{gap:6px;padding:8px 10px}body .pk.pcoll #pdisc .pda::after{font-size:30px}}}
/* sticky Change-speaker bar: slides in once the red stats scroll off the top */
#spkbar{position:fixed;top:0;left:0;right:0;z-index:60;display:flex;align-items:center;justify-content:center;gap:9px;height:46px;margin:0;padding:0 16px;box-sizing:border-box;
 border:0;border-bottom:1px solid color-mix(in srgb,#fff 18%,transparent);background:rgba(11,11,11,.93);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);
 color:var(--ink);font:inherit;cursor:pointer;transform:translateY(-105%);visibility:hidden;transition:transform .22s ease,visibility 0s linear .22s}
#spkbar.show{transform:none;visibility:visible;transition:transform .22s ease}
#spkbar .sbn{min-width:0;font:700 17px/1.1 Arial,Helvetica,sans-serif;letter-spacing:-.01em;color:var(--num-red);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#spkbar .tk{flex:none;font-size:11.5px;padding:2px 6px 1px;color:var(--money)}
.tk[hidden],.tk:empty{display:none!important}   /* mm31: no empty ticker pill anywhere (e.g. the Fed Chairman in the sticky bar) */
#spkbar .sba{display:inline-flex;align-items:center;position:relative}
#spkbar .sba::after{
  content:"";display:inline-block;box-sizing:border-box;
  width:15px;height:15px;padding:0;border-radius:50%;font-size:0;line-height:0;color:transparent;
  background:radial-gradient(circle at 50% 50%,#fff 0,#f7f6fc 30%,#ebe8f6 44%,rgba(190,180,220,.55) 52%,#fff 62%,#fff 100%);
  box-shadow:0 0 9px rgba(255,255,255,.9),0 0 6px rgba(210,200,235,.55);
  animation:spkdot2 2.35s ease-in-out infinite;
}
#spkbar.show .sbc{animation:pdcTextBreath 2.35s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){
  #spkbar .sba::after{animation:none!important;outline:none!important}
  #spkbar.show .sbc{animation:none!important;text-shadow:0 0 4px rgba(255,255,255,.22)}
}
#spkbar .sbc{flex:none;font-size:12px;font-weight:700;color:#f3eee4;margin-left:-3px;letter-spacing:.01em}
/* mm39: longer label ("Search other CEOs" / "Search other officials") stays on one line; the name shrinks/ellipsizes or wraps first */
#spkbar .sbc{white-space:nowrap}
@media (max-width:360px){#spkbar{gap:6px;padding:0 10px}#spkbar .sbn{font-size:16px}#spkbar .sbc{font-size:12px}}
#spkbar:focus-visible{outline:2px solid #fff;outline-offset:-4px}
@media (prefers-reduced-motion:reduce){#spkbar,#spkbar.show{transition:none}}
.secth{scroll-margin-top:58px!important}#cloud{scroll-margin-top:88px!important}#about{scroll-margin-top:56px!important}   /* jump targets clear the bar */

.mmform{display:grid;gap:4px;max-width:520px;margin:6px 0 12px;font-family:Arial,Helvetica,sans-serif}.mmform label{font-size:13px;font-weight:700;color:#f3eee4;margin-top:6px}.mmform .opt{font-weight:400;color:var(--muted)}.mmform input:not([type=checkbox]),.mmform textarea{font:16px/1.35 Arial,Helvetica,sans-serif;color:#f3eee4;background:#0b0b0b;border:1px solid #3a3733;border-radius:6px;padding:9px 11px;width:100%;box-sizing:border-box}.mmform textarea{resize:vertical;min-height:96px}.mmform input:focus,.mmform textarea:focus{outline:2px solid #ff5449;outline-offset:1px;border-color:#ff5449}.mmform button{justify-self:start;margin-top:10px;min-height:44px;padding:0 24px;border:0;border-radius:8px;background:#ff5449;color:#fff;font:700 16px Arial,Helvetica,sans-serif;cursor:pointer}.mmform button:hover{background:#ff6b61}.mmform button:disabled{opacity:.6;cursor:default}.mmform button:focus-visible{outline:2px solid #fff;outline-offset:2px}.mmform .mmhp{position:absolute!important;left:-9999px!important;width:1px;height:1px;opacity:0}.mmform .fmsg{margin:6px 0 0;min-height:1.2em;font-size:14px;color:#f3eee4}.mmform .fmsg.ok{color:#85bb65}.mmform .fmsg.err{color:#ff5449}@media (max-width:640px){.mmform button{width:100%}}
#about h4.abcontact{font:700 16px/1.2 Arial,Helvetica,sans-serif;color:#f3eee4;margin:14px 0 0}
/* ---- mm24 minimalist pass: fewer borders/labels/decoration, readable sizes (>=14px body on phones), Arial, black/cream/red/green ---- */
#cats button .ci,header .hview .vcard svg,header .hview .vcard .vt small{display:none!important}body #cats button.cat{grid-template-columns:1fr!important;column-gap:0!important}body #picker #cats .ct small{grid-column:1/-1!important}@media (max-width:480px){body #picker #cats .ct b{white-space:normal!important;font-size:14px!important;line-height:1.1!important;overflow-wrap:anywhere}}@media (max-width:379px){body .tbwrap td.w{overflow-wrap:anywhere}body .tbwrap th.barc{min-width:36px;width:36px}}@media (max-width:480px){body .tbwrap th.barc{letter-spacing:0!important;padding-left:4px!important;padding-right:2px!important;font-size:11px!important}}@media (max-width:480px){body #tfbar{flex-wrap:wrap!important;row-gap:8px!important}body #tfbar .yrs{flex:1 1 0!important;min-width:0!important;order:0!important}body #tfbar #docPick{flex-basis:100%;order:5}}   /* phones: All · None · years on one row, Choose documents below */   /* decorative icons + "Ranked table"/"Bigger = said more" */
body .pk.pcoll #pdisc .pdg{display:none!important}body .pk.psolo #persons button.chip.on::before{content:none!important;display:none!important}   /* "CEO"/"FED CHAIR" repeat the tab */
body #stats .stat{border:0!important}   /* boxes inside a bordered card: background only */
#more:not(.lim),.cloudwrap .cloud-bar{display:none!important}   /* the stats row already says how many words are shown */
#words h1#personTitle .ft{color:var(--muted)!important}
@media (max-width:640px){
 #personMeta{font-size:14px!important}#words h1#personTitle .ft{font-size:14px!important}
 #tfbar .chip,#tfbar button,#docPick summary,#docList,#words .controls label{font-size:14px!important}
 #cats button b{font-size:15px!important}#cats button small{font-size:13px!important}
 .mmform label{font-size:14px!important}#method{font-size:13px!important}
 th,th.num{font-size:12px!important}}

/* ---- Mouth Math / Word Cloud tabs (mm24): right under the red stats; tapping swaps the view in place (no scrolling).
   From 1100px wide both views sit side by side (table left, cloud right) and the tabs are hidden. ---- */
#vtabs{display:flex;gap:14px;margin:16px 4px 14px}
#vtabs button{--vc:var(--num-red);flex:1;min-height:46px;padding:10px 8px;font:700 16px/1.2 Arial,Helvetica,sans-serif;color:var(--vc);background:#0b0b0b;
 border:2px solid var(--vc);border-radius:6px;outline:2px solid color-mix(in srgb,var(--vc) 45%,transparent);outline-offset:3px;cursor:pointer;transition:background-color .15s}
#vtabs button[data-view="cloud"]{--vc:var(--num-red)}   /* mm32: no green; Word Cloud matches Mouth Math */
#vtabs button:hover{background:color-mix(in srgb,var(--vc) 12%,#0b0b0b)}
#vtabs button[aria-selected="true"]{color:#fff;background:color-mix(in srgb,var(--vc) 34%,#0b0b0b);outline-color:var(--vc)}
#vtabs button:focus-visible{outline:2px solid #fff}
/* mm30: selected states match. Mouth Math / Word Cloud tabs use the category buttons' look: unselected = card black, thin #2c2a27 border, text in
   the tab's identity color (red / green); selected = the category's warm red-gray (#a8807a since mm35; was #9a958c), dark text, a 3px identity-color underline
   (like the category's red underline). The old outer rings are gone; (mm32: Word Cloud now uses red too; the first-visit fade hint is gone.) */
#vtabs button{background:var(--card);border:1px solid var(--rule);border-radius:4px;outline:none;color:var(--vc);transition:border-color .15s,background-color .15s}
#vtabs button:hover{background:#171717;border-color:#5a5650}
#vtabs button[aria-selected="true"],#vtabs button[aria-selected="true"]:hover{background:#a8807a;border-color:#a8807a;color:#0b0b0b;box-shadow:inset 0 -3px 0 var(--vc)}
#vtabs button:focus-visible{outline:2px solid #fff;outline-offset:2px}
#cloud.live span:focus-visible{outline:2px solid #fff}   /* mm32: no green focus ring on cloud words */
/* mm39: Mouth Math / Word Cloud tabs: content-sized pair (equal widths), left-aligned with the stats, comfortable padding, 46px tall */
#vtabs{display:flex;justify-content:flex-start;gap:10px;margin-left:0;margin-right:0;width:auto}   /* mm39: full-width row (inherits), content-sized equal tabs left-aligned */
#vtabs button{flex:0 0 auto;width:9.6em;padding:10px 14px;white-space:nowrap;box-sizing:border-box}
@media (max-width:359px){#vtabs button{width:8.6em;padding:10px 10px;font-size:15px}}
#vpanes{position:relative}
#vpanes.tab-math #vCloud,#vpanes.tab-cloud #vMath{position:absolute;top:0;left:0;right:0;height:0;overflow:hidden;visibility:hidden;pointer-events:none}   /* the other view stays laid out (zero height, invisible), so a tap swaps instantly */
#vpanes .secth{display:none}   /* the tabs already name the view */
#vpanes #vMath .tbwrap{margin-top:4px}
aside.ad[data-slot="between"]{margin:22px auto 4px}
@media (min-width:1100px){
 #vtabs{display:none}
 #vpanes{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:26px;align-items:start}
 #vpanes>.vpane{position:static!important;height:auto!important;overflow:visible!important;visibility:visible!important;pointer-events:auto!important}
 #vpanes .secth{display:block;margin:20px 0 10px!important}
 #vpanes>#vCloud{position:sticky!important;top:12px}body.sbar #vpanes>#vCloud{top:58px}   /* the cloud stays in view next to a long table */
}

/* ---- Documents quick-select (All / None / years) as light text buttons (mm24): no fill, cream Arial 15px, thin cream outline when selected;
   the year fade only appears when the years really overflow (.ovf, set in JS) ---- */
body #tfbar button.chip,body #tfbar label.chip{background:transparent!important;color:#f3eee4!important;border:1px solid transparent!important;box-shadow:none!important;
 font:400 15px/1.2 Arial,Helvetica,sans-serif!important;padding:6px 9px!important;min-height:34px!important;border-radius:5px!important;position:relative}
body #tfbar button.chip:hover,body #tfbar label.chip:hover{border-color:rgba(243,238,228,.28)!important}
body #tfbar button.chip.on,body #tfbar label.chip.on{border-color:rgba(243,238,228,.6)!important;font-weight:700!important}
body #tfbar label.chip .muted{color:#a9a397!important;font-size:13px!important;font-weight:400}
body #tfbar #years input{position:absolute;opacity:0;width:1px;height:1px;margin:0}
body #tfbar #years label.chip:focus-within,body #tfbar button.chip:focus-visible{outline:2px solid #f3eee4;outline-offset:1px}
body #tfbar .yrs{-webkit-mask-image:none!important;mask-image:none!important;padding-right:0!important;gap:4px!important}
body #tfbar .yrs.ovf{-webkit-mask-image:linear-gradient(90deg,#000 85%,transparent)!important;mask-image:linear-gradient(90deg,#000 85%,transparent)!important;padding-right:18px!important}
body #tfbar{gap:6px!important}

/* mm30: the Fed Chairman page uses the same "From the mouth of <name>" line as CEOs and US Government (the mm25 "What the Fed Said" label is gone) */

/* ---- mm26: documents controls folded into one compact "Choose documents" link under the red stats (white Choose, red documents,
   white triangle; tapping the docs stat opens it too). Opens a bottom sheet on phones, a popover on wider screens, holding
   All / None / years and the document list. ---- */
body #tfbar{display:block!important;margin:8px 0 0!important;position:relative;min-height:0}
body #tfbar #docPick{display:inline-block;margin:0!important;padding:0;border:0}
body #tfbar #docPick>summary{display:inline-flex!important;align-items:center;min-height:32px!important;padding:4px 2px!important;border:0!important;background:none!important;
 box-shadow:none!important;font:700 15px/1.2 Arial,Helvetica,sans-serif!important;color:var(--num-red)!important;list-style:none;cursor:pointer;white-space:nowrap}
body #tfbar #docPick>summary::-webkit-details-marker{display:none}
body #tfbar #docPick>summary{gap:0!important;justify-content:flex-start!important;width:auto!important;flex:none!important}body #tfbar #docPick>summary>*{margin-left:0;flex:none}
body #docPick .dsx{font-size:30px!important;line-height:1!important;padding:0!important}
@media (min-width:1100px){body #tfbar{margin-bottom:12px!important}}
body #tfbar #docPick>summary::before{display:none!important}
body #tfbar #docPick>summary::after{content:"\25BE"!important;color:#fff!important;font-size:17px!important;line-height:1!important;margin-left:6px}
body #tfbar #docPick[open]>summary::after{content:"\25B4"!important}
body #tfbar #docPick>summary .dpc{color:#fff!important;margin-right:5px}
body #tfbar #docPick>summary:hover{text-decoration:underline;text-underline-offset:3px;background:none!important}
body #tfbar #docPick>summary:focus-visible{outline:2px solid #fff;outline-offset:2px}
body #tfbar #docPick[open]>summary{background:none!important;color:var(--num-red)!important;margin:0!important}
#docPick .dsback{position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,.6)}
#docPick .dsheet{position:fixed;left:0;right:0;bottom:0;z-index:1001;max-height:min(80vh,640px);overflow:auto;overscroll-behavior:contain;background:#121212;
 border-top:1px solid #3a3733;border-radius:14px 14px 0 0;padding:0 16px calc(16px + env(safe-area-inset-bottom));box-shadow:0 -10px 30px rgba(0,0,0,.6)}
#docPick .dshead{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;padding:10px 0 8px;background:#121212}
#docPick .dshead b{font:700 16px/1.2 Arial,Helvetica,sans-serif;color:#f3eee4}
#docPick .dsx{background:none;border:0;color:#f3eee4;font:400 28px/1 Arial,Helvetica,sans-serif;width:44px;height:44px;margin-right:-12px;cursor:pointer}
#docPick .dsx:focus-visible{outline:2px solid #fff;outline-offset:-4px}
#docPick .dsq{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin:0 0 10px}
body #docPick .dsq .yrs{flex:1 1 auto!important;min-width:0!important;order:0!important}
body #docPick .dsheet .speeches{max-height:none!important;overflow:visible!important;margin:0!important}
html.dsopen,html.dsopen body{overflow:hidden}
/* mm32 docs button (variant B): full-width outlined button under the red stats; the docs stat gets a small ▾ cue */
body #tfbar #docPick{display:block!important;width:100%;max-width:560px}   /* mm32: capped on wider screens, left-aligned under the stats */
body #tfbar #docPick>summary.dbtn{display:flex!important;flex-direction:column;align-items:stretch;gap:3px!important;width:100%!important;box-sizing:border-box;min-height:48px!important;
 padding:10px 14px!important;border:1px solid #6f6a62!important;border-radius:4px;background:#0f0f0f!important;white-space:normal;text-decoration:none!important;justify-content:center!important}
body #tfbar #docPick>summary.dbtn::after,body #tfbar #docPick>summary.dbtn::before{display:none!important;content:none!important}
body #tfbar #docPick>summary.dbtn:hover{border-color:#f3eee4!important;background:#151515!important}
body #tfbar #docPick[open]>summary.dbtn{border-color:#f3eee4!important}
#docPick .dbl1{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:2px 12px}

#docPick .dbn{font:700 17px/1.2 Arial,Helvetica,sans-serif;color:var(--num-red)}
#docPick .dbv{font:700 15px/1.2 Arial,Helvetica,sans-serif;color:#f3eee4;white-space:nowrap}#docPick .dbv::after{content:" \25BE";font-size:15px}#docPick[open] .dbv::after{content:" \25B4"}
#docPick .dbl2{font:400 13px/1.3 Arial,Helvetica,sans-serif;color:#8f897f;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
body #stats .stat:first-child .sl::after{content:" \25BE"}@media (max-width:640px){body #stats .stat:first-child .sl::after{content:attr(data-s) " \25BE"!important}}
body #stats .stat:first-child .sl{text-decoration:underline dotted #ff544988;text-underline-offset:3px}
#stats .stat:first-child{cursor:pointer}#stats .stat:first-child:focus-visible{outline:2px solid #fff;outline-offset:2px}
@media (min-width:641px){
 #docPick .dsback{background:transparent}
 #docPick .dsheet{position:absolute;left:0;right:auto;bottom:auto;top:calc(100% + 6px);width:min(580px,calc(100vw - 40px));max-height:min(70vh,560px);
  border:1px solid #3a3733;border-radius:8px;padding:0 16px 14px;box-shadow:0 12px 32px rgba(0,0,0,.7)}
}

/* mm28: with "Hide common stopwords" unchecked, stopwords (the, and, to ...) are italic in the table and the cloud */
#tb tr.stop td.w,#cloud span.stop{font-style:italic}

/* mm28: common words (stopwords) that would rank in the top N sit at the bottom of the table in faint gray italics with their real rank;
   "View words in actual order" (right below) turns Hide common stopwords off and puts them back in place */
#tb tr.tail td{color:#7d776d!important;font-weight:400!important}#tb tr.tail td.w{font-style:italic}#tb tr.tail .rr{font-style:normal;font-size:.86em;color:#6c675e}
#tb tr.tail td.cnt{color:#8a5550!important}
#tb tr.cwl td{color:#7d776d!important;font-weight:400!important;font-style:italic;cursor:pointer;padding-top:12px;padding-bottom:12px;user-select:none}#tb tr.cwl:hover td{background:#1a1919}#tb tr.cwl:focus-visible{outline:2px solid #7d776d;outline-offset:-2px}
.rsrow{display:flex;align-items:center;gap:8px;margin:12px 2px 4px;font:400 15px/1.3 Arial,Helvetica,sans-serif;color:#f3eee4;cursor:pointer}
.rsrow[hidden]{display:none}.rsrow input{width:18px;height:18px;accent-color:var(--num-red);margin:0}
/* mm33: Back to top button at the end of About: outlined like the docs button (cream Arial text, thin gray border), 44px tap target; shown even when About is collapsed on phones */
#about .abtop{margin:14px 0 2px;max-width:none}
#about .totop{display:inline-flex;align-items:center;gap:8px;min-height:44px;min-width:44px;padding:0 16px;font:700 15px/1 Arial,Helvetica,sans-serif;color:#f3eee4;background:transparent;border:1px solid #6f6a62;border-radius:4px;cursor:pointer;-webkit-tap-highlight-color:transparent;touch-action:manipulation}
#about .totop .tri{font-size:24px;line-height:0;color:#fff}
#about .totop:hover{border-color:#f3eee4}
#about .totop:active{background:rgba(243,238,228,.08)}
#about .totop:focus-visible{outline:2px solid #fff;outline-offset:2px}
#about:not(.open)>.abtop{display:block;margin-top:8px}
/* mm33: category buttons (Fed Chairman / CEOs / US Government) text ~20% bigger, name and count; phones may wrap "US Government" to two lines */
body #picker #cats .ct b{font-size:17.4px!important}body #picker #cats .ct small{font-size:13.8px!important}   /* was 14.5 / 11.5 */
@media (max-width:640px){body #picker #cats .ct b{font-size:18px!important}body #picker #cats .ct small{font-size:15.6px!important}}   /* was 15 / 13 */
@media (max-width:480px){body #picker #cats .ct b{font-size:16.8px!important;overflow-wrap:normal!important;word-break:normal!important}   /* was 14 / 13 */
 body #picker #cats.seg{grid-template-columns:repeat(3,minmax(min-content,1fr))!important}   /* equal widths when they fit; else the widest word ("Government") gets room instead of breaking mid-word */
 body #picker #cats .ct small{white-space:normal!important}}
@media (max-width:360px){body #cats button{padding:6px 7px!important}}
/* mm37: in the excerpts panel every occurrence of the selected word is red bold; the first occurrence glows softly 3 slow times
   (about 5 s) and then stays steady red. Only inside #pop (the cloud's #1 word never pulses). No glow with reduced motion. */
#pop mark{background:transparent!important;color:#ff5449!important;font-weight:700!important;padding:0!important;border-radius:0!important}
@keyframes mmExGlow{0%,100%{text-shadow:0 0 0 rgba(255,84,73,0)}50%{text-shadow:0 0 6px rgba(255,84,73,.9),0 0 16px rgba(255,84,73,.5)}}
#pop ol:first-of-type>li:first-child mark:first-of-type{animation:mmExGlow 1.8s ease-in-out 3}
#pop.noglow mark{animation:none!important}
@media (prefers-reduced-motion:reduce){#pop mark{animation:none!important}}
/* mm38: the Word Cloud #1 word = red word + a thin red contour that follows the letter shapes (one thin red line), no pill rings, no pulse.
   Live cloud: drawn on the p5 canvas; static / reduced-motion cloud: the same contour as the span's ::before background image. */
#cloud span.top::before,#cloud span.top::after{display:none}
#cloud:not(.live) span.top.ctr::before{display:block;content:"";position:absolute;pointer-events:none;inset:calc(var(--cm) * -1);border-radius:0;box-shadow:none;border:0;
 background:var(--ctr) center/100% 100% no-repeat}
#cloud:not(.live) span.top:hover::before,#cloud:not(.live) span.top.active::before{background-color:transparent}
/* mm50: high-tech red-and-black buttons (option B "red glow"): dark beveled black, selected = red border + red text + soft red glow; no pink */
body #cats button.cat,body #vtabs button{background:linear-gradient(180deg,#1a1a1a,#0c0c0c);border:1px solid #2a2a2a;border-radius:12px;box-shadow:inset 0 1px 0 rgba(255,255,255,.07),0 4px 12px rgba(0,0,0,.7);transition:border-color .15s,box-shadow .15s,color .15s}
body #cats button.cat{color:#d9d3ca}body #cats button.cat .ct small{color:#8d8380}
body #cats button.cat:hover,body #vtabs button:hover{border-color:#5a3532;background:linear-gradient(180deg,#1d1515,#0e0a0a)}
body #cats button.cat.on,body #cats button.cat.on:hover,body #vtabs button[aria-selected="true"],body #vtabs button[aria-selected="true"]:hover{background:radial-gradient(120% 140% at 50% 0%,#2a0d0b 0%,#120606 60%,#0a0505 100%);border-color:#ff5449;color:#ff5449;box-shadow:inset 0 0 18px rgba(255,84,73,.28),0 0 0 1px rgba(255,84,73,.35),0 0 22px rgba(255,84,73,.35)}
body #cats button.cat.on .ct small{color:#e9a29c}
/* mm51: Latest/All and Mouth Math/Word Cloud share the same dimensions: two equal full-width buttons, same height, gap and font */
@media (min-width:641px){body #vtabs button{height:44px;min-height:44px;font-size:15px}}
@media (max-width:389px){body #vtabs button{font-size:14.5px;padding:0 6px}}
@media (max-width:349px){body #vtabs button{font-size:12.5px;padding:0 4px}}
body #vtabs{scroll-margin-top:62px}   /* mm52: clears the sticky speaker bar when tabs scroll to the top */
/* mm55: toned-down red: bright red only on logo, speaker name, stats and #1 word */
body #cats button.cat.on,body #cats button.cat.on:hover,body #vtabs button[aria-selected="true"],body #vtabs button[aria-selected="true"]:hover{border-color:#9c3f39!important;color:#f3eee4!important;background:linear-gradient(180deg,#221515,#120b0b)!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 0 0 1px rgba(156,63,57,.3),0 0 14px rgba(255,84,73,.16)!important}
body #cats button.cat.on b{color:#f3eee4!important}body #cats button.cat.on .ct small{color:#c9a9a4!important}
body #vtabs button{color:#d9d3ca!important}body #vtabs button[aria-selected="true"]{color:#f3eee4!important}
body #persons button.chip.on,body .sbn{color:#f3eee4!important}
body .dbn,body .dbl1,body summary.dbtn{color:#f3eee4!important}body .dl1 .date{color:#c9a9a4!important}body button.only{color:#c9a9a4!important}
body button.nchip{color:#d9d3ca!important;border-color:#4a3432!important}
body button.nchip.on,body button.nchip[aria-pressed="true"]{background:#5c2724!important;border-color:#9c3f39!important;color:#fff!important}
body div.bar{background:linear-gradient(90deg,#8e3833,#5e2724)!important}
body td.num.cnt{color:#d7a8a2!important}
body tr.top td.num.cnt,body .top td.num.cnt{color:#ff5449!important}
/* mm56: tagline under the logo, white */
body header .brand{flex-direction:column!important;align-items:flex-start!important;flex-wrap:nowrap!important;gap:0!important}
body header .tagline{margin:6px 0 0;padding:0;color:#bbb;text-shadow:0 0 6px rgba(200,40,60,.25),0 0 12px rgba(140,80,220,.12);font:400 14px/1.1 Arial,Helvetica,sans-serif;letter-spacing:-.01em;white-space:nowrap}
@media (max-width:640px){body header .tagline{font-size:13px;margin-top:4px}}
/* mm57: tagline starts under the M of MOUTH; bigger white close × */
body header{--th:49px}
@media (max-width:1239px) and (min-width:641px){body header{--th:42px}}
@media (max-width:640px){body header{--th:var(--lh)}}
body header .tagline{margin-left:calc(var(--th) * 1.259 - .07em)!important}
#pop .x{color:#fff!important;font-size:32px!important;width:44px;height:44px;display:inline-flex;align-items:center;justify-content:center;margin:-10px -10px -10px 0}
body #docPick .dsx{color:#fff!important;font-size:38px!important}
/* mm58: stats sit right above the Super tabs; the tab jump lands on the stats */
body #stats{scroll-margin-top:12px;margin-top:10px}
/* mm58: selected person chip was cream-on-cream; dark with a soft red edge like the other selected buttons */
body #persons button.chip.on,body #persons button.chip.on:hover{background:linear-gradient(180deg,#221515,#120b0b)!important;border-color:#9c3f39!important;color:#f3eee4!important}
/* mm58: close × tucked further into the corner, a bit smaller, deliberately not level with the title */
#pop .x{font-size:28px!important;position:relative;top:-9px;right:-7px}
body #docPick .dsx{font-size:34px!important;position:relative;top:-10px;right:-6px}
/* mm59: Word Cloud #1 word = white with a soft red glow (no red contour) */
#cloud span.top{color:#ff5449!important;text-shadow:none!important}   /* mm60: plain red #1 word */
/* mm63: every white triangle is the same medium size (24px glyph), between the old small (11-17px) and big (30-33px) ones */
body .pk.pcoll #pdisc .pda::after{font-size:24px!important;line-height:1!important}body #spkbar .sba::after{font-size:0!important;line-height:0!important;width:15px!important;height:15px!important}
body #docPick .dbv::after,body #tfbar #docPick>summary::after,body #aboutToggle.abtog::after,body .tftog::after{font-size:24px!important;line-height:0!important;vertical-align:-3px;color:#fff}
body #stats .stat:first-child .sl::after{content:none!important}
@media (max-width:640px){body #stats .stat:first-child .sl::after{content:attr(data-s)!important}}
body #stats .stat:first-child b::after{content:" \25BE";color:#fff;font-size:24px;line-height:0;vertical-align:-2px}
body .sarr{font-size:24px!important;line-height:0;vertical-align:-3px;color:#fff}
body #persons button.chip.on,body #persons button.chip.on:hover{background:linear-gradient(180deg,#e0453b,#a3271f)!important;border-color:#ff7a70!important;color:#fff!important;box-shadow:0 0 14px rgba(255,84,73,.45),inset 0 1px 0 rgba(255,255,255,.25)!important;text-shadow:0 1px 1px rgba(0,0,0,.35)}   /* mm71: the selected speaker is unmistakable */
/* mm71: Word Race tab */
#vpanes.tab-math>#vRace,#vpanes.tab-cloud>#vRace,#vpanes.tab-ring>#vRace{display:none!important}#vpanes:not(.tab-ring)>#vRing{display:none!important}#vpanes.tab-ring>#vMath,#vpanes.tab-ring>#vCloud{display:none!important}@media (min-width:1100px){#vpanes.tab-ring{display:block!important}}
#vpanes.tab-race>#vMath,#vpanes.tab-race>#vCloud{display:none!important}
@media (min-width:1100px){#vpanes.tab-race{display:block!important}}
.racewrap{background:#121010;border:1px solid #3a2c2a;border-radius:10px;padding:16px 14px 14px}
.racewrap .rdate{font:700 34px/1.05 Arial,Helvetica,sans-serif;letter-spacing:-.03em;color:#ff5449}
.racewrap .rttl{color:#a49e93;font-size:14px;line-height:1.3;margin:4px 0 8px;min-height:36px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
#race .rrow{transition:transform .9s ease,opacity .6s ease}#race .rb{fill:#7a2a25;transition:width .9s ease}#race .rb.top{fill:#ff5449}
#race text{font-family:Arial,Helvetica,sans-serif;font-weight:700;font-size:17px}#race .rw{fill:#f3eee4}#race .rn{fill:#ff5449;transition:x .9s ease}
.racewrap .rplay{margin-top:6px;height:44px;padding:0 18px;border-radius:12px;border:1px solid #9c3f39;background:linear-gradient(180deg,#1a1a1a,#0c0c0c);color:#ff5449;font:700 15px Arial,Helvetica,sans-serif;cursor:pointer}
@media (prefers-reduced-motion:reduce){#race .rrow,#race .rb,#race .rn{transition:none}}
#cloud:not(.live) span.top.ctr::before{display:none!important}
.rplay .rtri{font-size:24px;line-height:0;vertical-align:-2px}
body #nbar .nchip{font-size:12px!important}@media (max-width:640px){body #nbar .nchip{font-size:12.5px!important}}
html,body{background-color:var(--bg);background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='520' height='520' viewBox='0 0 520 520' fill='none' stroke='%23c8504a' stroke-opacity='.13' stroke-width='1'%3E%3Cpath d='M-20 90C60 40 140 130 230 80S400 20 540 70'/%3E%3Cpath d='M-20 120C70 75 150 160 240 112S410 55 540 100'/%3E%3Cpath d='M-20 150C80 112 160 190 250 146S420 90 540 132'/%3E%3Cpath d='M-20 300C90 260 170 340 270 290S430 240 540 280'/%3E%3Cpath d='M-20 332C95 296 180 372 280 324S440 276 540 312'/%3E%3Cpath d='M-20 470C80 430 170 500 270 455S430 420 540 450'/%3E%3Cpath d='M-20 500C85 465 175 530 275 488S435 455 540 482'/%3E%3Cellipse cx='390' cy='205' rx='70' ry='34'/%3E%3Cellipse cx='390' cy='205' rx='44' ry='20'/%3E%3Cellipse cx='390' cy='205' rx='18' ry='8'/%3E%3Cellipse cx='120' cy='395' rx='62' ry='30'/%3E%3Cellipse cx='120' cy='395' rx='36' ry='16'/%3E%3C/svg%3E");background-size:520px 520px;background-attachment:scroll}
/* mm77: the three views as colorful 3D buttons */
html body #vtabs{gap:12px;margin-top:18px;margin-bottom:18px}
html body #vtabs button{--c1:#a8403a;--c2:#7a1f1c;--c3:#45100e;height:56px!important;min-height:56px!important;border-radius:14px!important;border:1px solid rgba(255,255,255,.28)!important;
 background:linear-gradient(180deg,var(--c1) 0%,var(--c2) 62%,var(--c3) 100%)!important;color:#fff!important;font:800 16px/1 Arial,Helvetica,sans-serif!important;letter-spacing:-.01em;
 text-shadow:0 1px 2px rgba(0,0,0,.45);box-shadow:inset 0 2px 0 rgba(255,255,255,.35),inset 0 -3px 0 rgba(0,0,0,.25),0 5px 0 var(--c3),0 9px 16px rgba(0,0,0,.55)!important;
 transform:translateY(-3px);opacity:.88;filter:saturate(.85);transition:transform .12s,box-shadow .12s,opacity .15s,filter .15s}
html body #vtabs button[data-view="cloud"]{--c1:#c99a52;--c2:#9a6b2a;--c3:#563811}
html body #vtabs button[data-view="race"]{--c1:#8f9a5c;--c2:#5f6b34;--c3:#323a17}
html body #vtabs button:hover{opacity:.9;filter:none}
html body #vtabs button[aria-selected="true"],html body #vtabs button[aria-selected="true"]:hover{opacity:1;background:linear-gradient(180deg,var(--c1) 0%,var(--c2) 62%,var(--c3) 100%)!important;border-color:#fff!important;color:#fff!important;filter:none;transform:translateY(0);
 box-shadow:inset 0 2px 0 rgba(255,255,255,.4),inset 0 -3px 0 rgba(0,0,0,.25),0 2px 0 var(--c3),0 0 0 2px #fff,0 0 22px var(--c2)!important}
html body #vtabs button:active{transform:translateY(2px)}
@media (min-width:641px){html body #vtabs button{height:54px!important;min-height:54px!important;font-size:17px!important}}
@media (max-width:389px){html body #vtabs button{font-size:14.5px!important}}
@media (prefers-reduced-motion:reduce){html body #vtabs button{transition:none}}
/* mm79: techie glow on the view buttons */
html body #vtabs button{position:relative;overflow:hidden;
 background:repeating-linear-gradient(0deg,rgba(255,255,255,.045) 0 1px,transparent 1px 3px),linear-gradient(180deg,var(--c1) 0%,var(--c2) 62%,var(--c3) 100%)!important;
 border:1px solid color-mix(in srgb,var(--c1) 70%,#fff)!important}
html body #vtabs button[aria-selected="true"],html body #vtabs button[aria-selected="true"]:hover{
 background:repeating-linear-gradient(0deg,rgba(255,255,255,.06) 0 1px,transparent 1px 3px),linear-gradient(180deg,var(--c1) 0%,var(--c2) 62%,var(--c3) 100%)!important;
 border-color:color-mix(in srgb,var(--c1) 40%,#fff)!important;
 box-shadow:inset 0 0 0 1px rgba(255,255,255,.25),inset 0 0 14px color-mix(in srgb,var(--c1) 60%,transparent),0 2px 0 var(--c3),0 0 0 1px color-mix(in srgb,var(--c1) 80%,#fff),0 0 14px var(--c1),0 0 30px color-mix(in srgb,var(--c1) 55%,transparent)!important;
 text-shadow:0 0 8px rgba(255,255,255,.55),0 1px 2px rgba(0,0,0,.5)}
html body #vtabs button::after{content:"";position:absolute;top:0;bottom:0;left:-60%;width:40%;pointer-events:none;
 background:linear-gradient(100deg,transparent,rgba(255,255,255,.22),transparent);transform:skewX(-20deg);opacity:0}
html body #vtabs button[aria-selected="true"]::after{opacity:1;animation:vsweep 3.6s ease-in-out infinite}
@keyframes vsweep{0%{left:-60%}45%,100%{left:130%}}
@media (prefers-reduced-motion:reduce){html body #vtabs button[aria-selected="true"]::after{animation:none;opacity:0}}
/* mm82: slow-blinking white dot beside the selected speaker */
.pk.pcoll #pdisc .pdn::before,body #persons button.chip.on::before{content:"";display:inline-block;width:12px;height:12px;border-radius:50%;background:#fff;margin-right:9px;vertical-align:.08em;box-shadow:0 0 7px rgba(255,255,255,.85);animation:spkdot 2.35s ease-in-out infinite}
@keyframes spkdot{0%{opacity:1;outline:1.5px solid rgba(255,255,255,.9);outline-offset:0}10%{outline-color:rgba(255,255,255,.85);outline-offset:1px}75%,100%{opacity:1;outline:1.5px solid rgba(255,255,255,0);outline-offset:9px}}
@media (prefers-reduced-motion:reduce){.pk.pcoll #pdisc .pdn::before,body #persons button.chip.on::before{animation:none}}
/* mm83: unselected view buttons grayed out */
html body #vtabs button[aria-selected="false"]{filter:grayscale(.8) brightness(.62)!important;opacity:.8!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.12),0 3px 0 var(--c3),0 6px 10px rgba(0,0,0,.5)!important}
html body #vtabs button[aria-selected="false"]:hover{filter:grayscale(.4) brightness(.8)!important;opacity:.95!important}
/* mm84: selected view = red, others = gingerbread gray */
html body #vtabs button[aria-selected="true"]{--c1:#c24a42;--c2:#8a2420;--c3:#4a100e}
html body #vtabs button[aria-selected="false"],html body #vtabs button[aria-selected="false"]:hover{--c1:#6e625a;--c2:#4a3f39;--c3:#2a221e;filter:none!important;opacity:1!important;color:#d8cdc3!important;text-shadow:0 1px 1px rgba(0,0,0,.5)}
html body #vtabs button[aria-selected="false"]:hover{--c1:#7c6e64;--c2:#56483f}
/* mm87: longer search hint wraps instead of squeezing the name */
@media (max-width:640px){html body .pk.pcoll #pdisc .pdn{overflow-wrap:normal;word-break:normal}}
/* mm90: Word Ring tab + 2x2 view buttons on phones */
#ringWord{text-align:right;font:700 30px/1.08 Arial,Helvetica,sans-serif;color:#ff5449;text-shadow:0 0 18px rgba(255,84,73,.6);padding:0 12px 5px;min-height:1.08em;cursor:pointer;user-select:none}@media (max-width:559px){#ringWord{font-size:28px;padding:0 10px 4px}}#vRing .ringwrap{background:#0b0b0b;border:1px solid var(--rule);border-radius:12px;overflow:hidden}
#ring{display:block;width:100%;height:min(78vh,640px);touch-action:manipulation}
@media (max-width:640px){#ring{height:min(62vh,440px)}}
/* mm96: tiny animated previews inside the view buttons */
html body #vtabs button{display:flex!important;align-items:center;justify-content:center;gap:8px}
#vtabs .vic{flex:none;width:34px;height:26px;overflow:visible}
#vtabs .vic *{transform-box:fill-box}
#vtabs .vr rect{animation:vrA 3s ease-in-out infinite}#vtabs .vr rect:nth-child(2){animation-name:vrB}#vtabs .vr rect:nth-child(3){animation-name:vrC}
@keyframes vrA{0%,30%{transform:translateY(0)}45%,80%{transform:translateY(7px)}95%,100%{transform:translateY(0)}}
@keyframes vrB{0%,30%{transform:translateY(0)}45%,80%{transform:translateY(-7px)}95%,100%{transform:translateY(0)}}
@keyframes vrC{0%,100%{transform:scaleX(1)}50%{transform:scaleX(1.3)}}
#vtabs .vr rect{transform-origin:left center}
#vtabs .vc rect{animation:vcF 3.2s ease-in-out infinite}#vtabs .vc rect:nth-child(2){animation-delay:-1s}#vtabs .vc rect:nth-child(3){animation-delay:-2s}#vtabs .vc rect:nth-child(4){animation-delay:-.5s}
@keyframes vcF{0%,100%{transform:translate(0,0);opacity:1}50%{transform:translate(1.5px,-1.5px);opacity:.55}}
#vtabs .vg{animation:vgS 9s linear infinite;transform-origin:50% 50%}
@keyframes vgS{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){#vtabs .vic,#vtabs .vic *{animation:none!important}}
@media (max-width:359px){#vtabs .vic{display:none}}
@media (max-width:640px){#vtabs .vic{width:26px;height:20px}html body #vtabs button{gap:6px;padding:0 20px 0 8px!important}}
html body .pk.pcoll #pdisc .pda{margin-left:14px!important}
/* mm107: Word Ring purple blended into Mouth Math, Word Race and Word Cloud */
html body div.bar{background:linear-gradient(90deg,#6e1512,#7a3aa0)!important}
html body tr.top div.bar{background:linear-gradient(90deg,#8a1a14,#9a4fc8)!important}
#race .rb{fill:url(#rgPurp)}#race .rb.top{fill:#ff5449}#race .rn{fill:#b77ee0}
html body p.abtop{text-align:right!important;display:flex!important;justify-content:flex-end!important}
/* mm113: Word Ring palette, red with small purple accents site-wide */
:root{--pu:#a24bd0;--pu2:#7b2fa8;--pug:rgba(162,75,208,.45)}
html body header{position:relative}
html body header::after{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;background:linear-gradient(90deg,#8a1a14,#e0453b 35%,#a24bd0 75%,transparent);opacity:.85;pointer-events:none}
html body #persons button.chip.on{box-shadow:0 0 14px rgba(224,69,59,.45),0 0 26px rgba(162,75,208,.3)!important}

html body input[type="checkbox"]{accent-color:#e0453b!important}
html body input[type="search"]:focus,html body input[type="text"]:focus,html body input[type="email"]:focus,html body textarea:focus{border-color:#a24bd0!important;box-shadow:0 0 0 2px rgba(162,75,208,.35)!important;outline:none}
html body a:hover{color:#c58cf0}
html body .totop:hover,html body #about .totop:hover{border-color:#a24bd0!important;box-shadow:0 0 12px rgba(162,75,208,.35)}
html body footer{border-top:1px solid rgba(162,75,208,.35)!important}
html body #tb tbody tr:hover td{background:rgba(162,75,208,.07)!important}
html body #vtabs button[aria-selected="false"]{--c1:#2a2626!important;--c2:#151313!important;--c3:#050505!important;filter:none!important;opacity:1!important}
html body #vtabs button[aria-selected="false"]{color:#fff!important}
html body #nbar .nchip{border:1px solid rgba(255,255,255,.35)!important;min-height:34px!important;height:34px!important;min-width:40px!important;padding:0 10px!important;font-size:12px!important;background:transparent!important;box-shadow:none!important}
html body #nbar .nchip[aria-pressed="true"]{border-color:#fff!important;background:#7a1f1c!important;color:#fff!important}
html body #nbar .nchip:hover{border-color:#fff!important}
html body #nbar button.nchip[data-n]{min-height:32px!important;height:32px!important;min-width:40px!important;padding:0 10px!important;font-size:12px!important;line-height:30px!important}
/* mm121: name + title on one row, Search Other dropdown underneath */
@media (max-width:640px){html body .pk.pcoll #pdisc{display:grid!important;grid-template-columns:auto 1fr;grid-template-areas:"n t";align-items:center;column-gap:14px;text-align:left}
html body .pk.pcoll #pdisc .pdn{grid-area:n}
html body .pk.pcoll #pdisc .pdt{grid-area:t;justify-self:end;text-align:left;font:700 12px/1.25 Arial,Helvetica,sans-serif;letter-spacing:.06em;text-transform:uppercase;color:#d9c9c6;border:1px solid rgba(255,255,255,.35);border-radius:4px;padding:4px 7px;max-width:11em;font-size:11px}
html body .pk.pcoll #pdisc .pda{margin-left:0!important;display:none!important}
}
@media (max-width:640px){html body .pk.pcoll #personInfo{display:none!important}}
/* mm190 preview: Word Cloud "Select a word for more info" hint (tap-friendly wording), red-tinted gray with a soft breathing glow */
.selhint{margin:4px 0 8px;text-align:center;font:700 12px/1.3 Arial,Helvetica,sans-serif;letter-spacing:.01em;color:#c9a3a0;white-space:nowrap;animation:selBreath 2.6s ease-in-out infinite}
#vpanes .secth#superCloud+.selhint{margin-top:-4px}
#superCloud,#superMath{text-align:center}
@keyframes selBreath{0%,100%{color:#c09a97;text-shadow:0 0 0 transparent}50%{color:#e8c4c0;text-shadow:0 0 6px rgba(230,80,90,.35),0 0 12px rgba(160,90,200,.18)}}
@media (max-width:360px){.selhint{font-size:11px}}
@media (prefers-reduced-motion:reduce){.selhint{animation:none;color:#d1aca8}}
/* per-category "Search Other ..." hints (phones): white pulsing light dot, one under each category button; tapping opens that category's list */
#chints{display:none}
@media (max-width:640px){
#chints{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:2px 0 8px}
html body #chints .chint{display:flex;align-items:flex-start;justify-content:flex-start;appearance:none;background:none;border:0;margin:0;padding:7px 2px 6px 4px;box-sizing:border-box;text-align:left;cursor:pointer;
  font:700 11px/1.3 Arial,Helvetica,sans-serif;letter-spacing:.005em;color:#bdb3a8;animation:pdcTextBreath 2.35s ease-in-out infinite}
html body #chints .chint.on{color:#f3eee4}
html body #chints .chint:focus-visible{outline:2px solid #fff;outline-offset:1px;border-radius:4px}
html body #chints .chint::before{content:"";flex:none;box-sizing:border-box;width:10px;height:10px;margin:2px 6px 0 0;border-radius:50%;
  background:radial-gradient(circle at 50% 50%,#fff 0,#f7f6fc 30%,#ebe8f6 44%,rgba(190,180,220,.55) 52%,#fff 62%,#fff 100%);
  box-shadow:0 0 7px rgba(255,255,255,.85),0 0 5px rgba(210,200,235,.5);animation:chdot 2.35s ease-in-out infinite}
html body #chints .chint[aria-expanded="true"]{animation:none;color:#f3eee4}
html body #chints .chint[aria-expanded="true"]::before{content:"\25BE";width:auto;height:auto;margin:0 4px 0 0;border-radius:0;font-size:13px;line-height:1.2;color:#fff;background:none;box-shadow:none;animation:none}
@keyframes chdot{0%{outline:1.5px solid rgba(255,255,255,.95);outline-offset:0}10%{outline-color:rgba(255,255,255,.9);outline-offset:1px}75%,100%{outline:1.5px solid rgba(255,255,255,0);outline-offset:8px}}
@media (prefers-reduced-motion:reduce){html body #chints .chint{animation:none;color:#f3eee4}html body #chints .chint::before{animation:none}}
}
@keyframes pdcTextBreath{
  0%,100%{color:#e8e2d8;text-shadow:0 0 0 transparent}
  45%{color:#fff;text-shadow:0 0 5px rgba(255,255,255,.4),0 0 10px rgba(255,255,255,.18)}
  55%{color:#fff;text-shadow:0 0 6px rgba(255,255,255,.45),0 0 12px rgba(255,255,255,.2)}
}

#pbio{margin:8px 0 2px;font:14px/1.5 Arial,Helvetica,sans-serif;color:var(--ink)}#pbio summary{cursor:pointer;font-weight:700;font-size:13px;color:var(--muted);min-height:32px;display:flex;align-items:center;gap:6px}#pbio p{margin:4px 0 6px;max-width:68ch}#pbio a{font-size:13px;font-weight:700;color:var(--ink)}
html body .rfoot{display:flex;align-items:center;gap:18px;margin-top:10px;flex-wrap:wrap}
html body .rfoot .rplay{margin-top:0!important;flex:none}
html body .rfoot .rNew,html body .vfoot .rNew{font:700 14px/1.2 Arial,Helvetica,sans-serif;color:#f3eee4;text-decoration:none}
html body .rfoot .rNew .rtri,html body .vfoot .rNew .rtri{font-size:20px;line-height:0;vertical-align:-2px;margin-left:2px;color:#fff}
html body .rfoot .rNew:hover,html body .vfoot .rNew:hover{color:#fff;text-decoration:underline}
html body .vtop .rwho{display:flex;align-items:center;min-width:0}
/* category buttons: soft red->purple outline glow on the selected one, faint glow on hover/tap */
html body #picker #cats button.cat,html body #cats button.cat{transition:border-color .2s,box-shadow .25s!important}
html body #picker #cats button.cat::before,html body #picker #cats button.cat::after,html body #cats button.cat::before,html body #cats button.cat::after{content:none!important;display:none!important}
html body #picker #cats button.cat.on,html body #picker #cats button.cat.on:hover,html body #cats button.cat.on,html body #cats button.cat.on:hover{border-color:#c4483f!important;box-shadow:0 0 0 1px rgba(150,90,220,.28),-3px 0 10px -2px rgba(255,84,73,.42),4px 0 12px -3px rgba(150,90,220,.32),inset 0 0 8px rgba(255,84,73,.10)!important}
@media (hover:hover){html body #picker #cats button.cat:not(.on):hover,html body #cats button.cat:not(.on):hover{border-color:#5a3532!important;box-shadow:0 0 8px -2px rgba(255,84,73,.22),3px 0 9px -4px rgba(150,90,220,.18)!important}}
html body #picker #cats button.cat:not(.on):active,html body #cats button.cat:not(.on):active{box-shadow:0 0 7px -2px rgba(255,84,73,.25),3px 0 8px -4px rgba(150,90,220,.18)!important}
/* docs button: stacked-doc icon feeding into a mouth + add cue */
#docPick .dbl1{align-items:center!important}
#docPick .dbico{display:inline-flex;flex:none;margin-right:8px;vertical-align:middle;filter:drop-shadow(0 0 4px rgba(150,90,220,.25))}
#docPick .dbfeed{animation:dbfeed 3.2s ease-in-out infinite}
@keyframes dbfeed{0%,35%{transform:translate(0,0);opacity:1}65%{transform:translate(13px,-1px) scale(.55);opacity:0}66%{transform:translate(0,0);opacity:0}85%,100%{transform:translate(0,0);opacity:1}}
@media (prefers-reduced-motion:reduce){#docPick .dbfeed{animation:none}}
#docPick .dbl1{justify-content:flex-start!important;column-gap:0!important}#docPick .dbl1 .dbn{padding-left:12px}#docPick .dbv::after{margin-left:5px}
html body #docPick .dbv::after{font-size:18px!important;vertical-align:-1px!important}
html body #stats .stat:first-child b::after{font-size:18px!important}
/* "Choose a view" label above the four view buttons */
html body #vtLbl{display:block;margin:6px 4px 0;font:700 11.5px/1.2 Arial,Helvetica,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#a8807a}
html body #vtLbl::after{content:"";display:block;width:26px;height:1px;margin-top:5px;background:linear-gradient(90deg,#ff5449,rgba(150,90,220,.55))}
html body #vtLbl+#vtabs{margin-top:9px}
@media (min-width:1100px){html body #vtLbl{display:none}}
/* view buttons: Mouth Math is the large main button; Word Race / Word Cloud / Word Ring sit in a compact row under "Alternative views" (below 1100px; hidden above) */
@media (max-width:1099px){
html body #vtabs{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;width:100%}
html body #vtabs button{width:auto!important;min-width:0;padding:0 6px!important;gap:6px;flex-direction:column}
html body #vtabs button[data-view="math"]{grid-column:1/-1;height:44px!important;min-height:44px!important;font-size:14px!important;padding:0 14px!important;border-radius:11px!important}
html body #vtabs button:not([data-view="math"]){height:44px!important;min-height:44px!important;font-size:12px!important;letter-spacing:0;gap:2px;border-radius:11px!important}
html body #vtabs button:not([data-view="math"]) .vic{width:20px;height:15px}
html body #vtabs .valt{grid-column:1/-1;margin:5px 2px -2px;font:700 10px/1.2 Arial,Helvetica,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#8f857c;text-align:center}
/* the main button is narrower (about 55% of the group) and centered above the three alternatives; the labels are centered over the group */
html body #vtabs button[data-view="math"]{justify-self:center;width:55%!important;min-width:150px}
html body #vtLbl{text-align:center}html body #vtLbl::after{margin-left:auto;margin-right:auto}
}
@media (min-width:641px) and (max-width:1099px){html body #vtabs button:not([data-view="math"]){flex-direction:row;height:42px!important;min-height:42px!important;font-size:13px!important;gap:7px}html body #vtabs button:not([data-view="math"]) .vic{width:22px;height:16px}html body #vtabs button[data-view="math"]{height:42px!important;min-height:42px!important}}
@media (max-width:359px){html body #vtabs button:not([data-view="math"]){font-size:11.5px!important;padding:0 3px!important}}
/* category buttons: label centered horizontally and vertically (each line when it wraps) */
html body #picker #cats button.cat{display:flex!important;align-items:center;justify-content:center;text-align:center}
html body #picker #cats button.cat .ct{flex:1 1 auto;align-items:center;justify-content:center;text-align:center}
html body #picker #cats button.cat .ct b{grid-column:auto;text-align:center}
html body .vtop .rwho b{padding:3px 0 3px 10px!important}   /* green dot + its pulse ring fully visible */
#docPick .dbl1 .dbn{margin-left:auto;font-size:14px;color:var(--num-red)}#docPick .dbv{color:#f3eee4}
html body .vtop .rwho b{font:700 22px/1.2 Arial,Helvetica,sans-serif;color:#ff5449;letter-spacing:-.015em}
html body .vtop .rwho b::before{content:"";display:inline-block;width:12px;height:12px;border-radius:50%;background:#fff;margin-right:9px;vertical-align:.08em;box-shadow:0 0 7px rgba(255,255,255,.85);animation:spkdot 2.35s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){html body .vtop .rwho b::before{animation:none}}
html body .vfoot{margin:22px 0 4px;padding-top:16px;border-top:1px solid rgba(255,255,255,.08);display:flex;align-items:center}
html body .pk.pcoll #pdisc .pdn::before,html body #persons button.chip.on::before,html body .vtop .rwho b::before{background:radial-gradient(circle at 50% 50%,#2fd23a 0,#22b52c 22%,rgba(60,200,70,.55) 32%,#fff 44%,#fff 100%)!important}

html body .dshead{display:flex!important;align-items:center}html body .dshead{position:relative}html body .dshead .dsclose2{position:absolute;right:16px;top:50%;transform:translateY(-50%);margin:0;height:32px;padding:0 12px;border:1px solid rgba(255,255,255,.35);border-radius:6px;background:transparent;color:#fff;font:700 14px Arial,Helvetica,sans-serif;cursor:pointer}
html body .dshead .dsclose2 .rtri{font-size:20px;line-height:0;vertical-align:-2px;margin-left:2px}
html body .dshead .dsclose2:hover{border-color:#fff}
html body .dshead .dsx{display:none!important}
@media (max-width:640px){html body .pk.pcoll #pdisc:has(.tk){grid-template-columns:1fr auto;grid-template-areas:"n t" "n k"}html body .pk.pcoll #pdisc:has(.tk) .pdt{justify-self:start}html body .pk.pcoll #pdisc .tk{grid-area:k;justify-self:start;margin:-2px 0 0!important}}
html body #vCloud .vfoot{padding-left:16px;padding-right:16px}
html body .vtop{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:nowrap;margin:2px 0 12px;padding:0 4px;min-height:1.4em}
html body .vtop .vhead{display:flex;align-items:center;margin:0;padding:0;min-width:0;flex:1 1 auto}
html body .vtop .vhead b{font:700 22px/1.2 Arial,Helvetica,sans-serif;color:#ff5449;letter-spacing:-.015em;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
html body .vtop .vstop{flex:none;display:inline-flex;align-items:center;gap:6px;margin:0;white-space:nowrap;font:600 14px/1.2 Arial,Helvetica,sans-serif;color:var(--ink);cursor:pointer}
html body .vtop .vstop input{margin:0;flex:none}
@media (max-width:640px){html body .vtop{gap:8px;padding:0 2px;margin-bottom:10px}
html body .vtop .vhead b{font-size:17px;letter-spacing:-.01em}
html body .vtop .vstop{font-size:12.5px;gap:5px}}
html body.view-cloud #q{display:none!important}
html body header #share{background:linear-gradient(180deg,#5a5160,#3d3542)!important;border-color:#8a7d94!important;color:#fff!important;box-shadow:none}
html body header #share:hover{background:linear-gradient(180deg,#685e70,#4a4150)!important}
/* mm184 preview: thin red-to-purple circle hint (replaces the thumbprint) in the Word Ring's center: spins with the wheel (JS sets size, position and rotation), always visible */
#vRing .ringwrap{position:relative}
.thumbhint{position:absolute;left:50%;top:50%;width:80px;height:80px;transform:translate(-50%,-50%);pointer-events:none;z-index:1;opacity:1}
.thumbhint *{pointer-events:none}
.thumbhint svg{position:absolute;left:0;top:0;width:100%;height:100%;overflow:visible;will-change:transform;filter:drop-shadow(0 0 2px rgba(255,84,73,.4)) drop-shadow(0 0 6px rgba(142,91,214,.25))}
.thumbhint .thc{fill:none;stroke:url(#thGrad);stroke-width:1.5}
.thglow{position:absolute;left:14%;top:14%;right:14%;bottom:14%;border-radius:50%;background:radial-gradient(circle,rgba(255,84,73,.16),rgba(142,91,214,.08) 55%,rgba(142,91,214,0) 72%);animation:thpulse 2.6s ease-in-out infinite}
@keyframes thpulse{0%,100%{opacity:.5;transform:scale(.92)}50%{opacity:1;transform:scale(1.08)}}
@media (prefers-reduced-motion:reduce){.thglow{animation:none;opacity:.7}}
html body #ring{position:relative;z-index:2;touch-action:none!important;cursor:grab}html body #ring:active{cursor:grabbing}html body #vRing .ringwrap{touch-action:none!important}
html body #race .rrow{cursor:pointer}html body #race .rrow:hover .rw{fill:#fff;text-decoration:underline}html body #ring{cursor:pointer}
@media (max-width:640px){html body .pk.pcoll #pdisc{align-items:start!important}html body .pk.pcoll #pdisc .pdn{display:flex!important;align-items:flex-start;line-height:1.15!important;padding-top:4px;align-self:start}html body .pk.pcoll #pdisc .pdn::before{flex:none;margin-top:calc(.575em - 6px)!important;vertical-align:0!important}html body .pk.pcoll #pdisc .pdt{align-self:start}html body .pk.pcoll #pdisc .pdc{margin-top:4px}}
html body #cats button.cat{border:1.5px solid rgba(255,255,255,.22)!important;box-shadow:none!important}
html body #cats button.cat.on{border:2px solid #e0453b!important;box-shadow:0 0 12px rgba(224,69,59,.35)!important}
/* Compact category tabs: no people-count, smaller padding/type; gray border, red when selected */
html body #picker #cats button.cat .ct small,html body #cats button.cat .ct small{display:none!important}
html body #picker #cats,html body #cats{gap:7px!important}
html body #picker #cats button.cat,html body #cats button.cat{
  padding:6px 10px!important;min-height:0!important;gap:0!important;height:auto!important;
  font-family:Arial,Helvetica,sans-serif!important;
  grid-template-rows:auto!important;
}
html body #picker #cats button.cat .ct b,html body #cats button.cat .ct b{
  font:700 13.5px/1.2 Arial,Helvetica,sans-serif!important;
  letter-spacing:-.01em!important;white-space:nowrap!important;overflow-wrap:normal!important;word-break:normal!important;
}
@media (max-width:640px){
  html body #picker #cats button.cat,html body #cats button.cat{padding:5px 8px!important}
  html body #picker #cats button.cat .ct b,html body #cats button.cat .ct b{
    font-size:12.5px!important;line-height:1.15!important;
    white-space:normal!important;overflow-wrap:break-word!important;word-break:normal!important;
  }
}
@media (max-width:480px){
  html body #picker #cats button.cat,html body #cats button.cat{padding:5px 7px!important}
  html body #picker #cats button.cat .ct b,html body #cats button.cat .ct b{font-size:12px!important}
}
@media (max-width:360px){
  html body #picker #cats button.cat,html body #cats button.cat{padding:4px 6px!important}
  html body #picker #cats button.cat .ct b,html body #cats button.cat .ct b{font-size:11.5px!important}
}

@media (max-width:640px){html body .pk.pcoll #pdisc:has(.tk){grid-template-columns:auto auto!important;justify-content:start;column-gap:12px!important}html body .pk.pcoll #pdisc:has(.tk) .pdt{white-space:nowrap;max-width:none!important;letter-spacing:.03em!important;padding:3px 6px!important;font-size:10.5px!important}}
@media (max-width:640px){html body .pk.pcoll #pdisc:has(.tk) .pdt.long{white-space:nowrap!important;max-width:none!important;font-size:9.5px!important;letter-spacing:.02em!important}}
@media (max-width:640px){html body .pk.pcoll #pdisc:has(.tk) .pdt.long.wrap{white-space:normal!important;max-width:9.5em!important}}
html body .pk.pcoll #pdisc .pdn{font-size:22px!important}
html body .pk.pcoll #pdisc .pdn::before,html body #persons button.chip.on::before,html body .vtop .rwho b::before{width:15px!important;height:15px!important;margin-right:11px!important;background:radial-gradient(circle at 50% 50%,#3ae046 0,#2fd23a 30%,#22b52c 44%,rgba(60,200,70,.6) 52%,#fff 62%,#fff 100%)!important;box-shadow:0 0 9px rgba(255,255,255,.9),0 0 6px rgba(60,220,80,.6)!important;animation:spkdot2 2.35s ease-in-out infinite!important}
@keyframes spkdot2{0%{outline:2px solid rgba(255,255,255,.95);outline-offset:0}10%{outline-color:rgba(255,255,255,.9);outline-offset:1px}75%,100%{outline:2px solid rgba(255,255,255,0);outline-offset:12px}}
@media (max-width:640px){html body .pk.pcoll #pdisc .pdn::before{margin-top:calc(.575em - 7.5px)!important}}
@media (prefers-reduced-motion:reduce){html body .pk.pcoll #pdisc .pdn::before,html body #persons button.chip.on::before,html body .vtop .rwho b::before{animation:none!important}}

/* ---- Compare (preview): two speakers' top words side by side, Mouth Math view only ---- */
.cmpbar{display:flex;justify-content:center;gap:8px;margin:6px 0 8px}
.cmpbtn{font:700 13px/1 Arial,Helvetica,sans-serif;color:#f3eee4;background:linear-gradient(180deg,#2a1d20,#1a1416);border:1px solid #ff5449;border-radius:999px;padding:8px 16px;cursor:pointer;box-shadow:0 0 10px rgba(255,84,73,.28),0 0 16px rgba(138,111,196,.18);letter-spacing:.02em}
.cmpbtn .ctri{font-size:15px;color:#ff5449;margin-left:4px;vertical-align:-1px}
.cmpbtn:hover,.cmpbtn[aria-expanded="true"]{box-shadow:0 0 14px rgba(255,84,73,.45),0 0 22px rgba(138,111,196,.3)}
.cmpx{font:700 13px/1 Arial,Helvetica,sans-serif;color:#cfc8bd;background:#1a1416;border:1px solid #6c5a5e;border-radius:999px;padding:8px 14px;cursor:pointer}
.cmpx:hover{border-color:#ff5449;color:#fff}
.cmppick{background:#151112;border:1px solid #3a2a2e;border-radius:10px;padding:10px;margin:0 0 10px;box-shadow:0 0 14px rgba(138,111,196,.15)}
.cmppick input{width:100%;box-sizing:border-box;font:14px Arial,Helvetica,sans-serif;padding:9px 11px;border-radius:8px;border:1px solid #4a3a3e;background:#0f0c0d;color:#f3eee4}
.cmppick .cmpcat{font:700 11px Arial,sans-serif;color:#8a6fc4;text-transform:uppercase;letter-spacing:.08em;margin:10px 2px 4px}
.cmppick .cmpl{display:flex;flex-wrap:wrap;gap:6px;max-height:260px;overflow:auto}
.cmppick .cmpl button{font:13px Arial,sans-serif;color:#f3eee4;background:#1f1719;border:1px solid #4a3a3e;border-radius:999px;padding:6px 11px;cursor:pointer}
.cmppick .cmpl button:hover{border-color:#ff5449}
.cmpgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.cmpcol{min-width:0}
.cmph{display:flex;align-items:center;gap:7px;font:700 15px/1.2 Arial,Helvetica,sans-serif;color:#ff5449;margin:2px 0 2px;min-width:0}
.cmph .cnm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cmph::before{content:"";flex:0 0 9px;height:9px;border-radius:50%;background:#3ddc84;box-shadow:0 0 6px rgba(61,220,132,.8)}
.cmpsub{font:11px Arial,sans-serif;color:#8d867b;margin:0 0 6px 16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cmprow{display:grid;grid-template-columns:22px minmax(0,1fr) auto;column-gap:6px;align-items:center;font:13px/1.25 Arial,sans-serif;color:#e8e2d8;padding:3px 4px;border-radius:5px;border:1px solid transparent}
.cmprow[data-w]{cursor:pointer}.cmprow[data-w]:hover,.cmprow.active{background:rgba(200,40,60,.12)}
.cmprow .r{color:#7d776d;text-align:right;font-size:11px}
.cmprow .w{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cmprow .c{color:#cfc8bd;font-size:12px;text-align:right}
.cmprow .b{grid-column:2/4;height:5px;margin-top:2px;border-radius:0;background:linear-gradient(90deg,rgba(150,28,28,.95),rgba(138,111,196,.75))}
.cmprow.both{border-color:rgba(138,111,196,.55);background:rgba(138,111,196,.09);box-shadow:0 0 6px rgba(138,111,196,.18)}
.cmpkey{text-align:center;font:11px Arial,sans-serif;color:#8d867b;margin:10px 0 0}
.cmpkey i{display:inline-block;width:10px;height:10px;border:1px solid rgba(138,111,196,.7);background:rgba(138,111,196,.15);border-radius:3px;vertical-align:-1px;margin-right:4px}
#vMath.cmpon .tbwrap,#vMath.cmpon #more,#vMath.cmpon #rsrow{display:none!important}
@media (max-width:400px){.cmpgrid{gap:6px}.cmprow{grid-template-columns:18px minmax(0,1fr) auto;column-gap:4px;font-size:12px;padding:3px 2px}.cmph{font-size:13px}.cmpsub{margin-left:14px}}

header .hact a.findings-link{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border:1px solid #4d2f3b;border-radius:999px;background:linear-gradient(180deg,#25161b,#140c10);color:#f3eee4;text-decoration:none;font:700 12.5px/1.2 Arial,Helvetica,sans-serif;box-shadow:0 0 12px rgba(255,84,73,.22),0 0 18px rgba(138,111,196,.16)}
header .hact a.findings-link:hover{border-color:#ff5449;color:#fff;box-shadow:0 0 14px rgba(255,84,73,.42),0 0 22px rgba(138,111,196,.28)}
header .hact a.findings-link .fdot{width:6px;height:6px;border-radius:50%;background:#ff5449;box-shadow:0 0 7px #ff5449;flex:none}
header .hact a.findings-link .fcnt,.cmpbtn.findings-pill .fcnt{display:inline-block;padding:1px 5px;border-radius:999px;background:rgba(255,84,73,.2);border:1px solid rgba(255,84,73,.55);color:#ff7a70;font:700 10.5px/1.1 Arial,Helvetica,sans-serif}
@media (max-width:640px){
  header .hact{flex-wrap:wrap;justify-content:flex-end;max-width:136px;row-gap:4px;top:8px!important;transform:none!important}
  header .hact a.findings-link{order:3;padding:3px 9px;font-size:11.5px}
  header .hact a.findings-link .fcnt{font-size:10px;padding:1px 4px}
}
.cmpbtn.findings-pill{text-decoration:none;border-color:#4d2f3b;background:linear-gradient(180deg,#25161b,#130c10);box-shadow:0 0 12px rgba(255,84,73,.18),0 0 16px rgba(138,111,196,.16)}
.cmpbtn.findings-pill:hover{border-color:#ff5449;color:#fff;box-shadow:0 0 14px rgba(255,84,73,.38),0 0 22px rgba(138,111,196,.28)}
#vMath.cmpon .findings-pill{display:none}
#findingsCard.fteaser{border-color:#3a2831;background:radial-gradient(120% 140% at 100% 0%,rgba(138,111,196,.12) 0%,rgba(255,84,73,.08) 42%,#0b0b0b 80%);box-shadow:0 0 22px rgba(255,84,73,.08),0 0 28px rgba(138,111,196,.08)}
.ft-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap;margin:0 0 6px}
.ft-eyebrow{display:inline-flex;align-items:center;gap:6px;font:700 11px/1 Arial,Helvetica,sans-serif;text-transform:uppercase;letter-spacing:.08em;color:#ff7a70}
.ft-eyebrow i{width:7px;height:7px;border-radius:50%;background:#ff5449;box-shadow:0 0 7px #ff5449;display:inline-block}
.ft-all{font:700 13px/1.2 Arial,Helvetica,sans-serif;color:#ff5449;text-decoration:none;border:1px solid rgba(255,84,73,.5);border-radius:999px;padding:5px 12px;background:rgba(255,84,73,.1);box-shadow:0 0 10px rgba(255,84,73,.18)}
.ft-all:hover{background:rgba(255,84,73,.2);color:#fff;border-color:#ff5449}
#findingsCard h2{margin:0 0 6px;font-size:20px;letter-spacing:-.02em;color:#f3eee4}
.ft-sub{margin:0 0 12px;font-size:14px;color:#b8b1a6;line-height:1.45}
.ft-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:0 0 12px}
.ft-item{display:block;text-decoration:none;border:1px solid #2e2429;border-radius:9px;padding:10px 12px;background:#110d10;transition:border-color .15s,box-shadow .15s}
.ft-item:hover{border-color:#ff5449;box-shadow:0 0 14px rgba(255,84,73,.18)}
.ft-item .ft-k{font:700 10.5px/1.2 Arial,Helvetica,sans-serif;text-transform:uppercase;letter-spacing:.06em;color:#b77ee0;margin:0 0 4px}
.ft-item .ft-t{font:700 14px/1.28 Arial,Helvetica,sans-serif;color:#f3eee4;margin:0 0 4px}
.ft-item .ft-d{font:400 12.5px/1.4 Arial,Helvetica,sans-serif;color:#a9a297;margin:0}
.ft-item .ft-d b{color:#ff5449}
@media (max-width:640px){.ft-grid{grid-template-columns:1fr;gap:8px}#findingsCard h2{font-size:18px}}
/* "Choose Category" showman/Monty-Python banner + 3 branching arrows pointing to the 3 category columns */
html body #catCue{order:-2!important;width:100%!important;align-self:stretch!important;box-sizing:border-box!important;display:flex;flex-direction:column;align-items:center;margin:0 0 -3px!important;padding:0;user-select:none}
html body #catCue .cc-badge{
  display:inline-flex;align-items:center;gap:6px;
  padding:2.5px 12px 2px;
  border:1.5px solid rgba(255,84,73,.75);
  border-radius:999px;
  background:linear-gradient(180deg,#261215,#12090b);
  box-shadow:0 0 12px rgba(255,84,73,.28),0 0 18px rgba(138,111,196,.18),inset 0 1px 0 rgba(255,255,255,.14);
  font:800 10.5px/1.15 Arial,Helvetica,sans-serif;
  letter-spacing:.14em;text-transform:uppercase;color:#f7f1e6;
}
html body #catCue .cc-star{color:#ff6b61;font-size:9.5px;line-height:1;text-shadow:0 0 6px rgba(255,84,73,.8)}
html body #catCue .cc-txt{color:#fff;text-shadow:0 0 10px rgba(255,84,73,.55)}
html body #catCue .cc-svg{display:block;width:100%!important;height:22px;margin:-1px 0 -2px;overflow:visible;filter:drop-shadow(0 0 5px rgba(255,84,73,.38))}
html body #catCue .cc-line{fill:none;stroke:url(#ccGrad);stroke-width:2.1;stroke-linecap:round;stroke-linejoin:round}
html body #catCue .cc-tip{fill:#ff5449;animation:ccBob 1.85s ease-in-out infinite}
html body #catCue .cc-tip.t2{animation-delay:.18s}
html body #catCue .cc-tip.t3{animation-delay:.36s}
@keyframes ccBob{0%,100%{transform:translateY(0)}50%{transform:translateY(2.2px)}}
@media (prefers-reduced-motion:reduce){html body #catCue .cc-tip{animation:none}}
@media (max-width:480px){
  html body #catCue{margin:0 0 -3px!important}
  html body #catCue .cc-badge{font-size:10px;padding:2px 10px;letter-spacing:.13em}
  html body #catCue .cc-svg{height:20px}
}
/* Unified Category + Search Section (tightened up with glowing red border encompassing active category + search section below) */
@media (max-width:1099px){
  html body main{display:flex!important;flex-direction:column!important;align-items:stretch!important;gap:8px!important}
  html body main .topgrid{display:contents!important}
  html body main aside.ad[data-slot="side"]{display:none!important}
  html body main #words{order:4!important;width:100%!important;box-sizing:border-box!important}
  html body #picker{
    order:0!important;width:100%!important;box-sizing:border-box!important;
    position:static!important;padding:8px 9px!important;margin:0!important;
    border:1.5px solid rgba(255,255,255,.18)!important;border-radius:11px!important;
  }
  html body #picker .pk{display:flex!important;flex-direction:column!important;gap:6px!important}
  html body #picker .catbar{
    display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;
    column-gap:7px!important;row-gap:0!important;align-items:stretch!important;margin:0!important;padding:0!important;
    border:0!important;background:none!important;box-shadow:none!important;
  }
  html body #picker #cats,html body #picker #chints{display:contents!important}
  html body #picker #cats button.cat:nth-child(1),html body #picker #chints .chint:nth-child(1){grid-column:1!important}
  html body #picker #cats button.cat:nth-child(2),html body #picker #chints .chint:nth-child(2){grid-column:2!important}
  html body #picker #cats button.cat:nth-child(3),html body #picker #chints .chint:nth-child(3){grid-column:3!important}
  html body #picker #cats button.cat{
    grid-row:1!important;margin:0!important;min-width:0!important;
    border-radius:9px 9px 0 0!important;
    border:1.5px solid rgba(255,255,255,.22)!important;
    border-bottom:1px solid rgba(255,255,255,.10)!important;
    background:linear-gradient(180deg,#1d1917,#131110)!important;
    padding:6px 8px 5px!important;min-height:30px!important;
    box-shadow:none!important;
    display:flex!important;align-items:center!important;justify-content:center!important;text-align:center!important;
  }
  html body #picker #cats button.cat .ct{display:block!important;min-width:0!important;width:100%!important;text-align:center!important}
  html body #picker #cats button.cat .ct b{display:block!important;font-size:13px!important;line-height:1.15!important;white-space:normal!important;overflow-wrap:break-word!important}
  html body #picker #chints .chint{
    grid-row:2!important;align-self:start!important;width:100%!important;margin:0!important;min-width:0!important;
    display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important;gap:4px!important;
    border-radius:0 0 9px 9px!important;
    border:1.5px solid rgba(255,255,255,.22)!important;
    border-top:0!important;
    background:linear-gradient(180deg,#131110,#0b0a0a)!important;
    padding:4px 7px 6px!important;
    font:700 11.5px/1.18 Arial,Helvetica,sans-serif!important;
    color:#d0c7bc!important;text-align:center!important;
  }
  html body #picker #chints .chint::before{
    content:""!important;order:2!important;flex:0 0 auto!important;align-self:center!important;
    width:8px!important;height:8px!important;margin:1px auto 0!important;
    border-radius:50%!important;border:1.5px solid rgba(243,238,228,.82)!important;
    background:radial-gradient(circle,#b5aea5 0 44%,transparent 52%)!important;
    animation:chdot 2.35s ease-in-out infinite!important;
  }
  html body #picker #chints .chint[aria-expanded="true"]::before{
    content:"\25BE"!important;width:auto!important;height:auto!important;margin:0 auto!important;
    border:0!important;border-radius:0!important;background:none!important;box-shadow:none!important;animation:none!important;
    font-size:12px!important;line-height:1!important;color:#fff!important;
  }
  html body #picker #cats button.cat.on,html body #picker #cats button.cat.on:hover{
    border:2px solid #e0453b!important;
    border-bottom:1px solid rgba(224,69,59,.42)!important;
    background:linear-gradient(180deg,rgba(224,69,59,.38),rgba(36,16,16,.96))!important;
    color:#fff!important;
    box-shadow:0 -3px 12px rgba(224,69,59,.36),inset 0 1px 0 rgba(255,255,255,.20)!important;
    position:relative!important;z-index:2!important;
  }
  html body #picker #chints .chint.on{
    border:2px solid #e0453b!important;
    border-top:0!important;
    background:linear-gradient(180deg,rgba(36,16,16,.96),rgba(18,10,10,.98))!important;
    color:#fff!important;
    padding-top:9px!important;padding-bottom:9px!important;
    box-shadow:0 6px 15px rgba(224,69,59,.42),inset 0 -1px 0 rgba(224,69,59,.28)!important;
    position:relative!important;z-index:2!important;
    animation:chintDrop .42s cubic-bezier(.22,1.15,.36,1) both!important;
  }
  @keyframes chintDrop{0%{padding-top:3px;padding-bottom:4px;box-shadow:0 2px 6px rgba(224,69,59,.18)}65%{padding-top:11px;padding-bottom:10px}100%{padding-top:9px;padding-bottom:9px}}
  html body #picker #chints .chint.on::before{
    border-color:#ff6b61!important;
    background:radial-gradient(circle,#ff5449 0 48%,transparent 56%)!important;
    box-shadow:0 0 7px rgba(255,84,73,.75)!important;
    animation:chdotRed 2.35s ease-in-out infinite!important;
  }
  @keyframes chdotRed{0%{outline:1.5px solid rgba(255,95,86,.95);outline-offset:0}10%{outline-color:rgba(255,95,86,.9);outline-offset:1px}75%,100%{outline:1.5px solid rgba(255,95,86,0);outline-offset:7px}}
  html body .pk.pcoll #pdisc{
    display:grid!important;grid-template-columns:auto 1fr!important;grid-template-areas:"n t"!important;
    align-items:center!important;column-gap:10px!important;text-align:left!important;
    width:100%!important;min-height:38px!important;margin:0!important;padding:5px 10px!important;
    box-sizing:border-box!important;border:1.5px solid rgba(255,255,255,.24)!important;border-radius:8px!important;
    background:linear-gradient(180deg,#171413,#100e0e)!important;cursor:pointer!important;
  }
  html body .pk.pcoll #pdisc .pdn{grid-area:n!important;display:flex!important;align-items:center!important;align-self:center!important;padding-top:0!important;font-size:18px!important;line-height:1.12!important;color:var(--num-red)!important;font-weight:700!important}
  html body .pk.pcoll #pdisc .pdt{grid-area:t!important;justify-self:end!important;align-self:center!important;text-align:center!important;max-width:13em!important;font:700 10.5px/1.18 Arial,Helvetica,sans-serif!important;letter-spacing:.05em!important;text-transform:uppercase!important;color:#e0d4d1!important;border:1px solid rgba(255,255,255,.32)!important;border-radius:4px!important;padding:3px 7px!important}
  html body .pk.pcoll #pdisc .pdg,html body .pk.pcoll #pdisc .pda,html body .pk.pcoll #personInfo{display:none!important}
  html body .pk.pcoll:not(.popen) #pfilter,html body .pk.pcoll:not(.popen) #az,html body .pk.pcoll:not(.popen) #persons{display:none!important}
}
@media (max-width:480px){
  html body #picker{padding:7px 8px!important}
  html body #picker .catbar{column-gap:6px!important}
  html body #picker #cats button.cat{padding:5px 4px 4px!important;min-height:26px!important}
  html body #picker #cats button.cat .ct b{font-size:11px!important;line-height:1.12!important}
  html body #picker #chints .chint{padding:4px 4px 5px!important;font-size:11.5px!important;line-height:1.15!important;gap:4px!important;justify-content:center!important;align-items:center!important;text-align:center!important}
  html body #picker #chints .chint.on{padding:8px 4px 9px!important}
  html body #picker #chints .chint::before{width:7px!important;height:7px!important;margin:1px auto 0!important;align-self:center!important}
}
</style></head><body class="mode-fed">
<header><div class="hact"><a class="findings-link" href="findings.html" title="15 word-count findings from the transcripts"><span class="fdot" aria-hidden="true"></span>Findings <span class="fcnt">15</span></a><a class="about-link" href="#about">About</a><button type="button" class="hbtn" id="share" title="Copy a link to this exact view">Share</button></div>
<div class="brand"><a class="logo" href="./" title="MouthMath home" aria-label="MouthMath home">__LOGO__</a>
<p class="tagline">Every word counts.</p>

</div>
</header>
<button type="button" id="spkbar" aria-hidden="true" tabindex="-1"><span class="sbn"></span><span class="tk sbt"></span><span class="sba" aria-hidden="true"></span><span class="sbc">Search</span></button>
<main>
<div class="topgrid">
<section class="card" id="picker"><div class="pk"><h2 class="sr-only">Who</h2><div id="catCue" class="cat-cue" aria-hidden="true"><span class="cc-badge"><span class="cc-star">&#9733;</span><span class="cc-txt">CHOOSE CATEGORY</span><span class="cc-star">&#9733;</span></span><svg class="cc-svg" viewBox="0 0 300 24" preserveAspectRatio="none"><defs><linearGradient id="ccGrad" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#ff5449"/><stop offset="50%" stop-color="#ff7a70"/><stop offset="100%" stop-color="#b77ee0"/></linearGradient></defs><path class="cc-line" d="M116 2 C 78 4, 51 7, 48.2 17"/><path class="cc-line" d="M150 2 L 150 17"/><path class="cc-line" d="M184 2 C 222 4, 249 7, 251.8 17"/><polygon class="cc-tip t1" points="48.2,23 41.2,14 48.2,16.5 55.2,14"/><polygon class="cc-tip t2" points="150,23 143,14 150,16.5 157,14"/><polygon class="cc-tip t3" points="251.8,23 244.8,14 251.8,16.5 258.8,14"/></svg></div><nav class="catbar" aria-label="Category"><div class="seg" id="cats" role="tablist" aria-label="Category"></div><div id="chints" role="group" aria-label="Search other speakers"></div></nav>
<button type="button" id="pdisc" aria-expanded="false" aria-controls="persons" hidden></button>
<div id="pfilter" hidden><input type="search" id="psearch" placeholder="Search name, company or ticker" aria-label="Search people" autocomplete="off">
<div id="idx" role="group" aria-label="Filter by stock index"></div></div>
<div id="az" role="toolbar" aria-label="Filter by last name" aria-controls="persons" hidden></div>
<div class="tf-row" id="persons"><span class="lbl">Person</span></div>
<div id="personInfo"><span class="eyebrow" id="eyebrow"></span></div>
</div></section>
<!-- ad slot: side · 300x250 desktop (hidden on phones) · reserved for an AdSense unit after approval -->
<aside class="ad" data-slot="side" data-ad-slot-name="side" data-ad-size="300x250" data-ad-size-phone="none"></aside>
</div>
<section class="card" id="words">
<h1 id="personTitle" class="sr-only">__DEFAULT_FT__ <span class="pn">__DEFAULT_TITLE__</span></h1>
<div id="tfbar" role="group" aria-label="Documents">
<details id="docPick"><summary class="dbtn" aria-label="Choose documents"><span class="dbl1"><span class="dbico" aria-hidden="true"><svg viewBox="0 0 34 26" width="34" height="26"><rect x="2" y="3" width="11" height="14" rx="1.5" fill="#1a1416" stroke="#8a6fc4" stroke-width="1.2"/><g class="dbfeed"><rect x="5" y="6" width="11" height="14" rx="1.5" fill="#141010" stroke="#f3eee4" stroke-width="1.3"/><path d="M7.5 10h6M7.5 13h6M7.5 16h4" stroke="#ff5449" stroke-width="1.2" stroke-linecap="round"/></g><path d="M21 13c2.5-3.2 8.5-3.2 11 0c-2.5 3.2-8.5 3.2-11 0z" fill="none" stroke="#ff5449" stroke-width="1.5"/><path d="M22 13h9" stroke="#ff5449" stroke-width="1"/></svg></span><span class="dbv" id="dbV">Add Speeches</span><span class="dbn" id="dbN"></span></span><span class="dbl2" id="dbLatest"></span></summary>
<div class="dsback" aria-hidden="true"></div>
<div class="dsheet" role="dialog" aria-label="Choose documents"><div class="dshead"><b>Documents</b><button type="button" class="dsclose2" id="dsClose2">Close <span class="rtri" aria-hidden="true">&#9662;</span></button><button type="button" class="dsx" id="dsClose" aria-label="Close">&times;</button></div>
<div class="dsq"><button class="chip" id="btnAll">Select all</button><button class="chip" id="btnNone">None</button><div class="yrs" id="years" role="group" aria-label="Years"></div></div>
<ul class="speeches" id="docList"></ul></div></details>
<div id="selSummary" class="sr-only"></div></div>
<div class="stats" id="stats" aria-label="Word counts for the selection">
<div class="stat"><b id="sDocs">–</b><span class="sl" data-s="docs">documents selected</span></div>
<div class="stat"><b id="sTotal">–</b><span class="sl" data-s="total words">total words</span></div>
<div class="stat"><b id="sUnique">–</b><span class="sl" data-s="unique">unique words</span></div>
<div class="stat"><b id="sShown">–</b><span class="sl" data-s="shown">words shown</span></div>
</div>
<div id="vtLbl" class="vtlbl" aria-hidden="true">Choose a view</div>
<div id="vtabs" role="tablist" aria-label="View"><button type="button" role="tab" id="tabMath" data-view="math" aria-selected="true" aria-controls="vMath">Mouth Math</button><span class="valt" aria-hidden="true">Alternative views</span><button type="button" role="tab" id="tabCloud" data-view="cloud" aria-selected="false" aria-controls="vCloud" tabindex="-1">Word Cloud</button><button type="button" role="tab" id="tabRace" data-view="race" aria-selected="false" aria-controls="vRace" tabindex="-1">Word Race</button><button type="button" role="tab" id="tabRing" data-view="ring" aria-selected="false" aria-controls="vRing" tabindex="-1">Word Ring</button></div><script>(()=>{const I={
race:'<svg class="vic vr" viewBox="0 0 26 20" aria-hidden="true"><rect x="1" y="2" width="20" height="4" rx="1.5" fill="currentColor"/><rect x="1" y="9" width="14" height="4" rx="1.5" fill="currentColor" opacity=".75"/><rect x="1" y="16" width="9" height="3" rx="1.5" fill="currentColor" opacity=".55"/></svg>',
cloud:'<svg class="vic vc" viewBox="0 0 26 20" aria-hidden="true"><rect x="2" y="3" width="9" height="3" rx="1.5" fill="currentColor" opacity=".7"/><rect x="13" y="2" width="11" height="4" rx="2" fill="currentColor"/><rect x="4" y="9" width="17" height="5" rx="2.5" fill="currentColor"/><rect x="7" y="16" width="12" height="3" rx="1.5" fill="currentColor" opacity=".6"/></svg>',
ring:'<svg class="vic" viewBox="0 0 26 20" aria-hidden="true"><g class="vg" stroke="currentColor" stroke-linecap="round">'+[...Array(16)].map((_,i)=>{const a=i/16*6.283,r0=4,r1=r0+(i%4===0?5.5:i%2?3:4),c=Math.cos(a),s=Math.sin(a);return `<line x1="${13+c*r0}" y1="${10+s*r0}" x2="${13+c*r1}" y2="${10+s*r1}" stroke-width="${i%4===0?1.6:1}"/>`}).join('')+'</g></svg>'};
document.querySelectorAll('#vtabs [data-view]').forEach(b=>{const v=I[b.dataset.view];if(v&&!b.querySelector('.vic'))b.insertAdjacentHTML('afterbegin',v)})})();</script>
<div id="nbar" role="group" aria-label="Number of words to show"><span class="nbl">Show</span><button class="nchip" data-n="5">5</button><button class="nchip" data-n="20">20</button><button class="nchip" data-n="50">50</button><button class="nchip" data-n="100">100</button><button class="nchip" data-n="all">Max</button><span class="nbl">words</span></div>
<div class="controls">
<input type="search" id="q" placeholder="Filter words (e.g. inflation, ^pro, ing$)…">
</div>
<div class="vtop">
<div class="rwho vhead" aria-live="polite"><b></b></div>
<label class="vstop"><input type="checkbox" id="hideStop" checked> Hide common stopwords</label>
</div>
<details id="pbio" open><summary>About this speaker</summary><p id="bioText"></p><a id="bioLink" href="speakers/">Full profile and top words &rarr;</a></details>
<div id="vpanes" class="tab-math">
<div class="vpane" id="vMath" role="tabpanel" aria-labelledby="tabMath"><h3 class="secth" id="superMath">Mouth Math</h3>
<div class="cmpbar"><button type="button" class="cmpbtn" id="cmpBtn" aria-expanded="false" aria-controls="cmpPick">Compare <span class="ctri" aria-hidden="true">&#9662;</span></button><a class="cmpbtn findings-pill" href="findings.html" title="Read 15 word-count findings across Fed Chairs, Presidents &amp; CEOs">Findings <span class="fcnt">15</span> &rarr;</a><button type="button" class="cmpx" id="cmpX" hidden>&#10005; Exit compare</button></div>
<div class="cmppick" id="cmpPick" hidden><input type="search" id="cmpQ" placeholder="Compare with… (search any speaker)" aria-label="Search a speaker to compare"><div id="cmpList"></div></div>
<div id="cmpOut" hidden></div>
<div class="tbwrap"><table class="only-standard"><thead><tr><th class="num" data-k="rank">Rank</th><th data-k="word">Word</th><th class="num" data-k="count">Count</th><th class="barc">Frequency</th></tr></thead>
<tbody id="tb"></tbody></table><div class="topring" id="topRing" aria-hidden="true" hidden></div></div>
<p class="muted" id="more"></p>
<label class="rsrow" id="rsrow" hidden><input type="checkbox" id="realSpots"> View words in actual order</label></div>
<div class="vpane" id="vCloud" role="tabpanel" aria-labelledby="tabCloud"><h3 class="secth" id="superCloud">Word Cloud</h3>
<p class="selhint">Select a word for more info</p>
<div class="cloudwrap"><div id="cloud"></div>
<div class="cloud-bar"><span class="muted" id="cloudNote"></span></div></div></div>
<div class="vpane" id="vRing" role="tabpanel" aria-labelledby="tabRing"><div class="ringword" id="ringWord" title="Tap for word context"></div><div class="ringwrap"><canvas id="ring" aria-label="Word Ring: each spike is a word, longer means said more"></canvas><div class="thumbhint" id="thumbHint" aria-hidden="true"><i class="thglow"></i><svg viewBox="-42 -42 84 84" focusable="false"><defs><linearGradient id="thGrad" gradientUnits="userSpaceOnUse" x1="-32" y1="-26" x2="32" y2="26"><stop offset="0" stop-color="#ff5449"/><stop offset=".5" stop-color="#d04a6a"/><stop offset="1" stop-color="#8e5bd6"/></linearGradient></defs><g class="thspin"><circle class="thc" cx="0" cy="0" r="32.5"/></g></svg></div></div></div><div class="vpane" id="vRace" role="tabpanel" aria-labelledby="tabRace"><div class="racewrap"><div class="rdate" id="rDate"></div><div class="rttl" id="rTtl"></div><svg id="race" viewBox="0 0 680 430" width="100%" role="img" aria-label="Top 10 words, added up speech by speech"></svg><svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs><linearGradient id="rgPurp" x1="0" x2="1"><stop offset="0" stop-color="#8e3833"/><stop offset="1" stop-color="#6e3a86"/></linearGradient></defs></svg><div class="rfoot"><button type="button" class="rplay" id="rPlay">Replay <span class="rtri">▸</span></button><a href="#picker" id="rNew" class="rNew">Select a new speaker <span class="rtri">&#9652;</span></a></div></div></div>
</div>
<!-- ad slot: between · 728x90 desktop, 320x100 phone · reserved for a relevant AdSense unit after approval (below the Mouth Math / Word Cloud views) -->
<aside class="ad" data-slot="between" data-ad-slot-name="between" data-ad-size="728x90" data-ad-size-phone="320x100"></aside>
</section>
<!-- ad slot: leader · 728x90 desktop, 320x50 phone · reserved for an AdSense unit after approval -->
<aside class="ad" data-slot="leader" data-ad-slot-name="leader" data-ad-size="728x90" data-ad-size-phone="320x50"></aside>
<p class="muted" id="method"><span id="dataThrough"></span>
<span class="kbd-hint" id="kbdHint">Shortcuts: <kbd>/</kbd> filter words · <kbd>V</kbd> switch Math ↔ Cloud · <kbd>S</kbd> share · <kbd>?</kbd> this hint</span></p>
<div id="toast" role="status" aria-live="polite"></div>
<!-- ad slot: incontent · 300x250 desktop and phone · reserved for an AdSense unit after approval -->
<aside class="ad" data-slot="incontent" data-ad-slot-name="incontent" data-ad-size="300x250" data-ad-size-phone="300x250"></aside>
<section class="card fteaser" id="findingsCard" aria-labelledby="ftTitle">
<div class="ft-head"><span class="ft-eyebrow"><i aria-hidden="true"></i>Transcript Research</span><a class="ft-all" href="findings.html">Read all 15 findings &rarr;</a></div>
<h2 id="ftTitle">15 Key Findings from the Transcripts</h2>
<p class="ft-sub">Concrete word-count patterns across 40 years of Federal Reserve Chairs, eight US Presidents, and S&amp;P 500 CEOs&mdash;normalized per 1,000 words.</p>
<div class="ft-grid">
<a class="ft-item" href="findings.html#f3"><div class="ft-k">Finding #03 &middot; Fed Chairs</div><div class="ft-t">Every Fed Chair said &ldquo;inflation&rdquo; more than the one before</div><p class="ft-d">From Volcker (<b>0.96/1k</b>) and Greenspan (<b>1.37</b>) to Bernanke (<b>2.71</b>), Yellen (<b>5.84</b>), and Powell (<b>11.53/1k</b>).</p></a>
<a class="ft-item" href="findings.html#f5"><div class="ft-k">Finding #05 &middot; Federal Reserve</div><div class="ft-t">AI dominates Fed governors&rsquo; speeches, not the Chair&rsquo;s</div><p class="ft-d">Barr (<b>6.84/1k</b>, 300 uses) and Lisa Cook (<b>6.42/1k</b>, 280 uses) lead on &ldquo;ai&rdquo;; Powell is at <b>0.00</b>.</p></a>
<a class="ft-item" href="findings.html#f8"><div class="ft-k">Finding #08 &middot; US Presidents</div><div class="ft-t">Every President from Carter to Biden has a signature word</div><p class="ft-d">Carter &ldquo;energy&rdquo; (<b>3.82/1k</b>), Reagan &ldquo;tax&rdquo; (<b>3.52</b>), Clinton &ldquo;people&rdquo; (<b>5.78</b>), Obama &ldquo;jobs&rdquo; (<b>2.57</b>), Trump &ldquo;great&rdquo; (<b>3.08</b>), Biden &ldquo;democracy&rdquo; (<b>1.35</b>).</p></a>
<a class="ft-item" href="findings.html#f11"><div class="ft-k">Finding #11 &middot; S&amp;P 500 CEOs</div><div class="ft-t">Tech CEOs top 12&ndash;14 &ldquo;AI&rdquo; mentions per 1,000 words</div><p class="ft-d">Robbins (<b>14.19/1k</b>), Amon (<b>13.88</b>), Pichai (<b>13.40</b>), and Su (<b>12.03</b>) vs. <b>0.00</b> for Abel (Berkshire) and Ortberg (Boeing).</p></a>
</div>
</section>
<section class="card" id="about"><h2><button type="button" class="abtog" id="aboutToggle" aria-expanded="true">About MouthMath</button></h2>
<h3 class="ablead">From Mouth to Math</h3>
<p class="absub">Word counts from official speeches, testimony, letters and court opinions by Federal Reserve officials, Chief Executive Officers and United States Government Officials.</p>
<p>When a document becomes available to the public, each word is ranked according to how often it&#8217;s used in that document. This provides the ability to derive the substance of a speech at a glance, as well as access to every instance where each word was used in the actual document or speech. MouthMath makes mundane words not so mundane.</p>
<p>MouthMath.com was created to be politically neutral, with no bias: every speaker is counted the same way. Not all speeches are publicly available.</p>
<p>All content is available on a best-effort basis and counts are updated as new material becomes available. Nothing on MouthMath.com is financial, investment or legal advice.</p>
<p>New here? Explore <a href="findings.html">15 Key Findings from the Transcripts</a>, read <a href="articles/how-mouthmath-counts-words.html">How MouthMath counts words</a>, <a href="articles/what-the-fed-chairs-talk-about-most.html">What the Fed Chairs talk about most</a> and <a href="articles/comparing-presidential-vocabulary.html">Comparing presidential vocabulary</a>, or browse <a href="speakers/">every speaker</a>.</p>
<h4 class="abcontact" id="contact">Contact</h4>
<form class="mmform" id="cform" action="https://api.web3forms.com/submit" method="POST"><input type="hidden" name="access_key" value="a7f0f3e1-21eb-42b6-af4b-7d083c91c1b4"><input type="hidden" name="subject" value="MouthMath contact"><input type="hidden" name="from_name" value="MouthMath website"><input type="checkbox" name="botcheck" class="mmhp" tabindex="-1" autocomplete="off" aria-hidden="true"><label for="cformN">Name <span class="opt">(optional)</span></label><input id="cformN" name="name" autocomplete="name" maxlength="100"><label for="cformE">Email</label><input id="cformE" type="email" name="email" required autocomplete="email" maxlength="200" inputmode="email"><label for="cformM">Message</label><textarea id="cformM" name="message" required rows="4" maxlength="5000"></textarea><button type="submit">Send</button><p class="fmsg" role="status" aria-live="polite"></p></form>
<p class="abfoot"><a href="findings.html">Findings</a> · <a href="articles/">Articles</a> · <a href="speakers/">Speakers</a> · <a href="contact.html">Contact</a> · <a href="privacy.html">Privacy Policy</a> · <a href="terms.html">Terms of Use</a></p>
<p class="abtop"><button type="button" class="totop" id="toTop"><span class="tri" aria-hidden="true">&#9652;</span>Back to top</button></p>
</section>
</main>
<footer class="sitefoot"><a href="./">Home</a> · <a href="findings.html">Findings</a> · <a href="articles/">Articles</a> · <a href="speakers/">Speakers</a> · <a href="contact.html">Contact</a> · <a href="privacy.html">Privacy Policy</a> · <a href="terms.html">Terms of Use</a> · Not financial advice · Not affiliated with anyone listed<div class="mmcopy">&copy; 2026 MouthMath</div></footer>
<div id="tvModal" class="tvm" hidden><div class="tvm-back" data-close></div>
<div class="tvm-panel" role="dialog" aria-modal="true" aria-labelledby="tvmTitle"><div class="tvm-head"><h3 id="tvmTitle"></h3><span class="tvm-sub">1-year daily price</span>
<button type="button" class="tvm-x" id="tvmX" aria-label="Close chart" data-close>&times;</button></div>
<div class="tvm-body" id="tvmBody"></div><p class="tvm-note">Chart and market data by TradingView. For information only, not investment advice.</p></div></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const STOP=new Set(D.stop),SC=new Set(D.sc),PEOPLE=D.people,BY=new Map(PEOPLE.map(p=>[p.slug,p]));
const CATS=[...new Set(PEOPLE.map(p=>p.category))].sort((a,b)=>(a==='CEOs')-(b==='CEOs')),CAT_LBL={'CEOs':'Chief Executive Officers'},DEFAULT=PEOPLE[0].slug;
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtDate=s=>new Date(s+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
let P=null,V=[],VI=new Map(),DOCS=[],YEARS=[],sel=new Set(),sortK='count',sortDir=-1;const LIMIT=2000,FIRST=10,CLOUD_MAX=150;
const NOPTS=['5','20','50','100','all'],NDEF='20';let NSHOW=NDEF,NPICK=false;const nDef=()=>VIEW==='cloud'?'50':NDEF;   // mm79: the cloud opens at 50, other views at 20, until a Show button is tapped
   // words shown in both views: 5, 50 (default on every device, mm35), 100 or all (the cloud caps at CLOUD_MAX = 150: past that the words get too small to read)
const nCap=()=>NSHOW==='all'?Infinity:+NSHOW;
const unitOf=n=>n===1?(P.unit||'document'):(P.unit_pl||(P.unit||'document')+'s');
const q=$('q'),hide=$('hideStop'),tb=$('tb');

// ---- per-person data (inline, or data/<slug>.json when the page would be too large) ----
async function loadPerson(p){
  if(!p.docs){const r=await fetch(p.external);if(!r.ok)throw new Error('could not load '+p.external);Object.assign(p,await r.json())}
  if(!p.ready){p.VI=new Map(p.vocab.map((w,i)=>[w,i]));
    p.docs.forEach(d=>{d.cnt=new Map();d.ms=new Map();d.occ=new Map();const x=d.x;
      for(let i=0;i<x.length;){const wi=x[i],n=x[i+1],m=x[i+2],k=x[i+3];d.cnt.set(wi,n);d.ms.set(wi,m);d.occ.set(wi,x.slice(i+4,i+4+k));i+=4+k}});
    p.ready=true}
  return p;
}

// ---- category / person picker ----
let azCat='',azSel='',idxSel='',pq='',pOpen=false;
const IDX=['Mag 7','S&P 500','Nasdaq 100','Dow 30'];
const CAT_ICON={   // hairline line-art icons for the category tiles
 'Federal Reserve':'<svg viewBox="0 0 24 24"><path d="M3 9.5 12 4l9 5.5M5 10v8M9.7 10v8M14.3 10v8M19 10v8M3 20.5h18"/></svg>',
 'CEOs':'<svg viewBox="0 0 24 24"><path d="M3 20.5h18M6 20.5V13M10.5 20.5V9M15 20.5v-6M19.5 20.5V5"/><path d="m5 10 5-4 4 3 6-5"/></svg>',
 'US Government':'<svg viewBox="0 0 24 24"><path d="M12 3v2.5M8 10a4 4 0 0 1 8 0M5.5 10h13M7 10v8M10.3 10v8M13.7 10v8M17 10v8M3.5 20.5h17M5 18.5h14"/></svg>'};
const matchQ=p=>{if(!pq)return true;const h=[p.name,p.org,p.ticker,p.role,p.group].filter(Boolean).join(' ').toLowerCase();
  return pq.toLowerCase().split(/\s+/).filter(Boolean).every(t=>h.includes(t))};
const lastName=p=>(p.sort_name||p.name.replace(/,?\s+(Jr|Sr)\.?$|,?\s+(II|III|IV)$/,'').trim().split(' ').pop()).toUpperCase();
function renderAZ(allIn,inCat){
  const az=$('az'),use=allIn.length>=8;     // only for the bigger categories (CEOs, US Government), not the five Fed Chairmen
  az.hidden=!use;az.parentElement.classList.toggle('has-az',use);if(!use){azSel='';return}
  const have=new Set(inCat.map(p=>lastName(p)[0]));
  if(azSel&&!have.has(azSel))azSel='';
  const L='ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
  az.innerHTML=`<button type="button" class="all" data-l="" aria-pressed="${!azSel}" title="Show everyone in ${esc(P.category)}">All</button>`+
    L.map(l=>`<button type="button" data-l="${l}" aria-pressed="${azSel===l}"${have.has(l)?` aria-label="Last names starting with ${l}"`:' disabled aria-label="No last names starting with '+l+'"'}>${l}</button>`).join('');
  const btns=[...az.querySelectorAll('button:not(:disabled)')],cur=btns.find(b=>b.getAttribute('aria-pressed')==='true')||btns[0];
  az.querySelectorAll('button:disabled').forEach(b=>b.tabIndex=-1);
  btns.forEach(b=>{b.tabIndex=b===cur?0:-1;b.onclick=()=>{azSel=b.dataset.l;renderPicker();const n=$('az').querySelector(`button[data-l="${azSel}"]`);n&&n.focus()}});
  az.onkeydown=e=>{const i=btns.indexOf(document.activeElement);if(i<0)return;let j=-1;
    if(e.key==='ArrowRight'||e.key==='ArrowDown')j=(i+1)%btns.length;else if(e.key==='ArrowLeft'||e.key==='ArrowUp')j=(i-1+btns.length)%btns.length;
    else if(e.key==='Home')j=0;else if(e.key==='End')j=btns.length-1;else if(e.key==='Escape'&&azSel){azSel='';renderPicker();$('az').querySelector('button.all').focus();e.preventDefault();return}
    if(j>=0){e.preventDefault();btns[i].tabIndex=-1;btns[j].tabIndex=0;btns[j].focus()}};
}
function renderPicker(){
  if(azCat!==P.category){azCat=P.category;azSel='';idxSel='';pq='';pOpen=false;$('psearch').value=''}
  $('cats').innerHTML=CATS.map(c=>{
    return `<button class="cat${P.category===c?' on':''}" role="tab" aria-selected="${P.category===c}" data-cat="${esc(c)}"><span class="ci" aria-hidden="true">${CAT_ICON[c]||''}</span><span class="ct"><b>${esc(CAT_LBL[c]||c)}</b></span></button>`}).join('');
  const allIn=PEOPLE.filter(p=>p.category===P.category),useF=allIn.length>=8,hasIdx=allIn.some(p=>(p.indices||[]).length);
  $('pfilter').hidden=!useF;$('idx').hidden=!hasIdx;if(!hasIdx)idxSel='';
  if(hasIdx){$('idx').innerHTML=[''].concat(IDX).map(k=>{const n=k?allIn.filter(p=>(p.indices||[]).includes(k)).length:allIn.length;
      return `<button type="button" class="chip ix" data-ix="${esc(k)}" aria-pressed="${idxSel===k}"${n?'':' disabled'}>${k?esc(k):'All'} <span class="n">${n}</span></button>`}).join('');
    $('idx').querySelectorAll('button').forEach(b=>b.onclick=()=>{idxSel=b.dataset.ix;renderPicker();const n=[...$('idx').querySelectorAll('button')].find(x=>x.dataset.ix===idxSel);n&&n.focus()})}
  const pre=allIn.filter(p=>(!idxSel||(p.indices||[]).includes(idxSel))&&matchQ(p));renderAZ(allIn,pre);
  const inCat=pre.filter(p=>!azSel||lastName(p)[0]===azSel),groups=[...new Set(inCat.map(p=>p.group||''))];
  const chip=p=>`<button class="chip${p.slug===P.slug?' on':''}" data-person="${p.slug}" title="${esc(p.role)}">${esc(p.name)}${p.ticker?` <span class="tk${p.tv?' tkc':''}"${p.tv?` data-tv="${esc(p.tv)}" data-tk="${esc(p.ticker)}" data-org="${esc(p.org||'')}" title="Show the 1-year ${esc(p.ticker)} price chart"`:''}>${esc(p.ticker)}</span>`:''}</button>`;
  $('persons').classList.toggle('grouped',groups.length>1||!!groups[0]);
  $('persons').innerHTML=groups.length>1||groups[0]?   // a category with subgroups (US Government: Cabinet / Senate / House / Governors / Supreme Court)
    groups.map(g=>`<div class="pg" role="group" aria-label="${esc(g)}"><span class="lbl">${esc(g)}</span>${inCat.filter(p=>(p.group||'')===g).map(chip).join('')}</div>`).join(''):
    '<span class="lbl">Person</span>'+(inCat.length?inCat.map(chip).join(''):'<span class="muted nomatch">No one matches. <button type="button" class="linkbtn" id="clearF">Clear filters</button></span>');
  // Phones: a category made of small sub-groups (US Government: Cabinet / Senate / House / Governors / Supreme Court) folds its people list behind one
  // disclosure that shows the selected person in red + the white arrow; tapping it opens the grouped list (no A-Z needed there).
  const coll=allIn.length>1,grp=allIn.some(p=>p.group),pk=$('picker').querySelector('.pk'),pd=$('pdisc');   // every multi-person category (CEOs, US Government)
  pk.classList.toggle('pcoll',coll);pk.classList.toggle('psolo',!coll);pk.classList.toggle('pgrp',coll&&grp);
  if(!coll){const on=$('persons').querySelector('.chip.on');if(on)on.dataset.glabel=P.group||P.category.replace(/s$/,'')}   // phones: single-person category (Fed Chairman) shows its name like the collapse row
  pk.classList.toggle('popen',coll&&pOpen);pd.hidden=!coll;pd.setAttribute('aria-expanded',coll&&pOpen?'true':'false');
  if(coll){pd.innerHTML=`<span class="pdg">${esc(P.group||P.category.replace(/s$/,''))}</span><span class="pdn">${esc(P.name)}</span>${P.ticker?(P.tv?`<span class="tk tkc" data-tv="${esc(P.tv)}" data-tk="${esc(P.ticker)}" data-org="${esc(P.org||'')}" title="Show the 1-year ${esc(P.ticker)} price chart">${esc(P.ticker)}</span>`:`<span class="tk">${esc(P.ticker)}</span>`):''}<span class="pda" aria-hidden="true"></span>`;
    pd.setAttribute('aria-label',`Search speakers: ${P.name}${P.ticker?' ('+P.ticker+')':''} selected. ${pOpen?'Hide':'Show'} all ${allIn.length} people in ${P.category}`);
    pd.onclick=()=>{pOpen=!pOpen;renderPicker();const s=$('psearch');if(pOpen&&s&&s.getClientRects().length)s.focus({preventScroll:true});else $('pdisc').focus()}}   // open = search box focused (phones show the keyboard)
  $('chints').innerHTML=CATS.map(c=>{const on=P.category===c,op=on&&pOpen;return `<button type="button" class="chint${on?' on':''}" data-cat="${esc(c)}" aria-expanded="${op}" aria-label="Search ${esc(CAT_LBL[c]||c)}">${op?'Close':esc(srchLbl(c))}</button>`}).join('');   // a "Search Other ..." hint under every category button
  document.querySelectorAll('#chints .chint').forEach(b=>b.onclick=()=>{const c=b.dataset.cat,foc=()=>{const s=$('psearch');if(pOpen&&s&&s.getClientRects().length)s.focus({preventScroll:true})};
    if(c===P.category){pOpen=!pOpen;renderPicker();foc()}else setPerson(PEOPLE.find(p=>p.category===c).slug).then(()=>{pOpen=true;renderPicker();foc()})});
  const cf=$('clearF');if(cf)cf.onclick=()=>{pq='';idxSel='';azSel='';$('psearch').value='';renderPicker();$('psearch').focus()};
  // mm40: the gray role description after the boxed label is gone (it repeated the label)
  document.querySelectorAll('#cats button').forEach(b=>b.onclick=()=>{if(b.dataset.cat!==P.category)setPerson(PEOPLE.find(p=>p.category===b.dataset.cat).slug)});
  document.querySelectorAll('#persons button.chip').forEach(b=>b.onclick=()=>{pOpen=false;(b.dataset.person!==P.slug?setPerson(b.dataset.person):Promise.resolve(renderPicker())).then(toStats)});
  ['#cats button.on','#persons button.on'].forEach(sel=>{const b=document.querySelector(sel);let r=b&&b.parentElement;
    while(r&&r.id!=='picker'&&!(r.scrollWidth>r.clientWidth))r=r.parentElement;if(r&&r.id==='picker')r=null;
    if(r){const l=r.querySelector('.lbl'),pad=l&&getComputedStyle(l).position==='sticky'?l.offsetWidth+12:24,
      x=b.offsetLeft-r.offsetLeft;if(x-pad<r.scrollLeft||x+b.offsetWidth>r.scrollLeft+r.clientWidth-20)r.scrollLeft=Math.max(0,x-pad)}});   // only if not fully visible
  scrollSelChip();
}
function scrollSelChip(){   // mm45: keep the selected speaker chip visible inside #persons without scrolling the page
  const b=document.querySelector('#persons button.chip.on'),host=$('persons');if(!b||!host)return;
  if(host.scrollHeight<=host.clientHeight+2)return;   // only when #persons is its own scroller
  const br=b.getBoundingClientRect(),hr=host.getBoundingClientRect();
  if(br.top<hr.top+4)host.scrollTop+=br.top-hr.top-8;
  else if(br.bottom>hr.bottom-4)host.scrollTop+=br.bottom-hr.bottom+8;
}
$('psearch').addEventListener('input',e=>{pq=e.target.value.trim();renderPicker()});
$('psearch').addEventListener('keydown',e=>{if(e.key==='Enter'){const b=$('persons').querySelector('button.chip');if(b){e.preventDefault();setPerson(b.dataset.person)}}
  else if(e.key==='Escape'&&e.target.value){e.target.value='';pq='';renderPicker();e.stopPropagation()}});
async function setPerson(slug,docIds){
  {const dp=$('docPick');if(dp&&dp.open)dp.open=false}   // mm26: a new speaker closes the documents sheet/popover
  hidePop();
  const p=await loadPerson(BY.get(slug)||BY.get(DEFAULT));
  P=p;V=p.vocab;VI=p.VI;DOCS=p.docs;YEARS=[...new Set(DOCS.map(d=>d.year))].sort().reverse();
  if(docIds===undefined){const latest=DOCS.length?DOCS.reduce((a,b)=>b.date>a.date?b:a,DOCS[0]):null;sel=new Set(latest?[latest.id]:[])}
  else if(docIds.includes('all'))sel=new Set(DOCS.map(d=>d.id));
  else if(docIds.includes('none')||!docIds.length)sel=new Set();
  else sel=new Set(docIds.filter(i=>DOCS.some(d=>d.id===i)));
  ['fed','ceo','cab','cong','scotus','gov'].forEach(m=>document.body.classList.toggle('mode-'+m,(P.mode||(P.category===PEOPLE[0].category?'fed':'ceo'))===m));
  $('bioText').textContent=P.bio||'';$('bioLink').href='speakers/'+encodeURIComponent(P.slug)+'.html';$('pbio').hidden=!P.bio;
  $('eyebrow').textContent=P.eyebrow||`${P.category.replace(/s$/,'')} · ${P.org}`;
  $('personTitle').innerHTML=`<span class="ft">From the mouth of</span> <span class="pn">${esc(P.display)}</span>`;   // mm40: no ticker here; it shows once, in the speaker row (and sticky bar)
  document.title=P.slug===DEFAULT?'MouthMath — Word Counts from Fed Chairman Speeches & CEO Earnings Calls':`MouthMath — From the mouth of ${P.display}${P.ticker?` (${P.ticker})`:''}`;
  $('dataThrough').textContent='Data through '+fmtDate(DOCS.map(d=>d.date).sort().pop())+'.';
  renderPicker();buildTimeframe();update();if(typeof sbFill==='function'&&sbOn)sbFill();
}

// ---- phone toggles: Timeframe details and About start collapsed on small screens ----
const PHONE=matchMedia('(max-width:640px)');

function setAbout(o){$('about').classList.toggle('open',o);$('aboutToggle').setAttribute('aria-expanded',o)}
setAbout(!PHONE.matches||location.hash==='#about');
$('aboutToggle').onclick=()=>setAbout(!$('about').classList.contains('open'));
document.querySelector('header a.about-link').addEventListener('click',()=>setAbout(true));
addEventListener('hashchange',()=>{if(location.hash==='#about')setAbout(true)});
$('toTop').onclick=()=>{const rm=matchMedia('(prefers-reduced-motion: reduce)').matches;   // mm33: smooth, or instant with reduced motion
  scrollTo({top:0,left:0,behavior:rm?'instant':'smooth'});const L=document.querySelector('header .logo');if(L)L.focus({preventScroll:true})};

// ---- timeframe UI ----
function buildTimeframe(){
  const host=u=>{try{return new URL(u).hostname.replace(/^www\./,'')}catch(e){return 'source'}};
  $('docList').innerHTML=DOCS.map(d=>`<li data-id="${d.id}"><input type="checkbox" id="cb_${d.id}" data-id="${d.id}" aria-describedby="dm_${d.id}">
 <div><label for="cb_${d.id}" class="dl1"><span class="date">${fmtDate(d.date)}</span><span class="dt">${esc(d.title)}</span><span class="dw">${d.words.toLocaleString()} words</span></label>
 <div class="dl2 muted" id="dm_${d.id}">${d.stype?`<span class="stype"><span class="sr">Source type: </span>${esc(d.stype)}</span>`:`<span>${esc(d.type[0].toUpperCase()+d.type.slice(1))}</span>`}${[d.location,d.note].filter(x=>x&&x!==host(d.url)).map(x=>`<span>${esc(x)}</span>`).join('')}<a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer" title="Open the original">${esc(host(d.url))}&nbsp;↗</a></div></div>
 <button type="button" class="only" data-only="${d.id}" aria-label="Select only ${esc(d.title)}">only</button></li>`).join('');
  $('years').innerHTML=YEARS.map(y=>{const n=DOCS.filter(d=>d.year===y).length;
    return `<label class="chip" id="yc_${y}"><input type="checkbox" data-year="${y}"> ${y} <span class="muted">(${n})</span></label>`}).join('');
  document.querySelectorAll('#docList input').forEach(cb=>cb.onchange=()=>{cb.checked?sel.add(cb.dataset.id):sel.delete(cb.dataset.id);update()});
  document.querySelectorAll('#docList .only').forEach(a=>a.onclick=()=>{sel=new Set([a.dataset.only]);update()});
  document.querySelectorAll('#years input').forEach(cb=>cb.onchange=()=>{
    DOCS.filter(d=>d.year===cb.dataset.year).forEach(d=>cb.checked?sel.add(d.id):sel.delete(d.id));update()});
}
// ---- mm26: the documents sheet (phones) / popover (wider): close on the backdrop, the x, Esc; the docs stat opens it ----
{const DP=$('docPick'),sm=DP.querySelector('summary'),phone=matchMedia('(max-width:640px)');
 DP.addEventListener('toggle',()=>{const o=DP.open;document.documentElement.classList.toggle('dsopen',o&&phone.matches);
  if(o){hidePop();yrsFit();requestAnimationFrame(()=>$('dsClose').focus({preventScroll:true}))}else if(DP.contains(document.activeElement))sm.focus({preventScroll:true})});
 DP.querySelector('.dsback').onclick=()=>{DP.open=false};$('dsClose').onclick=()=>{DP.open=false};$('dsClose2').onclick=()=>{DP.open=false};
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&DP.open){e.preventDefault();DP.open=false}});
 const ds=$('sDocs').closest('.stat');ds.tabIndex=0;ds.setAttribute('role','button');ds.setAttribute('aria-label','Choose documents');
 ds.onclick=()=>{DP.open=true};ds.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();DP.open=true}}}
$('btnAll').onclick=()=>{sel=new Set(DOCS.map(d=>d.id));update()};
$('btnNone').onclick=()=>{sel=new Set();update()};
function docKind(d){const t=(d&&d.type||'doc').replace(/^hearing remarks$/i,'remarks').replace(/^opinion of the Court$/i,'opinion');return t.replace(/\b\w/g,c=>c.toUpperCase())}
function kindNoun(n){   // speech / letter / opinion… per speaker
  const u=P&&P.unit||'',up=P&&P.unit_pl||'';
  if(u&&u!=='document')return n===1?u:(up||u+'s');
  const t=DOCS.map(d=>(d.type||'').toLowerCase()),sp=/^(speech|testimony|remarks|hearing|hearing remarks|address|floor remarks|conference)$/;
  if(t.length&&t.every(x=>sp.test(x)))return n===1?'speech':'speeches';
  if(t.length&&t.every(x=>x==='letter'))return n===1?'letter':'letters';
  if(t.length&&t.every(x=>/opinion/.test(x)))return n===1?'opinion':'opinions';
  return n===1?'document':'documents'}
function dbFill(){const n=DOCS.length,k=sel.size,e=$('dbN'),v=$('dbV');if(!e)return;
  const pl=kindNoun(2);const Pl=pl.charAt(0).toUpperCase()+pl.slice(1);if(v)v.textContent='Add '+Pl;{const h=document.querySelector('#docPick .dshead b');if(h)h.textContent=Pl}
  const L=n?DOCS.reduce((a,b)=>b.date>a.date?b:a,DOCS[0]):null,only=!!L&&k===1&&sel.has(L.id);
  e.textContent=k===n?`All ${n.toLocaleString()}`:`${k.toLocaleString()} of ${n.toLocaleString()}`;
  const l=$('dbLatest');if(l)l.textContent=only?`Latest · ${fmtDate(L.date)} · ${L.title}`:'';
  const sl=$('sDocs').closest('.stat').querySelector('.sl');if(sl){const w=kindNoun(k);sl.textContent=w;sl.setAttribute('data-s',w)}
  e.closest('summary').setAttribute('aria-label',`${Pl}: ${e.textContent} selected. Choose`)}
function yrsFit(){const y=$('years');if(y)y.classList.toggle('ovf',y.scrollWidth>y.clientWidth+1)}   // fade only when the years overflow
addEventListener('resize',()=>yrsFit());
function syncTimeframe(){
  DOCS.forEach(d=>{const on=sel.has(d.id);$('cb_'+d.id).checked=on;document.querySelector(`li[data-id="${d.id}"]`).classList.toggle('sel',on)});
  YEARS.forEach(y=>{const ids=DOCS.filter(d=>d.year===y).map(d=>d.id),k=ids.filter(i=>sel.has(i)).length;
    const cb=document.querySelector(`#years input[data-year="${y}"]`);cb.checked=k===ids.length;cb.indeterminate=k>0&&k<ids.length;
    $('yc_'+y).classList.toggle('on',k===ids.length)});
  const all=sel.size===DOCS.length;$('btnAll').classList.toggle('on',all);$('btnNone').classList.toggle('on',sel.size===0);yrsFit();
  const ds=DOCS.filter(d=>sel.has(d.id));
  $('selSummary').innerHTML=!ds.length?`<b>No ${unitOf(2)} selected.</b>`:
    `Showing <b>${all?'all '+ds.length:ds.length+' of '+DOCS.length}</b> ${unitOf(all?ds.length:DOCS.length)}`+
    ` (${fmtDate(ds[ds.length-1].date)}${ds.length>1?' – '+fmtDate(ds[0].date):''})`;
  syncHash();
}
// URL state: #person=<slug>&docs=<all|none|id,...>&n=<5|100|all>; default (Warsh, latest doc only, 50 words) = clean URL. Old mode=cloud / mode=visual links (and #cloud) scroll to the Word Cloud; mode=standard is ignored. Leaves #about etc. alone.
const OURS=/^#(person|docs|mode|n|view|vs)=/;
function syncHash(){
  if(!P)return;const all=sel.size===DOCS.length&&DOCS.length>0,none=!sel.size;
  const latest=DOCS.length?DOCS.reduce((a,b)=>b.date>a.date?b:a,DOCS[0]):null;
  const latestOnly=!!latest&&sel.size===1&&sel.has(latest.id),parts=[];
  if(P.slug!==DEFAULT)parts.push('person='+P.slug);
  if(latestOnly);   // latest-only is the default: omit docs= (clean URL when also default person)
  else if(all)parts.push('docs=all');
  else if(none)parts.push('docs=none');
  else parts.push('docs='+[...sel].join(','));
  if(CMP)parts.push('vs='+CMP.slug);
  if(NSHOW!==nDef())parts.push('n='+NSHOW);   // 50 words is the default (clean URL)
  if(VIEW==='cloud'&&!SIDE.matches)parts.push('view=cloud');if(VIEW==='race')parts.push('view=race');if(VIEW==='ring')parts.push('view=ring');   // the Word Cloud tab (side by side on wide screens: nothing to keep)
  const h=location.hash,ours=!h||OURS.test(h),want=parts.length?'#'+parts.join('&'):'';
  if(want)history.replaceState(null,'',want);else if(ours&&h)history.replaceState(null,'',location.pathname+location.search);
}

// ---- counting / table ----
let BASE=[];
function aggregate(){
  const cnt=new Map();
  DOCS.forEach(d=>{if(!sel.has(d.id))return;d.cnt.forEach((n,wi)=>cnt.set(wi,(cnt.get(wi)||0)+n))});
  BASE=[...cnt].map(([i,n])=>({word:V[i],count:n,stop:STOP.has(V[i])}));
}
// ---- polish: count-up on the red stats when a person loads (skipped for reduced motion and automated browsers) ----
let lastCountSlug='';const RM_CU=matchMedia('(prefers-reduced-motion: reduce)');
function setStat(id,n,anim){const el=$(id);el.dataset.v=n;cancelAnimationFrame(el._raf||0);
  if(!anim||RM_CU.matches||(navigator.webdriver&&!window.__countUp)||n<10){el.textContent=n.toLocaleString();return}
  const t0=performance.now(),D=650;
  const step=t=>{const k=Math.min(1,(t-t0)/D),e=1-Math.pow(1-k,3);el.textContent=Math.round(n*e).toLocaleString();if(k<1)el._raf=requestAnimationFrame(step)};
  el._raf=requestAnimationFrame(step)}
let cwOpen=false;   // the '+K common words' line: collapsed until tapped
function render(cloudToo=true){if(VIEW==='race')setTimeout(playRace,0);if(VIEW==='ring')setTimeout(playRing,0);   // one selection feeds both: the Mouth Math table (top N, sortable) and the Word Cloud (top N by count)
  const base=BASE.filter(x=>!(hide.checked&&x.stop));
  base.sort((a,b)=>b.count-a.count||(a.word<b.word?-1:a.word>b.word?1:0));
  let r=0,prev=null;base.forEach((x,i)=>{if(x.count!==prev){r=i+1;prev=x.count}x.rank=r});
  const s=q.value.trim().toLowerCase();let re=null;if(s){try{re=new RegExp(s)}catch(e){}}
  const match=s?base.filter(x=>re?re.test(x.word):x.word.includes(s)):base.slice();
  const cap=Math.min(nCap(),LIMIT);let tail=[];
  if(hide.checked){   // stopwords that WOULD rank in the top N go to the bottom of the N rows (faint gray italics, real rank)
    const full=BASE.slice().sort((a,b)=>b.count-a.count||(a.word<b.word?-1:a.word>b.word?1:0));
    let r2=0,p2=null;full.forEach((x,i)=>{if(x.count!==p2){r2=i+1;p2=x.count}x.rr=r2});
    tail=(s?full.filter(x=>re?re.test(x.word):x.word.includes(s)):full).slice(0,cap).filter(x=>x.stop)}
  const list=match.slice(0,cap);   // table: always the full top N real words (hide on), then sorted as chosen; the stopwords that would rank in the top N fold into ONE '+K common words' line
  list.sort((a,b)=>{const va=a[sortK],vb=b[sortK];const c=typeof va==='string'?(va<vb?-1:va>vb?1:0):va-vb;return c*sortDir||a.rank-b.rank});
  $('sDocs').textContent=sel.size===DOCS.length||sel.size===1?sel.size.toLocaleString():sel.size+' / '+DOCS.length;dbFill();
  const anim=P.slug!==lastCountSlug;lastCountSlug=P.slug;
  setStat('sTotal',base.reduce((t,x)=>t+x.count,0),anim);
  setStat('sUnique',base.length,anim);
  const max=base.length?base[0].count:1;
  const topW=list.length?list.reduce((a,b)=>b.count>a.count||(b.count===a.count&&b.word<a.word)?b:a).word:null;   // the single most frequent word (red)
  tb.innerHTML=(list.length||tail.length)?list.map(x=>`<tr class="${x.stop?'stop':''}${x.word===topW?' top':''}" data-w="${esc(x.word)}"${x.word===topW?` tabindex="0" role="button" aria-label="#1 word, ${esc(x.word)}: ${x.count.toLocaleString()} — show excerpts"`:''}><td class="num">${x.rank}</td><td class="w">${esc(x.word)}</td><td class="num cnt">${x.count.toLocaleString()}</td><td><div class="bar" style="width:${(100*x.count/max).toFixed(1)}%"></div></td></tr>`).join('')+
      (tail.length?`<tr class="cwl" tabindex="0" role="button" aria-expanded="${cwOpen}"><td class="num"></td><td class="w" colspan="3">${cwOpen?'Hide':'+'}${cwOpen?' ':''}${tail.length.toLocaleString()} common words</td></tr>`:'')+
      (cwOpen?tail:[]).map(x=>`<tr class="stop tail" data-w="${esc(x.word)}"><td class="num"></td><td class="w">${esc(x.word)} <span class="rr">(#${x.rr})</span></td><td class="num cnt">${x.count.toLocaleString()}</td><td></td></tr>`).join('')
    :`<tr><td colspan="4" class="empty">${sel.size?'No matching words.':'Select at least one document above.'}</td></tr>`;
  setStat('sShown',list.length,anim);
  $('realSpots').checked=!hide.checked;$('rsrow').hidden=!(tail.length||!hide.checked);
  $('more').textContent=match.length>list.length?`Showing the top ${list.length.toLocaleString()} of ${match.length.toLocaleString()} words${match.length>LIMIT&&NSHOW==='all'?' (table limit; use the filter to find others)':' · choose Max above to list every word'}.`:'';
  $('more').classList.toggle('lim',match.length>LIMIT&&NSHOW==='all');   // the line only shows when the table limit is hit
  document.querySelectorAll('th[data-k]').forEach(th=>{const l=th.dataset.l||(th.dataset.l=th.textContent.replace(/ [▲▼▴▾]$/,''));th.innerHTML=esc(l)+(th.dataset.k===sortK?`<span class="sarr" aria-hidden="true">${sortDir<0?' ▾':' ▴'}</span>`:'')});
  placeTopRing();cmpRender();
  if(cloudToo)drawCloud(match);
}
function placeTopRing(){const ring=$('topRing'),t=tb.querySelector('tr.top');if(!ring)return;if(!t){ring.hidden=true;return}
  const w=ring.parentNode.getBoundingClientRect(),r=t.getBoundingClientRect();ring.hidden=false;
  ring.style.cssText=`left:${(r.left-w.left).toFixed(1)}px;top:${(r.top-w.top).toFixed(1)}px;width:${r.width.toFixed(1)}px;height:${r.height.toFixed(1)}px`}
if(window.ResizeObserver)new ResizeObserver(()=>placeTopRing()).observe(document.querySelector('.tbwrap table'));
function update(){hidePop();syncTimeframe();aggregate();render()}
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{hidePop();const k=th.dataset.k;
  if(sortK===k)sortDir*=-1;else{sortK=k;sortDir=k==='count'?-1:1}render(false)});   // sorting only reorders the table; the cloud stays as is
q.oninput=()=>{hidePop();render()};hide.onchange=()=>{hidePop();render()};
$('realSpots').onchange=()=>{hide.checked=!$('realSpots').checked;hidePop();render();   // common words back in their real ranks (italic), then back to the top of the table
  requestAnimationFrame(()=>{const top=scrollY+$('stats').getBoundingClientRect().top-8;if(top<scrollY)scrollTo({top:Math.max(0,top),behavior:RM.matches?'instant':'smooth'})})};

// ---- sentence popover (hover = preview, click/tap = pin) ----
const TOK=/[a-z](?:\.[a-z])+\.?(?:'s)?(?![a-z0-9])|[a-z0-9]+(?:'[a-z]+)*/g; // = TOKEN_RE in build.py
function highlight(sent,word){ // same tokenizer rules as build.py; returns html + number of matches
  const norm=sent.replace(/[\u2018\u2019`]/g,"'"),low=norm.toLowerCase(),same=low.length===sent.length;
  let out='',last=0,n=0,m;TOK.lastIndex=0;
  while((m=TOK.exec(low))){let t=m[0];
    if(t.includes('.')){if(t.endsWith("'s"))t=t.slice(0,-2);if(!t.endsWith('.'))t+='.'}
    else if(t.endsWith("'s")&&!SC.has(t))t=t.slice(0,-2);
    if(!D.keepNum&&/^\d+$/.test(t))continue;
    if(t===word){n++;if(same){out+=esc(sent.slice(last,m.index))+'<mark>'+esc(sent.slice(m.index,m.index+m[0].length))+'</mark>';last=m.index+m[0].length}}}
  return {html:out+esc(sent.slice(last)),n};
}
const enc=s=>encodeURIComponent(s).replace(/-/g,'%2D');
const trimP=s=>s.replace(/^[\s"'\u201c\u2018(\[*]+/,'').replace(/[\s"'\u201d\u2019)\].,;:!?*]+$/,'');
function fragUrl(url,sent){ // Chrome/Edge/Safari text fragment: jumps to & highlights the sentence
  const w=sent.split(/\s+/);
  if(w.length<=10)return url+'#:~:text='+enc(trimP(sent));
  return url+'#:~:text='+enc(trimP(w.slice(0,5).join(' ')))+','+enc(trimP(w.slice(-5).join(' ')));
}
function srcLink(d,si){ // PDFs can't take text fragments; link to the page instead
  if(d.sp)return {href:d.url+'#page='+d.sp[si],label:'source ↗ (p. '+d.sp[si]+')'};
  return {href:fragUrl(d.url,d.s[si]),label:'source ↗'};
}
function stats(word){ // occurrences / distinct sentences / docs, from counts (independent of excerpts)
  const wi=VI.get(word);let n=0,m=0,docs=[];
  DOCS.forEach(d=>{if(!sel.has(d.id)||!d.cnt.has(wi))return;n+=d.cnt.get(wi);m+=d.ms.get(wi);docs.push(d)});
  return {n,m,docs};
}
function occurrences(word){ // [{doc, si, n}] embedded sentences for selected docs, newest first
  const wi=VI.get(word),items=[];
  DOCS.forEach(d=>{if(!sel.has(d.id))return;const a=d.occ.get(wi);if(!a)return;
    for(let i=0;i<a.length;){let j=i;while(j<a.length&&a[j]===a[i])j++;items.push({doc:d,si:a[i],n:j-i});i=j}});
  return items;
}
const pop=document.createElement('div');pop.id='pop';pop.hidden=true;pop.setAttribute('role','dialog');document.body.appendChild(pop);
let pinned=false,curWord=null,curRow=null,showAll=false,hoverT=null,hideT=null;
function popHTML(word){ // Compare columns: render against that column's speaker + documents
  const c=curRow&&curRow.dataset.cmp;if(c==='b'&&CMP){const lat=CMP.docs.length?CMP.docs.reduce((a,b)=>b.date>a.date?b:a,CMP.docs[0]):null;
    const sv=[P,VI,DOCS,sel];P=CMP;VI=CMP.VI;DOCS=CMP.docs;sel=new Set(lat?[lat.id]:[]);try{return popHTML0(word)}finally{[P,VI,DOCS,sel]=sv}}
  return popHTML0(word)}
function popHTML0(word){
  const st=stats(word),items=occurrences(word),excerpt=P.policy==='excerpt';
  const shown=(showAll&&!excerpt)?items:items.slice(0,FIRST),unit=n=>n===1?(P.unit||'document'):(P.unit_pl||(P.unit||'document')+'s');
  let h=`<div class="ph"><div><b>${esc(word)}</b>
   <div class="t" id="popCount">${st.n.toLocaleString()} occurrence${st.n===1?'':'s'} in ${st.m.toLocaleString()} sentence${st.m===1?'':'s'}`+
   ` · ${st.docs.length} of ${sel.size} selected ${unit(sel.size)}${st.n!==st.m?' · some sentences use it more than once':''}</div></div>
   <button class="x" title="Close (Esc)" aria-label="Close">×</button></div>`;
  let lastDoc=null;
  shown.forEach(it=>{if(it.doc!==lastDoc){if(lastDoc)h+='</ol>';lastDoc=it.doc;
      h+=`<div class="doc">${fmtDate(it.doc.date)} · <a href="${esc(it.doc.url)}" target="_blank" rel="noopener noreferrer">${esc(it.doc.title)}</a></div><ol>`}
    const s=it.doc.s[it.si],hl=highlight(s,word),L=srcLink(it.doc,it.si);
    h+=`<li data-n="${it.n}" data-hl="${hl.n}">${hl.html}${it.n>1?`<span class="twice">×${it.n}</span>`:''}`+
       `<a class="src" href="${esc(L.href)}" target="_blank" rel="noopener noreferrer" title="Open the original at this sentence">${L.label}</a></li>`});
  if(lastDoc)h+='</ol>';
  if(excerpt){
    const links=st.docs.map(d=>`<a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">${esc(d.title)}</a>`).join(', ');
    h+=`<div class="cap" id="popCap">${shown.length?`Showing ${shown.length} of ${st.m.toLocaleString()} sentence${st.m===1?'':'s'}`:'No excerpt shown for this word'}`+
       ` — read the full ${unit(st.docs.length)} at ${esc(P.source)}: ${links}</div>`;
  }else if(items.length>FIRST&&!showAll)h+=`<button class="more">Show all ${items.length.toLocaleString()} sentences (${st.n.toLocaleString()} occurrences)</button>`;
  h+=`<div class="hint">${pinned?'Esc or × to close':'Click the word to pin'} · “source ↗” opens the original</div>`+(P.credit?`<div class="credit">Source: ${esc(P.credit)}</div>`:'');
  return h;
}
function placePop(){
  if(!curRow||!curRow.isConnected)return;const isRow=curRow.tagName==='TR',vw=document.documentElement.clientWidth;
  const cell=(isRow?curRow.querySelector('td.w'):curRow).getBoundingClientRect();
  let left=isRow?cell.left+Math.min(cell.width,140)+8:cell.right+8,width=Math.min(600,vw-left-12);
  if(width<320){left=8;width=vw-16}
  pop.style.left=(left+scrollX)+'px';pop.style.width=width+'px';
  pop.style.top=((width===vw-16?cell.bottom+4:cell.top-8)+scrollY)+'px';
}
function showPop(tr,pin){
  if(curRow)curRow.classList.remove('active');
  if(curWord!==tr.dataset.w)showAll=false;
  curRow=tr;curWord=tr.dataset.w;pinned=pin||pinned&&curWord===tr.dataset.w;tr.classList.add('active');
  const fresh=pop.hidden||pop.dataset.w!==curWord;   // mm37: the glow plays once per opening, not again on pin / re-render
  pop.innerHTML=popHTML(curWord);pop.dataset.w=curWord;pop.classList.toggle('noglow',!fresh);pop.classList.toggle('expanded',showAll);pop.hidden=false;placePop();
}
// mm29: a tapped / clicked word (not a hover) scrolls the PAGE so the excerpts panel's top sits near the top of the screen, under the
// sticky speaker bar when that bar will be showing; the panel's own text is never scrolled. Reduced motion = instant jump.
function popToTop(){requestAnimationFrame(()=>{if(pop.hidden)return;const r=pop.getBoundingClientRect(),st=$('stats').getBoundingClientRect(),de=document.documentElement;
  const y=scrollY+r.top,bar=$('spkbar'),barH=bar&&getComputedStyle(bar).display!=='none'?bar.offsetHeight:0;
  let t=y-10-barH;if(scrollY+st.bottom-t>=0)t=y-10;   // the bar only shows once the red stats have scrolled away
  t=Math.max(0,Math.min(de.scrollHeight-innerHeight,Math.round(t)));if(Math.abs(t-scrollY)<4)return;
  scrollTo({top:t,behavior:RM.matches?'instant':'smooth'})})}
function hidePop(){pop.hidden=true;pinned=false;showAll=false;curWord=null;if(curRow)curRow.classList.remove('active');curRow=null}
const cloud=$('cloud');
[tb,cloud,$('cmpOut')].forEach(box=>{
box.addEventListener('mouseover',e=>{const tr=e.target.closest('[data-w]');if(!tr||pinned)return;clearTimeout(hideT);
  if(tr===curRow)return;clearTimeout(hoverT);hoverT=setTimeout(()=>showPop(tr,false),120)});
box.addEventListener('mouseleave',()=>{clearTimeout(hoverT);if(!pinned)hideT=setTimeout(hidePop,300)});
box.addEventListener('click',e=>{const tr=e.target.closest('[data-w]');if(!tr)return;clearTimeout(hoverT);clearTimeout(hideT);pinned=false;showPop(tr,true);popToTop()});
});
pop.addEventListener('mouseenter',()=>clearTimeout(hideT));
pop.addEventListener('mouseleave',()=>{if(!pinned)hideT=setTimeout(hidePop,300)});
pop.addEventListener('click',e=>{e.stopPropagation(); // re-render detaches e.target; don't let the outside-click handler close us
  if(e.target.closest('.x')){hidePop();return}
  if(e.target.closest('.more')&&P.policy!=='excerpt'){showAll=true;pinned=true;pop.innerHTML=popHTML(curWord);pop.classList.add('expanded','noglow');placePop()}});
document.addEventListener('keydown',e=>{if(e.key==='Escape')hidePop()});
// ---- polish: Share (copies the exact view's URL) and keyboard shortcuts ----
let toastT=null;
function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('on');clearTimeout(toastT);toastT=setTimeout(()=>t.classList.remove('on'),2200)}
async function shareView(){syncHash();const url=location.href;
  try{if(navigator.share&&matchMedia('(pointer:coarse)').matches){await navigator.share({title:document.title,url});return}
    await navigator.clipboard.writeText(url);toast('Link copied: '+P.name)}
  catch(err){if(err&&err.name==='AbortError')return;toast('Copy this link: '+url)}}
$('share').onclick=shareView;
document.addEventListener('keydown',e=>{
  if(!$('tvModal').hidden||e.metaKey||e.ctrlKey||e.altKey||e.target.closest('input,textarea,select,[contenteditable]'))return;
  if(e.key==='/'){e.preventDefault();q.focus();q.select()}
  else if(e.key==='v'||e.key==='V'){if(!SIDE.matches)setView(VIEW==='cloud'?'math':'cloud',true)}
  else if(e.key==='s'||e.key==='S'){shareView()}
  else if(e.key==='?'){toast('Shortcuts: / filter words · V switch Math ↔ Cloud · S share');const h=$('kbdHint');h.classList.add('flash');setTimeout(()=>h.classList.remove('flash'),1200)}});
// ---- Ad slots: ONE config block. Faint decorative placeholders (same sizes, no text) until ADS.client and the slot ids are filled in (then AdSense units render) ----
const ADS={
  client:'',            // set to 'ca-pub-5930727143587260' with real slot ids after approval (empty = mock placeholders; the AdSense script itself is in <head>)
  slots:{               // desktop size (w x h) and phone size (mw x mh); id = AdSense data-ad-slot
    leader:   {id:'',w:468,h:60, mw:320,mh:50},     // below the results card
    side:     {id:'',w:200,h:200},                  // desktop left column, below Who / Timeframe (hidden on phones)
    between:  {id:'',w:468,h:60, mw:320,mh:50},    // inside the results card, between the Mouth Math table and the Word Cloud
    incontent:{id:'',w:468,h:60, mw:320,mh:50}}};  // between the method note and About
function renderAds(){let live=false;if(ADS.client&&!(document.querySelector('#tb tr')&&($('bioText')||{}).textContent)){setTimeout(renderAds,800);return}   // adsense-content: no ad units before the word table and bio are on screen
  document.querySelectorAll('aside.ad').forEach(el=>{const c=ADS.slots[el.dataset.slot];if(!c){el.remove();return}
    ['w','h','mw','mh'].forEach(k=>el.style.setProperty('--a'+k,(c[k]||c[k.slice(1)])+'px'));
    if(ADS.client&&c.id){live=true;el.removeAttribute('aria-hidden');el.removeAttribute('role');el.setAttribute('aria-label','Advertisement');el.innerHTML=`<span class="adl">Advertisement</span><ins class="adsbygoogle" style="display:block" data-ad-client="${esc(ADS.client)}" data-ad-slot="${esc(c.id)}" data-ad-format="auto" data-full-width-responsive="true"></ins>`}
    else{const sz=`${c.w}x${c.h}`,ph=c.mw?`${c.mw}x${c.mh}`:'none';   // mock: decorative, no text; invisible metadata so a real unit can drop in later
      el.innerHTML=`<div class="adbox adfaint" role="presentation" aria-hidden="true" data-ad-slot-name="${el.dataset.slot}" data-ad-size="${sz}" data-ad-size-phone="${ph}"></div>`;
      el.removeAttribute('aria-label');el.setAttribute('aria-hidden','true');el.setAttribute('role','presentation')}});
  if(live){if(!document.querySelector('script[src*="adsbygoogle"]')){const sc=document.createElement('script');sc.async=true;sc.crossOrigin='anonymous';   // the AdSense script is already in <head>; this is a fallback
    sc.src='https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='+encodeURIComponent(ADS.client);document.head.appendChild(sc)}
    document.querySelectorAll('ins.adsbygoogle').forEach(()=>(window.adsbygoogle=window.adsbygoogle||[]).push({}))}}
renderAds();
document.addEventListener('click',e=>{if(!pop.hidden&&pinned&&!pop.contains(e.target)&&!e.target.closest('[data-w]'))hidePop()});

// ---- Word Cloud (below the Mouth Math table): word cloud (vanilla JS; spiral placement + measureText box collisions) ----
let cloudW=0,cloudInfo={placed:0,skipped:0,ms:0};
const PAL=['#b77ee0','#a66ad8','#c79bec'],PALRGB=PAL.map(h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16)));
const tint=(w,al)=>{const c=PALRGB[hcode(w)%PAL.length];return al>=1?PAL[hcode(w)%PAL.length]:`rgba(${c[0]},${c[1]},${c[2]},${al})`};   // depth: farther words are dimmer (alpha floor .66)
const hcode=s=>{let h=7;for(let i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))|0;return Math.abs(h)};
const mctx=document.createElement('canvas').getContext('2d');
// The cloud silhouette (unit coordinates: x 0..1 across, y 0..0.72 down): a flat-ish pill base with three overlapping bumps on top.
// Words are only placed where their whole box falls inside it, so the shape comes from the word placement itself (nothing is drawn).
const CS_ASPECT=0.72,CS_BUMPS=[[0.23,0.42,0.16],[0.52,0.34,0.22],[0.79,0.44,0.16]];
function inCloud(u,v){   // u: 0..1 across, v: 0..CS_ASPECT down
  if(u>=0.14&&u<=0.86&&v>=0.40&&v<=0.60)return true;   // body
  if(u>=0.04&&u<=0.96&&v>=0.48&&v<=0.72){const px=Math.max(0.16,Math.min(0.84,u)),dx=u-px,dy=v-0.60;if(dx*dx+dy*dy<=0.12*0.12)return true}
  for(const [cu,cv,r] of CS_BUMPS){const dx=u-cu,dy=v-cv;if(dx*dx+dy*dy<=r*r)return true}
  return false}
const CS_FILL=(()=>{let n=0,t=0;for(let i=0;i<50;i++)for(let j=0;j<36;j++){t++;if(inCloud((i+.5)/50,(j+.5)/50))n++}return n/t})();   // share of the 1 x CS_ASPECT frame the silhouette covers
function cloudLayoutAt(words,W,minF,mul,strict){
  const fam=getComputedStyle(cloud).fontFamily,GAP=2,RATIO=2.7,sq=Math.sqrt,Wc=W,stretch=(W<340?1.55:W<500?1.3:1)*Math.max(1,sq(words.length/50))*mul,Hf=CS_ASPECT*Wc*stretch,ox=0;
  // Words are set in lines that follow the cloud outline: line height peaks around the middle (biggest words, #1 first) and shrinks toward the top and the
  // bottom, so the rim is made of small bits. Words fill the lines in rank order (the line with the biggest type first), then the type is scaled up as far as all words still fit.
  const box=(x,n,f)=>{const mx=n?0:RING_MX,my=n?0:RING_MY;let wt,w,pad;f=Math.max(minF,f);   // #1 word: room for its two pill rings
    for(let k=0;k<4;k++){wt=f>=18?700:400;mctx.font=`${wt} ${f}px ${fam}`;pad=Math.round(f*.08)+1;
      w=Math.ceil(mctx.measureText(x.word).width)+2*pad;if(w+2*mx<=Wc*.5||f<=minF)break;f=Math.max(minF,f*(Wc*.5-2*mx)/w)}
    return {x,f:Math.round(f*10)/10,wt,pad,mx,my,w:w+GAP+2*mx,h:Math.ceil(f*1.12)+GAP+2*my}};
  const runsAt=(y,h,m)=>{const v0=(y+h*.3)/Hf*CS_ASPECT,v1=(y+h*.65)/Hf*CS_ASPECT,v2=(y+h)/Hf*CS_ASPECT,runs=[];let st=-1;
    for(let i=0;i<=400;i++){const u=i/400,ok=i<400&&inCloud(u,v0)&&inCloud(u,v1)&&inCloud(u,v2);
      if(ok&&st<0)st=u;if(!ok&&st>=0){const x0=st*Wc+m,x1=(i-1)/400*Wc-m;if(x1>x0)runs.push([x0,x1]);st=-1}}
    return runs};
  const cache=new Map(),runsC=(y,h)=>{const k=Math.round(y)*4096+h;let r=cache.get(k);if(!r){r=runsAt(y,h,2);cache.set(k,r)}return r};
  const tryPlace=(g,nW)=>{
    const fl=Math.max(minF,minF*g),fh=fl*(1+(RATIO-1)*Math.min(1,g)),sq0=sq(words[0].count),lo=sq(words[nW-1].count),MG=5,CAP=26,yc=Hf*0.5;
    const pool=words.slice(0,nW).map((x,n)=>{const b=box(x,n,sq0===lo?(fl+fh)/2:fl+(fh-fl)*Math.pow((sq(x.count)-lo)/(sq0-lo),1.1));
      b.d=Math.max(0,Math.min(1,(b.f-fl)/Math.max(1,fh-fl)));b.al=n?Math.round((0.66+0.34*sq(b.d))*100)/100:1;return b});   // depth: nearer (more frequent) = bigger and brighter, farther = smaller and dimmer
    const prof=ym=>fl+(fh-fl)*Math.pow(Math.max(0,1-Math.pow((ym-yc)/(Hf*0.6),2)),1.6);
    const pack=(list,h,y0)=>{const runs=runsC(y0,h),rows=runs.map(()=>[]),used=runs.map(()=>0);
      for(const b of list){let r=-1,rm=-1;runs.forEach((run,i)=>{const rest=run[1]-run[0]-used[i]-(rows[i].length?MG:0)-b.w;if(rest>=0&&rest>rm){rm=rest;r=i}});   // run with the most room left
        if(r<0)return null;used[r]+=b.w+(rows[r].length?MG:0);rows[r].push(b)}
      return {runs,rows}};
    const placed=[];let y=0,left=pool.slice();
    while(left.length&&y<Hf){
      const fd=prof(y+fl*0.7),cand=left.slice().sort((p,q)=>Math.abs(p.f-fd)-Math.abs(q.f-fd)||q.x.count-p.x.count);
      let list=[],h=0,pk=null;
      for(const c of cand){const nl=list.concat(c),nh=Math.max(h,c.h),np=pack(nl,nh,y);if(np){list=nl;h=nh;pk=np}}
      if(!list.length){y+=3;continue}
      if(y+h>Hf)break;
      pk.runs.forEach((run,r)=>{const row=pk.rows[r];if(!row.length)return;
        const seq=[];row.forEach((b,n)=>{if(!n)seq.push(b);else if(n%2)seq.unshift(b);else seq.push(b)});   // the line's biggest word sits mid-line
        const sw=seq.reduce((t,b)=>t+b.w,0),gp=seq.length>1?Math.min(CAP,(run[1]-run[0]-sw)/(seq.length-1)):0;
        let x=seq.length>1?run[0]+(run[1]-run[0]-sw-gp*(seq.length-1))/2:(run[0]+run[1]-seq[0].w)/2;
        seq.forEach(b=>{placed.push({x,y:y+(h-b.h)/2,w:b.w,h:b.h,b});x+=b.w+gp})});
      left=left.filter(b=>!list.includes(b));y+=h}
    return {placed,miss:nW-placed.length,steps:0}};
  let best=null,tries=1,sl=0.6,sh=5;
  if(tryPlace(sl,words.length).miss&&strict)return null;   // the most compact setting cannot hold every word: the caller tries smaller far words or a taller cloud
  for(let k=0;k<9;k++){const g=(sl+sh)/2;tries++;const r=tryPlace(g,words.length);if(!r.miss){best=r;sl=g}else sh=g}
  if(!best)best=tryPlace(sl,words.length);
  if(best.miss&&!strict){let nl=1,nh=words.length;best=null;for(let k=0;k<9&&nl<nh;k++){const n=Math.ceil((nl+nh)/2);tries++;const r=tryPlace(sl,n);if(!r.miss){best=r;best.miss=words.length-n;nl=n}else nh=n-1}   // last resort: keep the highest-ranked words that fit
    if(!best){best=tryPlace(sl,1);best.miss=words.length-1}}
  best.placed.forEach(c=>{c.x+=ox});
  return {placed:best.placed,miss:best.miss,tries,steps:best.steps,frame:{Wc,Hf,ox,minF,mul}};
}
// Every selected word is shown: try the normal sizes first; if they don't fit, let the farthest (smallest, dimmest) words go a little smaller, then make the cloud taller.
function cloudLayout(words,W){
  const mins=W<500?[11,10.5,10,9.5]:[12,11,10.5,10],muls=[1.15,1.3,1.5,1.75,2,2.4,3],last=mins[mins.length-1];let r=null,t=0;
  for(const m of mins){r=cloudLayoutAt(words,W,m,1,true);t++;if(r)break}
  if(!r)for(const mu of muls){r=cloudLayoutAt(words,W,last,mu,true);t++;if(r)break}
  if(!r)r=cloudLayoutAt(words,W,last,muls[muls.length-1],false);
  r.tries+=t;return r;
}
function drawCloud(list){
  stopSketch();
  const W=cloud.clientWidth;cloudW=W;if(!W)return 0;const t0=performance.now();
  const N=Math.min(NPICK?nCap():50,CLOUD_MAX),words=list.slice().sort((a,b)=>b.count-a.count||(a.word<b.word?-1:1)).slice(0,N);
  if(!words.length){cloud.style.height='';cloud.innerHTML=`<div class="empty">${sel.size?'No matching words.':'Select at least one document above.'}</div>`;
    $('cloudNote').textContent='';cloudInfo={placed:0,skipped:0,ms:0,mode:'static'};BODIES=[];return 0}
  const {placed,miss,tries,steps,frame}=cloudLayout(words,W);
  const py0=Math.min(...placed.map(c=>c.y)),y1=Math.max(...placed.map(c=>c.y+c.h)),ph=y1-py0+4;
  const minH=placed.length<=25?(W<600?200:230):0,y0=py0-Math.max(0,minH-ph)/2;   // short clouds (10/25 words) get room to float, words centered
  cloud.style.height=Math.ceil(Math.max(ph,minH))+'px';
  cloud.innerHTML=placed.map(c=>{const b=c.b,x=b.x;return `<span data-w="${esc(x.word)}" data-c="${x.count}" role="button" tabindex="0" aria-label="${x.word===words[0].word?'#1 word, ':''}${esc(x.word)}: ${x.count}${x.word===words[0].word?' — show excerpts':''}" `+
    `style="left:${(c.x+1+b.mx).toFixed(1)}px;top:${(c.y-y0+1+b.my).toFixed(1)}px;font-size:${b.f}px;font-weight:${b.wt};line-height:${c.h-2-2*b.my}px;height:${c.h-2-2*b.my}px;padding:0 ${b.pad}px;color:${x.word===words[0].word?'var(--num-red)':tint(x.word,b.al)}"${x.word===words[0].word||x.stop?` class="${[x.word===words[0].word?'top':'',x.stop?'stop':''].join(' ').trim()}"`:''}>${esc(x.word)}</span>`}).join('');
  TOPW=words[0].word;
  cloudInfo={placed:placed.length,skipped:miss,tries,steps,frame,ms:Math.round(performance.now()-t0),mode:'static'};
  buildBodies(placed,y0,W);markTop();ctrStatic();
  if(motion.checked&&BODIES.length)armSketch();
  $('cloudNote').textContent=`Top ${placed.length.toLocaleString()} of ${list.length.toLocaleString()} words${hide.checked?' (stopwords hidden)':''}`+
    `${list.length>placed.length+miss&&N===CLOUD_MAX?` · capped at ${CLOUD_MAX} to stay readable`:''}${miss?` · ${miss} didn't fit`:''}`;
  return placed.length;
}

// ---- Word Cloud motion: p5.js sketch (words as soft physics bodies); always the full selected timeframe ----
// p5 is loaded only when the Word Cloud first scrolls into view (and motion isn't reduced): pinned version, Subresource Integrity checked by the browser.
const P5_URL='https://cdn.jsdelivr.net/npm/p5@2.3.4/lib/p5.min.js',P5_SRI='sha384-Cs48F1uukMPysq29xNsf/FZL5ZNGsPfi6lDSGOxo6dypVFFiWO9Q3YbRKoXPPBii',MAX_BODIES=300;
// Words always float (no on/off toggle); prefers-reduced-motion users get the static layout, and so does everyone if p5 can't load.
const RM=matchMedia('(prefers-reduced-motion: reduce)'),motion={checked:!RM.matches,disabled:false};
RM.addEventListener('change',()=>{motion.checked=!RM.matches&&!motion.disabled;if(P)render()});
let P5P=null,SK=null,IO=null,BODIES=[],drawTok=0,frameN=0,TOPW=null,TOPB=null,REDC='#ff5449';
const PULSE={ph:0},RING_MX=15,RING_MY=11;   // PULSE.ph stays 0 (the #1 word no longer pulses; kept for the test hook). RING_*: room kept around the #1 word for its red contour (mm38, see ctrDims)   // top-word pulse period (CSS keyframes use the same 2.2 s)
// the single most frequent word in the cloud is drawn in the stat red (canvas + DOM spans)
function markTop(){if(!BODIES.length)return;const cn=b=>b.count;
  const t=BODIES.reduce((a,b)=>cn(b)>cn(a)||(cn(b)===cn(a)&&(b.count>a.count||(b.count===a.count&&b.word<a.word)))?b:a);
  TOPW=t.word;TOPB=t;REDC=getComputedStyle(document.documentElement).getPropertyValue('--num-red').trim()||REDC;
  BODIES.forEach(b=>{const on=b.word===TOPW;b.el.classList.toggle('top',on);b.el.style.color=on?'var(--num-red)':b.col})}
function ensureP5(){
  if(window.p5)return Promise.resolve();
  return P5P||(P5P=new Promise((ok,no)=>{const s=document.createElement('script');s.src=P5_URL;s.integrity=P5_SRI;s.crossOrigin='anonymous';
    const t=setTimeout(()=>{P5P=null;no(new Error('timeout'))},12000);
    s.onload=()=>{clearTimeout(t);window.p5?ok():no(new Error('p5 missing'))};s.onerror=()=>{clearTimeout(t);P5P=null;no(new Error('load failed'))};
    document.head.appendChild(s)}));
}
function buildBodies(placed,y0,W){
  const fam=getComputedStyle(cloud).fontFamily,spans=[...cloud.querySelectorAll('span[data-w]')];
  BODIES=placed.slice(0,MAX_BODIES).map((c,i)=>{const b=c.b,x=b.x;mctx.font=`${b.wt} 100px ${fam}`;
    const w0=b.w-2-2*b.mx,h0=c.h-2-2*b.my,hx=c.x+1+b.mx+w0/2,hy=c.y-y0+1+b.my+h0/2;
    return {word:x.word,count:x.count,el:spans[i],wt:b.wt,col:tint(x.word,b.al),fam,rw:mctx.measureText(x.word).width/100,
      hx,hy,x:hx,y:hy,vx:0,vy:0,sx:0,sy:0,mx:b.mx,my:b.my,f:b.f,ft:b.f,w:w0,h:h0,seed:i*7.31+1,rot:0,wv:waveOf(i)}});
  BODIES.forEach(boxOf);
}
function boxOf(b){if(b.f<0.4){b.w=b.h=0;return}const pad=Math.round(b.f*.08)+1;b.w=b.rw*b.f+2*pad;b.h=Math.ceil(b.f*1.12)}
function placeSpan(b,styleText){const el=b.el;if(!b.w){el.style.display='none';return}el.style.display='';
  el.style.left=(b.x-b.w/2).toFixed(1)+'px';el.style.top=(b.y-b.h/2).toFixed(1)+'px';
  if(SK){el.style.width=b.w.toFixed(1)+'px';el.style.height=b.h+'px'}
  else if(styleText){el.style.fontSize=b.f.toFixed(1)+'px';el.style.lineHeight=el.style.height=b.h+'px';el.style.padding=`0 ${Math.round(b.f*.08)+1}px`}}
// The cloud only animates while it is on screen: p5.js is fetched and the sketch started the first time the cloud scrolls into view
// (IntersectionObserver), then the loop pauses whenever it leaves the screen (see startSketch). Until then it is the static layout.
let ARM=null;
function armSketch(){const tok=++drawTok;if(ARM)ARM.disconnect();
  ARM=new IntersectionObserver(es=>{if(!es.some(e=>e.isIntersecting))return;ARM.disconnect();ARM=null;
    ensureP5().then(()=>{if(tok===drawTok&&BODIES.length)startSketch()})
      .catch(()=>{motion.checked=false;motion.disabled=true;$('cloudNote').textContent+=' · motion unavailable (p5.js could not load)'})},{rootMargin:'80px 0px'});
  ARM.observe(cloud)}
function stopSketch(){if(ARM){ARM.disconnect();ARM=null}if(IO){IO.disconnect();IO=null}if(SK){SK.remove();SK=null}cloud.classList.remove('live')}
function startSketch(){
  stopSketch();const W=cloud.clientWidth,H=cloud.clientHeight;if(!W||!H)return;
  BODIES.forEach(b=>{b.x=b.hx;b.y=b.hy;b.vx=b.vy=0;b.sx=b.sy=0;b.rot=0;b.f=b.ft;boxOf(b)});lastT=0;
  cloud.classList.add('live');cloudInfo.mode='p5';
  SK=new p5(p=>{
    p.setup=()=>{const cv=p.createCanvas(W,H);cv.elt.classList.add('cloudcv');cv.elt.setAttribute('aria-hidden','true');
      p.pixelDensity(Math.min(2,devicePixelRatio||1));p.frameRate(60);BODIES.forEach(b=>placeSpan(b))};
    p.draw=()=>{physics(p,W,H);paint(p);if(++frameN%3===0)BODIES.forEach(b=>placeSpan(b));else if(TOPB)placeSpan(TOPB)};   // the #1 word's rings track it every frame
  },cloud);
  IO=new IntersectionObserver(es=>es.forEach(e=>{if(SK)e.isIntersecting?SK.loop():SK.noLoop()}));IO.observe(cloud);   // pause off-screen
}
// "Floating on water": each word follows its own layered, eased sine drift around its home spot (slow vertical bob, slower
// sideways sway, a tiny tilt), riding a gentle swell that travels across the cloud so neighbours move together. Positions
// ease toward that target (frame-rate independent), overlaps are pushed apart softly (no velocity kicks), so there's no jitter.
function waveOf(i){const r=k=>{const v=Math.sin((i+1)*12.9898+k*78.233)*43758.5453;return v-Math.floor(v)};   // stable per-word randoms
  return {p1:r(1)*6.283,p2:r(2)*6.283,p3:r(3)*6.283,p4:r(4)*6.283,p5:r(5)*6.283,
    by:0.95+0.35*r(6),by2:1.7+0.5*r(7),sx:0.42+0.18*r(8),sx2:0.9+0.3*r(9),ro:0.55+0.25*r(10)}}   // rad/s: bob ~5-6.6 s, sway ~10-15 s
let lastT=0;
function physics(p,W,H){
  const t=p.millis()/1000*1.35,dt=Math.min(0.05,Math.max(0.001,t-(lastT||t-1/60)));lastT=t;
  const B=BODIES,GAP=1,ease=1-Math.pow(1-0.07,dt*60),sc=Math.max(0.65,Math.min(1,W/700))*(B.length>120?0.8:1);   // smaller swing on narrow or very dense clouds
  for(const b of B){b.f+=(b.ft-b.f)*0.1;if(Math.abs(b.ft-b.f)<0.03)b.f=b.ft;boxOf(b);if(!b.w)continue;
    const v=b.wv,top=b===TOPB,sz=top?Math.min(26,12+W*0.025)/15:Math.max(0.4,Math.min(1,1.3-b.f/55))*sc,swell=b.hx*0.009+b.hy*0.004;   // big words float less; the #1 word floats more (up to ~26px sway, ~17px bob)
    // main layer rides the shared swell (neighbours move together); a smaller second layer gives each word its own rhythm
    const ox=15*sz*(0.7*Math.sin(t*0.5-swell+v.p1*0.3)+0.3*Math.sin(t*v.sx2+v.p2)),
          oy=10*sz*(0.7*Math.sin(t*(top?1.25:1.05)-swell*1.2+v.p3*0.3)+0.3*Math.sin(t*v.by2+v.p4));   // #1: a slightly livelier bob
    b.sx=(b.sx||0)*0.985;b.sy=(b.sy||0)*0.985;                                                // separation offset relaxes slowly
    b.tx=Math.max((b.w/2+b.mx),Math.min(W-(b.w/2+b.mx),b.hx+ox+b.sx));b.ty=Math.max((b.h/2+b.my),Math.min(H-(b.h/2+b.my),b.hy+oy+b.sy));   // soft edges: the target stays inside
    b.x+=(b.tx-b.x)*ease;b.y+=(b.ty-b.y)*ease;
    b.rot=0}                            // <= ~1.3 degrees
  {const G=64,grid=new Map();     // spatial hash; overlapping boxes feed a smoothed separation offset (bigger words move less)
    B.forEach((b,i)=>{if(!b.w)return;for(let gx=Math.floor((b.x-(b.w/2+b.mx))/G);gx<=Math.floor((b.x+(b.w/2+b.mx))/G);gx++)for(let gy=Math.floor((b.y-(b.h/2+b.my))/G);gy<=Math.floor((b.y+(b.h/2+b.my))/G);gy++){
      const k=gx*4096+gy;(grid.get(k)||grid.set(k,[]).get(k)).push(i)}});
    const seen=new Set();
    for(const a of grid.values())for(let m=0;m<a.length;m++)for(let n=m+1;n<a.length;n++){const i=a[m],j=a[n],key=i<j?i*1000+j:j*1000+i;if(seen.has(key))continue;seen.add(key);
      const A=B[i],C=B[j],ox=((A.w+C.w)/2+A.mx+C.mx)+GAP-Math.abs(A.x-C.x),oy=((A.h+C.h)/2+A.my+C.my)+GAP-Math.abs(A.y-C.y);if(ox<=0||oy<=0)continue;
      const ma=C.w*C.h/(A.w*A.h+C.w*C.h),k=0.12;
      if(ox<oy){const s=A.x<C.x?-1:1;A.sx+=s*ox*ma*k;C.sx-=s*ox*(1-ma)*k;if(ox>3){A.x+=s*(ox-3)*ma*0.5;C.x-=s*(ox-3)*(1-ma)*0.5}}
      else{const s=A.y<C.y?-1:1;A.sy+=s*oy*ma*k;C.sy-=s*oy*(1-ma)*k;if(oy>3){A.y+=s*(oy-3)*ma*0.5;C.y-=s*(oy-3)*(1-ma)*0.5}}}}   // hard limit: never more than 3px of overlap
  for(const b of B){if(!b.w)continue;b.x=Math.max((b.w/2+b.mx),Math.min(W-(b.w/2+b.mx),b.x));b.y=Math.max((b.h/2+b.my),Math.min(H-(b.h/2+b.my),b.y))}
}
// ---- mm38: #1-word contour. Glyphs are dilated by a small gap, letter holes and narrow openings (e.g. inside "e") are filled, then thin
// red line(s) are traced just outside that silhouette. Cached per word/font/size. Used by the live canvas and the static span. ----
const CTR_TWO=false,CTR_RED='255,84,73';
const mkCv=(w,h)=>{const c=document.createElement('canvas');c.width=Math.max(1,w);c.height=Math.max(1,h);return c};
const CTRC=new Map();
function ctrDims(f){const g=Math.max(3,f*.085),w1=Math.max(1,f*.018),g2=Math.max(3,f*.07),w2=Math.max(.9,f*.014);const M=Math.ceil(g+w1+(CTR_TWO?g2+w2:0)+3);return {g,w1,g2,w2,M}}
// draw(c) paints the word in white on a context already scaled to CSS px; W,H in CSS px; pd = device pixel ratio
function ctrCanvas(key,W,H,pd,f,draw){const k=key+'|'+W+'|'+H+'|'+pd+'|'+(CTR_TWO?2:1);if(CTRC.has(k))return CTRC.get(k);
  const Wp=Math.ceil(W*pd),Hp=Math.ceil(H*pd),d=ctrDims(f);
  const S=mkCv(Wp,Hp),sx=S.getContext('2d');sx.setTransform(pd,0,0,pd,0,0);sx.fillStyle='#fff';draw(sx);
  const dil=(src,r)=>{const D=mkCv(Wp,Hp),c=D.getContext('2d'),R=r*pd;c.drawImage(src,0,0);if(R<=0)return D;
    const n=Math.max(16,Math.ceil(R*6));for(const m of [1,.75,.5,.25])for(let j=0;j<n;j++){const t=j/n*2*Math.PI;c.drawImage(src,Math.cos(t)*R*m,Math.sin(t)*R*m)}return D};
  // inner silhouette: dilate by the gap, then fill everything not reachable from the border (holes + closed-off openings)
  const I=dil(S,d.g),ic=I.getContext('2d',{willReadFrequently:true}),id=ic.getImageData(0,0,Wp,Hp),a=id.data,out=new Uint8Array(Wp*Hp),st=[];
  const push=i=>{if(!out[i]&&a[i*4+3]<128){out[i]=1;st.push(i)}};
  for(let x=0;x<Wp;x++){push(x);push((Hp-1)*Wp+x)}for(let y=0;y<Hp;y++){push(y*Wp);push(y*Wp+Wp-1)}
  while(st.length){const i=st.pop(),x=i%Wp;if(x>0)push(i-1);if(x<Wp-1)push(i+1);if(i>=Wp)push(i-Wp);if(i<Wp*(Hp-1))push(i+Wp)}
  for(let i=0;i<Wp*Hp;i++)if(!out[i]){a[i*4]=a[i*4+1]=a[i*4+2]=255;a[i*4+3]=255}
  ic.putImageData(id,0,0);
  const ring=(base,wd,alpha)=>{const A=dil(base,wd),c=A.getContext('2d');c.globalCompositeOperation='destination-out';c.drawImage(base,0,0);
    c.globalCompositeOperation='source-in';c.fillStyle=`rgba(${CTR_RED},${alpha})`;c.fillRect(0,0,Wp,Hp);return A};
  const C=mkCv(Wp,Hp),cc=C.getContext('2d');cc.drawImage(ring(I,d.w1,.95),0,0);
  if(CTR_TWO){const I2=dil(I,d.w1+d.g2);cc.drawImage(ring(I2,d.w2,.4),0,0)}
  if(CTRC.size>12)CTRC.clear();CTRC.set(k,C);return C}
const TOPCV=document.createElement('canvas'),TOPX=TOPCV.getContext('2d');
function paintTop(ctx,b,pd){const f=b.f,d=ctrDims(f),M=d.M,W=Math.ceil(b.w+2*M),H=Math.ceil(b.h+2*M),font=ctx.font,cx=W/2,cy=H/2+f*.03;
  const C=ctrCanvas(b.word+'|'+font,W,H,pd,f,c=>{c.font=font;c.textAlign='center';c.textBaseline='middle';c.fillText(b.word,cx,cy)});
  const Wp=C.width,Hp=C.height;if(TOPCV.width!==Wp||TOPCV.height!==Hp){TOPCV.width=Wp;TOPCV.height=Hp}
  const c=TOPX;c.setTransform(1,0,0,1,0,0);c.clearRect(0,0,Wp,Hp);
  c.setTransform(pd,0,0,pd,0,0);c.font=font;c.textAlign='center';c.textBaseline='middle';c.fillStyle=REDC;c.fillText(b.word,cx,cy);   // mm60: plain red #1 word (no outline, no glow)
  if(b.rot){const co=Math.cos(b.rot)*pd,sn=Math.sin(b.rot)*pd;ctx.setTransform(co,sn,-sn,co,b.x*pd,b.y*pd);ctx.drawImage(TOPCV,-W/2,-H/2,W,H);ctx.setTransform(pd,0,0,pd,0,0)}
  else ctx.drawImage(TOPCV,b.x-W/2,b.y-H/2,W,H)}
// static / reduced-motion cloud: the same contour behind the DOM span (text baseline matched with the font's ascent/descent)
function ctrStatic(){const e=cloud.querySelector('span.top');if(!e||cloud.classList.contains('live'))return;const cs=getComputedStyle(e),f=parseFloat(cs.fontSize);if(!f)return;
  const w0=e.offsetWidth;if(!w0)return;const d=ctrDims(f),M=d.M,w=e.offsetWidth,h=e.offsetHeight,W=w+2*M,H=h+2*M,pd=Math.min(3,devicePixelRatio||1),font=`${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  const C=ctrCanvas(e.dataset.w+'|'+font+'|s',W,H,pd,f,c=>{c.font=font;try{c.letterSpacing=cs.letterSpacing}catch(_){}c.textAlign='left';c.textBaseline='alphabetic';
    const mt=c.measureText(e.dataset.w),A=mt.fontBoundingBoxAscent||f*.905,D=mt.fontBoundingBoxDescent||f*.212,L=parseFloat(cs.lineHeight)||h;
    c.fillText(e.textContent,M+parseFloat(cs.paddingLeft||0),M+(L-(A+D))/2+A)});
  e.style.setProperty('--cm',M+'px');e.style.setProperty('--ctr',`url(${C.toDataURL()})`);e.classList.add('ctr')}
function paint(p){
  const ctx=p.drawingContext,pd=p.pixelDensity()||1;p.clear();ctx.setTransform(pd,0,0,pd,0,0);ctx.textAlign='center';ctx.textBaseline='middle';
  for(let i=BODIES.length-1;i>=0;i--){const b=BODIES[i];if(!b.w)continue;
    if(b.word===curWord){ctx.fillStyle=getComputedStyle(document.body).getPropertyValue('--hl').trim()||'#e2f0e7';ctx.beginPath();ctx.roundRect?ctx.roundRect(b.x-b.w/2,b.y-b.h/2,b.w,b.h,5):ctx.rect(b.x-b.w/2,b.y-b.h/2,b.w,b.h);ctx.fill()}
    ctx.font=`${STOP.has(b.word)?'italic ':''}${b.wt} ${b.f.toFixed(2)}px ${b.fam}`;   // stopwords italic (they only appear with 'Hide common stopwords' off)
    if(b.word===TOPW){paintTop(ctx,b,pd);continue}
    ctx.fillStyle=b.word===TOPW?REDC:b.col;
    if(b.rot){const c=Math.cos(b.rot)*pd,sn=Math.sin(b.rot)*pd;ctx.setTransform(c,sn,-sn,c,b.x*pd,(b.y+b.f*0.03)*pd);ctx.fillText(b.word,0,0);ctx.setTransform(pd,0,0,pd,0,0)}
    else ctx.fillText(b.word,b.x,b.y+b.f*0.03)}
}
// (mm24) The header jump links became the Mouth Math / Word Cloud tabs under the red stats (setView below).
// (mm32) The Word Cloud first-visit fade hint was removed; Word Cloud is red like Mouth Math.
// ---- Change speaker: after a pick the list folds and the name + red stats come to the top; a slim sticky bar (shown once the
// stats scroll away) brings the visitor back to the speaker list with the search focused ----
function toStats(){requestAnimationFrame(()=>{const r=$('stats').getBoundingClientRect();
  if(r.top<0||r.top>innerHeight*0.45)scrollTo({top:Math.max(0,scrollY+r.top-8),behavior:RM.matches?'instant':'smooth'})})}
function openSpeakers(){hidePop();if($('picker').querySelector('.pk').classList.contains('pcoll')){pOpen=true;renderPicker()}
  const vis=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden',s=$('psearch');
  const f=[s,document.querySelector('#persons button.chip.on'),$('pdisc'),document.querySelector('#cats button.on')].find(vis);
  if(f)f.focus({preventScroll:true});   // in the tap itself, so phones open the keyboard for the search
  scrollTo({top:0,behavior:RM.matches?'instant':'smooth'})}
// mm39: the speaker row / sticky bar label names who else you can search (Fed Chairman: plain 'Search')
function srchLbl(c){return 'Search'}
const SB=$('spkbar');let sbOn=false,sbRaf=0;
function sbFill(){if(!P)return;SB.querySelector('.sbn').textContent=P.name;SB.querySelector('.sbc').textContent=srchLbl(P.category);const t=SB.querySelector('.sbt');t.textContent=P.ticker||'';t.hidden=!P.ticker;
  SB.setAttribute('aria-label',`Search speakers: ${P.name}${P.ticker?' ('+P.ticker+')':''} selected`)}
function sbCheck(){sbRaf=0;const on=!!P&&$('stats').getBoundingClientRect().bottom<0;if(on===sbOn)return;sbOn=on;if(on)sbFill();
  SB.classList.toggle('show',on);SB.setAttribute('aria-hidden',on?'false':'true');SB.tabIndex=on?0:-1;document.body.classList.toggle('sbar',on)}
addEventListener('scroll',()=>{if(!sbRaf)sbRaf=requestAnimationFrame(sbCheck)},{passive:true});addEventListener('resize',()=>{if(!sbRaf)sbRaf=requestAnimationFrame(sbCheck)});
SB.onclick=openSpeakers;
// ---- Mouth Math / Word Cloud tabs: swap the view in place (no scrolling); from 1100px wide both show side by side ----
let VIEW='math';const SIDE=matchMedia('(min-width:1100px)');
function setView(v,user=false){VIEW=['cloud','race','ring'].includes(v)?v:'math';hidePop();$('vpanes').className='tab-'+VIEW;['math','cloud','race','ring'].forEach(x=>document.body.classList.toggle('view-'+x,VIEW===x));const nc=!NPICK&&NSHOW!==nDef();if(nc)setN(nDef(),false);
  document.querySelectorAll('#vtabs [role="tab"]').forEach(t=>{const on=t.dataset.view===VIEW;t.setAttribute('aria-selected',on?'true':'false');t.tabIndex=on?0:-1});
  if(P&&(nc||cloud.clientWidth&&cloud.clientWidth!==cloudW))render();else placeTopRing();   // the cloud is laid out when it first becomes visible
  if(VIEW==='race')playRace();else stopRace();if(VIEW==='ring')playRing();else stopRing();
  if(user)syncHash()}
// ---- mm71: Word Race: the top 10 words added up speech by speech, in date order ----
let raceT=0,raceRows={},raceKey='';

// ---- mm90: Word Ring (canvas): each spike ends in a word, longer = said more; hover/tap shows it in the center ----
const ringStill=()=>matchMedia('(prefers-reduced-motion:reduce)').matches;let ringRAF=0,ringW=[],ringKey='',ringHov=-1,ringPX=-1,ringPY=-1,ringTap=false;const ringPos=[];
function stopRing(){cancelAnimationFrame(ringRAF);ringRAF=0}
function ringData(){const pool=sel.size?DOCS.filter(d=>sel.has(d.id)):DOCS,m=new Map();
  pool.forEach(d=>d.cnt.forEach((n,wi)=>{const w=V[wi];if(hide.checked&&STOP.has(w))return;m.set(w,(m.get(w)||0)+n)}));
  const top=[...m].sort((a,b)=>b[1]-a[1]||(a[0]<b[0]?-1:1)).slice(0,Math.min(nCap(),RING_MAX)).map(([w,n])=>({w,n}));   // the Show buttons (5/20/50/100/Max) set how many spikes the ring has
  const gcd=(a,b)=>b?gcd(b,a%b):a;let st=37;while(top.length>1&&gcd(st,top.length)!==1)st++;   // scatter stride that always covers every word
  const ord=[];top.forEach((o,i)=>ord[(i*st)%top.length]=o);return {top,ord:ord.filter(Boolean)}}
const RING_MAX=150;let ringOff=0,ringVel=0,ringDrag=null,ringCur='';function playRing(){const c=$('ring');if(!c||!P)return;stopRing();const x=c.getContext('2d');let D=Math.min(devicePixelRatio||1,2);
  const RD=ringData(),words=RD.top,order=RD.ord,max=words.length?words[0].n:1;ringHov=-1;
  const RM=matchMedia('(prefers-reduced-motion:reduce)').matches,FILL=innerWidth<700?800:1300,seed=[...Array(FILL)].map(()=>[Math.random(),Math.random(),Math.random()]);
  const col=(a,t,al)=>{const h=Math.sin(a*2+t*.3)*.5+.5;return `rgba(${Math.round(225-50*h)},${Math.round(50+25*h)},${Math.round(80+150*h)},${al})`};
  const mkGlow=(r,g,b)=>{const S=48,k=document.createElement('canvas');k.width=k.height=S;const q=k.getContext('2d'),gr=q.createRadialGradient(S/2,S/2,0,S/2,S/2,S/2);gr.addColorStop(0,`rgba(${r},${g},${b},.9)`);gr.addColorStop(.3,`rgba(${r},${g},${b},.45)`);gr.addColorStop(.65,`rgba(${r},${g},${b},.12)`);gr.addColorStop(1,`rgba(${r},${g},${b},0)`);q.fillStyle=gr;q.fillRect(0,0,S,S);return k},GLOW=mkGlow(255,255,255),GLOWR=mkGlow(255,236,232);   // mm187 preview: one cached soft white halo sprite per dot (no shadowBlur per frame)
  function frame(now){const t=RM?0:now/1000,W=c.clientWidth,H=c.clientHeight;if(c.width!==W*D){c.width=W*D;c.height=H*D}x.setTransform(D,0,0,D,0,0);x.clearRect(0,0,W,H);
   if(!words.length){x.fillStyle='#a49e93';x.font='16px Arial';x.textAlign='center';x.fillText('No documents selected',W/2,H/2);return}
   const nar=W<560,cx=W/2,cy=H/2+(nar?4:8),R=Math.min(W,H)*(nar?.195:.21),Lmax=Math.min(W,H)*(nar?.185:.29),sq=1;
   const th=$('thumbHint');if(th){const S=Math.round(Math.min(114,R*1.7));th.style.cssText='left:'+cx+'px;top:'+cy+'px;width:'+S+'px;height:'+S+'px';th.firstElementChild.nextElementSibling.style.transform=RM?'none':'rotate('+(t*.042+ringOff)+'rad)'}   // mm184: the circle turns with the words (same angle as the labels), clockwise; still under reduced motion
   if(!ringDrag&&Math.abs(ringVel)>1e-4){ringOff+=ringVel;ringVel*=.95}
   x.globalCompositeOperation='source-over';x.textBaseline='middle';const n=order.length,labs=[],spk=[];
   ringPos.length=n;   // forget the angles of words that are no longer on the ring (after choosing fewer words or another speaker), so the readout always shows a real word
   for(let i=0;i<n;i++){const o=order[i],a=i/n*6.283+t*.042+ringOff,f=Math.sqrt(o.n/max),pulse=1,r0=R*1.05,r1=r0+Lmax*(.25+.75*f)*pulse,ca=Math.cos(a),sa=Math.sin(a),hv=i===ringHov;ringPos[i]=a;let dz=Math.abs((((a+1.5708)%6.283)+6.283)%6.283);dz=Math.min(dz,6.283-dz);const zw=6.283/Math.max(8,n)*1.35,zb=dz<zw?(1+Math.cos(dz/zw*3.1416))/2:0;
    spk.push({i,a,X0:cx+ca*r0,Y0:cy+sa*r0,X1:cx+ca*r1,Y1:cy+sa*r1,hv,f,top:o===words[0],c0:col(a,t,.55+.45*f),lw:hv?3:.8+1.6*f});   // mm188 preview: spikes + tip circles are collected here and drawn after the labels are placed, so they can step aside for the enlarged word
    const fs=Math.round((nar?7:8)+(nar?3:10)*f),fsz=fs+(hv?3:0);   // mm189 preview: words keep their small size all the way round, including at 12 o'clock (no zoom, no lift); the word at 12 is shown in the top-right readout
    let fromTop=(((a+1.5708)%6.283)+6.283)%6.283;const fadeOut=1.15,fadeIn0=4.0;let fade=fromTop<fadeOut?1-fromTop/fadeOut:fromTop<fadeIn0?0:(fromTop-fadeIn0)/(6.283-fadeIn0);fade=Math.max(0,Math.min(1,fade));fade=fade*fade*(3-2*fade);{const u=Math.max(0,Math.min(1,(dz-.03)/.13));fade*=u*u*(3-2*u)}   // mm189 preview: a word's label melts away as it reaches 12 o'clock, where the readout takes over
    const left=ca<0,pad=nar?8:12,lift=0,extra=0,up=0,bl='middle';
    let tx=cx+ca*(r1+pad+extra),ty=cy+sa*(r1+pad+extra)-up;
    x.font=`${hv||f>.5?700:400} ${fsz}px Arial`;const tw=x.measureText(o.w).width,th=fsz*1.25,m=nar?2:5;
    if(left){if(tx-tw<m)tx=m+tw;if(tx>W-m)tx=W-m}else{if(tx+tw>W-m)tx=W-m-tw;if(tx<m)tx=m}
    if(bl==='bottom'){if(ty-th<m)ty=m+th;if(ty>H-m)ty=H-m}else{if(ty-th*.5<m)ty=m+th*.5;if(ty+th*.5>H-m)ty=H-m-th*.5}
    const baseA=hv?1:Math.min(1,ringHov>=0?.3+.3*f:.55+.45*f);labs.push({o,i,a,f,zb,hv,fsz,left,fade,baseA,tx,ty,tw,th,ca,sa,r1,pad,extra,lift,up,bl,tyOff:0})}
   {let bi=-1,bd=9;labs.forEach((L,k)=>{let d=Math.abs((((L.a+1.5708)%6.283)+6.283)%6.283);d=Math.min(d,6.283-d);if(d<bd){bd=d;bi=k}});if(bi>=0){spk[bi].t12=true}}   // mm189 preview: the word at 12 o'clock is the one in the readout, so its spike is a touch brighter
   labs.sort((A,B)=>(B.o.n-A.o.n)||(A.o.w<B.o.w?-1:1));
   const minAng=nar?.45:.34,kept=[];
   for(const L of labs){if(L.fade<.05&&!L.hv){kept.push(L);continue}
    const close=kept.some(K=>{if(K.fade<.05)return false;let d=Math.abs(L.a-K.a)%6.283;d=Math.min(d,6.283-d);return d<minAng});
    if(close&&!L.hv)L.fade=0;kept.push(L)}
   const placed=[],gap=nar?4:6,mEdge=nar?2:5;
   const box=L=>{const y2=L.bl==='bottom'?L.ty:L.ty+L.th*.5,y1=y2-L.th;return{x1:(L.left?L.tx-L.tw:L.tx)-gap,y1:y1-gap,x2:(L.left?L.tx:L.tx+L.tw)+gap,y2:y2+gap}};
   const hit=(A,B)=>{const a=box(A),b=box(B);return a.x1<b.x2&&a.x2>b.x1&&a.y1<b.y2&&a.y2>b.y1};
   const clampLab=L=>{if(L.left){if(L.tx-L.tw<mEdge)L.tx=mEdge+L.tw;if(L.tx>W-mEdge)L.tx=W-mEdge}else{if(L.tx+L.tw>W-mEdge)L.tx=W-mEdge-L.tw;if(L.tx<mEdge)L.tx=mEdge}
    if(L.bl==='bottom'){if(L.ty-L.th<mEdge)L.ty=mEdge+L.th;if(L.ty>H-mEdge)L.ty=H-mEdge}else{if(L.ty-L.th*.5<mEdge)L.ty=mEdge+L.th*.5;if(L.ty+L.th*.5>H-mEdge)L.ty=H-mEdge-L.th*.5}};
   let RO=[];{let bi=-1,bd=9;labs.forEach(L=>{let d=Math.abs((((L.a+1.5708)%6.283)+6.283)%6.283);d=Math.min(d,6.283-d);if(d<bd){bd=d;bi=L.i}});const ro=bi>=0?order[bi]:null;   // mm189 preview: the top-right readout (the word at 12 o'clock) is an obstacle, so ring labels never run into it
    if(ro){x.font=`700 ${nar?14:17}px Arial`;const w2=x.measureText(`${ro.n.toLocaleString()} ${ro.n===1?'mention':'mentions'} \u00b7 #${words.indexOf(ro)+1}`).width;
     RO=[{x1:W-12-w2-6,x2:W,y1:6,y2:10+(nar?14:17)*1.3+4}]}
    RO.forEach(r=>placed.push({left:false,tx:r.x1,tw:r.x2-r.x1,ty:r.y2,th:r.y2-r.y1,bl:'bottom',fade:1,ro:1,zb:0,hv:false,fsz:0}))}
   const place=L=>{L.tx=cx+L.ca*(L.r1+L.pad+L.extra);L.ty=cy+L.sa*(L.r1+L.pad+L.extra)-L.up+L.tyOff;clampLab(L)};
   for(const L of labs){if(L.fade<.05&&!L.hv){placed.push(L);continue}
    for(let tries=0;tries<10;tries++){const P=placed.find(Q=>Q.fade>.05&&hit(L,Q));if(!P)break;
     const Lcx=L.left?L.tx-L.tw/2:L.tx+L.tw/2,Lcy=L.bl==='bottom'?L.ty-L.th*.5:L.ty,Pcx=P.left?P.tx-P.tw/2:P.tx+P.tw/2,Pcy=P.bl==='bottom'?P.ty-P.th*.5:P.ty;
     const nearEdge=(L.left&&L.tx-L.tw<=mEdge+1)||(!L.left&&L.tx+L.tw>=W-mEdge-1)||(P.left&&P.tx-P.tw<=mEdge+1)||(!P.left&&P.tx+P.tw>=W-mEdge-1);
     if(nearEdge||Math.abs(Lcy-Pcy)<L.th*.9){const dy=Lcy===Pcy?(L.i>P.i?1:-1):(Lcy>Pcy?1:-1);const need=(L.th+P.th)*.55-Math.abs(Lcy-Pcy)+gap;L.tyOff+=dy*Math.max(need,nar?7:9);L.extra+=nar?4:6}
     else{let ddx=Lcx-Pcx,ddy=Lcy-Pcy,len=Math.hypot(ddx,ddy)||1;const step=nar?6:9;L.extra+=step*.85;L.tyOff+=((ddy/len)*.55)*step-(nar?1:2)}
     place(L)}
    if(placed.some(Q=>Q.fade>.05&&hit(L,Q))){if(L.hv){L.extra+=nar?8:14;L.tyOff-=nar?10:16;place(L);if(placed.some(Q=>Q.fade>.05&&hit(L,Q)))L.fade*=.65}else L.fade=0}
    placed.push(L)}
   x.globalCompositeOperation='lighter';x.lineWidth=.7;
   for(let i=0;i<FILL;i++){const s=seed[i],a=i/FILL*6.283+t*.03+ringOff,b=Math.sin(t*.7+s[0]*6.28)*.5+.5,r0=R*(.85+s[1]*.25),len=Lmax*(.08+s[2]*.22)*(.8+.2*b);
    x.strokeStyle=col(a,t,.18+.25*b);x.beginPath();x.moveTo(cx+Math.cos(a)*r0,cy+Math.sin(a)*r0);x.lineTo(cx+Math.cos(a)*(r0+len),cy+Math.sin(a)*(r0+len));x.stroke()}
   x.globalCompositeOperation='source-over';
   for(const s of spk){if(s.hv)x.strokeStyle='#fff';else{const g=x.createLinearGradient(s.X0,s.Y0,s.X1,s.Y1);g.addColorStop(0,s.t12?s.c0.replace(/[\d.]+\)$/,'1)'):s.c0);g.addColorStop(1,s.t12?'#fff':`rgba(255,255,255,${.7+.3*s.f})`);x.strokeStyle=g}   // each spike blends from its red/purple into white at the tip (the spike at 12 o'clock is a touch brighter and thicker)
    x.lineWidth=s.lw+(s.t12?.8:0);x.beginPath();x.moveTo(s.X0,s.Y0);x.lineTo(s.X1,s.Y1);x.stroke()}
   for(const s of spk){const f=s.f,dr=(1.5+2*f)*1.3,dc=s.top?'#ff5449':'#fff',gr=dr*3.4*(s.t12?1.35:1),gs=s.top?GLOWR:GLOW;
    x.globalAlpha=s.hv||s.t12?1:.55+.35*f;x.drawImage(gs,s.X1-gr,s.Y1-gr,gr*2,gr*2);x.globalAlpha=1;x.beginPath();x.arc(s.X1,s.Y1,dr-.55,0,7);x.fillStyle='#0b0b0b';x.fill();x.strokeStyle=dc;x.lineWidth=1.1;x.stroke()}   // mm187: hollow circles with a soft white glow
   {const thS=Math.round(Math.min(114,R*1.7)),thR=thS*(32.5/84),fpR=nar?14:16,fpA=-2.25+(RM?0:t*.042+ringOff),fx=cx+Math.cos(fpA)*thR,fy=cy+Math.sin(fpA)*thR;
    x.save();x.globalCompositeOperation='lighter';x.globalAlpha=.95;x.drawImage(GLOWR,fx-fpR*2.3,fy-fpR*2.3,fpR*4.6,fpR*4.6);x.restore();
    x.save();x.beginPath();x.arc(fx,fy,fpR+1.2,0,6.283);x.fillStyle='#0b0b0b';x.fill();
    const fg=x.createLinearGradient(fx-fpR,fy-fpR,fx+fpR,fy+fpR);fg.addColorStop(0,'rgba(255,105,95,.98)');fg.addColorStop(.55,'rgba(224,69,59,.94)');fg.addColorStop(1,'rgba(168,95,228,.94)');
    x.lineWidth=1.45;x.strokeStyle=fg;x.beginPath();x.arc(fx,fy,fpR,0,6.283);x.stroke();
    x.lineWidth=1.2;x.strokeStyle='rgba(255,120,110,.96)';x.beginPath();x.arc(fx,fy,fpR*.58,0,6.283);x.stroke();
    x.fillStyle='rgba(255,250,246,.98)';x.beginPath();x.arc(fx,fy,fpR*.12,0,6.283);x.fill();
    x.restore()}
   [...labs].sort((A,B)=>(A.zb-B.zb)||(A.o.n-B.o.n)).forEach(L=>{const al=L.baseA*(L.hv?Math.max(L.fade,.35):L.fade);if(al<=.02)return;
    x.font=`${L.hv||L.f>.5?700:400} ${L.fsz}px Arial`;x.textAlign=L.left?'right':'left';x.textBaseline=L.bl;
    x.fillStyle=L.hv?`rgba(255,255,255,${al})`:L.o===words[0]?`rgba(255,84,73,${al})`:`rgba(243,238,228,${al})`;
    x.fillText(L.o.w,L.tx,L.ty)});
   x.textAlign='center';let tI=-1,tD=9;ringPos.forEach((p,i)=>{let d=Math.abs((((p+1.5708)%6.283)+6.283)%6.283);d=Math.min(d,6.283-d);if(d<tD){tD=d;tI=i}});const o=tI>=0?order[tI]:null;ringCur=o?o.w:'';
   const rw=$('ringWord');if(o){if(rw&&rw.textContent!==o.w)rw.textContent=o.w;x.textAlign='right';x.textBaseline='top';
    x.font=`700 ${nar?14:17}px Arial`;x.fillStyle='#f3eee4';x.fillText(`${o.n.toLocaleString()} ${o.n===1?'mention':'mentions'} \u00b7 #${words.indexOf(o)+1}`,W-12,10);x.textAlign='center';x.textBaseline='middle'}
   else{if(rw)rw.textContent='';x.font=`400 ${Math.max(12,R*.13)}px Arial`;x.fillStyle='rgba(243,238,228,.6)';x.fillText(matchMedia('(hover:hover)').matches?'Hover a word':'Tap a word',cx,cy)}
   if(ringPX>=0){const r=c.getBoundingClientRect(),px=ringPX-r.left,py=ringPY-r.top,ang=Math.atan2(py-cy,px-cx),dist=Math.hypot(px-cx,py-cy);
    if(dist>R*.9){let best=-1,bd=1e9;ringPos.forEach((p,i)=>{let d=Math.abs(((p%6.283)+6.283)%6.283-((ang+6.283)%6.283));d=Math.min(d,6.283-d);if(d<bd){bd=d;best=i}});ringHov=bd<(nar?.09:.06)?best:-1}
    else if(!ringTap)ringHov=-1}
   if(!RM&&VIEW==='ring'&&!document.hidden)ringRAF=requestAnimationFrame(frame)}
  ringRAF=requestAnimationFrame(frame);
  if(!c.dataset.wh){c.dataset.wh=1;const rw=$('ringWord');if(rw)rw.onclick=e=>{if(!ringCur)return;e.stopPropagation();rw.dataset.w=ringCur;showPop(rw,true)};const ang=e=>{const r=c.getBoundingClientRect(),W=r.width,H=r.height,nar=W<560;return Math.atan2(e.clientY-(r.top+H/2+(nar?4:8)),e.clientX-(r.left+W/2))};
   c.addEventListener('pointerdown',e=>{ringDrag={a:ang(e),t:performance.now(),x:e.clientX,y:e.clientY,mv:0};ringVel=0;try{c.setPointerCapture(e.pointerId)}catch(_){}});
   c.addEventListener('pointermove',e=>{if(!ringDrag)return;const a=ang(e);let d=a-ringDrag.a;if(d>Math.PI)d-=6.283;if(d<-Math.PI)d+=6.283;const now=performance.now(),dt=Math.max(8,now-ringDrag.t);ringOff+=d;ringVel=d/dt*16;ringDrag={a,t:now,x:ringDrag.x,y:ringDrag.y,mv:Math.max(ringDrag.mv,Math.hypot(e.clientX-ringDrag.x,e.clientY-ringDrag.y))};if(ringStill())playRing()});
   const end=e=>{if(ringDrag&&ringDrag.mv<8&&e&&e.type==='pointerup'&&ringCur){ringVel=0;c.dataset.w=ringCur;showPop(c,true);setTimeout(()=>{const p=document.getElementById('pop');if(p&&!p.hidden)p.scrollIntoView({block:'nearest',behavior:'smooth'})},60)}ringDrag=null;ringVel=Math.max(-.25,Math.min(.25,ringVel))};c.addEventListener('pointerup',end);c.addEventListener('pointercancel',end);c.addEventListener('touchmove',e=>{if(ringDrag)e.preventDefault()},{passive:false})}
  if(false){c.dataset.on=1;c.addEventListener('pointermove',e=>{if(e.pointerType==='mouse'){ringTap=false;ringPX=e.clientX;ringPY=e.clientY;if(ringStill())playRing()}});
   c.addEventListener('pointerleave',e=>{if(e.pointerType==='mouse'){ringPX=-1;ringHov=-1}});
   c.addEventListener('pointerdown',e=>{if(e.pointerType!=='mouse'){ringTap=true;ringPX=e.clientX;ringPY=e.clientY;if(ringStill())playRing()}})}
}
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&VIEW==='ring')playRing()});

function stopRace(){clearInterval(raceT);raceT=0}
function playRace(){const svg=$('race');if(!svg||!P)return;stopRace();if(!svg.dataset.ck){svg.dataset.ck=1;svg.addEventListener('click',e=>{const g=e.target.closest('.rrow')||e.target;const t=g.querySelector?g.querySelector('.rw'):null;const w=(t||e.target).textContent.trim();if(!w||!/^[a-z0-9'\-]+$/i.test(w))return;const el=t||e.target;el.dataset.w=w;e.stopPropagation();showPop(el,true)})}
  const pool=(sel.size>=2?DOCS.filter(d=>sel.has(d.id)):DOCS).slice().sort((a,b)=>a.date<b.date?-1:a.date>b.date?1:0);
  const nar=(svg.clientWidth||680)<520,VW=nar?380:680;svg.setAttribute('viewBox',`0 0 ${VW} 430`);const key=P.slug+'|'+pool.map(d=>d.id).join(',')+'|'+hide.checked+'|'+nar;if(key!==raceKey){svg.innerHTML='';raceRows={};raceKey=key}
  if(!pool.length){$('rDate').textContent='';$('rTtl').textContent='No documents selected';return}
  const N=10,RH=40,L=nar?112:140,W=nar?205:450,NS='http://www.w3.org/2000/svg',mk=(t,a,p)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);p.appendChild(e);return e};
  const row=w=>raceRows[w]||(raceRows[w]=(()=>{const g=mk('g',{class:'rrow'},svg);g.style.transform=`translate(0px,${N*RH+30}px)`;g.style.opacity=0;
    const t=mk('text',{x:L-10,y:26,'text-anchor':'end',class:'rw'},g);t.textContent=w;
    return {g,b:mk('rect',{x:L,y:6,height:28,width:0,rx:3,class:'rb'},g),n:mk('text',{x:L+8,y:26,class:'rn'},g)}})());
  const cum=new Map();let i=0;
  const step=()=>{const d=pool[i];d.cnt.forEach((n,wi)=>{const w=V[wi];if(hide.checked&&STOP.has(w))return;cum.set(w,(cum.get(w)||0)+n)});
    $('rDate').textContent=fmtDate(d.date);$('rTtl').textContent=`${i+1} of ${pool.length} · ${docKind(d)} · ${d.title}`;
    const top=[...cum].sort((a,b)=>b[1]-a[1]||(a[0]<b[0]?-1:1)).slice(0,N),max=top.length?top[0][1]:1,on=new Set(top.map(t=>t[0]));
    top.forEach(([w,c],k)=>{const r=row(w),bw=Math.max(4,c/max*W);r.g.style.transform=`translate(0px,${k*RH}px)`;r.g.style.opacity=1;
      r.b.setAttribute('width',bw);r.b.classList.toggle('top',k===0);r.n.setAttribute('x',L+bw+8);r.n.textContent=c.toLocaleString()});
    for(const w in raceRows)if(!on.has(w)){raceRows[w].g.style.transform=`translate(0px,${N*RH+30}px)`;raceRows[w].g.style.opacity=0}
    if(++i>=pool.length)stopRace()};
  if(RM.matches){while(i<pool.length)step();return}
  step();if(i<pool.length)raceT=setInterval(step,1100)}
$('rPlay').onclick=()=>{raceKey='';playRace()};
function jumpTo(which){setView(which,true)}   // kept for old callers/tests: same as tapping the tab
function cloudGlow(){}   // mm32: the Word Cloud first-visit fade hint was removed
// mm52: tapping a Super tab scrolls the page so the tabs sit near the top and the chosen view fills the screen
function tabsToTop(){const vt=$('stats')&&$('stats').getClientRects().length?$('stats'):$('vtabs');if(!vt||!vt.getClientRects().length)return;requestAnimationFrame(()=>vt.scrollIntoView({block:'start',behavior:RM.matches?'instant':'smooth'}))}
document.querySelectorAll('#vtabs [role="tab"]').forEach(t=>{t.onclick=()=>{setView(t.dataset.view,true);tabsToTop()};
  t.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const O=['math','cloud','race','ring'],i=O.indexOf(VIEW),v=e.key==='Home'?'math':e.key==='End'?'ring':O[(i+(e.key==='ArrowLeft'?3:1))%4];setView(v,true);$({math:'tabMath',cloud:'tabCloud',race:'tabRace',ring:'tabRing'}[v]).focus()}}});
cloudGlow();
function setN(n,go=true){NSHOW=n;document.querySelectorAll('#nbar .nchip').forEach(b=>b.setAttribute('aria-pressed',b.dataset.n===n?'true':'false'));if(go){hidePop();render();syncHash()}}
document.querySelectorAll('#nbar .nchip').forEach(b=>b.onclick=()=>{NPICK=true;setN(b.dataset.n)});
// ---- Ticker price chart: TradingView's free official Advanced Chart widget (their attribution kept as provided), loaded only on click ----
const tvM=$('tvModal'),tvBody=$('tvmBody');let tvBack=null;
function openChart(sym,tk,org){
  tvBack=document.activeElement;$('tvmTitle').textContent=`${tk}${org?' · '+org:''}`;
  tvBody.innerHTML='';const c=document.createElement('div');c.className='tradingview-widget-container';c.style.cssText='height:100%;width:100%';
  const slug=sym.replace(':','-');
  c.innerHTML='<div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%"></div>'+
    `<div class="tradingview-widget-copyright"><a href="https://www.tradingview.com/symbols/${encodeURIComponent(slug)}/" rel="noopener nofollow" target="_blank"><span class="blue-text">${esc(tk)} stock chart</span></a><span class="trademark"> by TradingView</span></div>`;
  const s=document.createElement('script');s.type='text/javascript';s.async=true;s.src='https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
  s.textContent=JSON.stringify({autosize:true,symbol:sym,interval:'D',range:'12M',timezone:'America/New_York',theme:'dark',style:'1',locale:'en',
    backgroundColor:'#0b0b0b',gridColor:'rgba(255,255,255,0.06)',hide_side_toolbar:true,allow_symbol_change:false,save_image:false,calendar:false,withdateranges:true,support_host:'https://www.tradingview.com'});
  c.appendChild(s);tvBody.appendChild(c);
  tvM.hidden=false;document.documentElement.classList.add('tvopen');hidePop();$('tvmX').focus()}
function closeChart(){if(tvM.hidden)return;tvM.hidden=true;tvBody.innerHTML='';document.documentElement.classList.remove('tvopen');if(tvBack&&tvBack.focus)tvBack.focus({preventScroll:true})}
// capture phase: a pill inside a person button opens the chart and does NOT select the person
document.addEventListener('click',e=>{const t=e.target.closest&&e.target.closest('.tk[data-tv]');if(!t)return;e.preventDefault();e.stopPropagation();openChart(t.dataset.tv,t.dataset.tk,t.dataset.org)},true);
tvM.addEventListener('click',e=>{if(e.target.closest('[data-close]'))closeChart()});
document.addEventListener('keydown',e=>{if(tvM.hidden)return;if(e.key==='Escape'){e.preventDefault();e.stopPropagation();closeChart()}
  else if(e.key==='Tab'){const f=[$('tvmX'),...tvM.querySelectorAll('.tradingview-widget-copyright a')];const i=f.indexOf(document.activeElement);
    if(i<0||(e.shiftKey&&i===0)||(!e.shiftKey&&i===f.length-1)){e.preventDefault();f[(i<0?0:(e.shiftKey?f.length-1:0))].focus()}}},true);

// Safety net: any off-site link (sources, documents, credits) opens in a new tab so visitors can come back; mailto and in-page links are left alone.
document.addEventListener('click',e=>{const a=e.target.closest&&e.target.closest('a[href]');if(a&&/^https?:/.test(a.href)&&a.origin!==location.origin&&!a.closest('.tradingview-widget-container')){a.target='_blank';a.rel='noopener noreferrer'}},true);setN(NSHOW,false);
tb.addEventListener('click',e=>{if(e.target.closest('tr.cwl')){cwOpen=!cwOpen;hidePop();render(false)}});   // tap '+K common words' to expand / collapse the gray rows
tb.addEventListener('keydown',e=>{if(e.target.closest&&e.target.closest('tr.cwl')&&(e.key==='Enter'||e.key===' ')){e.preventDefault();cwOpen=!cwOpen;hidePop();render(false);const l=tb.querySelector('tr.cwl');if(l)l.focus();return}});
tb.addEventListener('keydown',e=>{const r=e.target.closest('tr.top[data-w]');if(r&&(e.key==='Enter'||e.key===' ')){e.preventDefault();pinned=false;showPop(r,true);popToTop()}});
cloud.addEventListener('keydown',e=>{const s=e.target.closest('[data-w]');if(s&&(e.key==='Enter'||e.key===' ')){e.preventDefault();pinned=false;showPop(s,true);popToTop()}});
let rsT=null;
addEventListener('resize',()=>{placePop();clearTimeout(rsT);rsT=setTimeout(()=>{ // re-layout when the width changes (rotation, window resize)
  if(P&&cloud.clientWidth!==cloudW){hidePop();render()}},150)});
// self-check used by tests: highlighted matches == indexed occurrences; full-text people: occurrences == counts
window.__fedwords={occurrences,highlight,fragUrl,stats,setPerson,jumpTo,get view(){return SIDE.matches?'side':VIEW},setView,get cloudInfo(){return cloudInfo},get topWord(){return TOPW},get pulse(){return PULSE.ph},get bodies(){return BODIES},get sketch(){return SK},get P(){return P},checkAll(){const bad=[];V.forEach(w=>{
  const its=occurrences(w);its.forEach(it=>{if(highlight(it.doc.s[it.si],w).n!==it.n)bad.push(['hl',w,it.doc.id,it.si])});
  const st=stats(w),o=its.reduce((t,i)=>t+i.n,0);
  if(P.policy==='full'?o!==st.n:(o>st.n||new Set(its.map(i=>i.doc.id+':'+i.si)).size>FIRST*st.docs.length))bad.push(['cnt',w,o,st.n])});return bad}};

// ---- Compare (preview): second speaker, latest document, same Show count + stopword setting ----
let CMP=null;
function cmpTop(p,ids){const cnt=new Map();p.docs.forEach(d=>{if(!ids.has(d.id))return;d.cnt.forEach((n,wi)=>cnt.set(wi,(cnt.get(wi)||0)+n))});
  let a=[...cnt].map(([i,n])=>({word:p.vocab[i],count:n})).filter(x=>!(hide.checked&&STOP.has(x.word)));
  a.sort((x,y)=>y.count-x.count||(x.word<y.word?-1:1));let r=0,pv=null;a.forEach((x,i)=>{if(x.count!==pv){r=i+1;pv=x.count}x.rank=r});return a.slice(0,Math.min(nCap(),LIMIT))}
function cmpDocs(p,ids){const ds=p.docs.filter(d=>ids.has(d.id)).map(d=>d.date).sort();if(!ds.length)return 'No documents selected';
  return ds.length===1?fmtDate(ds[0]):`${ds.length} ${p.unit_pl||'documents'}, ${fmtDate(ds[0])} – ${fmtDate(ds[ds.length-1])}`}
function cmpRender(){const out=$('cmpOut'),on=!!CMP&&!!P;if(curRow&&curRow.dataset.cmp)hidePop();$('vMath').classList.toggle('cmpon',on);out.hidden=!on;$('cmpX').hidden=!on;
  $('cmpBtn').innerHTML=(on?'Change':'Compare')+' <span class="ctri" aria-hidden="true">&#9662;</span>';if(!on){out.innerHTML='';return}
  const lat=CMP.docs.length?CMP.docs.reduce((a,b)=>b.date>a.date?b:a,CMP.docs[0]):null;
  const A=cmpTop(P,sel),B=cmpTop(CMP,new Set(lat?[lat.id]:[]));const sa=new Set(A.map(x=>x.word)),sb=new Set(B.map(x=>x.word));
  const col=(p,L,other,docs,side)=>{const mx=L.length?L[0].count:1;return `<div class="cmpcol"><div class="cmph"><span class="cnm">${esc(p.name)}</span></div><div class="cmpsub">${esc(docs)}</div>`+
    (L.length?L.map(x=>`<div class="cmprow${other.has(x.word)?' both':''}" data-w="${esc(x.word)}" data-cmp="${side}" role="button" tabindex="0" title="${esc(x.word)}: ${x.count.toLocaleString()}"><span class="r">${x.rank}</span><span class="w">${esc(x.word)}</span><span class="c">${x.count.toLocaleString()}</span><div class="b" style="width:${(100*x.count/mx).toFixed(1)}%"></div></div>`).join(''):'<p class="muted">No words.</p>')+'</div>'};
  const both=A.filter(x=>sb.has(x.word)).length;
  out.innerHTML=`<div class="cmpgrid">${col(P,A,sb,cmpDocs(P,sel),'a')}${col(CMP,B,sa,cmpDocs(CMP,new Set(lat?[lat.id]:[])),'b')}</div><p class="cmpkey"><i></i>Outlined: in both top ${A.length===B.length?A.length:'lists'} (${both} shared word${both===1?'':'s'})</p>`}
function cmpList(){const qq=$('cmpQ').value.trim().toLowerCase();let h='';
  CATS.forEach(c=>{const ps=PEOPLE.filter(p=>p.category===c&&(!P||p.slug!==P.slug)&&(!qq||[p.name,p.org,p.ticker,p.role,p.group].filter(Boolean).join(' ').toLowerCase().includes(qq)));
    if(ps.length)h+=`<div class="cmpcat">${esc(CAT_LBL[c]||c)}</div><div class="cmpl">${ps.map(p=>`<button type="button" data-s="${p.slug}">${esc(p.name)}</button>`).join('')}</div>`});
  $('cmpList').innerHTML=h||'<p class="muted">No matching speakers.</p>'}
function cmpOpen(o){$('cmpPick').hidden=!o;$('cmpBtn').setAttribute('aria-expanded',o);if(o){$('cmpQ').value='';cmpList();if(!PHONE.matches)$('cmpQ').focus()}}
async function setCmp(slug,sync=true){if(!slug||!BY.has(slug)||(P&&slug===P.slug)){CMP=null}else{try{CMP=await loadPerson(BY.get(slug))}catch(e){CMP=null;console.error(e)}}
  cmpOpen(false);cmpRender();if(sync)syncHash()}
$('cmpBtn').onclick=()=>cmpOpen($('cmpPick').hidden);$('cmpQ').oninput=cmpList;
$('cmpList').onclick=e=>{const b=e.target.closest('button[data-s]');if(b)setCmp(b.dataset.s)};
$('cmpX').onclick=()=>{CMP=null;cmpOpen(false);cmpRender();syncHash()};
// initial state from URL: #person=<slug>&docs=<all|none|ids>; absent docs = latest only (old links: #docs=<ids> = default person)
function fromHash(){const hp=new URLSearchParams(location.hash.replace(/^#/,'').replace(/^[^=]*$/,''));
  {const n=hp.get('n');if(n)NPICK=true;if(n==='300')setN('all',false);else if(n==='150')setN('100',false);else if(n==='10')setN('5',false);else if(n==='25')setN('20',false);else if(NOPTS.includes(n))setN(n,false)}   // old links: 300 -> Max, 150 -> 100, 10 -> 5, 20/25 -> 50
  const toCloud=hp.get('view')==='cloud'||['cloud','visual'].includes(hp.get('mode'))||location.hash==='#cloud';   // #view=cloud, old Word Cloud links and the #cloud anchor open the cloud tab
  const toRace=hp.get('view')==='race',toRing=hp.get('view')==='ring';setView(toCloud?'cloud':'math');
  {const raw=hp.get('docs');let docIds;   // null = latest; none/empty = []; all = ['all']; else listed ids
    if(raw===null)docIds=undefined;else if(raw===''||raw==='none')docIds=[];else if(raw==='all')docIds=['all'];else docIds=raw.split(',').filter(Boolean);
    return setPerson(hp.get('person')||DEFAULT,docIds).then(()=>{
    if(toCloud)setView('cloud');if(toRace)setView('race');if(toRing)setView('ring');const vs=hp.get('vs');if(vs||CMP)return setCmp(vs)}).catch(e=>{
    tb.innerHTML=`<tr><td colspan="4" class="empty">Could not load data: ${esc(e.message)}</td></tr>`;console.error(e)})}}
fromHash();
// pasted/edited #person= links and back/forward on an open page (in-page anchors like #about are ignored)
addEventListener('hashchange',()=>{if(!location.hash||OURS.test(location.hash)){hidePop();fromHash()}});
</script>
<script>document.querySelectorAll('form.mmform').forEach(f=>f.addEventListener('submit',async e=>{e.preventDefault();const m=f.querySelector('.fmsg'),b=f.querySelector('button');if(f.botcheck.checked)return;if(!f.reportValidity())return;b.disabled=true;m.className='fmsg';m.textContent='Sending…';try{const r=await fetch(f.action,{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(f)))});const j=await r.json().catch(()=>({}));if(r.ok&&j.success){f.reset();m.className='fmsg ok';m.textContent='Thanks! Your message was sent.'}else{m.className='fmsg err';m.textContent='Sorry, the message could not be sent'+(j.message?': '+j.message:'')+'. Please try again later.'}}catch(err){m.className='fmsg err';m.textContent='Sorry, the message could not be sent (network error). Please try again later.'}finally{b.disabled=false}}))</script>
<script>(()=>{const b=document.getElementById('pbio');if(b&&matchMedia('(max-width:640px)').matches)b.open=false})()</script><script>(()=>{const e=document.getElementById('eyebrow'),b=document.getElementById('pdisc');if(!e||!b)return;const f=()=>{let t=b.querySelector('.pdt');if(!t){t=document.createElement('span');t.className='pdt';t.setAttribute('aria-hidden','true');b.appendChild(t)}let v=e.textContent.trim();if(/^Fed Chair(man|woman)?(\s|$|·)/i.test(v)){const on=document.querySelector('#persons button.chip.on');v=on&&on.dataset.person==='yellen'?'Federal Reserve Chairwoman':'Federal Reserve Chairman'}if(/^President\s*·/i.test(v))v=v.replace(/\s*·\s*/,' ');if(t.textContent!==v)t.textContent=v;t.classList.toggle('long',v.length>17);requestAnimationFrame(()=>{t.classList.remove('wrap');const nm=b.querySelector('.pdn');if(nm&&nm.getBoundingClientRect().height>parseFloat(getComputedStyle(nm).fontSize)*1.6)t.classList.add('wrap')})};f();new MutationObserver(f).observe(e,{childList:true,characterData:true,subtree:true});new MutationObserver(f).observe(b,{childList:true})})()</script><script>(()=>{['vMath','vCloud','vRing'].forEach(id=>{const p=document.getElementById(id);if(!p||p.querySelector('.vfoot'))return;p.insertAdjacentHTML('beforeend','<div class="vfoot"><a href="#picker" class="rNew">Select a new speaker <span class="rtri">&#9652;</span></a></div>')});const f=()=>{const c=document.querySelector('#persons button.chip.on');let v='';if(c){const n=c.cloneNode(true);n.querySelectorAll('.tk').forEach(x=>x.remove());v=n.textContent.trim()}document.querySelectorAll('.vtop .rwho b').forEach(x=>{if(x.textContent!==v)x.textContent=v})};f();const P=document.getElementById('persons');if(P)new MutationObserver(f).observe(P,{subtree:true,attributes:true,attributeFilter:['class'],childList:true});document.querySelectorAll('a.rNew').forEach(n=>n.onclick=e=>{e.preventDefault();const t=document.getElementById('picker');if(t)t.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});const d=document.getElementById('pdisc');if(d&&d.offsetParent&&d.getAttribute('aria-expanded')!=='true')d.click()})})()</script></body></html>
"""

if __name__ == "__main__":
    main()
