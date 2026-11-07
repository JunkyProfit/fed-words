"""Static, crawlable content pages (adsense-content): bios, speaker pages, articles, Terms of Use.
Called from build.py main() with the built people list; everything here is plain HTML, no JS needed to read it."""
import html, json, re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
SITE = "https://mouthmath.com/"
MONTHS = "January February March April May June July August September October November December".split()

FOOT_LINKS = [("./", "Home"), ("findings.html", "Findings"), ("articles/", "Articles"), ("contact.html", "Contact"),
              ("privacy.html", "Privacy Policy"), ("terms.html", "Terms of Use")]

def footer(current="", prefix=""):
    a = []
    for href, label in FOOT_LINKS:
        cur = ' aria-current="page"' if href == current else ""
        a.append(f'<a href="{prefix}{href}"{cur}>{label}</a>')
    return "<footer>" + " · ".join(a) + '<div class="mmcopy">&copy; 2026 MouthMath</div></footer>'

def fdate(iso):
    y, m, d = iso[:10].split("-")
    return f"{MONTHS[int(m) - 1]} {int(d)}, {y}"

# ---- bios: hand-written facts (content/bios.json) + one sentence about the documents, built from the data ----
GROUP_NOTE = {
    "Presidents": "The speeches come from The American Presidency Project at UC Santa Barbara and include inaugural addresses, State of the Union messages and addresses to the nation.",
    "Supreme Court": "The documents are written opinions, including opinions for the Court, concurrences and dissents, as published by the Supreme Court.",
    "Senate": "The documents are remarks on the Senate floor as printed in the Congressional Record.",
    "House": "The documents are remarks on the House floor as printed in the Congressional Record.",
    "Governors": "The documents are public statements from the governor's official website, such as news releases and remarks.",
    "Board of Governors": "The documents are public speeches and testimony from the Federal Reserve Board's official website.",
    "Cabinet": "The documents are public speeches, remarks and testimony from official government websites.",
}
SLUG_NOTE = {
    "volcker": "The documents are statements, speeches and testimony from his time as Chair, kept in the Federal Reserve's FRASER archive.",
    "cook": "The documents are his own public words, such as letters filed with the Securities and Exchange Commission and congressional testimony.",
    "jobs": "The documents are his own public words filed with the Securities and Exchange Commission.",
    "musk": "The documents are his two Tesla Master Plan essays and his testimony to Congress about SpaceX.",
}
FED_NOTE = "The documents are speeches, FOMC press conferences and testimony to Congress given as Chair, from the Federal Reserve's official website."
CEO_NOTE = "The documents are the CEO's own words to shareholders, such as yearly letters or the prepared remarks that open quarterly earnings calls."

def doc_note(p):
    if p["slug"] in SLUG_NOTE: return SLUG_NOTE[p["slug"]]
    if p.get("group") in GROUP_NOTE: return GROUP_NOTE[p["group"]]
    return FED_NOTE if p.get("mode") == "fed" else CEO_NOTE

def count_note(p):
    ds = p["docs"]; n = len(ds)
    y0, y1 = min(d["date"] for d in ds)[:4], max(d["date"] for d in ds)[:4]
    span = f"from {y0}" if y0 == y1 else f"from {y0} to {y1}"
    return f"MouthMath counts {n} {'document' if n == 1 else 'documents'} {span}."

ROLE_NOTE = {
    "Senate": "Senators serve six-year terms, and each state elects two.",
    "House": "Members of the House serve two-year terms and represent districts of roughly equal population.",
    "Governors": "Governors lead their state's executive branch, sign or veto bills and manage state agencies.",
    "Supreme Court": "Justices are nominated by the President, confirmed by the Senate and can serve for life.",
    "Board of Governors": "Fed governors are nominated by the President and confirmed by the Senate for terms of up to 14 years.",
    "Cabinet": "Cabinet secretaries are nominated by the President and confirmed by the Senate.",
}

def words_note(p, stop):
    tw = [w for w, _ in top_words(p, stop, 3)]
    q = [f"“{w}”" for w in tw]
    return f"Leaving out common words, the most used are {q[0]}, {q[1]} and {q[2]}."

def compose_bios(people, stop):
    bios = json.loads((CONTENT / "bios.json").read_text(encoding="utf-8"))
    for p in people:
        if p["slug"] in bios:
            parts = [bios[p["slug"]], ROLE_NOTE.get(p.get("group"), ""), doc_note(p), count_note(p), words_note(p, stop)]
            p["bio"] = " ".join(x for x in parts if x)
    compose_writeups(people, stop)

# ---- "What the numbers show": a short write-up per speaker, built only from the counts (adsense-content) ----
def peer_key(p): return p.get("group") or p.get("mode") or p["category"]

def q(w): return f"“{w}”"

def per_k(k, n): return f"{1000 * k / n:.1f}"

def compose_writeups(people, stop):
    ok = lambda w: w not in stop and not w.isdigit() and len(w) > 1
    C = {p["slug"]: counts(p) for p in people}
    pool = {}
    for p in people: pool.setdefault(peer_key(p), []).append(p["slug"])
    for p in people:
        c, ds = C[p["slug"]], p["docs"]
        if not ds: continue
        tot = sum(c.values()); n = len(ds)
        tw = [(w, k) for w, k in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])) if ok(w)]
        if len(tw) < 3: continue
        noun = p.get("doc_noun") or "documents"
        y0, y1 = min(d["date"] for d in ds)[:4], max(d["date"] for d in ds)[:4]
        span = y0 if y0 == y1 else f"{y0} to {y1}"
        (w1, k1), (w2, k2), (w3, k3) = tw[:3]
        out = [f"MouthMath counts {tot:,} words across {n} {'document' if n == 1 else 'documents'} from {span}, using {len(c):,} different words."]
        if k1 == k2:
            out.append(f"Leaving out common words, {q(w1)} and {q(w2)} are tied for first at {k1:,} uses each ({per_k(k1, tot)} per 1,000 words), followed by {q(w3)} at {k3:,}.")
        else:
            out.append(f"Leaving out common words, {q(w1)} leads with {k1:,} uses ({per_k(k1, tot)} per 1,000 words), ahead of {q(w2)} ({k2:,}) and {q(w3)} ({k3:,}).")
        top10 = ", ".join(q(w) for w, _ in tw[3:8])
        out.append(f"The rest of the top eight: {top10}.")
        if n >= 2:
            last = max(ds, key=lambda d: d["date"]); rest = [d for d in ds if d is not last]
            cl, cr = counts(p, [last]), counts(p, rest)
            nl, nr = sum(cl.values()) or 1, sum(cr.values()) or 1
            lt = [w for w, _ in sorted(cl.items(), key=lambda kv: (-kv[1], kv[0])) if ok(w)][:1]
            rise = sorted((w for w, k in cl.items() if ok(w) and k >= 5), key=lambda w: -(cl[w] / nl - cr.get(w, 0) / nr))[:1]
            if lt:
                t = f"In the newest document, from {fdate(last['date'])}, the top word is {q(lt[0])} ({cl[lt[0]]})"
                if rise and rise[0] != lt[0]:
                    w = rise[0]
                    t += f", and {q(w)} rose the most compared with earlier documents ({per_k(cl[w], nl)} vs. {per_k(cr.get(w, 0), nr)} per 1,000 words)"
                out.append(t + ".")
        peers = [s for s in pool[peer_key(p)] if s != p["slug"]]
        if peers:
            pc = Counter()
            for s2 in peers: pc.update(C[s2])
            pt = sum(pc.values()) or 1
            cand = [(w, k) for w, k in tw[:25] if k >= 10 and pc.get(w, 0) > 0]
            if cand:
                w, k = max(cand, key=lambda wk: wk[1] / tot - pc[wk[0]] / pt)
                out.append(f"Compared with the other {len(peers)} {esc_group(peer_key(p))} on MouthMath, {q(w)} stands out: {per_k(k, tot)} uses per 1,000 words here vs. {per_k(pc[w], pt)} for the rest of the group.")
            gt = [w for w, _ in sorted(pc.items(), key=lambda kv: (-kv[1], kv[0])) if ok(w)][:15]
            low = min(gt, key=lambda w: c.get(w, 0) / tot - pc[w] / pt) if gt else None
            if low and c.get(low, 0) / tot < 0.5 * pc[low] / pt:
                out.append(f"The opposite is {q(low)}, one of the group's most used words, at {per_k(c.get(low, 0), tot)} per 1,000 words here vs. {per_k(pc[low], pt)} for the others.")
        out.append("Counts leave out words like “the” and “and”, and they change as new documents are added.")
        p["wu"] = " ".join(out)

def esc_group(g):
    return {"fed": "Fed Chairs", "Fed Chairs": "Fed Chairs", "ceo": "CEOs", "Presidents": "presidents", "Supreme Court": "justices", "Senate": "senators",
            "House": "House members", "Governors": "governors", "Board of Governors": "Fed governors", "Cabinet": "Cabinet members"}.get(g, "speakers in this group")

# ---- home page: recently added documents ----
LAST_UPDATED = "October 31, 2026"
def recent_html(people, n=6):
    ds = sorted(((d["date"], p, d) for p in people for d in p["docs"]), key=lambda t: t[0], reverse=True)[:n]
    li = "".join(f'<li><a href="speakers/{esc(p["slug"])}.html">{esc(p["name"])}</a>: {esc(d["title"])} <span class="dt">· {fdate(d["date"])}</span></li>' for _, p, d in ds)
    return (f'<h4 class="abcontact" id="recent">Recently added</h4>\n<p class="upd">Last updated: {LAST_UPDATED}</p>\n'
            f'<ul class="abrecent"><li><a href="articles/warsh-oct-2026-fomc.html"><b>New analysis:</b> What Warsh&#8217;s October 28 press conference words show</a> <span class="dt">· October 31, 2026</span></li>{li}</ul>')

# ---- word counts from the packed doc arrays ----
def counts(p, docs=None):
    c, v = Counter(), p["vocab"]
    for d in (docs if docs is not None else p["docs"]):
        x, i = d["x"], 0
        while i < len(x):
            c[v[x[i]]] += x[i + 1]; i += 4 + x[i + 3]
    return c

def top_words(p, stop, n=25):
    c = counts(p)
    return [(w, k) for w, k in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])) if w not in stop and not w.isdigit()][:n]

# ---- page shell built from the privacy page (same black / cream / Arial look) ----
EXTRA_CSS = """

@media (max-width:440px){header{padding:10px 14px}header .in{flex-wrap:nowrap;gap:10px}header .logo img{height:31px}header .back{font-size:12.5px;padding:5px 10px;border:1px solid #3d2c32;border-radius:999px;background:linear-gradient(180deg,#21161a,#120d10);color:#f3eee4;text-decoration:none;box-shadow:0 0 10px rgba(255,84,73,.18)}}
.fhero{position:relative;border:1px solid #3a2830;border-radius:12px;padding:16px 18px 15px;margin:0 0 16px;background:radial-gradient(120% 140% at 100% 0%,rgba(162,75,208,.15) 0%,rgba(255,84,73,.11) 38%,rgba(11,11,11,.98) 76%),#0b0b0b;box-shadow:0 0 24px rgba(255,84,73,.10),0 0 32px rgba(138,111,196,.10)}
.feyebrow{display:inline-flex;align-items:center;gap:7px;font:700 11px/1 Arial,Helvetica,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#ff7a70;background:rgba(255,84,73,.10);border:1px solid rgba(255,84,73,.45);border-radius:999px;padding:5px 10px;margin:0 0 8px;box-shadow:0 0 12px rgba(255,84,73,.18)}
.feyebrow i{display:inline-block;width:7px;height:7px;border-radius:50%;background:#ff5449;box-shadow:0 0 8px #ff5449}
.fhero h1{font-size:27px;line-height:1.14;letter-spacing:-.025em;margin:0 0 7px;color:#f3eee4;text-shadow:0 0 18px rgba(255,84,73,.18)}
.flead{margin:0 0 12px;color:#c8c1b6;font-size:14.5px;line-height:1.48}
.fkpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 12px}
.fkpi{background:#120f11;border:1px solid #2f2529;border-radius:8px;padding:7px 9px;text-align:left}
.fkpi b{display:block;font-size:19px;line-height:1.1;color:#ff5449;letter-spacing:-.02em;text-shadow:0 0 10px rgba(255,84,73,.28)}
.fkpi span{display:block;font-size:11px;line-height:1.2;color:#a49e93;margin-top:2px}
.fnav{display:flex;flex-wrap:wrap;gap:6px;margin:0}
.fnav a{display:inline-flex;align-items:center;gap:5px;padding:6px 11px;border-radius:999px;border:1px solid #43303a;background:linear-gradient(180deg,#21171c,#130e11);color:#f3eee4;text-decoration:none;font:700 12px/1.1 Arial,Helvetica,sans-serif;box-shadow:0 0 10px rgba(138,111,196,.14)}
.fnav a:hover{border-color:#ff5449;color:#fff;box-shadow:0 0 12px rgba(255,84,73,.32),0 0 18px rgba(162,75,208,.22)}
.fnav a em{font-style:normal;color:#ff7a70;font-weight:700;font-size:11px}
.fsec-hd{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap;margin:20px 0 10px;padding-bottom:6px;border-bottom:1px solid #2e2629}
.fsec-hd h2{margin:0;font-size:20px;letter-spacing:-.02em;color:#f3eee4}
.fsec-hd span{font:700 11px/1 Arial,Helvetica,sans-serif;letter-spacing:.07em;text-transform:uppercase;color:#b77ee0}
.fcard{border:1px solid #2f262a;border-radius:11px;padding:14px 15px;margin:0 0 12px;background:linear-gradient(180deg,#0f0c0e 0%,#090809 100%);box-shadow:0 2px 18px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.03);scroll-margin-top:16px}
.fcard:hover{border-color:#4a353e;box-shadow:0 0 18px rgba(255,84,73,.10),0 0 24px rgba(138,111,196,.10)}
.ftop{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 6px}
.fnum{display:inline-flex;align-items:center;justify-content:center;padding:3px 8px;border-radius:999px;background:rgba(255,84,73,.15);border:1px solid rgba(255,84,73,.6);color:#ff5449;font:700 11.5px/1 Arial,Helvetica,sans-serif;letter-spacing:.04em;box-shadow:0 0 8px rgba(255,84,73,.22)}
.ftag{font:700 11px/1.2 Arial,Helvetica,sans-serif;letter-spacing:.06em;text-transform:uppercase;color:#b3a5c2}
.fcard h3{margin:0 0 8px;font-size:17.5px;line-height:1.24;letter-spacing:-.015em;color:#f3eee4}
.fcard p{margin:0 0 9px;color:#ddd7cd;font-size:14.5px;line-height:1.52}
.fcard p:last-child{margin-bottom:0}
.fcard p strong{color:#f3eee4}
.fcard .num{color:#ff5449;font-weight:700}
.fcard .pnum{color:#c79bec;font-weight:700}
.fviz{background:#131012;border:1px solid #2b2227;border-radius:8px;padding:9px 11px;margin:8px 0 10px}
.fviz-ttl{font:700 10.5px/1.2 Arial,Helvetica,sans-serif;letter-spacing:.06em;text-transform:uppercase;color:#a09689;margin:0 0 7px}
.fbrow{display:grid;grid-template-columns:124px minmax(0,1fr) auto;align-items:center;gap:8px;margin:4px 0;font-size:12.5px}
.fbrow .flbl{color:#dfd9cf;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:700}
.fbrow .flbl small{font-weight:400;color:#9a9388;font-size:11px}
.fbtrack{height:8px;background:#1d181b;border-radius:999px;overflow:hidden;border:1px solid #2b2327}
.fbfill{height:100%;border-radius:999px;background:linear-gradient(90deg,#ff5449 0%,#b77ee0 100%);box-shadow:0 0 8px rgba(255,84,73,.35)}
.fbfill.alt{background:linear-gradient(90deg,#8a6fc4 0%,#5f4796 100%);box-shadow:none}
.fbval{color:#f3eee4;font:700 12px/1 Arial,Helvetica,sans-serif;text-align:right;white-space:nowrap}
.fbval em{font-style:normal;color:#ff5449}
.fbval small{font-weight:400;color:#9a9388;font-size:11px}
.fgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:7px;margin:8px 0 10px}
.fstat{background:#141013;border:1px solid #2c2328;border-radius:8px;padding:7px 9px}
.fstat .fsw{font:700 10.5px/1.2 Arial,Helvetica,sans-serif;text-transform:uppercase;letter-spacing:.05em;color:#b3a5c2}
.fstat .fsv{font:700 16px/1.15 Arial,Helvetica,sans-serif;color:#ff5449;margin:3px 0 1px}
.fstat .fss{font-size:11px;color:#9e978c;line-height:1.25}
.flinks{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px;padding-top:8px;border-top:1px dashed #262024}
.flinks a{display:inline-flex;align-items:center;gap:4px;font:700 12px/1 Arial,Helvetica,sans-serif;color:#f3eee4;background:#191316;border:1px solid #3c2c33;border-radius:999px;padding:5px 10px;text-decoration:none}
.flinks a:hover{border-color:#ff5449;color:#ff7a70;box-shadow:0 0 10px rgba(255,84,73,.22)}
.fmethod{border:1px solid #352930;border-left:3px solid #b77ee0;border-radius:10px;padding:14px 16px;margin:22px 0 10px;background:#0d0b0e}
.fmethod h2{margin:0 0 6px;font-size:18px;color:#f3eee4}
.fmethod p{margin:0 0 8px;font-size:14px;color:#ccc5ba;line-height:1.5}
.fmethod p:last-child{margin-bottom:0}
@media (max-width:640px){
  .fhero{padding:12px 12px 11px;margin-bottom:11px}
  .feyebrow{font-size:10px;padding:4px 9px;margin-bottom:6px}
  .fhero h1{font-size:21px;margin-bottom:5px}
  .flead{font-size:13.2px;line-height:1.42;margin-bottom:9px}
  .fkpis{grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin-bottom:9px}
  .fkpi{padding:5px 6px}.fkpi b{font-size:15px}.fkpi span{font-size:10px}
  .fnav{gap:5px}.fnav a{padding:5px 9px;font-size:11.2px}
  .fsec-hd{margin:14px 0 8px;padding-bottom:5px}.fsec-hd h2{font-size:17.5px}
  .fcard{padding:11px 12px;margin-bottom:10px}
  .fcard h3{font-size:15.8px;margin-bottom:6px}
  .fcard p{font-size:13.6px;line-height:1.46;margin-bottom:7px}
  .fbrow{grid-template-columns:98px minmax(0,1fr) auto;gap:6px;font-size:11.5px}
}
table.wt{border-collapse:collapse;width:100%;max-width:520px;margin:8px 0 18px;font-size:15px}
table.wt th,table.wt td{border-bottom:1px solid var(--rule);padding:6px 8px;text-align:left}
table.wt th{color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.05em}
table.wt td.n,table.wt th.n{text-align:right;font-variant-numeric:tabular-nums}
.eyb{color:var(--muted);font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;margin:0 0 4px}
ol.docs{padding-left:22px}ol.docs li{margin:6px 0}ol.docs .dt{color:var(--muted);font-size:14px}
.cta{display:inline-block;margin:6px 0 4px;font-weight:700}
ul.plain{list-style:none;padding:0}ul.plain li{margin:6px 0}
.grp{margin-top:22px}
"""

def shell(privacy, *, title, desc, path, body, current="", prefix=""):
    head, rest = privacy.split("<main>", 1)
    tail = rest.split("</main>", 1)[1]
    url = SITE + path
    head = head.replace("<title>Privacy Policy — MouthMath</title>", f"<title>{html.escape(title)} — MouthMath</title>")
    head = head.replace("https://mouthmath.com/privacy.html", url)
    head = head.replace('content="Privacy Policy — MouthMath"', f'content="{html.escape(title)} — MouthMath"')
    head = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{html.escape(desc)}">', head, 1)
    head = re.sub(r'<meta property="og:description" content="[^"]*">', f'<meta property="og:description" content="{html.escape(desc)}">', head, 1)
    head = re.sub(r'<meta name="twitter:description" content="[^"]*">', f'<meta name="twitter:description" content="{html.escape(desc)}">', head, 1)
    head = head.replace("</style>", EXTRA_CSS + "</style>", 1)
    tail = re.sub(r"<footer>.*?</footer>", lambda m: footer(current), tail, 1, flags=re.S)
    tail = tail.replace("document.getElementById('toTop').onclick", "(document.getElementById('toTop')||{}).onclick")
    page = head + "<main>\n" + body + '\n<p class="abtop"><button type="button" class="totop" id="toTop"><span class="tri" aria-hidden="true">&#9652;</span>Back to top</button></p>\n</main>' + tail
    if prefix:   # pages in sub-folders: point relative links back to the site root
        page = re.sub(r'((?:href|src)=")(?!https?:|#|mailto:|/|data:)([^"]*)"',
                      lambda m: m.group(1) + prefix + (m.group(2) if m.group(2) != "./" else "") + '"', page)
    return page

def esc(s): return html.escape(s, quote=True)

# ---- speaker pages ----
def speaker_page(p, stop, privacy):
    tw = top_words(p, stop)
    rows = "\n".join(f'<tr><td class="n">{i}</td><td>{esc(w)}</td><td class="n">{k:,}</td></tr>' for i, (w, k) in enumerate(tw, 1))
    docs = sorted(p["docs"], key=lambda d: d["date"], reverse=True)
    li = []
    for d in docs:
        t = esc(d["title"])
        link = f'<a href="{esc(d["url"])}">{t}</a>' if d.get("url") else t
        li.append(f'<li>{link} <span class="dt">· {fdate(d["date"])} · {d["words"]:,} words</span></li>')
    total = sum(d["words"] for d in p["docs"])
    body = (f'<p class="eyb">{esc(p.get("eyebrow") or p["role"])}</p>\n<h1>{esc(p["name"])}</h1>\n'
            f'<p class="upd">{esc(p["role"])}</p>\n<p>{esc(p.get("bio", ""))}</p>\n'
            + (f'<h2>What the numbers show</h2>\n<p>{esc(p["wu"])}</p>\n' if p.get("wu") else "") +
            f'<p><a class="cta" href="../#person={esc(p["slug"])}">See every word in MouthMath &rarr;</a></p>\n'
            f'<h2>Top 25 words</h2>\n<p>The most used words across all {len(docs)} {"document" if len(docs)==1 else "documents"} '
            f'({total:,} words in all), leaving out common words such as “the”, “and” and “of”.</p>\n'
            f'<table class="wt"><thead><tr><th class="n">Rank</th><th>Word</th><th class="n">Times said</th></tr></thead>\n<tbody>\n{rows}\n</tbody></table>\n'
            f'<h2>Documents counted</h2>\n<p>Each link opens the original on {esc(p["source"])}.</p>\n<ol class="docs">\n' + "\n".join(li) + "\n</ol>\n"
            + (f'<p class="upd">{esc(p["credit"])}</p>' if p.get("credit") else ""))
    desc = f'{p["name"]}, {p["role"]}: a short profile, the top 25 words and links to the {len(docs)} public documents MouthMath counts.'
    return shell(privacy, title=p["name"], desc=desc, path=f'speakers/{p["slug"]}.html', body=body, prefix="../")

def speakers_index(people, privacy):
    groups = {}
    for p in people:
        g = p.get("group") or {"fed": "Federal Reserve Chairs", "ceo": "CEOs"}.get(p.get("mode"), p["category"])
        groups.setdefault(g, []).append(p)
    out = ['<h1>Speakers</h1>\n<p class="upd">Everyone MouthMath counts, with a short profile and their most used words.</p>']
    for g, ps in groups.items():
        out.append(f'<h2 class="grp">{esc(g)}</h2>\n<ul class="plain">' + "".join(
            f'<li><a href="{esc(p["slug"])}.html">{esc(p["name"])}</a> <span class="dt">· {esc(p["role"])}</span></li>' for p in ps) + "</ul>")
    return shell(privacy, title="Speakers", desc="Every speaker on MouthMath: Federal Reserve Chairs, CEOs and U.S. government officials, with profiles and top words.",
                 path="speakers/", body="\n".join(out), prefix="../")

# ---- terms ----
def md_inline(s):
    s = esc(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)

def terms_page(privacy):
    src = (CONTENT / "terms.md").read_text(encoding="utf-8")   # copy of the parked draft, "Draft, not live" line removed
    out, ul = [], False
    for line in src.splitlines():
        line = line.rstrip()
        if line.startswith("- "):
            if not ul: out.append("<ul>"); ul = True
            out.append(f"<li>{md_inline(line[2:])}</li>"); continue
        if ul: out.append("</ul>"); ul = False
        if not line: continue
        if line.startswith("# "): out.append("<h1>Terms of Use</h1>")
        elif line.startswith("## "): out.append(f"<h2>{md_inline(line[3:])}</h2>")
        elif "Last updated" in line:
            out.append('<p class="upd">Last updated: ' + line.split("Last updated:", 1)[1].strip() + "</p>")
        else:
            out.append(f"<p>{md_inline(line).replace('Contact', '<a href=\"contact.html\">Contact</a>', 1) if 'Contact page' in line else md_inline(line)}</p>")
    if ul: out.append("</ul>")
    return shell(privacy, title="Terms of Use", desc="MouthMath Terms of Use: best-effort word counts, not advice, public sources, acceptable use.",
                 path="terms.html", body="\n".join(out), current="terms.html")

# ---- articles (text in content/articles/*.html, tables filled from the data) ----
ARTICLES = [("how-mouthmath-counts-words", "How MouthMath counts words"),
            ("what-the-fed-chairs-talk-about-most", "What the Fed Chairs talk about most"),
            ("comparing-presidential-vocabulary", "Comparing presidential vocabulary"),
            ("warsh-oct-2026-fomc", "What Kevin Warsh’s October 28 press conference words show")]

def article_page(slug, title, privacy, fill):
    body = (CONTENT / "articles" / f"{slug}.html").read_text(encoding="utf-8")
    for k, v in fill.items():
        body = body.replace("{{" + k + "}}", v)
    desc = re.sub(r"<[^>]+>", "", body.split("</p>", 1)[0].split("<p>", 1)[-1])[:155]
    return shell(privacy, title=title, desc=desc, path=f"articles/{slug}.html",
                 body=f"<h1>{esc(title)}</h1>\n" + body + '\n<p><a href="./">More articles</a> · <a href="../speakers/">All speakers</a></p>', prefix="../")

def articles_index(privacy):
    li = '<li><strong><a href="../findings.html">18 Key Findings from the Transcripts</a></strong> &mdash; concrete word-count patterns across Fed Chairs, US Presidents, and S&amp;P 500 CEOs.</li>' + "".join(f'<li><a href="{s}.html">{esc(t)}</a></li>' for s, t in ARTICLES)
    return shell(privacy, title="Articles", desc="Short articles and data findings about how MouthMath counts words and what the numbers show.",
                 path="articles/", body=f'<h1>Articles &amp; Findings</h1>\n<p class="upd">Short reads on how MouthMath works and what the counts show.</p>\n<ul class="plain">{li}</ul>\n<p><a href="../speakers/">Browse all speakers</a></p>',
                 current="articles/", prefix="../")

def table(rows, heads):
    h = "".join(f'<th{" class=\"n\"" if i else ""}>{x}</th>' for i, x in enumerate(heads))
    b = "".join("<tr>" + "".join(f'<td{" class=\"n\"" if i else ""}>{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<table class="wt"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'

def article_fill(by, stop):
    f = {}
    fed = [s for s in ("volcker", "greenspan", "bernanke", "yellen", "powell", "warsh") if s in by]
    rows = []
    for s in fed:
        p = by[s]; tw = top_words(p, stop, 5)
        rows.append([f'<a href="../speakers/{s}.html">{esc(p["name"])}</a>', str(len(p["docs"])), ", ".join(w for w, _ in tw)])
    f["FED_TABLE"] = table(rows, ["Chair", "Documents", "Top 5 words"])
    pres = [s for s in ("eisenhower", "kennedy", "carter", "reagan", "bush41", "clinton", "bush43", "obama", "trump", "biden") if s in by]
    rows = []
    for s in pres:
        p = by[s]; c = counts(p); tot = sum(c.values()); n = len(p["docs"])
        rows.append([f'<a href="../speakers/{s}.html">{esc(p["name"])}</a>', str(n), f"{tot // n:,}", f"{len(c):,}",
                     ", ".join(w for w, _ in top_words(p, stop, 5))])
    if "warsh" in by:
        p = by["warsh"]; rows = []
        pcs = sorted((d for d in p["docs"] if d["type"] == "press conference"), key=lambda d: d["date"])
        for d in pcs:
            c = counts(p, [d]); tw = [w for w, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])) if w not in stop and not w.isdigit()][:5]
            rows.append([fdate(d["date"]), f'{d["words"]:,}', str(c.get("inflation", 0)), str(c.get("policy", 0)), ", ".join(tw)])
        f["WARSH_PC_TABLE"] = table(rows, ["Press conference", "Words", "“inflation”", "“policy”", "Top 5 words"])
        rows = []
        for w in ("data", "prices", "financial", "colleagues", "productivity", "question", "markets"):
            rows.append([w] + [f'{1000 * counts(p, [d]).get(w, 0) / d["words"]:.1f}' for d in pcs])
        f["WARSH_RATE_TABLE"] = table(rows, ["Word"] + [fdate(d["date"]).rsplit(",", 1)[0] for d in pcs])
    f["PRES_TABLE"] = table(rows, ["President", "Speeches", "Words per speech", "Different words", "Top 5 words"])
    return f

def stats(by, stop):   # printed by build.py so the article text can be checked against the data
    for s, p in by.items():
        if p.get("mode") == "fed" or p.get("group") == "Presidents":
            c = counts(p); tot = sum(c.values())
            print(f"  [stats] {s}: docs {len(p['docs'])} words {tot} unique {len(c)} per-doc {tot // len(p['docs'])} "
                  + ", ".join(f"{w} {k}" for w, k in top_words(p, stop, 15)))


def findings_page(privacy):
    body = """<section class="fhero" aria-label="Overview">
<div class="feyebrow"><i aria-hidden="true"></i>MouthMath Research &middot; 18 Findings</div>
<h1>18 Key Findings from the Transcripts</h1>
<p class="flead">What Federal Reserve Chairs, US Presidents, and S&amp;P 500 CEOs emphasize most&mdash;and what they rarely say&mdash;measured by exact word counts and normalized per 1,000 words across MouthMath&rsquo;s public-transcript corpus.</p>
<div class="fkpis">
<div class="fkpi"><b>18</b><span>Transcript findings</span></div>
<div class="fkpi"><b>89</b><span>Speakers counted</span></div>
<div class="fkpi"><b>40 yrs</b><span>Fed Chair span</span></div>
<div class="fkpi"><b>Per 1k</b><span>Normalized rates</span></div>
</div>
<nav class="fnav" aria-label="Findings categories">
<a href="#fed">Federal Reserve <em>01&ndash;07</em></a>
<a href="#presidents">US Presidents <em>08&ndash;10</em></a>
<a href="#ceos">CEOs <em>11&ndash;15</em></a>
<a href="#warsh">New Fed Chair <em>16&ndash;18</em></a>
<a href="#method">Method</a>
</nav>
</section>

<div class="fsec-hd" id="fed"><h2>I. Federal Reserve</h2><span>Findings 01 &ndash; 07 &middot; Chairs &amp; Governors</span></div>

<article class="fcard" id="f1">
<div class="ftop"><span class="fnum">#01</span><span class="ftag">Federal Reserve Chair &middot; Jerome Powell (Aug 2024 &ndash; Mar 2026)</span></div>
<h3>Powell&rsquo;s &ldquo;inflation&rdquo; peaked in his big framework speeches, then faded as his term wound down</h3>
<div class="fviz">
<div class="fviz-ttl">&ldquo;inflation&rdquo; frequency across landmark Powell speeches (260 total mentions in 20 docs)</div>
<div class="fbrow"><span class="flbl">Aug 23, 2024 <small>JH</small></span><div class="fbtrack"><div class="fbfill" style="width:100%"></div></div><span class="fbval"><em>23.4</em>/1k <small>(54 / 2,312w)</small></span></div>
<div class="fbrow"><span class="flbl">Aug 22, 2025 <small>JH</small></span><div class="fbtrack"><div class="fbfill" style="width:72%"></div></div><span class="fbval"><em>16.9</em>/1k <small>(54 / 3,199w)</small></span></div>
<div class="fbrow"><span class="flbl">Oct 14, 2025 <small>Bal.</small></span><div class="fbtrack"><div class="fbfill alt" style="width:12%"></div></div><span class="fbval">2.7/1k <small>(7 / 2,554w)</small></span></div>
<div class="fbrow"><span class="flbl">Jan&ndash;Mar 2026 <small>End</small></span><div class="fbtrack"><div class="fbfill alt" style="width:5%"></div></div><span class="fbval">0 &amp; 4 <small>mentions</small></span></div>
</div>
<p>Across Jerome Powell&rsquo;s 20 indexed documents (<span class="num">22,557 total words</span> from August 2024 to March 2026), <strong>&ldquo;inflation&rdquo;</strong> is his #1 content word at <span class="num">260 mentions</span> (<span class="num">11.53 per 1,000 words</span>). Nearly half of those uses fall in two annual Jackson Hole policy addresses: his August 23, 2024 <em>&ldquo;Review and Outlook&rdquo;</em> speech (<span class="num">54 uses</span> in 2,312 words, or ~23 per 1,000) and his August 22, 2025 framework review speech (<span class="num">54 uses</span> in 3,199 words, or ~17 per 1,000).</p>
<p>By his October 14, 2025 speech <em>&ldquo;Understanding the Fed&rsquo;s Balance Sheet,&rdquo;</em> <strong>&ldquo;inflation&rdquo;</strong> drops to <span class="pnum">7 mentions</span> in 2,554 words (~2.7 per 1,000), and his final two indexed documents&mdash;a brief January 11, 2026 statement and March 21, 2026 award remarks&mdash;contain <span class="pnum">0</span> and <span class="pnum">4 mentions</span>.</p>
<div class="flinks"><a href="./#person=powell&amp;docs=all">Explore Jerome Powell &rarr;</a></div>
</article>

<article class="fcard" id="f2">
<div class="ftop"><span class="fnum">#02</span><span class="ftag">Federal Reserve Chair &middot; Trade &amp; Policy Shifts</span></div>
<h3>&ldquo;Tariff&rdquo; entered Powell&rsquo;s vocabulary in spring 2025</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">All 2024 Speeches</div><div class="fsv">0</div><div class="fss">&ldquo;tariff&rdquo; or &ldquo;tariffs&rdquo; mentions</div></div>
<div class="fstat"><div class="fsw">Mar 7, 2025</div><div class="fsv">1</div><div class="fss">First mention in sample</div></div>
<div class="fstat"><div class="fsw">Apr &ndash; Jun 2025</div><div class="fsv">5 &middot; 4 &middot; 5</div><div class="fss">Apr 4, Apr 16 &amp; Jun 24 testimony</div></div>
<div class="fstat"><div class="fsw">Aug &ndash; Sep 2025</div><div class="fsv">6 &middot; 4</div><div class="fss">Aug 22 Jackson Hole &amp; Sep 23</div></div>
</div>
<p>In all of Jerome Powell&rsquo;s 2024 speeches on MouthMath, <strong>&ldquo;tariff&rdquo;</strong> and <strong>&ldquo;tariffs&rdquo;</strong> appear <span class="num">0 times</span>. The word enters his remarks on <strong>March 7, 2025</strong> (<span class="num">1 mention</span>), then becomes a regular fixture across spring and summer 2025: <span class="num">5 mentions</span> on April 4, 2025, <span class="num">4</span> on April 16, 2025, <span class="num">5</span> in his June 24, 2025 semiannual testimony to Congress, <span class="num">6</span> on August 22, 2025, and <span class="num">4</span> on September 23, 2025.</p>
<div class="flinks"><a href="./#person=powell&amp;docs=all">Jerome Powell Word Table &rarr;</a></div>
</article>

<article class="fcard" id="f3">
<div class="ftop"><span class="fnum">#03</span><span class="ftag">Federal Reserve Chairs &middot; Five-Chair Historical Comparison</span></div>
<h3>From Volcker to Powell, each Fed Chair in our sample said &ldquo;inflation&rdquo; more often than the one before&mdash;then Warsh broke the streak</h3>
<div class="fviz">
<div class="fviz-ttl">&ldquo;inflation&rdquo; mentions per 1,000 total words across six Fed Chairs</div>
<div class="fbrow"><span class="flbl">Warsh <small>2026</small></span><div class="fbtrack"><div class="fbfill alt" style="width:44%"></div></div><span class="fbval"><em>5.11</em>/1k <small>(119 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Powell <small>2024&ndash;26</small></span><div class="fbtrack"><div class="fbfill" style="width:100%"></div></div><span class="fbval"><em>11.53</em>/1k <small>(260 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Yellen <small>2016&ndash;17</small></span><div class="fbtrack"><div class="fbfill" style="width:51%"></div></div><span class="fbval"><em>5.84</em>/1k <small>(282 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Bernanke <small>2013&ndash;14</small></span><div class="fbtrack"><div class="fbfill alt" style="width:24%"></div></div><span class="fbval">2.71/1k <small>(131 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Greenspan <small>2005</small></span><div class="fbtrack"><div class="fbfill alt" style="width:12%"></div></div><span class="fbval">1.37/1k <small>(60 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Volcker <small>1986&ndash;87</small></span><div class="fbtrack"><div class="fbfill alt" style="width:8%"></div></div><span class="fbval">0.96/1k <small>(70 uses)</small></span></div>
</div>
<p>Measured per 1,000 total words, <strong>&ldquo;inflation&rdquo;</strong> rises in every consecutive Chair&rsquo;s corpus: <strong>Paul Volcker</strong> at <span class="pnum">0.96</span> (<span class="pnum">70 uses</span> in 1986&ndash;87), <strong>Alan Greenspan</strong> at <span class="pnum">1.37</span> (<span class="pnum">60 uses</span> in 2005), <strong>Ben Bernanke</strong> at <span class="pnum">2.71</span> (<span class="pnum">131 uses</span> in 2013&ndash;14), <strong>Janet Yellen</strong> at <span class="num">5.84</span> (<span class="num">282 uses</span> in 2016&ndash;17), and <strong>Jerome Powell</strong> at <span class="num">11.53</span> (<span class="num">260 uses</span> in 2024&ndash;26). <strong>Kevin Warsh</strong> breaks that run at <span class="num">5.11</span> (<span class="num">119 uses</span> in 23,297 words, June&ndash;October 2026)&mdash;see <a href="#f16">Finding #16</a>.</p>
<p>While each Chair&rsquo;s 20-speech sample captures the economic backdrop near the end of their tenure, the steady climb from Volcker through Powell also aligns with the institutional shift toward explicit inflation targeting and modern &ldquo;forward guidance,&rdquo; where public communication is itself part of monetary policy. These are sample-level word counts, not a full record of each Chair&rsquo;s remarks, and Warsh&rsquo;s sample so far is only six documents, mostly press conferences.</p>
<div class="flinks">
<a href="./#person=warsh&amp;docs=all">Warsh &rarr;</a>
<a href="./#person=powell&amp;docs=all">Powell &rarr;</a>
<a href="./#person=yellen&amp;docs=all">Yellen &rarr;</a>
<a href="./#person=bernanke&amp;docs=all">Bernanke &rarr;</a>
<a href="./#person=greenspan&amp;docs=all">Greenspan &rarr;</a>
<a href="./#person=volcker&amp;docs=all">Volcker &rarr;</a>
</div>
</article>

<article class="fcard" id="f4">
<div class="ftop"><span class="fnum">#04</span><span class="ftag">Federal Reserve Chairs &middot; 1980s vs. 2020s Policy Vocabulary</span></div>
<h3>Volcker talked about banks and deficits, not inflation</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">Volcker &ldquo;banks&rdquo;</div><div class="fsv">3.00 / 1k</div><div class="fss">Over 3&times; his &ldquo;inflation&rdquo; rate</div></div>
<div class="fstat"><div class="fsw">Volcker &ldquo;deficit&rdquo;</div><div class="fsv">1.61 / 1k</div><div class="fss">1986&ndash;87 fiscal &amp; trade focus</div></div>
<div class="fstat"><div class="fsw">Volcker &ldquo;inflation&rdquo;</div><div class="fsv">0.96 / 1k</div><div class="fss">Post-disinflation late tenure</div></div>
<div class="fstat"><div class="fsw">Powell &ldquo;deficit&rdquo;</div><div class="fsv">0.00 / 1k</div><div class="fss">Modern Fed avoids fiscal commentary</div></div>
</div>
<p>Paul Volcker is remembered for breaking the high inflation of the late 1970s and early 1980s, but by his 1986&ndash;87 speeches on MouthMath, inflation had been subdued and banking stability and fiscal deficits led his agenda. Volcker said <strong>&ldquo;banks&rdquo;</strong> <span class="num">3.00 times per 1,000 words</span> and <strong>&ldquo;deficit&rdquo;</strong> <span class="num">1.61 times per 1,000 words</span>, compared with <span class="pnum">0.96</span> for <strong>&ldquo;inflation.&rdquo;</strong></p>
<p>Jerome Powell&rsquo;s 2024&ndash;26 corpus shows the opposite pattern: <strong>&ldquo;deficit&rdquo;</strong> appears at <span class="pnum">0.00 per 1,000 words</span>, reflecting how strictly modern Fed Chairs avoid commenting on fiscal budget policy.</p>
<div class="flinks"><a href="./#person=volcker&amp;docs=all">Explore Paul Volcker &rarr;</a><a href="./#person=powell&amp;docs=all">Explore Jerome Powell &rarr;</a></div>
</article>

<article class="fcard" id="f5">
<div class="ftop"><span class="fnum">#05</span><span class="ftag">Federal Reserve Board &middot; Governors vs. Chairs</span></div>
<h3>AI has taken over Fed governors&rsquo; speeches&mdash;and Warsh is the first Chair in our sample to say it</h3>
<div class="fviz">
<div class="fviz-ttl">&ldquo;ai&rdquo; mentions per 1,000 words across Federal Reserve officials</div>
<div class="fbrow"><span class="flbl">Michael Barr</span><div class="fbtrack"><div class="fbfill" style="width:100%"></div></div><span class="fbval"><em>6.84</em>/1k <small>(300 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Lisa Cook</span><div class="fbtrack"><div class="fbfill" style="width:94%"></div></div><span class="fbval"><em>6.42</em>/1k <small>(280 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Christopher Waller</span><div class="fbtrack"><div class="fbfill alt" style="width:57%"></div></div><span class="fbval">3.92/1k <small>(167 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Philip Jefferson</span><div class="fbtrack"><div class="fbfill alt" style="width:43%"></div></div><span class="fbval">2.95/1k <small>(128 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Michelle Bowman</span><div class="fbtrack"><div class="fbfill alt" style="width:37%"></div></div><span class="fbval">2.54/1k <small>(87 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Kevin Warsh</span><div class="fbtrack"><div class="fbfill alt" style="width:15%"></div></div><span class="fbval">1.03/1k <small>(24 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Jerome Powell</span><div class="fbtrack"><div class="fbfill alt" style="width:1%"></div></div><span class="fbval">0.00/1k <small>(0 uses)</small></span></div>
</div>
<p>Artificial intelligence has become a central research and policy theme for Federal Reserve governors: <strong>Michael Barr</strong> leads at <span class="num">6.84 mentions of &ldquo;ai&rdquo; per 1,000 words</span> (<span class="num">300 total uses</span>, including single-speech peaks of <span class="num">99</span> on February 17, 2026 and <span class="num">85</span> on July 14, 2026), followed by <strong>Lisa Cook</strong> at <span class="num">6.42 per 1,000</span> (<span class="num">280 uses</span>, with peaks of <span class="num">66</span> on July 17, 2025 and <span class="num">71</span> on May 27, 2026), <strong>Christopher Waller</strong> (<span class="pnum">3.92</span>, 167 uses), <strong>Philip Jefferson</strong> (<span class="pnum">2.95</span>, 128 uses), and <strong>Michelle Bowman</strong> (<span class="pnum">2.54</span>, 87 uses).</p>
<p>Across Jerome Powell&rsquo;s 20 indexed documents, <strong>&ldquo;ai&rdquo;</strong> appears <span class="num">0.00 times per 1,000 words</span>, as it does for Yellen, Bernanke, Greenspan, and Volcker. <strong>Kevin Warsh</strong> changes that: <span class="num">24 uses</span> across his first six documents (<span class="pnum">1.03 per 1,000</span>)&mdash;still well below the governors&rsquo; rates (see <a href="#f17">Finding #17</a>).</p>
<div class="flinks">
<a href="./#person=barr&amp;docs=all">Barr &rarr;</a>
<a href="./#person=lisacook&amp;docs=all">Cook &rarr;</a>
<a href="./#person=waller&amp;docs=all">Waller &rarr;</a>
<a href="./#person=jefferson&amp;docs=all">Jefferson &rarr;</a>
<a href="./#person=bowman&amp;docs=all">Bowman &rarr;</a>
<a href="./#person=warsh&amp;docs=all">Warsh &rarr;</a>
</div>
</article>

<article class="fcard" id="f6">
<div class="ftop"><span class="fnum">#06</span><span class="ftag">Federal Reserve Supervision &middot; Michelle Bowman</span></div>
<h3>Bowman is the &ldquo;banks and risk&rdquo; governor</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">Bowman &ldquo;banks&rdquo;</div><div class="fsv">8.02 / 1k</div><div class="fss">275 uses in 34,306 words</div></div>
<div class="fstat"><div class="fsw">Bowman &ldquo;risk&rdquo;</div><div class="fsv">5.95 / 1k</div><div class="fss">vs. 0.58 / 1k for Powell</div></div>
<div class="fstat"><div class="fsw">Other Govs &ldquo;banks&rdquo;</div><div class="fsv">1.5 &ndash; 3.1 / 1k</div><div class="fss">Waller, Barr &amp; Jefferson range</div></div>
<div class="fstat"><div class="fsw">Bowman &ldquo;inflation&rdquo;</div><div class="fsv">2.04 / 1k</div><div class="fss">Less than one-fifth of Powell (11.53)</div></div>
</div>
<p><strong>Michelle Bowman</strong> uses <strong>&ldquo;banks&rdquo;</strong> at <span class="num">8.02 per 1,000 words</span> (<span class="num">275 uses</span> across 34,306 words) and <strong>&ldquo;risk&rdquo;</strong> at <span class="num">5.95 per 1,000 words</span>&mdash;well ahead of Waller, Barr, and Jefferson on <strong>&ldquo;banks&rdquo;</strong> (<span class="pnum">1.5 to 3.1 per 1,000</span>) and more than ten times Powell&rsquo;s rate on <strong>&ldquo;risk&rdquo;</strong> (<span class="pnum">0.58 per 1,000</span>). Meanwhile, her <strong>&ldquo;inflation&rdquo;</strong> rate (<span class="pnum">2.04 per 1,000</span>) is less than a fifth of Powell&rsquo;s (<span class="num">11.53</span>), matching her bank-supervision role.</p>
<div class="flinks"><a href="./#person=bowman&amp;docs=all">Explore Michelle Bowman &rarr;</a></div>
</article>

<article class="fcard" id="f7">
<div class="ftop"><span class="fnum">#07</span><span class="ftag">Federal Reserve Payments &amp; Digital Assets &middot; Barr &amp; Waller</span></div>
<h3>Stablecoins are almost entirely a Barr and Waller topic</h3>
<p>Combined mentions of <strong>&ldquo;stablecoin&rdquo;</strong> and <strong>&ldquo;stablecoins&rdquo;</strong> reach <span class="num">1.78 per 1,000 words</span> for <strong>Michael Barr</strong> (<span class="pnum">0.64</span> singular + <span class="pnum">1.14</span> plural) and <span class="num">0.59 per 1,000 words</span> for <strong>Christopher Waller</strong> (<span class="pnum">0.14</span> + <span class="pnum">0.45</span>). Across the rest of the Board, <strong>Jerome Powell</strong>, <strong>Lisa Cook</strong>, and <strong>Philip Jefferson</strong> are at <span class="num">0.00</span>, while <strong>Michelle Bowman</strong> is at <span class="pnum">0.06 per 1,000 words</span>.</p>
<div class="flinks"><a href="./#person=barr&amp;docs=all">Michael Barr &rarr;</a><a href="./#person=waller&amp;docs=all">Christopher Waller &rarr;</a></div>
</article>

<div class="fsec-hd" id="presidents"><h2>II. US Presidents</h2><span>Findings 08 &ndash; 10 &middot; Carter through Biden (~20 Speeches Each)</span></div>

<article class="fcard" id="f8">
<div class="ftop"><span class="fnum">#08</span><span class="ftag">US Presidents &middot; Signature Vocabulary (1977 &ndash; 2025)</span></div>
<h3>Presidents of both parties each have a signature word</h3>
<div class="fviz">
<div class="fviz-ttl">Highest-rate signature words among all 8 indexed US Presidents (per 1,000 words)</div>
<div class="fbrow"><span class="flbl">Clinton (D) <small>&ldquo;people&rdquo;</small></span><div class="fbtrack"><div class="fbfill" style="width:100%"></div></div><span class="fbval"><em>5.78</em>/1k <small>(458 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Bush 43 (R) <small>&ldquo;america&rdquo;</small></span><div class="fbtrack"><div class="fbfill" style="width:90%"></div></div><span class="fbval"><em>5.19</em>/1k <small>(#1 of 8)</small></span></div>
<div class="fbrow"><span class="flbl">Bush 41 (R) <small>&ldquo;world&rdquo;</small></span><div class="fbtrack"><div class="fbfill" style="width:81%"></div></div><span class="fbval"><em>4.66</em>/1k <small>(#1 of 8)</small></span></div>
<div class="fbrow"><span class="flbl">Carter (D) <small>&ldquo;energy&rdquo;</small></span><div class="fbtrack"><div class="fbfill alt" style="width:66%"></div></div><span class="fbval">3.82/1k <small>(200 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Reagan (R) <small>&ldquo;tax&rdquo;</small></span><div class="fbtrack"><div class="fbfill alt" style="width:61%"></div></div><span class="fbval">3.52/1k <small>(255 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Trump (R) <small>&ldquo;great&rdquo;</small></span><div class="fbtrack"><div class="fbfill alt" style="width:53%"></div></div><span class="fbval">3.08/1k <small>(272 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Obama (D) <small>&ldquo;jobs&rdquo;</small></span><div class="fbtrack"><div class="fbfill alt" style="width:44%"></div></div><span class="fbval">2.57/1k <small>(232 uses)</small></span></div>
<div class="fbrow"><span class="flbl">Biden (D) <small>&ldquo;democracy&rdquo;</small></span><div class="fbtrack"><div class="fbfill alt" style="width:23%"></div></div><span class="fbval">1.35/1k <small>(91 uses)</small></span></div>
</div>
<p>Comparing roughly 20 major speeches per president (~52,000 to 90,000 words each), every president from Jimmy Carter to Joe Biden leads all eight presidents in at least one defining word per 1,000 words:</p>
<ul>
<li><strong>Jimmy Carter (D):</strong> <strong>&ldquo;energy&rdquo;</strong> at <span class="num">3.82 per 1,000</span> (<span class="num">200 uses</span>, highest of all 8) and <strong>&ldquo;soviet&rdquo;</strong> at <span class="pnum">2.67</span> (<span class="pnum">140 uses</span>).</li>
<li><strong>Ronald Reagan (R):</strong> <strong>&ldquo;tax&rdquo;</strong> at <span class="num">3.52 per 1,000</span> (<span class="num">255 uses</span>, highest of all 8) and <strong>&ldquo;freedom&rdquo;</strong> at <span class="pnum">2.11</span> (<span class="pnum">153 uses</span>).</li>
<li><strong>George H. W. Bush (R):</strong> <strong>&ldquo;world&rdquo;</strong> at <span class="num">4.66 per 1,000</span> (highest of all 8) and <strong>&ldquo;war&rdquo;</strong> at <span class="pnum">1.77</span>.</li>
<li><strong>Bill Clinton (D):</strong> <strong>&ldquo;people&rdquo;</strong> at <span class="num">5.78 per 1,000</span> (<span class="num">458 uses</span>, highest of all 8).</li>
<li><strong>George W. Bush (R):</strong> <strong>&ldquo;america&rdquo;</strong> at <span class="num">5.19 per 1,000</span> (highest of all 8), <strong>&ldquo;freedom&rdquo;</strong> at <span class="pnum">2.35</span> (<span class="pnum">147 uses</span>), and <strong>&ldquo;terrorists&rdquo;</strong> at <span class="pnum">1.93</span> (<span class="pnum">121 uses</span>).</li>
<li><strong>Barack Obama (D):</strong> <strong>&ldquo;jobs&rdquo;</strong> at <span class="num">2.57 per 1,000</span> (<span class="num">232 uses</span>, highest of all 8).</li>
<li><strong>Donald Trump (R):</strong> <strong>&ldquo;great&rdquo;</strong> at <span class="num">3.08 per 1,000</span> (<span class="num">272 uses</span>) and <strong>&ldquo;tremendous&rdquo;</strong> at <span class="pnum">0.37</span> (<span class="pnum">33 uses</span>)&mdash;both highest of all 8.</li>
<li><strong>Joe Biden (D):</strong> <strong>&ldquo;democracy&rdquo;</strong> at <span class="num">1.35 per 1,000</span> (<span class="num">91 uses</span>) and <strong>&ldquo;folks&rdquo;</strong> at <span class="pnum">0.99</span> (<span class="pnum">67 uses</span>)&mdash;both highest of all 8.</li>
</ul>
<div class="flinks">
<a href="./#person=trump&amp;docs=all">Trump &rarr;</a>
<a href="./#person=biden&amp;docs=all">Biden &rarr;</a>
<a href="./#person=obama&amp;docs=all">Obama &rarr;</a>
<a href="./#person=bush43&amp;docs=all">Bush 43 &rarr;</a>
<a href="./#person=clinton&amp;docs=all">Clinton &rarr;</a>
<a href="./#person=bush41&amp;docs=all">Bush 41 &rarr;</a>
<a href="./#person=reagan&amp;docs=all">Reagan &rarr;</a>
<a href="./#person=carter&amp;docs=all">Carter &rarr;</a>
</div>
</article>

<article class="fcard" id="f9">
<div class="ftop"><span class="fnum">#09</span><span class="ftag">US Presidents &middot; Pronoun Frequency (Stopwords Included)</span></div>
<h3>Presidential &ldquo;I&rdquo; versus &ldquo;we&rdquo; cuts across party lines</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">Biden &ldquo;I&rdquo;</div><div class="fsv">11.63 / 1k</div><div class="fss">Highest &ldquo;I&rdquo; rate in sample</div></div>
<div class="fstat"><div class="fsw">Clinton &ldquo;I&rdquo; &amp; &ldquo;we&rdquo;</div><div class="fsv">11.26 &middot; 20.74</div><div class="fss">#2 on &ldquo;I&rdquo;, #1 on &ldquo;we&rdquo; per 1k</div></div>
<div class="fstat"><div class="fsw">Trump &ldquo;I&rdquo;</div><div class="fsv">10.39 / 1k</div><div class="fss">Close behind Biden &amp; Clinton</div></div>
<div class="fstat"><div class="fsw">Bush 43 &ldquo;I&rdquo;</div><div class="fsv">6.64 / 1k</div><div class="fss">Lowest &ldquo;I&rdquo; rate of all 8</div></div>
</div>
<p>When common stopwords are included, every president in the sample uses <strong>&ldquo;we&rdquo;</strong> more often than <strong>&ldquo;I,&rdquo;</strong> and the variation cuts across party lines. Per 1,000 words, <strong>Joe Biden</strong> (<span class="num">11.63</span>) and <strong>Bill Clinton</strong> (<span class="num">11.26</span>) use <strong>&ldquo;I&rdquo;</strong> most frequently, with <strong>Donald Trump</strong> close behind at <span class="num">10.39</span>, while <strong>George W. Bush</strong> is lowest at <span class="pnum">6.64</span>. First-person plural <strong>&ldquo;we&rdquo;</strong> ranges from <span class="pnum">15.57 per 1,000</span> (<strong>George H. W. Bush</strong>) to <span class="num">20.74 per 1,000</span> (<strong>Bill Clinton</strong>).</p>
<div class="flinks"><a href="./#person=biden&amp;docs=all">Biden &rarr;</a><a href="./#person=clinton&amp;docs=all">Clinton &rarr;</a><a href="./#person=trump&amp;docs=all">Trump &rarr;</a><a href="./#person=bush43&amp;docs=all">Bush 43 &rarr;</a></div>
</article>

<article class="fcard" id="f10">
<div class="ftop"><span class="fnum">#10</span><span class="ftag">US Presidents &middot; Geopolitical Shifts</span></div>
<h3>The Cold War disappears from presidential language as &ldquo;China&rdquo; rises</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">Carter &ldquo;soviet&rdquo;</div><div class="fsv">2.67 / 1k</div><div class="fss">Bush 41: 1.18 &middot; Reagan: 1.05</div></div>
<div class="fstat"><div class="fsw">Post-1991 &ldquo;soviet&rdquo;</div><div class="fsv">0.01 &ndash; 0.05</div><div class="fss">Clinton (0.05) through Biden</div></div>
<div class="fstat"><div class="fsw">Reagan &ldquo;china&rdquo;</div><div class="fsv">0.03 / 1k</div><div class="fss">Cold War-era baseline</div></div>
<div class="fstat"><div class="fsw">Trump &amp; Biden &ldquo;china&rdquo;</div><div class="fsv">0.57 &middot; 0.47</div><div class="fss">Nearly 20&times; Reagan&rsquo;s rate</div></div>
</div>
<p>Mentions of <strong>&ldquo;soviet&rdquo;</strong> per 1,000 words track the end of the Cold War almost to the year: <strong>Jimmy Carter</strong> (<span class="num">2.67</span>), <strong>George H. W. Bush</strong> (<span class="num">1.18</span>), and <strong>Ronald Reagan</strong> (<span class="num">1.05</span>) drop to <span class="pnum">0.05</span> under <strong>Bill Clinton</strong> and <span class="pnum">0.01&ndash;0.02</span> for every president thereafter. Meanwhile, <strong>&ldquo;china&rdquo;</strong> climbs from <span class="pnum">0.03 per 1,000</span> under Reagan to <span class="num">0.57</span> under <strong>Donald Trump</strong> and <span class="num">0.47</span> under <strong>Joe Biden</strong>.</p>
<div class="flinks"><a href="./#person=carter&amp;docs=all">Carter &rarr;</a><a href="./#person=reagan&amp;docs=all">Reagan &rarr;</a><a href="./#person=trump&amp;docs=all">Trump &rarr;</a><a href="./#person=biden&amp;docs=all">Biden &rarr;</a></div>
</article>

<div class="fsec-hd" id="ceos"><h2>III. Chief Executive Officers</h2><span>Findings 11 &ndash; 15 &middot; Shareholder Letters &amp; Earnings Calls</span></div>

<article class="fcard" id="f11">
<div class="ftop"><span class="fnum">#11</span><span class="ftag">S&amp;P 500 CEOs &middot; Tech vs. Traditional Industry</span></div>
<h3>AI dominates tech CEOs&rsquo; remarks, with old-economy CEOs as the exceptions</h3>
<div class="fviz">
<div class="fviz-ttl">&ldquo;ai&rdquo; mentions per 1,000 words in CEO prepared remarks &amp; letters</div>
<div class="fbrow"><span class="flbl">Chuck Robbins <small>Cisco</small></span><div class="fbtrack"><div class="fbfill" style="width:100%"></div></div><span class="fbval"><em>14.19</em>/1k</span></div>
<div class="fbrow"><span class="flbl">Cristiano Amon <small>QCOM</small></span><div class="fbtrack"><div class="fbfill" style="width:98%"></div></div><span class="fbval"><em>13.88</em>/1k</span></div>
<div class="fbrow"><span class="flbl">Sundar Pichai <small>GOOGL</small></span><div class="fbtrack"><div class="fbfill" style="width:94%"></div></div><span class="fbval"><em>13.40</em>/1k</span></div>
<div class="fbrow"><span class="flbl">Lisa Su <small>AMD</small></span><div class="fbtrack"><div class="fbfill" style="width:85%"></div></div><span class="fbval"><em>12.03</em>/1k</span></div>
<div class="fbrow"><span class="flbl">Mark Zuckerberg <small>META</small></span><div class="fbtrack"><div class="fbfill alt" style="width:55%"></div></div><span class="fbval">7.85/1k</span></div>
<div class="fbrow"><span class="flbl">Satya Nadella <small>MSFT</small></span><div class="fbtrack"><div class="fbfill alt" style="width:55%"></div></div><span class="fbval">7.78/1k</span></div>
<div class="fbrow"><span class="flbl">Abel / Ortberg <small>BRK / BA</small></span><div class="fbtrack"><div class="fbfill alt" style="width:1%"></div></div><span class="fbval">0.00/1k</span></div>
</div>
<p>Among networking, chip, and cloud CEOs, more than one in every hundred words is <strong>&ldquo;ai&rdquo;</strong>: <strong>Chuck Robbins</strong> (Cisco) leads at <span class="num">14.19 per 1,000 words</span>, followed by <strong>Cristiano Amon</strong> (Qualcomm, <span class="num">13.88</span>), <strong>Sundar Pichai</strong> (Alphabet, <span class="num">13.40</span>), <strong>Lisa Su</strong> (AMD, <span class="num">12.03</span>), <strong>Mark Zuckerberg</strong> (Meta, <span class="pnum">7.85</span>), and <strong>Satya Nadella</strong> (Microsoft, <span class="pnum">7.78</span>).</p>
<p>At the other end of the S&amp;P 500, <strong>Greg Abel</strong> (Berkshire Hathaway&rsquo;s February 28, 2026 letter) and <strong>Kelly Ortberg</strong> (Boeing) use <strong>&ldquo;ai&rdquo;</strong> <span class="num">0 times</span>, while <strong>Brian Niccol</strong> (Starbucks, <span class="pnum">0.50</span>) and <strong>Joaquin Duato</strong> (Johnson &amp; Johnson, <span class="pnum">0.74</span>) mention it less than once per 1,000 words.</p>
<div class="flinks">
<a href="./#person=robbins&amp;docs=all">Robbins &rarr;</a>
<a href="./#person=amon&amp;docs=all">Amon &rarr;</a>
<a href="./#person=pichai&amp;docs=all">Pichai &rarr;</a>
<a href="./#person=su&amp;docs=all">Su &rarr;</a>
<a href="./#person=zuckerberg&amp;docs=all">Zuckerberg &rarr;</a>
<a href="./#person=nadella&amp;docs=all">Nadella &rarr;</a>
</div>
</article>

<article class="fcard" id="f12">
<div class="ftop"><span class="fnum">#12</span><span class="ftag">S&amp;P 500 CEOs &middot; Customer Focus vs. AI</span></div>
<h3>&ldquo;Customers&rdquo; versus &ldquo;AI&rdquo;: who talks about whom</h3>
<div class="fviz">
<div class="fviz-ttl">Top CEOs by &ldquo;customers&rdquo; mentions per 1,000 words</div>
<div class="fbrow"><span class="flbl">John Furner <small>Walmart</small></span><div class="fbtrack"><div class="fbfill" style="width:100%"></div></div><span class="fbval"><em>7.80</em>/1k</span></div>
<div class="fbrow"><span class="flbl">Marc Benioff <small>CRM</small></span><div class="fbtrack"><div class="fbfill" style="width:93%"></div></div><span class="fbval"><em>7.23</em>/1k</span></div>
<div class="fbrow"><span class="flbl">Chuck Robbins <small>Cisco</small></span><div class="fbtrack"><div class="fbfill" style="width:91%"></div></div><span class="fbval"><em>7.10</em>/1k</span></div>
<div class="fbrow"><span class="flbl">John Stankey <small>AT&amp;T</small></span><div class="fbtrack"><div class="fbfill alt" style="width:80%"></div></div><span class="fbval">6.27/1k</span></div>
<div class="fbrow"><span class="flbl">Brian Niccol <small>SBUX</small></span><div class="fbtrack"><div class="fbfill alt" style="width:77%"></div></div><span class="fbval">6.01/1k</span></div>
<div class="fbrow"><span class="flbl">Andy Jassy <small>Amazon</small></span><div class="fbtrack"><div class="fbfill alt" style="width:65%"></div></div><span class="fbval">5.06/1k</span></div>
</div>
<p><strong>&ldquo;Customers&rdquo;</strong> per 1,000 words is led by <strong>John Furner</strong> (Walmart, <span class="num">7.80</span>), <strong>Marc Benioff</strong> (Salesforce, <span class="num">7.23</span>), <strong>Chuck Robbins</strong> (Cisco, <span class="num">7.10</span>), <strong>John Stankey</strong> (AT&amp;T, <span class="pnum">6.27</span>), <strong>Brian Niccol</strong> (Starbucks, <span class="pnum">6.01</span>), and <strong>Andy Jassy</strong> (Amazon, <span class="pnum">5.06</span>). In Jassy&rsquo;s shareholder letter, <strong>&ldquo;customers&rdquo;</strong> (<span class="num">13 mentions</span>) and <strong>&ldquo;customer&rdquo;</strong> (<span class="num">8 mentions</span>) still outrank <strong>&ldquo;ai&rdquo;</strong> (<span class="pnum">7 mentions</span>).</p>
<div class="flinks">
<a href="./#person=furner&amp;docs=all">Furner &rarr;</a>
<a href="./#person=benioff&amp;docs=all">Benioff &rarr;</a>
<a href="./#person=jassy&amp;docs=all">Jassy &rarr;</a>
<a href="./#person=niccol&amp;docs=all">Niccol &rarr;</a>
</div>
</article>

<article class="fcard" id="f13">
<div class="ftop"><span class="fnum">#13</span><span class="ftag">Berkshire Hathaway &middot; Greg Abel (Feb 28, 2026 Letter)</span></div>
<h3>Abel&rsquo;s first Berkshire letter centers on the company, not himself</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">&ldquo;berkshire&rdquo;</div><div class="fsv">17 uses</div><div class="fss">#1 content word (1,730w letter)</div></div>
<div class="fstat"><div class="fsw">&ldquo;businesses&rdquo; &amp; &ldquo;operating&rdquo;</div><div class="fsv">10 &middot; 9</div><div class="fss">Core operating focus</div></div>
<div class="fstat"><div class="fsw">&ldquo;insurance&rdquo; &amp; &ldquo;operations&rdquo;</div><div class="fsv">7 &middot; 7</div><div class="fss">Followed by &ldquo;capital&rdquo; (6)</div></div>
<div class="fstat"><div class="fsw">&ldquo;warren&rdquo; vs. &ldquo;ai&rdquo;</div><div class="fsv">4 vs. 0</div><div class="fss">4 nods to Buffett; 0 mentions of AI</div></div>
</div>
<p>In <strong>Greg Abel&rsquo;s</strong> February 28, 2026 shareholder letter (<span class="num">1,730 words</span>), the highest-frequency content words are <strong>&ldquo;berkshire&rdquo;</strong> (<span class="num">17</span>), <strong>&ldquo;businesses&rdquo;</strong> (<span class="num">10</span>), <strong>&ldquo;operating&rdquo;</strong> (<span class="num">9</span>), <strong>&ldquo;insurance&rdquo;</strong> (<span class="pnum">7</span>), <strong>&ldquo;operations&rdquo;</strong> (<span class="pnum">7</span>), <strong>&ldquo;capital&rdquo;</strong> (<span class="pnum">6</span>), and <strong>&ldquo;warren&rdquo;</strong> (<span class="pnum">4</span>). <strong>&ldquo;AI&rdquo;</strong> appears <span class="num">0 times</span>.</p>
<div class="flinks"><a href="./#person=abel&amp;docs=all">Explore Greg Abel &rarr;</a></div>
</article>

<article class="fcard" id="f14">
<div class="ftop"><span class="fnum">#14</span><span class="ftag">JPMorgan Chase &middot; Jamie Dimon (2025 &amp; 2026 Letters)</span></div>
<h3>Dimon&rsquo;s letters are full of &ldquo;should&rdquo;</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">&ldquo;should&rdquo;</div><div class="fsv">46 uses</div><div class="fss">Across 13,347 words (2 letters)</div></div>
<div class="fstat"><div class="fsw">&ldquo;need&rdquo;</div><div class="fsv">25 uses</div><div class="fss">Public-policy prescription tone</div></div>
<div class="fstat"><div class="fsw">&ldquo;capital&rdquo; &amp; &ldquo;global&rdquo;</div><div class="fsv">33 &middot; 31</div><div class="fss">Core banking &amp; macro terms</div></div>
<div class="fstat"><div class="fsw">&ldquo;bank&rdquo; / &ldquo;america&rdquo; / &ldquo;world&rdquo;</div><div class="fsv">30 &middot; 27 &middot; 27</div><div class="fss">Apr 7, 2025 &amp; Apr 6, 2026 letters</div></div>
</div>
<p>Across <strong>Jamie Dimon&rsquo;s</strong> two indexed annual shareholder letters (April 7, 2025 and April 6, 2026, totaling <span class="num">13,347 words</span>), <strong>&ldquo;should&rdquo;</strong> appears <span class="num">46 times</span> and <strong>&ldquo;need&rdquo;</strong> <span class="num">25 times</span>, right alongside <strong>&ldquo;capital&rdquo;</strong> (<span class="pnum">33</span>), <strong>&ldquo;global&rdquo;</strong> (<span class="pnum">31</span>), <strong>&ldquo;bank&rdquo;</strong> (<span class="pnum">30</span>), <strong>&ldquo;america&rdquo;</strong> (<span class="pnum">27</span>), and <strong>&ldquo;world&rdquo;</strong> (<span class="pnum">27</span>)&mdash;reflecting how much of his annual letter is policy prescription alongside banking results.</p>
<div class="flinks"><a href="./#person=dimon&amp;docs=all">Explore Jamie Dimon &rarr;</a></div>
</article>

<article class="fcard" id="f15">
<div class="ftop"><span class="fnum">#15</span><span class="ftag">SpaceX &amp; Tesla &middot; Elon Musk (2006 &ndash; 2016 Documents)</span></div>
<h3>Musk&rsquo;s early documents are about launch, not cars</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">&ldquo;launch&rdquo;</div><div class="fsv">38 uses</div><div class="fss">#1 content word across 5 docs</div></div>
<div class="fstat"><div class="fsw">&ldquo;spacex&rdquo; &amp; &ldquo;space&rdquo;</div><div class="fsv">28 &middot; 26</div><div class="fss">Aug 2, 2006 &ndash; Jul 20, 2016</div></div>
<div class="fstat"><div class="fsw">&ldquo;nasa&rdquo; &amp; &ldquo;commercial&rdquo;</div><div class="fsv">25 &middot; 19</div><div class="fss">Congressional testimony focus</div></div>
<div class="fstat"><div class="fsw">&ldquo;falcon&rdquo; &amp; &ldquo;competition&rdquo;</div><div class="fsv">15 &middot; 15</div><div class="fss">&ldquo;ai&rdquo; appears 0 times</div></div>
</div>
<p><strong>Elon Musk&rsquo;s</strong> five indexed documents on MouthMath span August 2, 2006 to July 20, 2016 (Congressional testimony and master-plan essays). Because three of those five texts are SpaceX testimony before Congress, spaceflight vocabulary dominates his counts: <strong>&ldquo;launch&rdquo;</strong> (<span class="num">38</span>), <strong>&ldquo;spacex&rdquo;</strong> (<span class="num">28</span>), <strong>&ldquo;space&rdquo;</strong> (<span class="num">26</span>), <strong>&ldquo;nasa&rdquo;</strong> (<span class="pnum">25</span>), <strong>&ldquo;commercial&rdquo;</strong> (<span class="pnum">19</span>), <strong>&ldquo;falcon&rdquo;</strong> (<span class="pnum">15</span>), and <strong>&ldquo;competition&rdquo;</strong> (<span class="pnum">15</span>). Across those 2006&ndash;2016 documents, <strong>&ldquo;ai&rdquo;</strong> appears <span class="num">0 times</span>.</p>
<div class="flinks"><a href="./#person=musk&amp;docs=all">Explore Elon Musk &rarr;</a></div>
</article>

<div class="fsec-hd" id="warsh"><h2>IV. New Fed Chair</h2><span>Findings 16 &ndash; 18 &middot; Kevin Warsh (Jun &ndash; Oct 2026)</span></div>

<article class="fcard" id="f16">
<div class="ftop"><span class="fnum">#16</span><span class="ftag">Federal Reserve Chair &middot; Kevin Warsh (Jun &ndash; Oct 2026)</span></div>
<h3>Warsh breaks the Chair-by-Chair climb in &ldquo;inflation&rdquo; talk</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">Warsh &ldquo;inflation&rdquo;</div><div class="fsv">5.11 / 1k</div><div class="fss">119 uses in 23,297 words</div></div>
<div class="fstat"><div class="fsw">Powell &ldquo;inflation&rdquo;</div><div class="fsv">11.53 / 1k</div><div class="fss">260 uses, 2024&ndash;26</div></div>
<div class="fstat"><div class="fsw">Warsh prepared texts</div><div class="fsv">6.98 / 1k</div><div class="fss">34 uses in 4,871 words</div></div>
<div class="fstat"><div class="fsw">Warsh press conferences</div><div class="fsv">4.61 / 1k</div><div class="fss">85 uses in 18,426 words</div></div>
</div>
<p>Across <strong>Kevin Warsh&rsquo;s</strong> six indexed documents (June 17 to October 28, 2026: four FOMC press conferences, one Congressional testimony, and one speech), <strong>&ldquo;inflation&rdquo;</strong> appears <span class="num">119 times</span> in <span class="num">23,297 words</span>, or <span class="num">5.11 per 1,000</span>&mdash;tied with <strong>&ldquo;policy&rdquo;</strong> (also 119) as his most-used content word, and less than half of Powell&rsquo;s <span class="pnum">11.53</span>. That ends the run in <a href="#f3">Finding #03</a>, where each Chair from Volcker through Powell came in higher than the one before.</p>
<p><strong>Caveat:</strong> Powell&rsquo;s sample is speeches and testimony, while most of Warsh&rsquo;s words come from press-conference answers. Counting only Warsh&rsquo;s prepared testimony and speech, his rate is <span class="pnum">6.98 per 1,000</span>&mdash;still below Powell, but closer. This is a word-count pattern in a small, early sample, not evidence of a change in policy.</p>
<div class="flinks"><a href="./#person=warsh&amp;docs=all">Explore Kevin Warsh &rarr;</a><a href="articles/warsh-oct-2026-fomc.html">Warsh&rsquo;s October press conference &rarr;</a></div>
</article>

<article class="fcard" id="f17">
<div class="ftop"><span class="fnum">#17</span><span class="ftag">Federal Reserve Chairs &middot; Artificial Intelligence</span></div>
<h3>Warsh is the first Fed Chair in our sample to say &ldquo;AI&rdquo;</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">Warsh &ldquo;ai&rdquo;</div><div class="fsv">24 uses</div><div class="fss">1.03 / 1k across 6 documents</div></div>
<div class="fstat"><div class="fsw">Five earlier Chairs</div><div class="fsv">0</div><div class="fss">Volcker through Powell samples</div></div>
<div class="fstat"><div class="fsw">Warsh Aug 28 speech</div><div class="fsv">8 uses</div><div class="fss">in 3,563 words</div></div>
<div class="fstat"><div class="fsw">Michael Barr</div><div class="fsv">6.84 / 1k</div><div class="fss">Governors still lead</div></div>
</div>
<p><strong>&ldquo;ai&rdquo;</strong> appears <span class="num">0 times</span> in MouthMath&rsquo;s samples for Powell, Yellen, Bernanke, Greenspan, and Volcker. <strong>Kevin Warsh</strong> says it <span class="num">24 times</span> (<span class="pnum">1.03 per 1,000 words</span>), and it shows up in every one of his six documents: <span class="pnum">12</span> across four FOMC press conferences, <span class="pnum">4</span> in his July 14 testimony, and <span class="pnum">8</span> in his August 28 speech.</p>
<p>The governors are still far ahead&mdash;<strong>Michael Barr</strong> at <span class="pnum">6.84 per 1,000</span> and <strong>Lisa Cook</strong> at <span class="pnum">6.42</span> (<a href="#f5">Finding #05</a>). The earlier Chairs&rsquo; samples are from before AI was a common topic, so the zero partly reflects when they spoke.</p>
<div class="flinks"><a href="./#person=warsh&amp;docs=all">Explore Kevin Warsh &rarr;</a><a href="./#person=barr&amp;docs=all">Barr &rarr;</a></div>
</article>

<article class="fcard" id="f18">
<div class="ftop"><span class="fnum">#18</span><span class="ftag">Federal Reserve Chairs &middot; Speaking Style</span></div>
<h3>Warsh&rsquo;s signature word is &ldquo;think&rdquo;&mdash;mostly in live Q&amp;A</h3>
<div class="fgrid">
<div class="fstat"><div class="fsw">Warsh &ldquo;think&rdquo;</div><div class="fsv">3.86 / 1k</div><div class="fss">90 uses in 23,297 words</div></div>
<div class="fstat"><div class="fsw">Five earlier Chairs</div><div class="fsv">0.28 / 1k</div><div class="fss">65 uses in 235,199 words</div></div>
<div class="fstat"><div class="fsw">Warsh press conferences</div><div class="fsv">4.67 / 1k</div><div class="fss">86 uses in 18,426 words</div></div>
<div class="fstat"><div class="fsw">Warsh prepared texts</div><div class="fsv">0.82 / 1k</div><div class="fss">4 uses in 4,871 words</div></div>
</div>
<p><strong>Kevin Warsh</strong> says <strong>&ldquo;think&rdquo;</strong> <span class="num">90 times</span> (<span class="num">3.86 per 1,000 words</span>), versus <span class="pnum">0.28 per 1,000</span> for Volcker, Greenspan, Bernanke, Yellen, and Powell combined. Nearly all of it comes from his FOMC press conferences: <span class="pnum">29</span> on June 17, <span class="pnum">26</span> on July 29, <span class="pnum">12</span> on September 16, and <span class="pnum">19</span> on October 28, compared with just <span class="pnum">2</span> each in his July 14 testimony and August 28 speech.</p>
<p><strong>Caveat:</strong> this contrast likely reflects format as much as personal style. About 79% of Warsh&rsquo;s counted words are press-conference answers, while the earlier Chairs&rsquo; samples are mainly prepared speeches and testimony, where &ldquo;I think&rdquo; is rare. On prepared texts alone, Warsh&rsquo;s rate (<span class="pnum">0.82</span>) is much closer to the others.</p>
<div class="flinks"><a href="./#person=warsh&amp;docs=all">Explore Kevin Warsh &rarr;</a></div>
</article>

<section class="fmethod" id="method" aria-labelledby="methodH">
<h2 id="methodH">Methodology &amp; How Words Are Counted</h2>
<p><strong>Tokenization:</strong> MouthMath lowercases all text, converts curly apostrophes to straight apostrophes, strips trailing possessive <code>&rsquo;s</code> (so <code>Fed&rsquo;s</code> is counted with <code>fed</code>, while contractions like <code>it&rsquo;s</code> stay intact), preserves <code>u.s.</code> as a single token, and excludes standalone numbers by default.</p>
<p><strong>Normalization:</strong> Because speakers have different total word counts (from single 1,700-word shareholder letters to 90,000-word presidential speech collections), cross-speaker comparisons above are reported as <strong>mentions per 1,000 total words</strong> alongside raw occurrence counts. Singular and plural forms (such as <code>tariff</code> and <code>tariffs</code>, or <code>customer</code> and <code>customers</code>) are counted as distinct word tokens unless noted as combined.</p>
<p><strong>Verify in context:</strong> Every finding above can be inspected directly in the <a href="./">MouthMath interactive explorer</a>&mdash;select any speaker, choose <strong>All</strong> documents in the timeframe bar, and tap any word to read the sentences behind the count.</p>
</section>"""
    return shell(
        privacy,
        title="18 Key Findings from the Transcripts",
        desc="18 data-driven word-frequency findings across Federal Reserve Chairs, US Presidents, and S&P 500 CEOs, measured per 1,000 words from official transcripts.",
        path="findings.html",
        body=body,
        current="findings.html",
        prefix="",
    )

def build_all(people, stop, privacy, write):
    by = {p["slug"]: p for p in people}
    urls = []
    (ROOT / "speakers").mkdir(exist_ok=True); (ROOT / "articles").mkdir(exist_ok=True)
    keep = set()
    for p in people:
        write(ROOT / "speakers" / f'{p["slug"]}.html', speaker_page(p, stop, privacy)); keep.add(f'{p["slug"]}.html')
        urls.append(f'speakers/{p["slug"]}.html')
    for f in (ROOT / "speakers").glob("*.html"):
        if f.name not in keep and f.name != "index.html": f.unlink()
    write(ROOT / "speakers" / "index.html", speakers_index(people, privacy)); urls.insert(0, "speakers/")
    fill = article_fill(by, stop)
    for s, t in ARTICLES:
        write(ROOT / "articles" / f"{s}.html", article_page(s, t, privacy, fill)); urls.insert(0, f"articles/{s}.html")
    write(ROOT / "articles" / "index.html", articles_index(privacy)); urls.insert(0, "articles/")
    write(ROOT / "findings.html", findings_page(privacy)); urls.insert(0, "findings.html")
    write(ROOT / "terms.html", terms_page(privacy)); urls.insert(0, "terms.html")
    stats(by, stop)
    return urls
