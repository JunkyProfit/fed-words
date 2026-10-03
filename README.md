# Mouth Math

*(Formerly "Said Count" and "Fed Words". The repo and URL stay `fed-words` for now: https://junkyprofit.github.io/fed-words/.)*

A static website that lists every word a public figure said in their official
documents, ranked from most to least frequent. Choose a **category** (Fed Chair, CEOs, US Government),
then a **person**. Inside US Government, people are listed in labelled groups (Cabinet, Congress,
Supreme Court; the `group` field in `people.json`):

| Category | Person | Documents | Source |
|---|---|---|---|
| Fed Chair | **Kevin Warsh** (sworn in May 22, 2026) | official speeches + testimony as Chair (full text) | federalreserve.gov |
| CEOs | **Alex Karp** (Palantir) | 4 most recent quarterly letters to shareholders | palantir.com |
| CEOs | **Andy Jassy** (Amazon) | 2025 and 2024 annual shareholder letters | aboutamazon.com |
| CEOs | **Greg Abel** (Berkshire Hathaway) | his 2025 letter (his first as CEO) | berkshirehathaway.com |
| US Government › Cabinet | **Scott Bessent** (Treasury) | 5 speeches, Feb–Aug 2026 (as prepared for delivery) | home.treasury.gov |
| US Government › Cabinet | **Marco Rubio** (State) | 5 transcripts, Feb–Sep 2026 (his turns only) | state.gov |
| US Government › Cabinet | **Howard Lutnick** (Commerce) | 3 prepared testimony statements, 2025–2026 | appropriations.senate.gov |
| US Government › Cabinet | **Pete Hegseth** (War/Defense) | 2 written statements + his spoken turns in the Apr 30, 2026 SASC hearing | armed-services.senate.gov, appropriations.senate.gov |
| US Government › Congress | **Mike Johnson** (Speaker), **Hakeem Jeffries** (House Democratic Leader), **John Thune** (Senate Majority Leader), **Charles E. Schumer** (Senate Democratic Leader) | up to 5 most recent floor speeches each in 2026 (his own remarks only) | Congressional Record via govinfo.gov |
| US Government › Supreme Court | **all nine Justices** | up to 3 most recent signed opinions each, October Term 2025 (opinion of the Court, concurrence or dissent) | supremecourt.gov |

All federal texts are U.S. government works, not subject to copyright (17 U.S.C. §105), so they
are embedded in full ("Show all", source links). commerce.gov, war.gov, defense.gov and congress.gov
block the build machine, so Commerce/War testimony comes from the Senate committees' own pages and
floor remarks from govinfo.gov.

The page header is site-wide ("Every word they said, ranked"), not tied to the default person.
The selected person's label pill, role, document count and source appear in the Who card, and
"Every word <person> said, ranked" heads the results. Each person has a header tint, a label pill and a document noun (`mode`, `eyebrow`,
`doc_noun1`, `unit`/`unit_pl` and an optional popover `credit` line in `people.json`).

Open `index.html` in a browser (serve the folder over HTTP: with this many people the page is
over 1.5 MB, so `build.py` keeps the default person inline and writes the others to
`data/<person>.json`, loaded on demand). No external dependencies; it has with a filter box (plain text or regex), a
"hide common stopwords" toggle (off by default, so every word is listed), and
sortable Rank / Word / Count columns. People and their metadata are listed in
`people.json`.

**Timeframe selector:** the Range row (All / None / per-year chips) and a selection summary are
always visible; the document list sits behind a **Choose documents** expander (closed by default).
Each document shows its date, title and word count on one line, and its type, location/note and
source link on a second line. Check one or more documents, use "only" to pick a single
one, tick a year to add or remove all of that year's speeches, or use All / None.
Counts, ranks, totals, the stopword toggle, and the filter all recompute in the
browser for whatever is selected. Per-transcript counts are embedded in
`index.html`, so it's still one self-contained file. The selection is kept in the
URL (`#person=karp&docs=pltr-q2-2026,...`; the default view, Warsh with every
document, has a clean URL, and old `#docs=...` links still open Warsh), so you can
bookmark or share a specific view.

**Sentences on hover:** hover over a word to see every sentence where it appears
in the selected transcripts, with the word highlighted. Click or tap a word to
pin the panel (close it with × or Esc). The header shows occurrences and sentences
separately (e.g. "34 occurrences in 32 sentences"). A "×2" badge marks a sentence
that uses the word twice. The occurrence total always equals the word's count. The
first 10 sentences are shown; "Show all N" expands a scrollable list. Each sentence
has a **source ↗** link, a text-fragment URL (`…htm#:~:text=start,end`) that jumps
to and highlights that sentence on federalreserve.gov in Chrome, Edge, and Safari.
The speech title link is a plain fallback for other browsers.

**WordViz mode (word cloud):** two thumbnail cards at the top (**Standard**, a sketched page, and
**WordViz**, a framed mini cloud; buttons with `aria-pressed`) switch
between the ranked table and a word cloud for the same person, timeframe, filter, and
stopword setting. Font size scales with the square root of the count, from 12px to 72px
(the largest size is smaller on narrow screens). "Show top 50 / 150 / 300" sets how many
words are drawn; the default is 150. On wide screens (900px and up) WordViz puts Who and Timeframe in a
left sidebar with the cloud beside them; on narrow screens the cloud comes right after the compact
Who/Timeframe cards (stats and filter below it). Switching to WordViz turns on "Hide common stopwords"
so "the" doesn't dominate. You can turn it off again, and going back to Standard restores
your earlier setting. Hover a word for its count and the same sentence popover as the table
(source links, CEO 10-sentence caps); click or tap to pin it. The layout is plain JavaScript
with no library: words are sized with canvas `measureText` and placed largest-first along a
spiral with box collision checks. It re-lays out when the width changes (rotation or window
resize). The view is kept in the URL (`#mode=visual`, plus `&n=50|300` when not 150).

### Licensing: public domain vs. excerpts
| Source | Status | Treatment |
|---|---|---|
| federalreserve.gov (Fed Chair) | U.S. government work, public domain | full sentences embedded, "Show all" |
| treasury.gov, state.gov, Senate committee sites, govinfo.gov CREC, supremecourt.gov | U.S. government works (17 U.S.C. §105) | full sentences embedded, "Show all"; credit line in popover |
| company sites (CEO letters) | copyrighted | derived data only (below) |

**How the federal texts are cleaned** (`fetch_officials.py`):
- Treasury/State pages: only the official's own words (State transcripts keep only "SECRETARY RUBIO:" turns);
  press-release leads, headings and tags are removed. A speech given through an interpreter (Peru) is skipped.
- Committee PDFs/DOCX: cover pages, running headers, page numbers and headings are removed. Hegseth's FY27
  Senate Appropriations statement was 99% identical to his SASC statement, so only one is used; from the SASC
  hearing transcript only "Secretary Hegseth:" turns are kept.
- Congressional Record: only paragraphs under the leader's own label ("Mr. THUNE." etc.); other members,
  presiding-officer/clerk lines, material inserted into the Record (indented) and procedural
  unanimous-consent granules are dropped; at most one speech per day, minimum 250 words. Speaker Johnson
  rarely speaks on the floor, so he has 3.
- Supreme Court opinions: page heads attribute each page; each opinion starts at "Justice X delivered the
  opinion of the Court" / "Justice X, … dissenting." Syllabus, footnotes (smaller type), captions and headings
  are removed; per curiam opinions are not used. Preliminary prints lose the "i"/"l" of fi/fl ligatures, so
  those glyphs are detected by width with PyMuPDF and repaired; spaced initialisms ("U. S.") are written
  "U.S." like other sources.

**Not included (yet):** a "World leaders" category was planned (Vladimir Putin via en.kremlin.ru,
Benjamin Netanyahu via gov.il, Ayatollah Ali Khamenei via english.khamenei.ir), but none of those
official sites could be reached from the build machine (kremlin.ru doesn't connect; gov.il and
khamenei.ir return bot challenges), and they weren't bypassed.

### CEO letters: counts + short excerpts only
The Fed's transcripts are US-government works (public domain), so they're embedded in
full. CEO letters are copyrighted, so the repo and the page contain **only derived data**:
per-letter word counts, and for hover, a limited set of individual excerpt sentences,
each linked to the original letter.
- Raw letter text is saved by `fetch_ceo.py` to `local_sources/` (**gitignored**, never
  committed). `build.py` turns it into `derived/<person>.json` (counts + excerpts), which
  is committed, so the site can be rebuilt without `local_sources/`.
- Excerpts are chosen per letter, up to a budget of **25% of the letter's words**
  (`EXCERPT_BUDGET` in `build.py`). The selection favors sentences that cover the most
  not-yet-covered content words. A plain "10 sentences per word" cap wasn't enough on its
  own: words used once or twice would pull in 94–100% of all sentences.
  The current share of each letter's sentences embedded: Karp 25.7–32.4%,
  Jassy 28.5–28.9%, Abel 27.5%. `build.py` prints these numbers and stops with an error if
  any letter would go over 50%.
- The popover shows at most **10 sentences per word** for CEOs, with no "Show all", and
  a note "Showing k of N sentences — read the full letter at <source>". Some words
  show "No excerpt shown for this word"; the count is still exact.
- Letters are trimmed to text the CEO wrote: no signatures or titles, P.S. notes,
  epigraph quotes, reprinted letters (Amazon's 1997 Bezos letter), tables, page
  headers, or page numbers. Berkshire's PDF links open at the page the sentence is on
  (`2025ltr.pdf#page=N`).

## Files
| File | Purpose |
|---|---|
| `fetch.py` | Downloads the chair's speeches + testimony from federalreserve.gov's JSON feeds (`/json/ne-speeches.json`, `/json/ne-testimony.json`), pulls out just the body text (no nav, footnotes, or editorial notes), and saves it to `transcripts/*.txt`, with source URLs/dates in `transcripts/index.json`. |
| `fetch.py` → `transcripts/warsh/` | Cleaned text of each Fed speech, plus `index.json` metadata. |
| `fetch_ceo.py` | **Manual**, not run by `publish.sh`. Downloads the CEO letters from the companies' own sites (Palantir's letter pages, aboutamazon.com articles, and the Berkshire PDF via `pdftotext`) into `local_sources/<person>/` (gitignored). It's polite (about 1 request/s, identifying User-Agent) and only fetches what's missing (`--refresh` re-downloads; `--only karp` limits it to one person). Karp's 4 newest letters are discovered from palantir.com/investors (`max` in `PEOPLE`); the Amazon letter URLs are listed in the script; Berkshire's are `letters/<year>ltr.pdf` for 2025 onward (Abel's years as CEO). |
| `fetch_officials.py` | **Manual**, not run by `publish.sh`. Cabinet (`--only cabinet`), congressional leaders (`--only congress`) and Supreme Court (`--only scotus`), or one slug (`--only thune`). Writes `transcripts/<slug>/` (committed; public domain); raw downloads are cached in `raw/officials/` (gitignored). Idempotent: skips people already fetched unless `--refresh`. Polite (about 1 request/s, identifying User-Agent). The Court needs PyMuPDF (`pip install pymupdf`) for ligature repair. |
| `people.json` | Categories, people, display names, sources, and `policy` (`full` = embed all sentences, `excerpt` = derived data only). |
| `derived/` | Committed derived data for each `excerpt`-policy person (CEOs): per-letter word counts and the excerpt sentences. No full text. |
| `build.py` | Splits each document into sentences, tokenizes and counts the words, builds the word→sentence index, prints a summary per person, and writes `index.html`. If the page would go over 1.5 MB (or with `--split`), the non-default people are written to `data/<person>.json` and loaded on demand. |
| `raw/`, `local_sources/` | Downloads and raw CEO text (gitignored). |

Python 3.8+ standard library only, except PyMuPDF for the Supreme Court step of `fetch_officials.py`.

## Run it
```bash
python3 fetch.py            # add any new speeches/testimony by "Chair(man) Kevin Warsh"
python3 fetch_ceo.py        # (manual, occasional) refresh CEO letters into local_sources/
python3 fetch_officials.py  # (manual, occasional) Cabinet, Congress leaders, Supreme Court
python3 build.py            # regenerate derived/ + index.html and print totals/top words
python3 -m http.server 8000 # then open http://localhost:8000/
```
Options: `fetch.py --refresh` (download existing items again), `fetch.py --speaker "^Chair Jerome H\\. Powell$"`
(a regex matched against the feed's speaker field), `build.py --keep-numbers` (count tokens like `2026`).

### Tokenization rules
Text is lowercased. Punctuation, hyphens, and dashes split words. Contractions stay
whole (`don't`, `it's`, `we're`). Possessive `'s` is dropped (`Fed's` → `fed`). Curly
apostrophes are normalized. Tokens that are only digits are skipped by default.
Dotted initialisms are kept as one token with a trailing dot: `U.S.` → `u.s.`,
`U.K.` → `u.k.`, `E.U.` → `e.u.`, `U.S.-based` → `u.s.` + `based`, `U.S.'s` → `u.s.`.
They aren't expanded (`u.s.` is not mapped to "united states"), and `A.I.` (`a.i.`)
is counted separately from `AI` (`ai`). `e.g.` and `i.e.` are stopwords. Undotted
forms still split on punctuation (`S&P` → `s` + `p`).
The stopword list is in `build.py`.

Sentences are split at `.`, `!`, or `?` followed by a capitalized word. The split is
skipped after common abbreviations (Mr., Dr., vol., Jan., …), dotted initials (U.S.,
e.g., i.e., N. Gregory), and ". . ." ellipses. Splits only happen at spaces, so
per-sentence counts always add up to the transcript totals. `build.py` checks this
and stops with an error if they don't.

## Refresh with new speeches
Run `python3 fetch.py && python3 build.py`, then redeploy `index.html`. You can safely
run this every week:
- `fetch.py` only downloads items not already in `transcripts/index.json`. Saved
  transcripts are never deleted or overwritten unless you pass `--refresh`.
- If a feed can't be reached, it exits without changing anything.
- Pages that yield fewer than 50 words are skipped with a warning.
- `index.json`, the transcript files, and `index.html` are written atomically.
- If the Fed's page layout changes and sidebar text gets into the extracted body
  ("Related Content", "Back to Top", HTML tags), `fetch.py` rejects that page
  instead of saving it.
- After changing the extraction rules, run `python3 fetch.py --refresh && python3 build.py`
  to re-extract all saved speeches.
- Running it again with no new speeches produces a byte-identical `index.html`.
  The page shows "Data through <latest transcript date>", not the build time,
  so there is nothing new to commit. To keep the site updated automatically,
  run `./publish.sh` on a schedule (cron, or a GitHub Actions workflow with
  `on: schedule`).

## Live site
- Site: https://junkyprofit.github.io/fed-words/
- Repo: https://github.com/JunkyProfit/fed-words. GitHub Pages serves `index.html`
  from the root of the `main` branch.

### Publish updates
```bash
./publish.sh
```
This pulls the latest from GitHub, then runs `python3 fetch.py && python3 build.py`
(Fed only; CEO letters come from the committed `derived/` files, or from `local_sources/` if it
exists; the federal officials' transcripts are committed in `transcripts/<slug>/`).
If `git status --porcelain` shows changes, it commits "Add new transcript(s)
<today's date>" and pushes. Otherwise it prints "No changes". GitHub Pages redeploys
on its own about 1–2 minutes after a push. The manual equivalent is
`python3 fetch.py && python3 build.py && git add -A && git commit -m 'Update' && git push`.
`.gitignore` keeps `raw/`, `local_sources/`, screenshots, and build logs out of the repo.

## Deploy (it's a static site)
- **GitHub Pages:** push this folder to a repo, then go to Settings → Pages →
  "Deploy from a branch" → `main` / root. The site will be at `https://<user>.github.io/<repo>/`.
- **Netlify:** drag the folder onto https://app.netlify.com/drop, or run
  `netlify deploy --prod --dir .`.
- **Cloudflare Pages, S3, or any web host:** upload `index.html`.

## Caveats / next steps
- Only official prepared remarks posted on federalreserve.gov are included. FOMC
  press conference transcripts (unscripted Q&A) are PDFs at
  https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm. To add them, use
  `pdftotext` and keep only the Chair's turns ("CHAIR WARSH." / "CHAIRMAN WARSH.").
- Congressional Q&A after testimony isn't included. The prepared testimony is, but
  hearing transcripts are published separately by GPO.
- Only Greg Abel's own letter is used for Berkshire; Warren Buffett's earlier letters
  aren't included. Older Karp letters (back to 2022) exist but only the 4 most recent are used.
- SEC EDGAR blocks automated access from the build machine, so letters come from the
  companies' own websites instead.
- Warsh's 2006–2011 speeches as a Governor are left out on purpose. The speaker
  filter only matches remarks given as Chair.
