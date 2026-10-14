"""Static, crawlable content pages (adsense-content): bios, speaker pages, articles, Terms of Use.
Called from build.py main() with the built people list; everything here is plain HTML, no JS needed to read it."""
import html, json, re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
SITE = "https://mouthmath.com/"
MONTHS = "January February March April May June July August September October November December".split()

FOOT_LINKS = [("./", "Home"), ("articles/", "Articles"), ("contact.html", "Contact"),
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
    "Cabinet": "The documents are public speeches, remarks and testimony from official government websites.",
}
SLUG_NOTE = {
    "volcker": "The documents are statements, speeches and testimony from his time as Chair, kept in the Federal Reserve's FRASER archive.",
    "cook": "The documents are his own public words, such as letters filed with the Securities and Exchange Commission and congressional testimony.",
    "jobs": "The documents are his own public words filed with the Securities and Exchange Commission.",
    "musk": "The documents are his two Tesla Master Plan essays and his testimony to Congress about SpaceX.",
}
FED_NOTE = "The documents are speeches and testimony to Congress given as Chair, from the Federal Reserve's official website."
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
            ("comparing-presidential-vocabulary", "Comparing presidential vocabulary")]

def article_page(slug, title, privacy, fill):
    body = (CONTENT / "articles" / f"{slug}.html").read_text(encoding="utf-8")
    for k, v in fill.items():
        body = body.replace("{{" + k + "}}", v)
    desc = re.sub(r"<[^>]+>", "", body.split("</p>", 1)[0].split("<p>", 1)[-1])[:155]
    return shell(privacy, title=title, desc=desc, path=f"articles/{slug}.html",
                 body=f"<h1>{esc(title)}</h1>\n" + body + '\n<p><a href="./">More articles</a> · <a href="../speakers/">All speakers</a></p>', prefix="../")

def articles_index(privacy):
    li = "".join(f'<li><a href="{s}.html">{esc(t)}</a></li>' for s, t in ARTICLES)
    return shell(privacy, title="Articles", desc="Short articles about how MouthMath counts words and what the numbers show.",
                 path="articles/", body=f'<h1>Articles</h1>\n<p class="upd">Short reads on how MouthMath works and what the counts show.</p>\n<ul class="plain">{li}</ul>\n<p><a href="../speakers/">Browse all speakers</a></p>',
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
    pres = [s for s in ("carter", "reagan", "bush41", "clinton", "bush43", "obama", "trump", "biden") if s in by]
    rows = []
    for s in pres:
        p = by[s]; c = counts(p); tot = sum(c.values()); n = len(p["docs"])
        rows.append([f'<a href="../speakers/{s}.html">{esc(p["name"])}</a>', str(n), f"{tot // n:,}", f"{len(c):,}",
                     ", ".join(w for w, _ in top_words(p, stop, 5))])
    f["PRES_TABLE"] = table(rows, ["President", "Speeches", "Words per speech", "Different words", "Top 5 words"])
    return f

def stats(by, stop):   # printed by build.py so the article text can be checked against the data
    for s, p in by.items():
        if p.get("mode") == "fed" or p.get("group") == "Presidents":
            c = counts(p); tot = sum(c.values())
            print(f"  [stats] {s}: docs {len(p['docs'])} words {tot} unique {len(c)} per-doc {tot // len(p['docs'])} "
                  + ", ".join(f"{w} {k}" for w, k in top_words(p, stop, 15)))

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
    write(ROOT / "terms.html", terms_page(privacy)); urls.insert(0, "terms.html")
    stats(by, stop)
    return urls
