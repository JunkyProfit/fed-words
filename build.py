#!/usr/bin/env python3
"""Count every word each person said and write a single self-contained index.html.

People are listed in people.json.
  policy "full"    (Fed Chair; public domain): full transcripts in transcripts/<slug>/ (fetch.py);
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
        if (LOCAL / P["slug"] / "index.json").exists():
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
                         "n_sentences": d["n_sentences"], "s": d["excerpts"], "sp": d.get("pages"), "idx": idx})
    docs.sort(key=lambda d: (d["date"], d["url"]), reverse=True)
    return docs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-numbers", action="store_true", help="count digit-only tokens like 2026")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--split", action="store_true", help="force per-person data files in data/")
    a = ap.parse_args()

    people_out, report = [], []
    for P in json.loads((ROOT / "people.json").read_text(encoding="utf-8")):
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
            if d["sp"]:
                jd["sp"] = d["sp"]
            jdocs.append(jd)
        people_out.append({k: P[k] for k in ("slug", "name", "display", "category", "role", "org", "policy",
                                             "source", "doc_noun")}
                          | {k: P[k] for k in ("group", "mode", "eyebrow", "doc_noun1", "unit", "unit_pl", "credit") if P.get(k)}
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

    common = {"stop": sorted(STOPWORDS), "sc": sorted(S_CONTRACTIONS), "keepNum": a.keep_numbers}
    def render(inline_people):
        data = dict(common, people=inline_people)
        return TEMPLATE.replace("__DEFAULT_TITLE__", html.escape(people_out[0]["display"])).replace(
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
    print(f"\nWrote {ROOT / 'index.html'} ({len(page.encode('utf-8')) / 1024:.0f} KB"
          f"{', per-person data in data/' if split else ', all data inline'})")

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/png" href="assets/favicon.png?v=mm1">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png?v=mm1">
<title>Mouth Math — every word they said, ranked</title>
<meta name="description" content="Mouth Math: every word public figures said in their official speeches, letters and texts, counted and ranked.">
<meta name="application-name" content="Mouth Math">
<meta name="apple-mobile-web-app-title" content="Mouth Math">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Mouth Math">
<meta property="og:title" content="Mouth Math — every word they said, ranked">
<meta property="og:description" content="Word counts from official speeches, letters and texts by public figures, ranked from most to least frequent.">
<meta property="og:url" content="https://junkyprofit.github.io/fed-words/">
<meta property="og:image" content="https://junkyprofit.github.io/fed-words/assets/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Mouth Math logo">
<meta name="twitter:card" content="summary">
<style>
:root{--num-red:#9e1b24;--bg:#f5f0e6;--card:#fffdf8;--ink:#2b2a26;--muted:#6e6658;--accent:#3f6250;--line:#e6dccb;--header:#4f6656;--green:#7fa98b;--sage:#9cc7ad;--green-soft:#edf5f0;--chip-on:#dcebdf;--chip-ink:#2f4f3b}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
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
 header .logo img{height:34px}header h1{font-size:20px}}
#about{scroll-margin-top:16px}#about ul.sources{margin:0 0 10px;padding-left:20px;max-width:72ch}#about ul.sources li{margin:3px 0}#about h2{font-size:18px}#about p{margin:0 0 10px;max-width:72ch}
.notice{border:1px solid #e0b252;background:#fff8e6;border-left:5px solid #d99a1e;border-radius:8px;padding:10px 14px;margin-top:12px;max-width:72ch}
.notice strong{color:#7a4d00}header h1{margin:0;font-size:24px}header p{margin:4px 0 0;opacity:.85}
main{max-width:960px;margin:0 auto;padding:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin-bottom:16px}
h2{font-size:16px;margin:0 0 10px}.muted{color:var(--muted);font-size:13px}
.tf-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.tf-row .lbl{font-weight:600;font-size:13px;color:var(--muted);min-width:70px}
button.chip,label.chip{border:1px solid var(--line);background:var(--bg);border-radius:999px;padding:4px 12px;font:inherit;font-size:13px;cursor:pointer;display:inline-flex;gap:6px;align-items:center}
button.chip.on,label.chip.on{background:var(--chip-on);color:var(--chip-ink);border-color:var(--sage)}label.chip.on .muted{color:#47604f}
label.chip input{margin:0}
ul.speeches{list-style:none;margin:0;padding:0;font-size:14px}
ul.speeches li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:0 10px;align-items:start;padding:8px 8px;border-top:1px solid var(--line);border-radius:6px}
ul.speeches li.sel{background:var(--green-soft)}ul.speeches input{margin:3px 0 0}
.dl1{display:grid;grid-template-columns:7.4em minmax(0,1fr) auto;gap:2px 12px;align-items:baseline;cursor:pointer}
.dl1 .dt{font-weight:500;line-height:1.35}.dl1 .dw{color:var(--muted);font-size:13px;white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}
.dl2{margin:3px 0 0 calc(7.4em + 12px);font-size:12.5px;line-height:1.45}.dl2>*+*::before{content:"\00b7";display:inline-block;padding:0 6px;color:#b3a891;text-decoration:none}
.dl2 a{white-space:nowrap}
button.only{border:1px solid var(--line);background:var(--bg);color:var(--accent);border-radius:999px;font:inherit;font-size:12px;line-height:1.5;padding:0 9px;cursor:pointer}
button.only:hover{border-color:var(--sage)}
@media (max-width:600px){.dl1{grid-template-columns:minmax(0,1fr) auto}.dl1 .dw{grid-row:1;grid-column:2}.dl1 .dt{grid-column:1/-1}.dl2{margin-left:0}
 ul.speeches li{padding:8px 4px}}
.date{font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
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
tr.stop td.w{color:var(--muted)}td.cnt{color:var(--num-red);font-weight:600} /* word-count numbers: one variable, easy to revert */
tr[data-w]{cursor:help}tr[data-w]:hover td{background:#f0f7f2}tr.active td{background:#e2f0e7}
#pop{position:absolute;z-index:50;background:var(--card);border:1px solid #d9cdb6;border-radius:10px;box-shadow:0 10px 30px rgba(60,45,20,.18);
 padding:12px 14px;font-size:14px;max-height:60vh;overflow:auto;line-height:1.45}
#pop[hidden]{display:none}#pop.expanded{max-height:75vh}
#pop .ph{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;position:sticky;top:-12px;background:var(--card);padding:2px 0 8px;border-bottom:1px solid var(--line);margin-bottom:6px}
#pop .ph .t{font-size:13px;color:var(--muted)}#pop .ph b{font-size:16px;color:var(--ink)}
#pop .x{border:0;background:none;font-size:20px;line-height:1;cursor:pointer;color:var(--muted)}
#pop .doc{margin:10px 0 4px;font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
#pop ol{margin:0;padding-left:20px}#pop li{margin:5px 0}
#pop mark{background:#ffe27a;padding:0 1px;border-radius:2px}
#pop .src{font-size:12px;margin-left:6px;white-space:nowrap}#pop .twice{font-size:11px;color:#8a5a00;background:#fff3cd;border-radius:4px;padding:0 4px;margin-left:4px}
#pop .more{margin-top:10px;border:1px solid var(--accent);color:var(--accent);background:var(--card);border-radius:8px;padding:6px 12px;cursor:pointer;font:inherit;font-size:13px}
#pop .hint{font-size:12px;color:var(--muted);margin-top:8px}a{color:var(--accent)}.empty{padding:20px;text-align:center;color:var(--muted)}
#picker .tf-row:last-of-type{margin-bottom:4px}#personInfo{margin-top:2px}
body.mode-ceo header{background:#6a5f4e;box-shadow:inset 0 -4px 0 #d8c8a4}
#personInfo .eyebrow{display:inline-block;font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;background:var(--chip-on);color:var(--chip-ink);border-radius:999px;padding:1px 10px;margin:2px 6px 2px 0;vertical-align:1px}
#words h2#personTitle{margin:0 0 10px;font-size:18px}
header p#siteSub{max-width:640px}
.seg{display:inline-flex;gap:4px;background:#efe7d8;border:1px solid #d9cdb6;border-radius:12px;padding:4px;margin:0 0 12px}
.seg button{border:0;background:transparent;color:#5c5548;font:inherit;font-size:15px;font-weight:600;padding:7px 22px;border-radius:9px;cursor:pointer}
.seg button:hover{color:var(--ink);background:rgba(255,253,248,.6)}
.seg button.on{background:var(--chip-on);color:var(--chip-ink);box-shadow:inset 0 0 0 2px var(--accent),0 1px 2px rgba(60,45,20,.15)}.seg button.on::before{content:"\2713\00a0"}
#persons button.chip.on{font-weight:600;box-shadow:inset 0 0 0 1px var(--accent)}
body.mode-cab header{background:#56604a;box-shadow:inset 0 -4px 0 #c9d0b5}
body.mode-cong header{background:#6b5148;box-shadow:inset 0 -4px 0 #d9bfb3}
body.mode-scotus header{background:#3f4a45;box-shadow:inset 0 -4px 0 #c2cbc5}
.only-fed,.only-ceo,.only-cab,.only-cong,.only-scotus{display:none}
body.mode-fed .only-fed,body.mode-ceo .only-ceo,body.mode-cab .only-cab,body.mode-cong .only-cong,body.mode-scotus .only-scotus{display:inline}
#cats{flex-wrap:wrap}#pop .credit{font-size:11px;color:var(--muted);margin-top:4px}
#pop .cap{font-size:12px;color:var(--muted);margin-top:8px;padding-top:6px;border-top:1px dashed var(--line)}
.viewbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 14px}
.viewbar .lbl{font-weight:600;font-size:13px;color:var(--muted)}
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
#timeframe .tf-row{margin-bottom:8px}.yrs{display:contents}
#docPick{margin-top:8px;border-top:1px solid var(--line);padding-top:8px}
#docPick>summary{cursor:pointer;font-weight:600;font-size:14px;color:var(--accent);list-style:none;display:inline-flex;align-items:center;gap:6px;padding:3px 0}
#docPick>summary::-webkit-details-marker{display:none}
#docPick>summary::before{content:"";width:7px;height:7px;border-right:2px solid currentColor;border-bottom:2px solid currentColor;transform:rotate(-45deg);transition:transform .15s;margin:0 3px 0 1px}
#docPick[open]>summary::before{transform:rotate(45deg)}#docPick>summary .muted{font-weight:400}
#docPick .hint{margin:4px 0 6px}
#timeframe{container-type:inline-size}
@container (max-width:520px){.dl1{grid-template-columns:minmax(0,1fr) auto}.dl1 .dw{grid-row:1;grid-column:2}.dl1 .dt{grid-column:1/-1}.dl2{margin-left:0}ul.speeches li{padding:8px 4px}}
/* WordViz, wide screens: Who + Timeframe in a sidebar, the cloud beside it */
@media (min-width:900px){
 body.view-visual main{display:grid;grid-template-columns:300px minmax(0,1fr);column-gap:16px;max-width:1280px;align-items:start}
 body.view-visual main>*{grid-column:1/-1}
 body.view-visual .topgrid{grid-column:1;grid-row:2/span 2;display:block}
 body.view-visual #words{grid-column:2;grid-row:2}
 body.view-visual .stats{grid-column:2;grid-row:3}
 body.view-visual .stat{min-width:120px}}
@media (min-width:1100px){body.view-visual main{grid-template-columns:340px minmax(0,1fr)}}
/* WordViz, narrow screens: results right after the compact Who + Timeframe area; stats and filters below the cloud */
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
 #words h2#personTitle{font-size:16px}
 body.view-visual #words{display:flex;flex-direction:column}body.view-visual #words>*{order:2}
 body.view-visual #personTitle{order:0}body.view-visual #words>.only-visual{order:1;display:flex;flex-direction:column}
 body.view-visual #cloud{order:0}body.view-visual .scrub{order:1;margin-top:8px}body.view-visual .cloud-bar{order:2;margin-top:6px}body.view-visual #words .controls{margin:8px 0 0}}
body.view-visual .only-standard,body:not(.view-visual) .only-visual{display:none}
.cloud-bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:2px 0 6px;font-size:14px}
.cloud-bar select{font:inherit;font-size:14px;padding:3px 6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
#cloud{position:relative;width:100%;min-height:120px;overflow:hidden;margin:4px 0 2px}
#cloud span{position:absolute;white-space:nowrap;cursor:help;border-radius:5px;letter-spacing:-.01em;transition:background-color .12s}
#cloud span:hover,#cloud span.active{background:#e2f0e7}#cloud .empty{position:static}


#cloud canvas.cloudcv{position:absolute;left:0;top:0;pointer-events:none;z-index:0}
#cloud.live span{color:transparent!important;background:transparent!important;font-size:0!important;padding:0!important;z-index:1}
#cloud.live span:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.cloud-bar .motion{display:inline-flex;gap:5px;align-items:center;cursor:pointer}
.scrub{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:4px 0 8px;font-size:13px}.scrub[hidden]{display:none}
.scrub input[type=range]{flex:1;min-width:140px;accent-color:var(--num-red,#9e1b24)}
.scrub .play{flex:none;width:32px;height:32px;border-radius:50%;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;font-size:12px;line-height:1}
.scrub .play:hover{border-color:var(--ink)}#scrubLbl{color:var(--muted);min-width:0;flex-basis:100%}
@media (min-width:640px){#scrubLbl{flex-basis:auto;flex:2}}
/* ---- Black line-art theme (matches the logo's thin black strokes); delete this block to revert ---- */
:root{--ink:#141413;--cream:#f5efe2;--rule:#1c1b19;--hl:#ece3cf;--ink:#141413}
body{color:var(--ink)}a{color:var(--ink);text-decoration-color:rgba(20,20,19,.45);text-underline-offset:2px}a:hover{text-decoration-color:var(--ink)}
body[class] header{background:var(--ink);color:var(--cream)}
body.mode-fed header{box-shadow:inset 0 -3px 0 #9cc7ad}body.mode-ceo header{box-shadow:inset 0 -3px 0 #d8c8a4}
body.mode-cab header{box-shadow:inset 0 -3px 0 #c9d0b5}body.mode-cong header{box-shadow:inset 0 -3px 0 #d9bfb3}body.mode-scotus header{box-shadow:inset 0 -3px 0 #c2cbc5}
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
.scrub .play{border:1px solid var(--rule)}.scrub .play:hover{background:var(--ink);color:var(--cream)}
:focus-visible{outline-color:var(--ink)}
@media (max-width:640px){#cats{border:0}#cats button{border:1px solid var(--rule);background:var(--card);padding:5px 11px;font-size:13px}#cats button.on{background:var(--ink);color:var(--cream)}}
</style></head><body class="mode-fed">
<header><a class="about-link" href="#about">About</a>
<div class="brand"><a class="logo" href="./" title="Mouth Math home"><img src="assets/logo.png?v=mm1" width="433" height="104" alt="Mouth Math"></a>
<div class="titles"><h1 id="siteTitle">Every word they said, ranked</h1>
<p id="siteSub">Word counts from official speeches, testimony, letters and court opinions by public figures: Fed chairs, CEOs and the US Government (Cabinet secretaries, congressional leaders and Supreme Court Justices).</p></div></div></header>
<main>
<div class="viewbar" role="group" aria-label="View"><span class="lbl">View</span>
<div class="vcards" id="views"><button type="button" class="vcard" data-view="standard" aria-pressed="true"><svg viewBox="0 0 76 50" aria-hidden="true" fill="none" stroke="#2b2a26" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3h36l8 8v36H16z" fill="#fffdf8"/><path d="M52 3v8h8"/><path d="M21 14h3M21 21h3M21 28h3M21 35h3M21 42h3" stroke-width="1.6"/><path d="M28 14h26M28 21h21M28 28h17M28 35h12M28 42h8" stroke-dasharray="3 2.2"/></svg><span class="vt"><b>Standard</b><small>Ranked table</small></span></button>
<button type="button" class="vcard" data-view="visual" aria-pressed="false"><svg viewBox="0 0 76 50" aria-hidden="true"><rect x="1.5" y="1.5" width="73" height="47" rx="2" fill="#fffdf8" stroke="#2b2a26" stroke-width="1.6"/><rect x="5.5" y="5.5" width="65" height="39" fill="none" stroke="#2b2a26" stroke-width=".8"/><g fill="#2b2a26" font-family="system-ui,-apple-system,Segoe UI,Roboto,sans-serif" text-anchor="middle"><text x="38" y="29" font-size="13" font-weight="700">said</text><text x="20" y="16" font-size="7" font-weight="600">every</text><text x="55" y="17" font-size="8.5" font-weight="600">word</text><text x="19" y="38" font-size="6">we</text><text x="55" y="39" font-size="7.5" font-weight="600">math</text><text x="37" y="40" font-size="5.5">ranked</text><text x="61" y="29" font-size="5">yes</text><text x="15" y="27" font-size="5.5">now</text></g></svg><span class="vt"><b>WordViz</b><small>Word cloud</small></span></button></div>
<span class="muted" id="viewHint"></span></div>
<div class="topgrid">
<section class="card" id="picker"><h2>Who</h2>
<div class="seg" id="cats" role="tablist" aria-label="Category"></div>
<div class="tf-row" id="persons"><span class="lbl">Person</span></div>
<div id="personInfo"><span class="eyebrow" id="eyebrow"></span> <span class="muted" id="personMeta"></span></div>
</section>
<section class="card" id="timeframe"><h2>Timeframe</h2>
<div class="tf-row"><span class="lbl">Range</span>
  <button class="chip" id="btnAll">All</button><button class="chip" id="btnNone">None</button><span class="yrs" id="years"></span></div>
<div id="selSummary"></div>
<details id="docPick"><summary>Choose documents <span class="muted" id="docCount"></span></summary>
<p class="muted hint">Tick one or more · “only” selects just that one</p>
<ul class="speeches" id="docList"></ul></details>
</section>
</div>
<section class="card stats">
<div class="stat"><b id="sDocs">–</b>documents selected</div>
<div class="stat"><b id="sTotal">–</b>total words</div>
<div class="stat"><b id="sUnique">–</b>unique words</div>
<div class="stat"><b id="sShown">–</b>words shown</div>
</section>
<section class="card" id="words">
<h2 id="personTitle">Every word __DEFAULT_TITLE__ said, ranked</h2>
<div class="controls">
<input type="search" id="q" placeholder="Filter words (e.g. inflation, ^pro, ing$)…">
<label><input type="checkbox" id="hideStop"> Hide common stopwords</label>
</div>
<div class="only-visual"><div class="cloud-bar"><label>Show top <select id="cloudN" aria-label="Number of words in the cloud">
<option value="50">50</option><option value="150" selected>150</option><option value="300">300</option></select> words</label>
<label class="motion" title="Animated p5.js word cloud (off = static layout)"><input type="checkbox" id="motion"> Motion</label>
<span class="muted" id="cloudNote"></span></div>
<div class="scrub" id="scrubBar" hidden><button type="button" id="play" class="play" aria-label="Play through the documents in date order">&#9654;</button>
<input type="range" id="scrub" min="1" max="1" value="1" step="1" aria-label="Show counts through this document (date order)" aria-describedby="scrubLbl">
<span id="scrubLbl" aria-live="polite"></span></div>
<div id="cloud"></div></div>
<table class="only-standard"><thead><tr><th class="num" data-k="rank">Rank</th><th data-k="word">Word</th><th class="num" data-k="count">Count</th><th style="width:30%"></th></tr></thead>
<tbody id="tb"></tbody></table>
<p class="muted only-standard" id="more"></p>
</section>
<p class="muted" id="method">Tokenization: lowercase; punctuation and hyphens split words; contractions kept (don't, it's, we're);
possessive 's removed (Fed's → fed); digit-only tokens __NUMNOTE__. <span class="only-fed">Fed transcripts: footnotes and editorial notes excluded.</span>
<span class="only-ceo">CEO letters: signature blocks, tables, section headings/numerals and quoted epigraphs excluded.</span>
<span class="only-cab">Cabinet texts: remarks as prepared for delivery, prepared testimony, and the Secretary's own turns in hearing transcripts; cover pages, headings, other speakers and bracketed notes excluded.</span>
<span class="only-cong">Congressional Record (daily edition): only the leader's own floor remarks; other members, presiding-officer and clerk text, material inserted into the Record, and procedural unanimous-consent requests excluded.</span>
<span class="only-scotus">Supreme Court opinions (October Term 2025): only the Justice's own signed opinion (opinion of the Court, concurrence or dissent); syllabus, footnotes, headings and captions excluded.</span>
Totals, ranks and counts are recomputed in your browser for the selected person and documents.
Hover a word to see the sentences where it was used (click or tap to pin). <span id="dataThrough"></span></p>
<section class="card" id="about"><h2>About Mouth Math</h2>
<p>This site was built by someone who believes in transparency and truth. It counts every word in official,
publicly available texts by public figures, taken from each official source:</p>
<ul class="sources">
<li><strong>Fed Chair:</strong> speech and testimony transcripts published on
<a href="https://www.federalreserve.gov/newsevents/speeches.htm" target="_blank" rel="noopener">federalreserve.gov</a>.</li>
<li><strong>CEOs:</strong> shareholder letters posted by each company on its own website (palantir.com, aboutamazon.com, berkshirehathaway.com).</li>
<li><strong>US Government</strong>, in three groups:
<ul>
<li><strong>Cabinet:</strong> remarks and testimony published by the
<a href="https://home.treasury.gov/news/press-releases" target="_blank" rel="noopener">Treasury Department</a> and the
<a href="https://www.state.gov/" target="_blank" rel="noopener">State Department</a>, and testimony posted by the Senate
Appropriations and Armed Services Committees (Commerce and War/Defense secretaries).</li>
<li><strong>Congress:</strong> floor remarks by the Republican and Democratic leaders of the House and Senate, from the
<a href="https://www.govinfo.gov/app/collection/crec" target="_blank" rel="noopener">Congressional Record</a> (daily edition, govinfo.gov).</li>
<li><strong>Supreme Court:</strong> signed opinions of all nine Justices from the October Term 2025, published on
<a href="https://www.supremecourt.gov/opinions/slipopinion/25" target="_blank" rel="noopener">supremecourt.gov</a>.</li>
</ul></li>
</ul>
<p><strong>Licensing approach.</strong> Works of the U.S. government, including texts by federal officials such as the
Fed Chair, Cabinet secretaries, members of Congress and Supreme Court Justices, are not subject to copyright
(<a href="https://www.law.cornell.edu/uscode/text/17/105" target="_blank" rel="noopener">17 U.S.C. §105</a>), so every
sentence is available on hover. Other texts (CEO letters) are copyrighted by their
publishers: for those we publish only word counts and short excerpts (at most about a quarter of each text, and at most
10 sentences per word), each linked to the original, and never the full text.</p>
<p><strong>Neutrality.</strong> We present word counts without commentary. Nothing is edited or interpreted; footnotes,
editorial notes and other speakers' words are left out, and every sentence shown links back to its source so you can
check it yourself. The same selection rules apply to everyone in a group (for example, the most recent
qualifying floor remarks for each congressional leader of both parties, and the most recent signed opinions for every
Justice). Inclusion of a person does not imply endorsement, and this site is not affiliated with or endorsed by
any government, institution, company, or person listed.</p>
<p><strong>How it works:</strong> words are lowercased and counted across the documents you select.
“Hide common stopwords” removes very common words like “the” and “and”. Press conference Q&amp;A isn't included yet.</p>
<div class="notice" role="note"><strong>Not financial advice.</strong> This site is for informational and entertainment
purposes only and is not financial, investment, or trading advice. It is not affiliated with or endorsed by the
Federal Reserve, the White House, any federal department, Congress, the Supreme Court, or by any company
or person listed.</div>
</section>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const STOP=new Set(D.stop),SC=new Set(D.sc),PEOPLE=D.people,BY=new Map(PEOPLE.map(p=>[p.slug,p]));
const CATS=[...new Set(PEOPLE.map(p=>p.category))],DEFAULT=PEOPLE[0].slug;
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtDate=s=>new Date(s+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
let P=null,V=[],VI=new Map(),DOCS=[],YEARS=[],sel=new Set(),sortK='count',sortDir=-1;const LIMIT=2000,FIRST=10;
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
function renderPicker(){
  $('cats').innerHTML=CATS.map(c=>`<button class="${P.category===c?'on':''}" role="tab" aria-selected="${P.category===c}" data-cat="${esc(c)}">${esc(c)}</button>`).join('');
  const inCat=PEOPLE.filter(p=>p.category===P.category),groups=[...new Set(inCat.map(p=>p.group||''))];
  const chip=p=>`<button class="chip${p.slug===P.slug?' on':''}" data-person="${p.slug}" title="${esc(p.role)}">${esc(p.name)}</button>`;
  $('persons').classList.toggle('grouped',groups.length>1||!!groups[0]);
  $('persons').innerHTML=groups.length>1||groups[0]?   // a category with subgroups (US Government: Cabinet / Congress / Supreme Court)
    groups.map(g=>`<div class="pg" role="group" aria-label="${esc(g)}"><span class="lbl">${esc(g)}</span>${inCat.filter(p=>(p.group||'')===g).map(chip).join('')}</div>`).join(''):
    '<span class="lbl">Person</span>'+inCat.map(chip).join('');
  $('personMeta').textContent=`${P.role} · ${P.docs.length} ${P.docs.length===1?(P.doc_noun1||P.doc_noun.replace(/s$/,'')):P.doc_noun} from ${P.source}`;
  document.querySelectorAll('#cats button').forEach(b=>b.onclick=()=>{if(b.dataset.cat!==P.category)setPerson(PEOPLE.find(p=>p.category===b.dataset.cat).slug)});
  document.querySelectorAll('#persons button').forEach(b=>b.onclick=()=>{if(b.dataset.person!==P.slug)setPerson(b.dataset.person)});
  ['#cats button.on','#persons button.on'].forEach(sel=>{const b=document.querySelector(sel),r=b&&b.parentElement;
    if(r&&r.scrollWidth>r.clientWidth){const l=r.querySelector('.lbl'),pad=l&&getComputedStyle(l).position==='sticky'?l.offsetWidth+12:24,
      x=b.offsetLeft-r.offsetLeft;if(x-pad<r.scrollLeft||x+b.offsetWidth>r.scrollLeft+r.clientWidth-20)r.scrollLeft=Math.max(0,x-pad)}});   // only if not fully visible
}
async function setPerson(slug,docIds){
  hidePop();
  const p=await loadPerson(BY.get(slug)||BY.get(DEFAULT));
  P=p;V=p.vocab;VI=p.VI;DOCS=p.docs;YEARS=[...new Set(DOCS.map(d=>d.year))].sort().reverse();
  const ids=(docIds||[]).filter(i=>DOCS.some(d=>d.id===i));
  sel=new Set(ids.length?ids:DOCS.map(d=>d.id));
  ['fed','ceo','cab','cong','scotus'].forEach(m=>document.body.classList.toggle('mode-'+m,(P.mode||(P.category===PEOPLE[0].category?'fed':'ceo'))===m));
  $('eyebrow').textContent=P.eyebrow||`${P.category.replace(/s$/,'')} · ${P.org}`;
  $('personTitle').textContent=`Every word ${P.display} said, ranked`;
  document.title=P.slug===DEFAULT?'Mouth Math — every word they said, ranked':`Mouth Math — every word ${P.display} said, ranked`;
  $('dataThrough').textContent='Data through '+fmtDate(DOCS.map(d=>d.date).sort().pop())+'.';
  renderPicker();buildTimeframe();update();
}

// ---- timeframe UI ----
function buildTimeframe(){
  const host=u=>{try{return new URL(u).hostname.replace(/^www\./,'')}catch(e){return 'source'}};
  $('docList').innerHTML=DOCS.map(d=>`<li data-id="${d.id}"><input type="checkbox" id="cb_${d.id}" data-id="${d.id}" aria-describedby="dm_${d.id}">
 <div><label for="cb_${d.id}" class="dl1"><span class="date">${fmtDate(d.date)}</span><span class="dt">${esc(d.title)}</span><span class="dw">${d.words.toLocaleString()} words</span></label>
 <div class="dl2 muted" id="dm_${d.id}"><span>${esc(d.type[0].toUpperCase()+d.type.slice(1))}</span>${[d.location,d.note].filter(Boolean).map(x=>`<span>${esc(x)}</span>`).join('')}<a href="${esc(d.url)}" target="_blank" rel="noopener" title="Open the original">${esc(host(d.url))}&nbsp;↗</a></div></div>
 <button type="button" class="only" data-only="${d.id}" aria-label="Select only ${esc(d.title)}">only</button></li>`).join('');
  $('docCount').textContent=`(${DOCS.length} ${unitOf(DOCS.length)})`;
  $('years').innerHTML=YEARS.map(y=>{const n=DOCS.filter(d=>d.year===y).length;
    return `<label class="chip" id="yc_${y}"><input type="checkbox" data-year="${y}"> ${y} <span class="muted">(${n})</span></label>`}).join('');
  document.querySelectorAll('#docList input').forEach(cb=>cb.onchange=()=>{cb.checked?sel.add(cb.dataset.id):sel.delete(cb.dataset.id);update()});
  document.querySelectorAll('#docList .only').forEach(a=>a.onclick=()=>{sel=new Set([a.dataset.only]);update()});
  document.querySelectorAll('#years input').forEach(cb=>cb.onchange=()=>{
    DOCS.filter(d=>d.year===cb.dataset.year).forEach(d=>cb.checked?sel.add(d.id):sel.delete(d.id));update()});
}
$('btnAll').onclick=()=>{sel=new Set(DOCS.map(d=>d.id));update()};
$('btnNone').onclick=()=>{sel=new Set();update()};
function syncTimeframe(){
  DOCS.forEach(d=>{const on=sel.has(d.id);$('cb_'+d.id).checked=on;document.querySelector(`li[data-id="${d.id}"]`).classList.toggle('sel',on)});
  YEARS.forEach(y=>{const ids=DOCS.filter(d=>d.year===y).map(d=>d.id),k=ids.filter(i=>sel.has(i)).length;
    const cb=document.querySelector(`#years input[data-year="${y}"]`);cb.checked=k===ids.length;cb.indeterminate=k>0&&k<ids.length;
    $('yc_'+y).classList.toggle('on',k===ids.length)});
  const all=sel.size===DOCS.length;$('btnAll').classList.toggle('on',all);$('btnNone').classList.toggle('on',sel.size===0);
  const ds=DOCS.filter(d=>sel.has(d.id));
  $('selSummary').innerHTML=!ds.length?`<b>No ${unitOf(2)} selected.</b>`:
    `Showing <b>${all?'all '+ds.length:ds.length+' of '+DOCS.length}</b> ${unitOf(all?ds.length:DOCS.length)}`+
    ` (${fmtDate(ds[ds.length-1].date)}${ds.length>1?' – '+fmtDate(ds[0].date):''})`;
  syncHash();
}
// URL state: #person=<slug>&docs=<id,...>&mode=visual&n=<50|300>; default view = clean URL. Leaves #about etc. alone.
const OURS=/^#(person|docs|mode|n)=/;
function syncHash(){
  if(!P)return;const all=sel.size===DOCS.length,parts=[];
  if(P.slug!==DEFAULT||!all)parts.push('person='+P.slug);
  if(!all)parts.push('docs='+[...sel].join(','));
  if(VIEW==='visual'){parts.push('mode=visual');if(cloudN.value!=='150')parts.push('n='+cloudN.value)}
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
function render(){
  const base=BASE.filter(x=>!(hide.checked&&x.stop));
  base.sort((a,b)=>b.count-a.count||(a.word<b.word?-1:a.word>b.word?1:0));
  let r=0,prev=null;base.forEach((x,i)=>{if(x.count!==prev){r=i+1;prev=x.count}x.rank=r});
  const s=q.value.trim().toLowerCase();let re=null;if(s){try{re=new RegExp(s)}catch(e){}}
  const list=s?base.filter(x=>re?re.test(x.word):x.word.includes(s)):base.slice();
  list.sort((a,b)=>{const va=a[sortK],vb=b[sortK];const c=typeof va==='string'?(va<vb?-1:va>vb?1:0):va-vb;return c*sortDir||a.rank-b.rank});
  $('sDocs').textContent=sel.size+' / '+DOCS.length;
  $('sTotal').textContent=base.reduce((t,x)=>t+x.count,0).toLocaleString();
  $('sUnique').textContent=base.length.toLocaleString();
  if(VIEW==='visual'){tb.innerHTML='';$('sShown').textContent=drawCloud(list).toLocaleString();return}
  cloud.innerHTML='';
  const max=base.length?base[0].count:1;
  tb.innerHTML=list.length?list.slice(0,LIMIT).map(x=>`<tr class="${x.stop?'stop':''}" data-w="${esc(x.word)}"><td class="num">${x.rank}</td><td class="w">${esc(x.word)}</td><td class="num cnt">${x.count.toLocaleString()}</td><td><div class="bar" style="width:${(100*x.count/max).toFixed(1)}%"></div></td></tr>`).join('')
    :`<tr><td colspan="4" class="empty">${sel.size?'No matching words.':'Select at least one document above.'}</td></tr>`;
  $('sShown').textContent=list.length.toLocaleString();
  $('more').textContent=list.length>LIMIT?`Showing first ${LIMIT} of ${list.length} — use the filter to find others.`:'';
  document.querySelectorAll('th[data-k]').forEach(th=>{th.textContent=th.textContent.replace(/ [▲▼]$/,'')+(th.dataset.k===sortK?(sortDir<0?' ▼':' ▲'):'')});
}
function update(){hidePop();syncTimeframe();aggregate();render()}
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{hidePop();const k=th.dataset.k;
  if(sortK===k)sortDir*=-1;else{sortK=k;sortDir=k==='count'?-1:1}render()});
q.oninput=()=>{hidePop();render()};hide.onchange=()=>{hidePop();render()};

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
function popHTML(word){
  const st=stats(word),items=occurrences(word),excerpt=P.policy==='excerpt';
  const shown=(showAll&&!excerpt)?items:items.slice(0,FIRST),unit=n=>n===1?(P.unit||'document'):(P.unit_pl||(P.unit||'document')+'s');
  let h=`<div class="ph"><div><b>${esc(word)}</b>
   <div class="t" id="popCount">${st.n.toLocaleString()} occurrence${st.n===1?'':'s'} in ${st.m.toLocaleString()} sentence${st.m===1?'':'s'}`+
   ` · ${st.docs.length} of ${sel.size} selected ${unit(sel.size)}${st.n!==st.m?' · some sentences use it more than once':''}</div></div>
   <button class="x" title="Close (Esc)" aria-label="Close">×</button></div>`;
  let lastDoc=null;
  shown.forEach(it=>{if(it.doc!==lastDoc){if(lastDoc)h+='</ol>';lastDoc=it.doc;
      h+=`<div class="doc">${fmtDate(it.doc.date)} · <a href="${esc(it.doc.url)}" target="_blank" rel="noopener">${esc(it.doc.title)}</a></div><ol>`}
    const s=it.doc.s[it.si],hl=highlight(s,word),L=srcLink(it.doc,it.si);
    h+=`<li data-n="${it.n}" data-hl="${hl.n}">${hl.html}${it.n>1?`<span class="twice">×${it.n}</span>`:''}`+
       `<a class="src" href="${esc(L.href)}" target="_blank" rel="noopener" title="Open the original at this sentence">${L.label}</a></li>`});
  if(lastDoc)h+='</ol>';
  if(excerpt){
    const links=st.docs.map(d=>`<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.title)}</a>`).join(', ');
    h+=`<div class="cap" id="popCap">${shown.length?`Showing ${shown.length} of ${st.m.toLocaleString()} sentence${st.m===1?'':'s'}`:'No excerpt shown for this word'}`+
       ` — read the full ${unit(st.docs.length)} at ${esc(P.source)}: ${links}</div>`;
  }else if(items.length>FIRST&&!showAll)h+=`<button class="more">Show all ${items.length.toLocaleString()} sentences (${st.n.toLocaleString()} occurrences)</button>`;
  h+=`<div class="hint">${pinned?'Pinned. Press Esc or × to close.':'Click the word to pin this panel.'} “source ↗” opens the original at that sentence${excerpt?(DOCS.some(d=>d.sp)?' (PDFs: at that page)':''):' (Chrome/Edge/Safari)'}; the title link opens the document.</div>`+(P.credit?`<div class="credit">Source: ${esc(P.credit)}</div>`:'');
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
  pop.innerHTML=popHTML(curWord);pop.classList.toggle('expanded',showAll);pop.hidden=false;placePop();
}
function hidePop(){pop.hidden=true;pinned=false;showAll=false;curWord=null;if(curRow)curRow.classList.remove('active');curRow=null}
const cloud=$('cloud'),cloudN=$('cloudN');
[tb,cloud].forEach(box=>{
box.addEventListener('mouseover',e=>{const tr=e.target.closest('[data-w]');if(!tr||pinned)return;clearTimeout(hideT);
  if(tr===curRow)return;clearTimeout(hoverT);hoverT=setTimeout(()=>showPop(tr,false),120)});
box.addEventListener('mouseleave',()=>{clearTimeout(hoverT);if(!pinned)hideT=setTimeout(hidePop,300)});
box.addEventListener('click',e=>{const tr=e.target.closest('[data-w]');if(!tr)return;clearTimeout(hoverT);clearTimeout(hideT);pinned=false;showPop(tr,true)});
});
pop.addEventListener('mouseenter',()=>clearTimeout(hideT));
pop.addEventListener('mouseleave',()=>{if(!pinned)hideT=setTimeout(hidePop,300)});
pop.addEventListener('click',e=>{e.stopPropagation(); // re-render detaches e.target; don't let the outside-click handler close us
  if(e.target.closest('.x')){hidePop();return}
  if(e.target.closest('.more')&&P.policy!=='excerpt'){showAll=true;pinned=true;pop.innerHTML=popHTML(curWord);pop.classList.add('expanded');placePop()}});
document.addEventListener('keydown',e=>{if(e.key==='Escape')hidePop()});
document.addEventListener('click',e=>{if(!pop.hidden&&pinned&&!pop.contains(e.target)&&!e.target.closest('[data-w]'))hidePop()});

// ---- WordViz mode (hash value mode=visual): word cloud (vanilla JS; spiral placement + measureText box collisions) ----
let VIEW='standard',stopStd=null,cloudW=0,cloudInfo={placed:0,skipped:0,ms:0};
const PAL=['#141413','#2f4f3b','#141413','#3a3833','#6a5f4e','#141413','#56705c','#7d6646'];
const hcode=s=>{let h=7;for(let i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))|0;return Math.abs(h)};
const mctx=document.createElement('canvas').getContext('2d');
function cloudLayout(words,W){
  const fam=getComputedStyle(cloud).fontFamily,maxF=Math.max(28,Math.min(72,W*0.11)),minF=12,GAP=2;
  const sq=Math.sqrt,hi=sq(words[0].count),lo=sq(words[words.length-1].count);
  const boxes=words.map(x=>{ // sqrt scaling between the least and most frequent shown word
    let f=hi===lo?Math.min(36,maxF):minF+(maxF-minF)*(sq(x.count)-lo)/(hi-lo),wt,w,pad;
    for(let k=0;k<4;k++){wt=f>=30?700:f>=18?600:500;mctx.font=`${wt} ${f}px ${fam}`;pad=Math.round(f*.08)+1;
      w=Math.ceil(mctx.measureText(x.word).width)+2*pad;if(w<=W-4||f<=minF)break;f=Math.max(minF,f*(W-4)/w)}
    return {x,f:Math.round(f*10)/10,wt,pad,w:w+GAP,h:Math.ceil(f*1.12)+GAP}});
  const area=boxes.reduce((t,b)=>t+b.w*b.h,0),H=Math.max(220,area/(W*0.5));
  // exact collisions: spatial hash of placed boxes; fast reject: 4px bitmap of cells fully covered by a placed box
  const G=40,grid=new Map(),K=(i,j)=>i*65536+j+32768,placed=[],cx=W/2,cy=H/2,E=W/H*1.25; // ellipse a bit wider than the box so the cloud fills it
  const sx=Math.max(1,E),sy=Math.max(1,1/E),sm=Math.max(sx,sy); // spiral pitch runs along the shorter axis
  const C=4,OY=1.5*H,CW=Math.ceil(W/C)+1,CH=Math.ceil(4*H/C)+1,occ=new Uint8Array(CW*CH);
  const busy=(x,y)=>{const i=x/C|0,j=(y+OY)/C|0;return j>=0&&j<CH&&occ[j*CW+i]===1};
  const cells=(r,fn)=>{for(let i=Math.floor(r.x/G);i<=Math.floor((r.x+r.w)/G);i++)for(let j=Math.floor(r.y/G);j<=Math.floor((r.y+r.h)/G);j++)if(fn(K(i,j)))return true;return false};
  const hit=c=>cells(c,k=>{const a=grid.get(k);return a&&a.some(o=>c.x<o.x+o.w&&c.x+c.w>o.x&&c.y<o.y+o.h&&c.y+c.h>o.y)});
  const add=c=>{cells(c,k=>{(grid.get(k)||grid.set(k,[]).get(k)).push(c)});placed.push(c);
    for(let j=Math.max(0,Math.ceil((c.y+OY)/C));j<Math.min(CH,Math.floor((c.y+c.h+OY)/C));j++)
      for(let i=Math.ceil(c.x/C);i<Math.floor((c.x+c.w)/C);i++)occ[j*CW+i]=1};
  let steps=0,todo=boxes.map((b,n)=>[b,n]),y0=0,y1=H,phase=0,rPrev=0,rFloor=0;
  for(;todo.length&&phase<6;phase++){ // words that don't fit are retried in a taller band (cloud grows up and down)
    const miss=[],rMax=Math.max(W/2/sx,(y1-y0)/2/sy)*1.5;
    for(const [b,n] of todo){const th0=n*2.39996,pitch=Math.max(4,b.h*.35);let ok=false;
      // the middle is already packed: start each spiral at 55% of the previous word's radius
      let r=Math.max(rFloor,rPrev*0.55),t=r*2*Math.PI/pitch;
      for(;r<rMax;){steps++;
        const x=cx+r*Math.cos(t+th0)*sx-b.w/2,y=cy+r*Math.sin(t+th0)*sy-b.h/2;
        t+=Math.min(0.35,3/Math.max(1,r*sm));r=pitch*t/(2*Math.PI);
        if(x<0||y<y0||x+b.w>W||y+b.h>y1)continue;
        if(busy(x+b.w/2,y+b.h/2)||busy(x+1,y+1)||busy(x+b.w-1,y+1)||busy(x+1,y+b.h-1)||busy(x+b.w-1,y+b.h-1))continue;
        const c={x,y,w:b.w,h:b.h,b};if(!hit(c)){add(c);rPrev=r;ok=true;break}}
      if(!ok)miss.push([b,n])}
    todo=miss;rFloor=(y1-y0)/2/sy*0.92;rPrev=0;y0=Math.max(y0-H*0.2,-OY);y1=Math.min(y1+H*0.2,2.5*H)}
  const out={placed,miss:todo.length,tries:phase,steps};
  return out;
}
function drawCloud(list){
  stopSketch();stopPlay();
  const W=cloud.clientWidth;cloudW=W;if(!W)return 0;const t0=performance.now();
  const N=+cloudN.value,words=list.slice().sort((a,b)=>b.count-a.count||(a.word<b.word?-1:1)).slice(0,N);
  if(!words.length){cloud.style.height='';cloud.innerHTML=`<div class="empty">${sel.size?'No matching words.':'Select at least one document above.'}</div>`;
    $('cloudNote').textContent='';cloudInfo={placed:0,skipped:0,ms:0,mode:'static'};BODIES=[];$('scrubBar').hidden=true;return 0}
  const {placed,miss,tries,steps}=cloudLayout(words,W);
  const y0=Math.min(...placed.map(c=>c.y)),y1=Math.max(...placed.map(c=>c.y+c.h));
  cloud.style.height=Math.ceil(y1-y0+4)+'px';
  cloud.innerHTML=placed.map(c=>{const b=c.b,x=b.x;return `<span data-w="${esc(x.word)}" data-c="${x.count}" role="button" tabindex="0" aria-label="${esc(x.word)}: ${x.count}" `+
    `style="left:${(c.x+1).toFixed(1)}px;top:${(c.y-y0+1).toFixed(1)}px;font-size:${b.f}px;font-weight:${b.wt};line-height:${c.h-2}px;height:${c.h-2}px;padding:0 ${b.pad}px;color:${PAL[hcode(x.word)%PAL.length]}">${esc(x.word)}</span>`}).join('');
  cloudInfo={placed:placed.length,skipped:miss,tries,steps,ms:Math.round(performance.now()-t0),mode:'static'};
  buildBodies(placed,y0,W);setupScrub();
  if(motion.checked){const tok=++drawTok;ensureP5().then(()=>{if(tok===drawTok&&VIEW==='visual'&&BODIES.length)startSketch()})
    .catch(()=>{motion.checked=false;motion.disabled=true;$('cloudNote').textContent+=' · motion unavailable (p5.js could not load)'})}
  $('cloudNote').textContent=`Top ${placed.length.toLocaleString()} of ${list.length.toLocaleString()} words${hide.checked?' (stopwords hidden)':''}`+
    `${miss?` · ${miss} didn't fit`:''} · size ∝ √count · hover or tap a word for its count and sentences`;
  return placed.length;
}

// ---- WordViz motion: p5.js sketch (words as soft physics bodies) + date scrubber ----
// p5 is loaded only when WordViz is shown with Motion on: pinned version, Subresource Integrity checked by the browser.
const P5_URL='https://cdn.jsdelivr.net/npm/p5@2.3.4/lib/p5.min.js',P5_SRI='sha384-Cs48F1uukMPysq29xNsf/FZL5ZNGsPfi6lDSGOxo6dypVFFiWO9Q3YbRKoXPPBii',MAX_BODIES=300;
const motion=$('motion'),scrub=$('scrub'),RM=matchMedia('(prefers-reduced-motion: reduce)');
motion.checked=!RM.matches;RM.addEventListener('change',()=>{motion.checked=!RM.matches;if(VIEW==='visual'&&P)render()});
motion.onchange=()=>{hidePop();render()};
let P5P=null,SK=null,IO=null,BODIES=[],SEQ=[],STEP=0,drawTok=0,playT=null,frameN=0;
function ensureP5(){
  if(window.p5)return Promise.resolve();
  return P5P||(P5P=new Promise((ok,no)=>{const s=document.createElement('script');s.src=P5_URL;s.integrity=P5_SRI;s.crossOrigin='anonymous';
    const t=setTimeout(()=>{P5P=null;no(new Error('timeout'))},12000);
    s.onload=()=>{clearTimeout(t);window.p5?ok():no(new Error('p5 missing'))};s.onerror=()=>{clearTimeout(t);P5P=null;no(new Error('load failed'))};
    document.head.appendChild(s)}));
}
// font size for a count, on the same sqrt scale as the static layout (final step = exactly the static size)
function sizer(words,W){const maxF=Math.max(28,Math.min(72,W*0.11)),minF=12,sq=Math.sqrt,hi=sq(words[0].count),lo=sq(words[words.length-1].count);
  return c=>c<=0?0:hi===lo?Math.min(36,maxF)*sq(c)/hi:sq(c)>=lo?minF+(maxF-minF)*(sq(c)-lo)/(hi-lo):minF*sq(c)/lo}
function buildBodies(placed,y0,W){
  const fam=getComputedStyle(cloud).fontFamily,spans=[...cloud.querySelectorAll('span[data-w]')],g=sizer(placed.map(c=>c.b.x).sort((a,b)=>b.count-a.count),W);
  SEQ=DOCS.filter(d=>sel.has(d.id)).slice().reverse();          // selected documents, oldest first
  BODIES=placed.slice(0,MAX_BODIES).map((c,i)=>{const b=c.b,x=b.x,wi=VI.get(x.word);mctx.font=`${b.wt} 100px ${fam}`;
    let run=0;const cum=SEQ.map(d=>run+=(d.cnt.get(wi)||0));
    const w0=b.w-2,h0=c.h-2,hx=c.x+1+w0/2,hy=c.y-y0+1+h0/2;
    return {word:x.word,count:x.count,el:spans[i],wt:b.wt,col:spans[i].style.color,fam,rw:mctx.measureText(x.word).width/100,
      fF:b.f,k:b.f/(g(x.count)||1),g,cum,hx,hy,x:hx,y:hy,vx:0,vy:0,f:b.f,ft:b.f,w:w0,h:h0,seed:i*7.31+1}});
  BODIES.forEach(boxOf);
}
function boxOf(b){if(b.f<0.4){b.w=b.h=0;return}const pad=Math.round(b.f*.08)+1;b.w=b.rw*b.f+2*pad;b.h=Math.ceil(b.f*1.12)}
function setupScrub(){
  const K=SEQ.length;$('scrubBar').hidden=K<2;scrub.max=K;STEP=K;scrub.value=K;scrubLabel();
}
function scrubLabel(){const K=SEQ.length;if(!K)return;const d=SEQ[STEP-1];
  $('scrubLbl').innerHTML=STEP===K?`All ${K} ${unitOf(K)} (${fmtDate(SEQ[0].date)} – ${fmtDate(d.date)}) · drag or press ▶ to watch the counts build up in date order`:
    `Through <b>${fmtDate(d.date)}</b> · ${STEP} of ${K}: ${esc(d.title)} · word sizes = counts so far (the popover still covers all selected)`}
function applyStep(k){STEP=Math.max(1,Math.min(SEQ.length,k));scrub.value=STEP;scrubLabel();
  BODIES.forEach(b=>{const c=b.cum[STEP-1];b.ft=Math.min(b.fF,b.k*b.g(c));b.el.setAttribute('aria-label',`${b.word}: ${c} (through ${SEQ[STEP-1].date})`)});
  if(!SK){BODIES.forEach(b=>{b.f=b.ft;boxOf(b);placeSpan(b,true)})}       // static mode: resize in place (never overlaps: counts only grow)
}
function placeSpan(b,styleText){const el=b.el;if(!b.w){el.style.display='none';return}el.style.display='';
  el.style.left=(b.x-b.w/2).toFixed(1)+'px';el.style.top=(b.y-b.h/2).toFixed(1)+'px';
  if(SK){el.style.width=b.w.toFixed(1)+'px';el.style.height=b.h+'px'}
  else if(styleText){el.style.fontSize=b.f.toFixed(1)+'px';el.style.lineHeight=el.style.height=b.h+'px';el.style.padding=`0 ${Math.round(b.f*.08)+1}px`}}
scrub.oninput=()=>{stopPlay();hidePop();applyStep(+scrub.value)};
function stopPlay(){clearInterval(playT);playT=null;$('play').innerHTML='&#9654;';$('play').setAttribute('aria-label','Play through the documents in date order')}
$('play').onclick=()=>{if(playT){stopPlay();return}hidePop();if(STEP>=SEQ.length)applyStep(1);
  $('play').innerHTML='&#10074;&#10074;';$('play').setAttribute('aria-label','Pause');
  playT=setInterval(()=>{if(STEP>=SEQ.length){stopPlay();return}applyStep(STEP+1)},SK?1400:900)};
function stopSketch(){if(IO){IO.disconnect();IO=null}if(SK){SK.remove();SK=null}cloud.classList.remove('live')}
function startSketch(){
  stopSketch();const W=cloud.clientWidth,H=cloud.clientHeight;if(!W||!H)return;
  BODIES.forEach(b=>{b.x=b.hx;b.y=b.hy;b.vx=b.vy=0;b.f=b.ft;boxOf(b)});
  cloud.classList.add('live');cloudInfo.mode='p5';
  SK=new p5(p=>{
    p.setup=()=>{const cv=p.createCanvas(W,H);cv.elt.classList.add('cloudcv');cv.elt.setAttribute('aria-hidden','true');
      p.pixelDensity(Math.min(2,devicePixelRatio||1));p.frameRate(60);BODIES.forEach(b=>placeSpan(b))};
    p.draw=()=>{physics(p,W,H);paint(p);if(++frameN%3===0)BODIES.forEach(b=>placeSpan(b))};
  },cloud);
  IO=new IntersectionObserver(es=>es.forEach(e=>{if(SK)e.isIntersecting?SK.loop():SK.noLoop()}));IO.observe(cloud);   // pause off-screen
}
function physics(p,W,H){
  const t=p.millis()/1000,B=BODIES,GAP=1;
  for(const b of B){b.f+=(b.ft-b.f)*0.1;if(Math.abs(b.ft-b.f)<0.03)b.f=b.ft;boxOf(b);if(!b.w)continue;
    const ax=(p.noise(b.seed,t*0.22)-0.5)*0.16+(b.hx-b.x)*0.003,ay=(p.noise(b.seed+91,t*0.22)-0.5)*0.12+(b.hy-b.y)*0.003;
    b.vx=(b.vx+ax)*0.9;b.vy=(b.vy+ay)*0.9;b.x+=b.vx;b.y+=b.vy}
  for(let it=0;it<3;it++){const G=64,grid=new Map();     // spatial hash; push overlapping boxes apart (bigger words move less)
    B.forEach((b,i)=>{if(!b.w)return;for(let gx=Math.floor((b.x-b.w/2)/G);gx<=Math.floor((b.x+b.w/2)/G);gx++)for(let gy=Math.floor((b.y-b.h/2)/G);gy<=Math.floor((b.y+b.h/2)/G);gy++){
      const k=gx*4096+gy;(grid.get(k)||grid.set(k,[]).get(k)).push(i)}});
    const seen=new Set();
    for(const a of grid.values())for(let m=0;m<a.length;m++)for(let n=m+1;n<a.length;n++){const i=a[m],j=a[n],key=i<j?i*1000+j:j*1000+i;if(seen.has(key))continue;seen.add(key);
      const A=B[i],C=B[j],ox=(A.w+C.w)/2+GAP-Math.abs(A.x-C.x),oy=(A.h+C.h)/2+GAP-Math.abs(A.y-C.y);if(ox<=0||oy<=0)continue;
      const ma=C.w*C.h/(A.w*A.h+C.w*C.h);
      if(ox<oy){const s=A.x<C.x?-1:1;A.x+=s*ox*ma;C.x-=s*ox*(1-ma);A.vx*=.5;C.vx*=.5}else{const s=A.y<C.y?-1:1;A.y+=s*oy*ma;C.y-=s*oy*(1-ma);A.vy*=.5;C.vy*=.5}}}
  for(const b of B){if(!b.w)continue;b.x=Math.max(b.w/2,Math.min(W-b.w/2,b.x));b.y=Math.max(b.h/2,Math.min(H-b.h/2,b.y))}
}
function paint(p){
  const ctx=p.drawingContext;p.clear();ctx.textAlign='center';ctx.textBaseline='middle';
  for(let i=BODIES.length-1;i>=0;i--){const b=BODIES[i];if(!b.w)continue;
    if(b.word===curWord){ctx.fillStyle=getComputedStyle(document.body).getPropertyValue('--hl').trim()||'#e2f0e7';ctx.beginPath();ctx.roundRect?ctx.roundRect(b.x-b.w/2,b.y-b.h/2,b.w,b.h,5):ctx.rect(b.x-b.w/2,b.y-b.h/2,b.w,b.h);ctx.fill()}
    ctx.font=`${b.wt} ${b.f.toFixed(2)}px ${b.fam}`;ctx.fillStyle=b.col;ctx.fillText(b.word,b.x,b.y+b.f*0.03)}
}
function setView(v,user){
  v=v==='visual'?'visual':'standard';
  document.querySelectorAll('#views button').forEach(b=>{const on=b.dataset.view===v;b.classList.toggle('on',on);b.setAttribute('aria-pressed',on)});
  $('viewHint').textContent=v==='visual'?'WordViz: bigger words were used more often.':'Ranked table of every word.';
  if(v===VIEW)return;
  hidePop();VIEW=v;document.body.classList.toggle('view-visual',v==='visual');if(v!=='visual'){stopSketch();stopPlay()}
  // Visual turns "hide stopwords" on (so "the" doesn't dominate); Standard restores the previous setting
  if(v==='visual'){stopStd=hide.checked;hide.checked=true}else if(stopStd!==null){hide.checked=stopStd;stopStd=null}
  if(P){render();syncHash()}
  if(user&&v==='visual'){const r=$('words').getBoundingClientRect();if(r.top>innerHeight*0.6)$('words').scrollIntoView({behavior:'smooth',block:'start'})}
}
document.querySelectorAll('#views button').forEach(b=>b.onclick=()=>setView(b.dataset.view,true));
cloudN.onchange=()=>{hidePop();render();syncHash()};
cloud.addEventListener('keydown',e=>{const s=e.target.closest('[data-w]');if(s&&(e.key==='Enter'||e.key===' ')){e.preventDefault();pinned=false;showPop(s,true)}});
let rsT=null;
addEventListener('resize',()=>{placePop();clearTimeout(rsT);rsT=setTimeout(()=>{ // re-layout when the width changes (rotation, window resize)
  if(VIEW==='visual'&&P&&cloud.clientWidth!==cloudW){hidePop();render()}},150)});
// self-check used by tests: highlighted matches == indexed occurrences; full-text people: occurrences == counts
window.__fedwords={occurrences,highlight,fragUrl,stats,setPerson,setView,get view(){return VIEW},get cloudInfo(){return cloudInfo},get bodies(){return BODIES},get sketch(){return SK},applyStep,get P(){return P},checkAll(){const bad=[];V.forEach(w=>{
  const its=occurrences(w);its.forEach(it=>{if(highlight(it.doc.s[it.si],w).n!==it.n)bad.push(['hl',w,it.doc.id,it.si])});
  const st=stats(w),o=its.reduce((t,i)=>t+i.n,0);
  if(P.policy==='full'?o!==st.n:(o>st.n||new Set(its.map(i=>i.doc.id+':'+i.si)).size>FIRST*st.docs.length))bad.push(['cnt',w,o,st.n])});return bad}};
// initial state from URL: #person=<slug>&docs=<ids>  (old links: #docs=<ids> = default person)
function fromHash(){const hp=new URLSearchParams(location.hash.replace(/^#/,'').replace(/^[^=]*$/,''));
  if(['50','150','300'].includes(hp.get('n')))cloudN.value=hp.get('n');
  setView(hp.get('mode')==='visual'?'visual':'standard');
  return setPerson(hp.get('person')||DEFAULT,(hp.get('docs')||'').split(',').filter(Boolean)).catch(e=>{
    tb.innerHTML=`<tr><td colspan="4" class="empty">Could not load data: ${esc(e.message)}</td></tr>`;console.error(e)})}
fromHash();
// pasted/edited #person= links and back/forward on an open page (in-page anchors like #about are ignored)
addEventListener('hashchange',()=>{if(!location.hash||OURS.test(location.hash)){hidePop();fromHash()}});
</script></body></html>
"""

if __name__ == "__main__":
    main()
