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
                          | {k: P[k] for k in ("mode", "eyebrow", "doc_noun1", "unit", "unit_pl", "credit") if P.get(k)}
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
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png?v=mm1">
<title>Mouth Math — every word __DEFAULT_TITLE__ said, ranked</title>
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
:root{--bg:#f5f0e6;--card:#fffdf8;--ink:#2b2a26;--muted:#6e6658;--accent:#3f6250;--line:#e6dccb;--header:#4f6656;--green:#7fa98b;--sage:#9cc7ad;--green-soft:#edf5f0;--chip-on:#dcebdf;--chip-ink:#2f4f3b}
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
ul.speeches{list-style:none;margin:0;padding:0}ul.speeches li{display:flex;gap:10px;align-items:flex-start;padding:6px 0;border-top:1px solid var(--line)}
ul.speeches li.sel{background:var(--green-soft)}ul.speeches input{margin-top:5px}
.date{font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
a.only{font-size:12px;margin-left:6px;cursor:pointer}
#selSummary{margin-top:8px;font-size:14px}
.stats{display:flex;gap:14px;flex-wrap:wrap}.stat{flex:1;min-width:150px;background:var(--bg);border-radius:8px;padding:10px 14px}
.stat b{display:block;font-size:24px;color:var(--accent)}
.controls{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
input[type=search]{flex:1;min-width:220px;padding:9px 12px;border:1px solid var(--line);border-radius:8px;font-size:15px}
input[type=search]:focus{outline:none;border-color:var(--sage);box-shadow:0 0 0 3px rgba(127,169,139,.25)}
input[type=checkbox]{accent-color:#6b9477}:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}
th{cursor:pointer;user-select:none;background:var(--bg);position:sticky;top:0;border-bottom-color:var(--sage)}th:hover{color:var(--accent)}
td.num,th.num{text-align:right}.bar{height:8px;background:#a9c9b2;border-radius:4px}
tr.stop td.w{color:var(--muted)}
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
header .eyebrow{display:inline-block;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;background:rgba(255,255,255,.16);border-radius:999px;padding:1px 10px;margin-bottom:4px}
.seg{display:inline-flex;gap:4px;background:#efe7d8;border:1px solid #d9cdb6;border-radius:12px;padding:4px;margin:0 0 12px}
.seg button{border:0;background:transparent;color:#5c5548;font:inherit;font-size:15px;font-weight:600;padding:7px 22px;border-radius:9px;cursor:pointer}
.seg button:hover{color:var(--ink);background:rgba(255,253,248,.6)}
.seg button.on{background:var(--chip-on);color:var(--chip-ink);box-shadow:inset 0 0 0 2px var(--accent),0 1px 2px rgba(60,45,20,.15)}.seg button.on::before{content:"\2713\00a0"}
#persons button.chip.on{font-weight:600;box-shadow:inset 0 0 0 1px var(--accent)}
body.mode-pol header{background:#4f5b66;box-shadow:inset 0 -4px 0 #bfcad3}
body.mode-rel header{background:#5f5568;box-shadow:inset 0 -4px 0 #d4c8db}
.only-fed,.only-ceo,.only-pol,.only-rel{display:none}
body.mode-fed .only-fed,body.mode-ceo .only-ceo,body.mode-pol .only-pol,body.mode-rel .only-rel{display:inline}
#cats{flex-wrap:wrap}#pop .credit{font-size:11px;color:var(--muted);margin-top:4px}
#pop .cap{font-size:12px;color:var(--muted);margin-top:8px;padding-top:6px;border-top:1px dashed var(--line)}
.viewbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0 0 14px}
.viewbar .lbl{font-weight:600;font-size:13px;color:var(--muted)}.viewbar .seg{margin:0}.viewbar .seg button{font-size:14px;padding:6px 18px}
body.view-visual .only-standard,body:not(.view-visual) .only-visual{display:none}
.cloud-bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:2px 0 6px;font-size:14px}
.cloud-bar select{font:inherit;font-size:14px;padding:3px 6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
#cloud{position:relative;width:100%;min-height:120px;overflow:hidden;margin:4px 0 2px}
#cloud span{position:absolute;white-space:nowrap;cursor:help;border-radius:5px;letter-spacing:-.01em;transition:background-color .12s}
#cloud span:hover,#cloud span.active{background:#e2f0e7}#cloud .empty{position:static}
</style></head><body class="mode-fed">
<header><a class="about-link" href="#about">About</a>
<div class="brand"><a class="logo" href="./" title="Mouth Math home"><img src="assets/logo.png?v=mm1" width="433" height="104" alt="Mouth Math"></a>
<div class="titles"><div class="eyebrow" id="eyebrow"></div><h1 id="h1">Every word __DEFAULT_TITLE__ said, ranked</h1>
<p id="sub">Word frequencies from official sources</p></div></div></header>
<main>
<div class="viewbar"><span class="lbl">View</span>
<div class="seg" id="views" role="tablist" aria-label="View"><button data-view="standard" role="tab">Standard</button><button data-view="visual" role="tab">Visual</button></div>
<span class="muted" id="viewHint"></span></div>
<section class="card" id="picker"><h2>Who</h2>
<div class="seg" id="cats" role="tablist" aria-label="Category"></div>
<div class="tf-row" id="persons"><span class="lbl">Person</span></div>
<div id="personInfo" class="muted"></div>
</section>
<section class="card" id="timeframe"><h2>Timeframe</h2>
<div class="tf-row"><span class="lbl">Quick</span>
  <button class="chip" id="btnAll">All</button><button class="chip" id="btnNone">None</button></div>
<div class="tf-row" id="years"><span class="lbl">By year</span></div>
<div class="tf-row"><span class="lbl">Documents</span><span class="muted">tick one or more · “only” selects just that one</span></div>
<ul class="speeches" id="docList"></ul>
<div id="selSummary"></div>
</section>
<section class="card stats">
<div class="stat"><b id="sDocs">–</b>documents selected</div>
<div class="stat"><b id="sTotal">–</b>total words</div>
<div class="stat"><b id="sUnique">–</b>unique words</div>
<div class="stat"><b id="sShown">–</b>words shown</div>
</section>
<section class="card" id="words">
<div class="controls">
<input type="search" id="q" placeholder="Filter words (e.g. inflation, ^pro, ing$)…">
<label><input type="checkbox" id="hideStop"> Hide common stopwords</label>
</div>
<div class="only-visual"><div class="cloud-bar"><label>Show top <select id="cloudN" aria-label="Number of words in the cloud">
<option value="50">50</option><option value="150" selected>150</option><option value="300">300</option></select> words</label>
<span class="muted" id="cloudNote"></span></div><div id="cloud"></div></div>
<table class="only-standard"><thead><tr><th class="num" data-k="rank">Rank</th><th data-k="word">Word</th><th class="num" data-k="count">Count</th><th style="width:30%"></th></tr></thead>
<tbody id="tb"></tbody></table>
<p class="muted only-standard" id="more"></p>
</section>
<p class="muted" id="method">Tokenization: lowercase; punctuation and hyphens split words; contractions kept (don't, it's, we're);
possessive 's removed (Fed's → fed); digit-only tokens __NUMNOTE__. <span class="only-fed">Fed transcripts: footnotes and editorial notes excluded.</span>
<span class="only-ceo">CEO letters: signature blocks, tables, section headings/numerals and quoted epigraphs excluded.</span>
<span class="only-pol">Presidential transcripts (Daily Compilation of Presidential Documents): only the President's words; audience reactions, [bracketed] notes, other speakers and closing notes excluded.</span>
<span class="only-rel">Vatican texts: English text as published by the Holy See; page headings, footnotes, scripture citations in parentheses, and summaries read by others excluded.</span>
Totals, ranks and counts are recomputed in your browser for the selected person and documents.
Hover a word to see the sentences where it was used (click or tap to pin). <span id="dataThrough"></span></p>
<section class="card" id="about"><h2>About Mouth Math</h2>
<p>This site was built by someone who believes in transparency and truth. It counts every word in official,
publicly available texts by public figures, taken from each official source:</p>
<ul class="sources">
<li><strong>Fed Chair:</strong> speech and testimony transcripts published on
<a href="https://www.federalreserve.gov/newsevents/speeches.htm" target="_blank" rel="noopener">federalreserve.gov</a>.</li>
<li><strong>CEOs:</strong> shareholder letters posted by each company on its own website (palantir.com, aboutamazon.com, berkshirehathaway.com).</li>
<li><strong>U.S. President:</strong> official transcripts from the
<a href="https://www.govinfo.gov/app/collection/cpd" target="_blank" rel="noopener">Daily Compilation of Presidential Documents</a>
(U.S. Government Publishing Office, govinfo.gov), the official record of the President's remarks.</li>
<li><strong>Pope:</strong> English texts published by the Holy See on <a href="https://www.vatican.va/" target="_blank" rel="noopener">vatican.va</a>
(© Dicastery for Communication – Libreria Editrice Vaticana).</li>
</ul>
<p><strong>Licensing approach.</strong> Works of the U.S. government (Fed and White House transcripts) are in the public
domain, so every sentence is available on hover. Other texts (CEO letters, Vatican texts) are copyrighted by their
publishers: for those we publish only word counts and short excerpts (at most about a quarter of each text, and at most
10 sentences per word), each linked to the original, and never the full text.</p>
<p><strong>Translations.</strong> Where a text was originally given in another language, we use the official English
translation published by that government or institution. Counts reflect that published English text.</p>
<p><strong>Neutrality.</strong> We present word counts without commentary. Nothing is edited or interpreted; footnotes,
editorial notes and other speakers' words are left out, and every sentence shown links back to its source so you can
check it yourself. Inclusion of a person does not imply endorsement, and this site is not affiliated with or endorsed by
any government, institution, company, or person listed.</p>
<p><strong>How it works:</strong> words are lowercased and counted across the documents you select.
“Hide common stopwords” removes very common words like “the” and “and”. Press conference Q&amp;A isn't included yet.</p>
<div class="notice" role="note"><strong>Not financial advice.</strong> This site is for informational and entertainment
purposes only and is not financial, investment, or trading advice. It is not affiliated with or endorsed by the
Federal Reserve, the White House, the Holy See, or by any company or person listed.</div>
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
  $('persons').innerHTML='<span class="lbl">Person</span>'+PEOPLE.filter(p=>p.category===P.category).map(p=>
    `<button class="chip${p.slug===P.slug?' on':''}" data-person="${p.slug}" title="${esc(p.role)}">${esc(p.name)}</button>`).join('');
  $('personInfo').textContent=`${P.role} · ${P.docs.length} ${P.docs.length===1?(P.doc_noun1||P.doc_noun.replace(/s$/,'')):P.doc_noun} from ${P.source}`;
  document.querySelectorAll('#cats button').forEach(b=>b.onclick=()=>{if(b.dataset.cat!==P.category)setPerson(PEOPLE.find(p=>p.category===b.dataset.cat).slug)});
  document.querySelectorAll('#persons button').forEach(b=>b.onclick=()=>{if(b.dataset.person!==P.slug)setPerson(b.dataset.person)});
}
async function setPerson(slug,docIds){
  hidePop();
  const p=await loadPerson(BY.get(slug)||BY.get(DEFAULT));
  P=p;V=p.vocab;VI=p.VI;DOCS=p.docs;YEARS=[...new Set(DOCS.map(d=>d.year))].sort().reverse();
  const ids=(docIds||[]).filter(i=>DOCS.some(d=>d.id===i));
  sel=new Set(ids.length?ids:DOCS.map(d=>d.id));
  ['fed','ceo','pol','rel'].forEach(m=>document.body.classList.toggle('mode-'+m,(P.mode||(P.category===PEOPLE[0].category?'fed':'ceo'))===m));
  $('eyebrow').textContent=P.eyebrow||`${P.category.replace(/s$/,'')} · ${P.org}`;
  $('h1').textContent=`Every word ${P.display} said, ranked`;
  document.title=`Mouth Math — every word ${P.display} said, ranked`;
  const noun=n=>n===1?(P.doc_noun1||P.doc_noun.replace(/s$/,'')):P.doc_noun;
  $('sub').textContent=`Word frequencies across ${DOCS.length} ${noun(DOCS.length)} from ${P.source}`;
  $('dataThrough').textContent='Data through '+fmtDate(DOCS.map(d=>d.date).sort().pop())+'.';
  renderPicker();buildTimeframe();update();
}

// ---- timeframe UI ----
function buildTimeframe(){
  $('docList').innerHTML=DOCS.map(d=>`<li data-id="${d.id}"><input type="checkbox" id="cb_${d.id}" data-id="${d.id}">
 <label for="cb_${d.id}"><span class="date">${fmtDate(d.date)}</span> <a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.title)}</a>
 <span class="muted">(${d.type}, ${d.words.toLocaleString()} words)${[d.location,d.note].filter(Boolean).map(esc).join(' · ').replace(/^(?=.)/,' — ')}</span></label>
 <a class="only" data-only="${d.id}">only</a></li>`).join('');
  $('years').innerHTML='<span class="lbl">By year</span>'+YEARS.map(y=>{const n=DOCS.filter(d=>d.year===y).length;
    return `<label class="chip" id="yc_${y}"><input type="checkbox" data-year="${y}"> ${y} <span class="muted">(${n})</span></label>`}).join('');
  document.querySelectorAll('#docList input').forEach(cb=>cb.onchange=()=>{cb.checked?sel.add(cb.dataset.id):sel.delete(cb.dataset.id);update()});
  document.querySelectorAll('#docList a.only').forEach(a=>a.onclick=()=>{sel=new Set([a.dataset.only]);update()});
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
  tb.innerHTML=list.length?list.slice(0,LIMIT).map(x=>`<tr class="${x.stop?'stop':''}" data-w="${esc(x.word)}"><td class="num">${x.rank}</td><td class="w">${esc(x.word)}</td><td class="num">${x.count.toLocaleString()}</td><td><div class="bar" style="width:${(100*x.count/max).toFixed(1)}%"></div></td></tr>`).join('')
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

// ---- Visual mode: word cloud (vanilla JS; spiral placement + measureText box collisions) ----
let VIEW='standard',stopStd=null,cloudW=0,cloudInfo={placed:0,skipped:0,ms:0};
const PAL=['#3f6250','#2f4f3b','#4f6656','#5e7f63','#6a5f4e','#7d6646','#56705c'];
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
  const W=cloud.clientWidth;cloudW=W;if(!W)return 0;const t0=performance.now();
  const N=+cloudN.value,words=list.slice().sort((a,b)=>b.count-a.count||(a.word<b.word?-1:1)).slice(0,N);
  if(!words.length){cloud.style.height='';cloud.innerHTML=`<div class="empty">${sel.size?'No matching words.':'Select at least one document above.'}</div>`;
    $('cloudNote').textContent='';cloudInfo={placed:0,skipped:0,ms:0};return 0}
  const {placed,miss,tries,steps}=cloudLayout(words,W);
  const y0=Math.min(...placed.map(c=>c.y)),y1=Math.max(...placed.map(c=>c.y+c.h));
  cloud.style.height=Math.ceil(y1-y0+4)+'px';
  cloud.innerHTML=placed.map(c=>{const b=c.b,x=b.x;return `<span data-w="${esc(x.word)}" data-c="${x.count}" role="button" tabindex="0" aria-label="${esc(x.word)}: ${x.count}" `+
    `style="left:${(c.x+1).toFixed(1)}px;top:${(c.y-y0+1).toFixed(1)}px;font-size:${b.f}px;font-weight:${b.wt};line-height:${c.h-2}px;height:${c.h-2}px;padding:0 ${b.pad}px;color:${PAL[hcode(x.word)%PAL.length]}">${esc(x.word)}</span>`}).join('');
  cloudInfo={placed:placed.length,skipped:miss,tries,steps,ms:Math.round(performance.now()-t0)};
  $('cloudNote').textContent=`Top ${placed.length.toLocaleString()} of ${list.length.toLocaleString()} words${hide.checked?' (stopwords hidden)':''}`+
    `${miss?` · ${miss} didn't fit`:''} · size ∝ √count · hover or tap a word for its count and sentences`;
  return placed.length;
}
function setView(v,user){
  v=v==='visual'?'visual':'standard';
  document.querySelectorAll('#views button').forEach(b=>{const on=b.dataset.view===v;b.classList.toggle('on',on);b.setAttribute('aria-selected',on)});
  $('viewHint').textContent=v==='visual'?'Word cloud: bigger words were used more often.':'Ranked table of every word.';
  if(v===VIEW)return;
  hidePop();VIEW=v;document.body.classList.toggle('view-visual',v==='visual');
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
window.__fedwords={occurrences,highlight,fragUrl,stats,setPerson,setView,get view(){return VIEW},get cloudInfo(){return cloudInfo},get P(){return P},checkAll(){const bad=[];V.forEach(w=>{
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
