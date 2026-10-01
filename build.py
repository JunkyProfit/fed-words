#!/usr/bin/env python3
"""Count every word the Fed Chair spoke in transcripts/*.txt and write index.html.

Usage: python3 build.py [--keep-numbers] [--top 15]
Reads transcripts/index.json (written by fetch.py) for titles/dates/links.
"""
import argparse, html, json, re
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
TDIR = ROOT / "transcripts"

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
you've your yours yourself yourselves
""".split())

TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)*")

def tokenize(text, keep_numbers=False):
    text = text.lower().replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")
    out = []
    for t in TOKEN_RE.findall(text):          # hyphens/dashes/punctuation split words
        if t.endswith("'s") and t not in S_CONTRACTIONS:
            t = t[:-2]                         # possessive: fed's -> fed
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

def split_sentences(text):
    """Split into sentences. Breaks only at whitespace, so tokens are never cut and
    per-sentence token counts always add up to the whole-transcript count."""
    out = []
    for para in re.split(r"\n\s*\n", text):
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
            out.append(para[start:m.end()].strip())
            start = m.end()
        if para[start:].strip():
            out.append(para[start:].strip())
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-numbers", action="store_true", help="count digit-only tokens like 2026")
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()

    meta = []
    for m in json.loads((TDIR / "index.json").read_text(encoding="utf-8")):
        if (TDIR / m["file"]).exists():
            meta.append(m)
        else:
            print(f"WARN: {m['file']} listed in index.json but missing; skipped")
    if not meta:
        raise SystemExit("No transcripts found; run fetch.py first.")
    meta.sort(key=lambda m: (m["date"], m["url"]), reverse=True)
    total = Counter()
    for m in meta:
        text = (TDIR / m["file"]).read_text(encoding="utf-8")
        m["sents"] = split_sentences(text)
        m["sent_toks"] = [tokenize(x, a.keep_numbers) for x in m["sents"]]
        c = Counter(t for toks in m["sent_toks"] for t in toks)
        # Consistency guarantee: sentence-level occurrences == whole-text counts.
        assert c == Counter(tokenize(text, a.keep_numbers)), f"sentence split changed counts in {m['file']}"
        m["counts"], m["words"], m["unique"] = c, sum(c.values()), len(c)
        m["id"], m["year"] = Path(m["file"]).stem, m["date"][:4]
        total.update(c)

    rows = sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))
    n_total, n_unique = sum(total.values()), len(total)
    non_stop = [(w, c) for w, c in rows if w not in STOPWORDS]
    n_total_ns = sum(c for _, c in non_stop)

    print(f"Transcripts: {len(meta)}  ({meta[-1]['date']} to {meta[0]['date']})")
    for m in meta:
        ns = {w: c for w, c in m["counts"].items() if w not in STOPWORDS}
        top = sorted(m["counts"].items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        print(f"  {m['date']} {m['type']:9s} {m['words']:5d} words {m['unique']:5d} unique | "
              f"stopwords hidden: {sum(ns.values()):5d} words {len(ns):5d} unique | "
              f"{len(m['sents']):4d} sentences | {m['title']}")
        print(f"      top5: " + ", ".join(f"{w} {c}" for w, c in top))
    for y in sorted({m["year"] for m in meta}, reverse=True):
        ms = [m for m in meta if m["year"] == y]
        yc = Counter()
        for m in ms:
            yc.update(m["counts"])
        print(f"  Year {y}: {len(ms)} transcript(s), {sum(yc.values())} words, {len(yc)} unique")
    print(f"All: total words: {n_total}   Unique words: {n_unique}")
    print(f"All, stopwords hidden: {n_total_ns} words, {len(non_stop)} unique")
    print(f"\nTop {a.top} (all words):")
    for i, (w, c) in enumerate(rows[: a.top], 1):
        print(f"  {i:2d}. {w:15s} {c}")
    print(f"\nTop {a.top} (stopwords hidden):")
    for i, (w, c) in enumerate(non_stop[: a.top], 1):
        print(f"  {i:2d}. {w:15s} {c}")

    # Compact embedding: shared vocabulary; per transcript the sentence texts ("s") and a flat
    # word->sentence index ("x") = [wordIndex, n, sent_1 .. sent_n, ...] with one sentence index
    # per occurrence (so n == that word's count in the transcript; repeats = used twice in a sentence).
    vocab = [w for w, _ in rows]
    vidx = {w: i for i, w in enumerate(vocab)}
    docs = []
    for m in meta:
        occ = {}
        for si, toks in enumerate(m["sent_toks"]):
            for t in toks:
                occ.setdefault(vidx[t], []).append(si)
        flat = []
        for wi in sorted(occ):
            flat += [wi, len(occ[wi])] + occ[wi]
        d = {k: m[k] for k in ("id", "date", "year", "type", "title", "location", "url", "words")}
        d["s"] = m["sents"]
        d["x"] = flat
        docs.append(d)
    data = {"vocab": vocab, "docs": docs, "stop": sorted(STOPWORDS),
            "sc": sorted(S_CONTRACTIONS), "keepNum": a.keep_numbers}

    speaker = meta[0].get("speaker", "Fed Chair")
    page = TEMPLATE
    for k, v in {
        "__SPEAKER__": html.escape(speaker),
        "__N__": str(len(meta)),
        # Latest transcript date (not build time) so rebuilds without new speeches are byte-identical.
        "__DATA_THROUGH__": "{d:%b} {d.day}, {d:%Y}".format(d=datetime.strptime(meta[0]["date"], "%Y-%m-%d")),
        "__NUMNOTE__": "included" if a.keep_numbers else "excluded",
        "__DATA__": json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/"),
    }.items():
        page = page.replace(k, v)
    out = ROOT / "index.html"
    tmp = ROOT / "index.html.tmp"
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(out)                       # atomic: never leaves a half-written index.html
    print(f"\nWrote {out} ({out.stat().st_size / 1024:.0f} KB)")

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/png" href="assets/favicon.png">
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">
<title>Fed Words — every word __SPEAKER__ said, ranked</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2433;--muted:#6b7385;--accent:#1f4e8c;--line:#e3e6ec}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
html{scroll-behavior:smooth}
header{background:var(--accent);color:#fff;padding:22px 28px;position:relative}
header a.about-link{position:absolute;top:22px;right:28px;color:#fff;font-size:14px;opacity:.9;text-decoration:none;border:1px solid rgba(255,255,255,.5);border-radius:999px;padding:3px 12px}
header a.about-link:hover{opacity:1;background:rgba(255,255,255,.12)}
header .brand{display:flex;align-items:center;gap:18px;padding-right:90px}
header .logo{flex:none;display:block;background:#fff;border-radius:10px;padding:6px 10px;box-shadow:0 1px 3px rgba(0,0,0,.25);line-height:0}
header .logo img{height:44px;width:auto;display:block}
header .titles{min-width:0}
@media (max-width:640px){header{padding:16px}header a.about-link{top:16px;right:16px}
 header .brand{flex-direction:column;align-items:flex-start;gap:10px;padding-right:0}
 header .logo img{height:34px}header h1{font-size:20px}}
#about{scroll-margin-top:16px}#about h2{font-size:18px}#about p{margin:0 0 10px;max-width:72ch}
.notice{border:1px solid #e0b252;background:#fff8e6;border-left:5px solid #d99a1e;border-radius:8px;padding:10px 14px;margin-top:12px;max-width:72ch}
.notice strong{color:#7a4d00}header h1{margin:0;font-size:24px}header p{margin:4px 0 0;opacity:.85}
main{max-width:960px;margin:0 auto;padding:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin-bottom:16px}
h2{font-size:16px;margin:0 0 10px}.muted{color:var(--muted);font-size:13px}
.tf-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.tf-row .lbl{font-weight:600;font-size:13px;color:var(--muted);min-width:70px}
button.chip,label.chip{border:1px solid var(--line);background:var(--bg);border-radius:999px;padding:4px 12px;font:inherit;font-size:13px;cursor:pointer;display:inline-flex;gap:6px;align-items:center}
button.chip.on,label.chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
label.chip input{margin:0}
ul.speeches{list-style:none;margin:0;padding:0}ul.speeches li{display:flex;gap:10px;align-items:flex-start;padding:6px 0;border-top:1px solid var(--line)}
ul.speeches li.sel{background:#eef3fb}ul.speeches input{margin-top:5px}
.date{font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
a.only{font-size:12px;margin-left:6px;cursor:pointer}
#selSummary{margin-top:8px;font-size:14px}
.stats{display:flex;gap:14px;flex-wrap:wrap}.stat{flex:1;min-width:150px;background:var(--bg);border-radius:8px;padding:10px 14px}
.stat b{display:block;font-size:24px;color:var(--accent)}
.controls{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
input[type=search]{flex:1;min-width:220px;padding:9px 12px;border:1px solid var(--line);border-radius:8px;font-size:15px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}
th{cursor:pointer;user-select:none;background:var(--bg);position:sticky;top:0}th:hover{color:var(--accent)}
td.num,th.num{text-align:right}.bar{height:8px;background:#9db7dc;border-radius:4px}
tr.stop td.w{color:var(--muted)}
tr[data-w]{cursor:help}tr[data-w]:hover td{background:#f1f5fc}tr.active td{background:#e3ecfa}
#pop{position:absolute;z-index:50;background:#fff;border:1px solid #c9d3e3;border-radius:10px;box-shadow:0 10px 30px rgba(20,40,80,.18);
 padding:12px 14px;font-size:14px;max-height:60vh;overflow:auto;line-height:1.45}
#pop[hidden]{display:none}#pop.expanded{max-height:75vh}
#pop .ph{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;position:sticky;top:-12px;background:#fff;padding:2px 0 8px;border-bottom:1px solid var(--line);margin-bottom:6px}
#pop .ph .t{font-size:13px;color:var(--muted)}#pop .ph b{font-size:16px;color:var(--ink)}
#pop .x{border:0;background:none;font-size:20px;line-height:1;cursor:pointer;color:var(--muted)}
#pop .doc{margin:10px 0 4px;font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
#pop ol{margin:0;padding-left:20px}#pop li{margin:5px 0}
#pop mark{background:#ffe27a;padding:0 1px;border-radius:2px}
#pop .src{font-size:12px;margin-left:6px;white-space:nowrap}#pop .twice{font-size:11px;color:#8a5a00;background:#fff3cd;border-radius:4px;padding:0 4px;margin-left:4px}
#pop .more{margin-top:10px;border:1px solid var(--accent);color:var(--accent);background:#fff;border-radius:8px;padding:6px 12px;cursor:pointer;font:inherit;font-size:13px}
#pop .hint{font-size:12px;color:var(--muted);margin-top:8px}a{color:var(--accent)}.empty{padding:20px;text-align:center;color:var(--muted)}
</style></head><body>
<header><a class="about-link" href="#about">About</a>
<div class="brand"><a class="logo" href="./" title="Fed Words home"><img src="assets/logo.png" width="342" height="104" alt="Fed Words"></a>
<div class="titles"><h1>Every word __SPEAKER__ said, ranked</h1>
<p>Word frequencies across __N__ official transcripts from federalreserve.gov</p></div></div></header>
<main>
<section class="card" id="timeframe"><h2>Timeframe</h2>
<div class="tf-row"><span class="lbl">Quick</span>
  <button class="chip" id="btnAll">All</button><button class="chip" id="btnNone">None</button></div>
<div class="tf-row" id="years"><span class="lbl">By year</span></div>
<div class="tf-row"><span class="lbl">Speeches</span><span class="muted">tick one or more · “only” selects just that one</span></div>
<ul class="speeches" id="docList"></ul>
<div id="selSummary"></div>
</section>
<section class="card stats">
<div class="stat"><b id="sDocs">–</b>transcripts selected</div>
<div class="stat"><b id="sTotal">–</b>total words</div>
<div class="stat"><b id="sUnique">–</b>unique words</div>
<div class="stat"><b id="sShown">–</b>words shown</div>
</section>
<section class="card">
<div class="controls">
<input type="search" id="q" placeholder="Filter words (e.g. inflation, ^pro, ing$)…">
<label><input type="checkbox" id="hideStop"> Hide common stopwords</label>
</div>
<table><thead><tr><th class="num" data-k="rank">Rank</th><th data-k="word">Word</th><th class="num" data-k="count">Count</th><th style="width:30%"></th></tr></thead>
<tbody id="tb"></tbody></table>
<p class="muted" id="more"></p>
</section>
<p class="muted">Tokenization: lowercase; punctuation and hyphens split words; contractions kept (don't, it's, we're);
possessive 's removed (Fed's → fed); digit-only tokens __NUMNOTE__. Footnotes and editorial notes excluded.
Totals, ranks and counts are recomputed in your browser for the selected transcripts.
Hover a word to see the sentences where it was used (click or tap to pin). Data through __DATA_THROUGH__.</p>
<section class="card" id="about"><h2>About this site</h2>
<p>This site was built by someone who believes in transparency and truth. It takes the official, publicly available
speech and testimony transcripts of the Chair of the Federal Reserve, published on
<a href="https://www.federalreserve.gov/newsevents/speeches.htm" target="_blank" rel="noopener">federalreserve.gov</a>,
and counts every word. Nothing is edited or interpreted; footnotes and editorial notes are left out. Every number comes straight from the transcripts,
and every sentence links back to its original source so you can check it yourself.</p>
<p>Our goal is simply to offer a more fun way to explore what the Fed Chair says. We aren't pushing a viewpoint, and
the word counts are presented without commentary.</p>
<p><strong>How it works:</strong> words are lowercased and counted across the transcripts you select.
“Hide common stopwords” removes very common words like “the” and “and”. Press conference Q&amp;A isn't included yet.</p>
<div class="notice" role="note"><strong>Not financial advice.</strong> This site is for informational and entertainment
purposes only and is not financial, investment, or trading advice. It is not affiliated with or endorsed by the
Federal Reserve.</div>
</section>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const STOP=new Set(D.stop), V=D.vocab, DOCS=D.docs;
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtDate=s=>new Date(s+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
const YEARS=[...new Set(DOCS.map(d=>d.year))].sort().reverse();
let sel=new Set(DOCS.map(d=>d.id)), sortK='count', sortDir=-1; const LIMIT=2000;

// ---- timeframe UI ----
$('docList').innerHTML=DOCS.map(d=>`<li data-id="${d.id}"><input type="checkbox" id="cb_${d.id}" data-id="${d.id}">
 <label for="cb_${d.id}"><span class="date">${fmtDate(d.date)}</span> <a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.title)}</a>
 <span class="muted">(${d.type}, ${d.words.toLocaleString()} words) — ${esc(d.location)}</span></label>
 <a class="only" data-only="${d.id}">only</a></li>`).join('');
$('years').insertAdjacentHTML('beforeend',YEARS.map(y=>{const n=DOCS.filter(d=>d.year===y).length;
 return `<label class="chip" id="yc_${y}"><input type="checkbox" data-year="${y}"> ${y} <span class="muted">(${n})</span></label>`}).join(''));
document.querySelectorAll('#docList input').forEach(cb=>cb.onchange=()=>{cb.checked?sel.add(cb.dataset.id):sel.delete(cb.dataset.id);update()});
document.querySelectorAll('#docList a.only').forEach(a=>a.onclick=()=>{sel=new Set([a.dataset.only]);update()});
document.querySelectorAll('#years input').forEach(cb=>cb.onchange=()=>{
  DOCS.filter(d=>d.year===cb.dataset.year).forEach(d=>cb.checked?sel.add(d.id):sel.delete(d.id));update()});
$('btnAll').onclick=()=>{sel=new Set(DOCS.map(d=>d.id));update()};
$('btnNone').onclick=()=>{sel=new Set();update()};

function syncTimeframe(){
  DOCS.forEach(d=>{const on=sel.has(d.id);$('cb_'+d.id).checked=on;document.querySelector(`li[data-id="${d.id}"]`).classList.toggle('sel',on)});
  YEARS.forEach(y=>{const ids=DOCS.filter(d=>d.year===y).map(d=>d.id),k=ids.filter(i=>sel.has(i)).length;
    const cb=document.querySelector(`#years input[data-year="${y}"]`);cb.checked=k===ids.length;cb.indeterminate=k>0&&k<ids.length;
    $('yc_'+y).classList.toggle('on',k===ids.length)});
  const all=sel.size===DOCS.length;$('btnAll').classList.toggle('on',all);$('btnNone').classList.toggle('on',sel.size===0);
  const ds=DOCS.filter(d=>sel.has(d.id));
  $('selSummary').innerHTML=!ds.length?'<b>No transcripts selected.</b>':
    `Showing <b>${all?'all '+ds.length:ds.length+' of '+DOCS.length}</b> transcript${(all?ds.length:DOCS.length)>1?'s':''}`+
    ` (${fmtDate(ds[ds.length-1].date)}${ds.length>1?' – '+fmtDate(ds[0].date):''})`;
  if(!all)history.replaceState(null,'','#docs='+[...sel].join(','));
  else if(location.hash.startsWith('#docs='))history.replaceState(null,'',location.pathname); // keep #about etc.
}

// ---- counting / table ----
let BASE=[];
function aggregate(){
  const cnt=new Map();
  DOCS.forEach(d=>{if(!sel.has(d.id))return;const x=d.x;for(let i=0;i<x.length;){cnt.set(x[i],(cnt.get(x[i])||0)+x[i+1]);i+=2+x[i+1]}});
  BASE=[...cnt].map(([i,n])=>({word:V[i],count:n,stop:STOP.has(V[i])}));
}
function render(){
  const base=BASE.filter(x=>!(hide.checked&&x.stop));
  base.sort((a,b)=>b.count-a.count||(a.word<b.word?-1:a.word>b.word?1:0));
  let r=0,prev=null;base.forEach((x,i)=>{if(x.count!==prev){r=i+1;prev=x.count}x.rank=r});
  const s=q.value.trim().toLowerCase();let re=null;if(s){try{re=new RegExp(s)}catch(e){}}
  const list=s?base.filter(x=>re?re.test(x.word):x.word.includes(s)):base.slice();
  list.sort((a,b)=>{const va=a[sortK],vb=b[sortK];const c=typeof va==='string'?(va<vb?-1:va>vb?1:0):va-vb;return c*sortDir||a.rank-b.rank});
  const max=base.length?base[0].count:1;
  tb.innerHTML=list.length?list.slice(0,LIMIT).map(x=>`<tr class="${x.stop?'stop':''}" data-w="${esc(x.word)}"><td class="num">${x.rank}</td><td class="w">${esc(x.word)}</td><td class="num">${x.count.toLocaleString()}</td><td><div class="bar" style="width:${(100*x.count/max).toFixed(1)}%"></div></td></tr>`).join('')
    :`<tr><td colspan="4" class="empty">${sel.size?'No matching words.':'Select at least one transcript above.'}</td></tr>`;
  $('sDocs').textContent=sel.size+' / '+DOCS.length;
  $('sTotal').textContent=base.reduce((t,x)=>t+x.count,0).toLocaleString();
  $('sUnique').textContent=base.length.toLocaleString();
  $('sShown').textContent=list.length.toLocaleString();
  $('more').textContent=list.length>LIMIT?`Showing first ${LIMIT} of ${list.length} — use the filter to find others.`:'';
  document.querySelectorAll('th[data-k]').forEach(th=>{th.textContent=th.textContent.replace(/ [▲▼]$/,'')+(th.dataset.k===sortK?(sortDir<0?' ▼':' ▲'):'')});
}
function update(){if(typeof hidePop==='function')hidePop();syncTimeframe();aggregate();render()}
const q=$('q'),hide=$('hideStop'),tb=$('tb');
document.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{hidePop();const k=th.dataset.k;
  if(sortK===k)sortDir*=-1;else{sortK=k;sortDir=k==='count'?-1:1}render()});
q.oninput=()=>{hidePop();render()};hide.onchange=()=>{hidePop();render()};
// restore selection from URL (#docs=id1,id2) so a view can be shared/bookmarked
const m=location.hash.match(/docs=([^&]*)/);
if(m){const ids=m[1].split(',').filter(i=>DOCS.some(d=>d.id===i));if(ids.length)sel=new Set(ids)}
// ---- sentence popover (hover = preview, click/tap = pin) ----
const SC=new Set(D.sc), VI=new Map(V.map((w,i)=>[w,i]));
DOCS.forEach(d=>{d.occ=new Map();const x=d.x;for(let i=0;i<x.length;){const wi=x[i],n=x[i+1];d.occ.set(wi,x.slice(i+2,i+2+n));i+=2+n}});
const TOK=/[a-z0-9]+(?:'[a-z]+)*/g;
function highlight(sent,word){ // same tokenizer rules as build.py; returns html + number of matches
  const norm=sent.replace(/[\u2018\u2019`]/g,"'"),low=norm.toLowerCase(),same=low.length===sent.length;
  let out='',last=0,n=0,m;TOK.lastIndex=0;
  while((m=TOK.exec(low))){let t=m[0];if(t.endsWith("'s")&&!SC.has(t))t=t.slice(0,-2);
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
function occurrences(word){ // [{doc, si, n}] for selected transcripts, newest first
  const wi=VI.get(word),items=[];
  DOCS.forEach(d=>{if(!sel.has(d.id))return;const a=d.occ.get(wi);if(!a)return;
    for(let i=0;i<a.length;){let j=i;while(j<a.length&&a[j]===a[i])j++;items.push({doc:d,si:a[i],n:j-i});i=j}});
  return items;
}
const pop=document.createElement('div');pop.id='pop';pop.hidden=true;pop.setAttribute('role','dialog');document.body.appendChild(pop);
let pinned=false,curWord=null,curRow=null,showAll=false,hoverT=null,hideT=null;const FIRST=10;
function popHTML(word){
  const items=occurrences(word),occ=items.reduce((t,x)=>t+x.n,0),ndocs=new Set(items.map(x=>x.doc.id)).size;
  const shown=showAll?items:items.slice(0,FIRST);let h=`<div class="ph"><div><b>${esc(word)}</b>
   <div class="t" id="popCount">${occ.toLocaleString()} occurrence${occ===1?'':'s'} in ${items.length.toLocaleString()} sentence${items.length===1?'':'s'}`+
   ` · ${ndocs} of ${sel.size} selected transcript${sel.size===1?'':'s'}${occ!==items.length?' · some sentences use it more than once':''}</div></div>
   <button class="x" title="Close (Esc)" aria-label="Close">×</button></div>`;
  let lastDoc=null;
  shown.forEach(it=>{if(it.doc!==lastDoc){if(lastDoc)h+='</ol>';lastDoc=it.doc;
      h+=`<div class="doc">${fmtDate(it.doc.date)} · <a href="${esc(it.doc.url)}" target="_blank" rel="noopener">${esc(it.doc.title)}</a></div><ol>`}
    const s=it.doc.s[it.si],hl=highlight(s,word);
    h+=`<li data-n="${it.n}" data-hl="${hl.n}">${hl.html}${it.n>1?`<span class="twice">×${it.n}</span>`:''}`+
       `<a class="src" href="${esc(fragUrl(it.doc.url,s))}" target="_blank" rel="noopener" title="Open the speech at this sentence">source ↗</a></li>`});
  if(lastDoc)h+='</ol>';
  if(items.length>FIRST&&!showAll)h+=`<button class="more">Show all ${items.length.toLocaleString()} sentences (${occ.toLocaleString()} occurrences)</button>`;
  h+=`<div class="hint">${pinned?'Pinned. Press Esc or × to close.':'Click the word to pin this panel.'} “source ↗” jumps to the sentence (Chrome/Edge/Safari); the title link opens the speech.</div>`;
  return h;
}
function placePop(){
  if(!curRow)return;const cell=curRow.querySelector('td.w').getBoundingClientRect(),vw=document.documentElement.clientWidth;
  let left=cell.left+Math.min(cell.width,140)+8,width=Math.min(600,vw-left-12);
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
tb.addEventListener('mouseover',e=>{const tr=e.target.closest('tr[data-w]');if(!tr||pinned)return;clearTimeout(hideT);
  if(tr===curRow)return;clearTimeout(hoverT);hoverT=setTimeout(()=>showPop(tr,false),120)});
tb.addEventListener('mouseleave',()=>{clearTimeout(hoverT);if(!pinned)hideT=setTimeout(hidePop,300)});
pop.addEventListener('mouseenter',()=>clearTimeout(hideT));
pop.addEventListener('mouseleave',()=>{if(!pinned)hideT=setTimeout(hidePop,300)});
tb.addEventListener('click',e=>{const tr=e.target.closest('tr[data-w]');if(!tr)return;clearTimeout(hoverT);clearTimeout(hideT);pinned=false;showPop(tr,true)});
pop.addEventListener('click',e=>{e.stopPropagation(); // re-render detaches e.target; don't let the outside-click handler close us
  if(e.target.closest('.x')){hidePop();return}
  if(e.target.closest('.more')){showAll=true;pinned=true;pop.innerHTML=popHTML(curWord);pop.classList.add('expanded');placePop()}});
document.addEventListener('keydown',e=>{if(e.key==='Escape')hidePop()});
document.addEventListener('click',e=>{if(!pop.hidden&&pinned&&!pop.contains(e.target)&&!e.target.closest('tr[data-w]'))hidePop()});
addEventListener('resize',placePop);
// self-check used by tests: every highlighted match must equal the indexed occurrence count
window.__fedwords={occurrences,highlight,fragUrl,checkAll(){let bad=[];V.forEach(w=>{occurrences(w).forEach(it=>{
  if(highlight(it.doc.s[it.si],w).n!==it.n)bad.push([w,it.doc.id,it.si])})});return bad}};
update();
</script></body></html>
"""

if __name__ == "__main__":
    main()
