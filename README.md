# Mouth Math

*(Formerly "Said Count" and "Fed Words". The repo and URL stay `fed-words` for now: https://junkyprofit.github.io/fed-words/.)*

A static website that lists every word a public figure said in their official
documents, ranked from most to least frequent. Choose a **category** (Fed Chair, CEOs, US Government),
then a **person**. Inside US Government, people are listed in labelled groups (Cabinet, Congress,
Supreme Court; the `group` field in `people.json`). For CEOs and US Government an **A–Z index** (plus, for CEOs, a search box and stock-index chips) filters the
people by last name (a right-hand column in the Who card on wide screens, a compact scrolling row on phones;
letters with nobody are disabled, "All" clears the filter, arrow keys/Home/End move between letters, Esc resets):

| Category | Person | Documents | Source |
|---|---|---|---|
| Fed Chair | **Kevin Warsh** (sworn in May 22, 2026) | official speeches + testimony as Chair (full text) | federalreserve.gov |
| CEOs | **Alex Karp** (Palantir) | 4 most recent quarterly letters to shareholders | palantir.com |
| CEOs | **Andy Jassy** (Amazon) | 2025 and 2024 annual shareholder letters | aboutamazon.com |
| CEOs | **Greg Abel** (Berkshire Hathaway) | his 2025 letter (his first as CEO) | berkshirehathaway.com |
| CEOs | **Sundar Pichai** (Alphabet/Google) | his prepared remarks from the 8 most recent earnings calls (Q3 2024 to Q2 2026) | abc.xyz (Alphabet's own transcripts) |
| CEOs | **Satya Nadella** (Microsoft, MSFT; Mag 7, S&P 500, Nasdaq 100, Dow 30) | his prepared section of the 4 most recent earnings calls (Q2 FY2025 to Q4 FY2026) | microsoft.com |
| CEOs | **Mark Zuckerberg** (Meta, META; Mag 7, S&P 500, Nasdaq 100) | his prepared section of the 4 most recent earnings calls (Q3 2025 to Q2 2026) | investor.atmeta.com |
| CEOs | **Jamie Dimon** (JPMorgan Chase, JPM; S&P 500, Dow 30) | 2 signed annual shareholder letters (2025, 2024) | jpmorganchase.com |
| CEOs | **John Furner** (Walmart, WMT; S&P 500, Nasdaq 100, Dow 30) | his prepared section of the 3 most recent earnings calls (Q4 FY2026 to Q2 FY2027) | stock.walmart.com |
| CEOs | **Ryan McInerney** (Visa, V; S&P 500, Dow 30) | his prepared section of the 4 most recent earnings calls (Q4 FY2025 to Q3 FY2026) | investor.visa.com |
| CEOs | **Joaquin Duato** (Johnson & Johnson, JNJ; S&P 500, Dow 30) | his prepared section of the 4 most recent earnings calls (Q3 2025 to Q2 2026) | investor.jnj.com |
| CEOs | **Ted Decker** (Home Depot, HD; S&P 500, Dow 30) | his prepared section of the 3 most recent earnings calls (Q1 2025 to Q1 2026) | ir.homedepot.com |
| CEOs | **Brian Moynihan** (Bank of America, BAC; S&P 500) | his prepared section of the 2 most recent earnings calls (Q1 2026 to Q2 2026) | investor.bankofamerica.com |
| CEOs | **Lisa Su** (AMD, AMD; S&P 500, Nasdaq 100) | her prepared section of the 4 most recent earnings calls (Q4 2024 to Q1 2026) | ir.amd.com |
| CEOs | **Marc Benioff** (Salesforce, CRM; S&P 500, Dow 30) | his prepared section of the 4 most recent earnings calls (Q4 FY2025 to Q2 FY2027) | investor.salesforce.com |
| CEOs | **Chuck Robbins** (Cisco, CSCO; S&P 500, Nasdaq 100, Dow 30) | his prepared section of the 4 most recent earnings calls (Q1 FY2026 to Q4 FY2026) | investor.cisco.com |
| CEOs | **Ted Pick** (Morgan Stanley, MS; S&P 500) | 2 signed annual shareholder letters (2026, 2025) | morganstanley.com |
| CEOs | **Jane Fraser** (Citigroup, C; S&P 500) | her prepared section of the 3 most recent earnings calls (Q4 2025 to Q2 2026) | citigroup.com |
| CEOs | **John Stankey** (AT&T, T; S&P 500) | his prepared section of the 4 most recent earnings calls (Q3 2025 to Q2 2026) | investors.att.com |
| CEOs | **Cristiano Amon** (Qualcomm, QCOM; S&P 500, Nasdaq 100) | his prepared section of the 4 most recent earnings calls (Q4 FY2025 to Q3 FY2026) | investor.qualcomm.com |
| CEOs | **Dara Khosrowshahi** (Uber, UBER; S&P 500) | his prepared section of the 4 most recent earnings calls (Q3 2025 to Q2 2026) | investor.uber.com |
| CEOs | **Brian Niccol** (Starbucks, SBUX; S&P 500, Nasdaq 100) | his prepared section of the 4 most recent earnings calls (Q4 FY2025 to Q3 FY2026) | investor.starbucks.com |
| CEOs | **Kelly Ortberg** (Boeing, BA; S&P 500, Dow 30) | his prepared section of the 4 most recent earnings calls (Q3 2025 to Q2 2026) | investors.boeing.com |
| US Government › Cabinet | **Scott Bessent** (Treasury) | 42 speeches & testimony, Mar 2025–Sep 2026: every speech (as prepared for delivery) and prepared testimony posted by Treasury since he took office; found automatically from Treasury's press-release index, readouts/joint statements/press statements excluded, a statement repeated to a second committee counted once | home.treasury.gov |
| US Government › Cabinet | **Marco Rubio** (State) | 5 transcripts, Feb–Sep 2026 (his turns only) | state.gov |
| US Government › Cabinet | **Howard Lutnick** (Commerce) | 3 prepared testimony statements, 2025–2026 | appropriations.senate.gov |
| US Government › Cabinet | **Pete Hegseth** (War/Defense) | 2 written statements + his spoken turns in the Apr 30, 2026 SASC hearing | armed-services.senate.gov, appropriations.senate.gov |
| US Government › Congress | **Mike Johnson** (Speaker), **Hakeem Jeffries** (House Democratic Leader), **John Thune** (Senate Majority Leader), **Charles E. Schumer** (Senate Democratic Leader) | up to 5 most recent floor speeches each in 2026 (his own remarks only) | Congressional Record via govinfo.gov |
| US Government › Supreme Court | **all nine Justices** | up to 3 most recent signed opinions each, October Term 2025 (opinion of the Court, concurrence or dissent) | supremecourt.gov |

All federal texts are U.S. government works, not subject to copyright (17 U.S.C. §105), so they
are embedded in full ("Show all", source links). commerce.gov, war.gov, defense.gov and congress.gov
block the build machine, so Commerce/War testimony comes from the Senate committees' own pages and
floor remarks from govinfo.gov.

**Data-driven CEO list:** `ceos.json` lists each company (ticker, index membership, first day as CEO, and how to find
the texts on the company's own IR site: a Q4 IR feed, links scraped from an IR page, or a URL pattern), and `kind`
(`transcript`: keep only the CEO's own prepared section, from his speaker label to the next speaker or the Q&A;
`letter`: the signed letter from the salutation to the signature). `fetch_ceo.py` reads it and `ceo_extract.py`
does the generic cutting (speaker labels in the formats the IR vendors use, repeated page headers/footers, participant
lists). `build.py` adds every `ceos.json` company to the CEO picker automatically (`order` sets the picker order,
roughly by market cap), so adding a CEO is one JSON entry plus `python3 fetch_ceo.py --only <slug>`. Every CEO was
checked against the company's own latest (2026) call transcript or letter. AMD's transcripts print no call date, so
for those the PDF's own file date is used (it can be a few days after the call).
The CEO picker has a **search box** (name, company or ticker), **index chips** (All, Mag 7, S&P 500, Nasdaq 100,
Dow 30, with counts) and the A–Z index; all three combine.

Skipped in this wave: **Jensen Huang** (Nvidia's own call materials have no prepared remarks by him: the CFO gives
the prepared commentary and Huang speaks only in the Q&A; its annual report has no CEO letter), **Elon Musk** (Tesla
blocks the build machine), **John Ternus** (Apple posts no call text, see below). Not yet checked: other large caps such
as Broadcom, Eli Lilly, Mastercard, Oracle, Exxon Mobil, Costco and Netflix (next wave). Home Depot's 2Q26 transcript
is skipped because no text could be extracted from the PDF.

**CEO source types:** every CEO document carries a small **Source type** label in the document list
(`Shareholder letter` or `Earnings call prepared remarks`, the `source_type` field written by `fetch_ceo.py`).

**Apple:** John Ternus became Apple's CEO on Sept 1, 2026 (Tim Cook is Executive Chairman; Apple Newsroom,
Apr 20, 2026). `fetch_ceo.py --only ternus` is ready and `people.json` has his entry, but Apple publishes only
a press release and an audio webcast for each earnings call (no transcript or prepared remarks), so nothing is
saved and the site skips him until Apple itself posts call text. His first call (fiscal Q4 2026) is expected in late
October 2026 (Apple hasn't announced the date; Oct 29 is the usual estimate).
Not added: **Elon Musk** (ir.tesla.com and tesla.com return 403 to the build machine; SEC EDGAR is blocked too)
and **Ryan Cohen** (GameStop's press releases only paraphrase him, the proxy letter is signed by the Board, and
his own annual-meeting remarks exist only as an SEC filing, which is blocked). Third-party transcripts and social
posts are not used.

The page header is site-wide ("Every Word Out Of Their Mouth Counts": title case, Arial, tight tracking; on phones it sits on its own line under the logo and scales with the screen width so it stays on one line), not tied to the default person.

CEO stock tickers (from `ceos.json`: `companies[].ticker`, plus `existing_tickers` for the original five) show as a small money-green outlined pill in Arial caps, both on each CEO's chip in the people list and after the selected speaker's name in the results title (e.g. "From the mouth of Jamie Dimon [JPM]"). Fed and government people have no ticker, so no pill.
The selected person's label pill, role, document count and source appear in the Who card, and
"From the mouth of <person>" heads the results (lead-in lighter and slightly smaller, the name bold; per-person page title "Mouth Math — From the mouth of <person> (TICKER)"). Each person has a header tint, a label pill and a document noun (`mode`, `eyebrow`,
`doc_noun1`, `unit`/`unit_pl` and an optional popover `credit` line in `people.json`).

Open `index.html` in a browser (serve the folder over HTTP: with this many people the page is
over 1.5 MB, so `build.py` keeps the default person inline and writes the others to
`data/<person>.json`, loaded on demand). The only external file is p5.js for Super Cloud motion (optional, SRI-pinned, loaded on demand). It has a filter box (plain text or regex), a
"hide common stopwords" toggle (**on by default**, so common words like "the", "and" and "that" are left
out when you first open the site; uncheck it to list every word), and
sortable Rank / Word / Count columns. People and their metadata are listed in
`people.json`.

**Timeframe selector:** one slim row inside the results card, right under the red stats: All / None, per-year
chips and a small **Choose documents** toggle (the document list opens below it; closed by default).
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

**Ad slots:** three faint placeholder units (a mock hairline mark, the made-up name "Sponsor", "Your ad here",
and a tiny "Advertisement" label; no real brands): a leaderboard below the results card (728x90, 320x50 on phones), a
300x250 sidebar unit below Who (desktop only) and a 300x250 in-content unit between the method note and
About. They never sit above the red stats or next to controls. To switch to AdSense, fill in the single `ADS` config
block in `build.py` (`client` = `ca-pub-5930727143587260`, plus each slot's `id`) and real units replace the placeholders.
The AdSense script (publisher `ca-pub-5930727143587260`) is already in the `<head>` of every page (index.html and privacy.html),
and `/ads.txt` lists `google.com, pub-5930727143587260, DIRECT, f08c47fec0942fa0`. Each placeholder (and the "Sponsor your ad here" text link under it) is an
"Advertise here" mailto link with the subject "Advertising on Mouth Math"; the address is assembled in JS
(`AD_MAIL` in `build.py`) so it never appears as plain text in the HTML.

**Polish:** the red stats count up when a person loads (skipped with prefers-reduced-motion); a **Share** button in the
header copies the exact view's URL (person, documents, view; the native share sheet on phones); keyboard shortcuts
`/` (filter words), `V` (switch view), `S` (share), `?` (hint).

**Views:** two thumbnail cards at the top, **Super Cloud** (the default, a framed mini cloud, shown in the stat red)
and **Super Math** (the ranked table, a sketched page), are buttons with `aria-pressed` that switch
between the ranked table and a word cloud (Super Cloud) for the same person, timeframe, filter, and
stopword setting. Font size scales with the square root of the count, from 12px to 72px
(the largest size is smaller on narrow screens). One shared **Show 25 / 50 / 100 / 150 / All words** chip row
(Arial, red outline; the selected chip is filled red; 40px tall, full-width on phones) sits right under the Timeframe
row and sets how many words both views show; the default is **50**. Super Math lists the top N most frequent words
(after the word filter) and then applies the column sort; All lists every word (table limit 2,000). The cloud draws
at most 300 words, so All in Super Cloud means the top 300. Super Cloud turns on "Hide common stopwords"
so "the" doesn't dominate. You can turn it off again, and going back to Super Math restores
your earlier setting (on, unless you unchecked it). Hover a word for its count and the same sentence popover as the table
(source links, CEO 10-sentence caps); click or tap to pin it.

**Layout order (every view, every screen size):** the person's name ("From the mouth of <person>"), then the
red stats (documents, total words, unique words, words shown), then the Super Cloud or the Super Math table. The stats
live inside the results card, right under the name, so nothing can push them below the cloud or table. On wide
screens (900px and up) the Who panel sits in a left sidebar in both views.
**Privacy Policy:** `privacy.html` (generated by `build.py` from the `PRIVACY` template, same black/cream Arial look) covers Google AdSense cookies and personalized ads (links to Google's "How Google uses information from sites or apps that use our services" and adssettings.google.com), third-party vendor cookies, no accounts/logins and no personal data collected by the site itself, the TradingView chart embed, hosting and jsDelivr. The contact address is assembled in JS (like the ad mailto). It is linked from the page footer and the About section.

**Header:** the logo is an inline SVG (`assets/logo-inline.svg`, inlined by `build.py`): the original Mouth Math line art, open lips with "+ − = 1" inside and three sound waves, drawn as a faithful vector of `/workspace/logo-options/mouth-math-logo.jpg` in cream lines on black with the lip strokes in the site red (#ff5449, the stat / Super Cloud red; `LIPS=red` in `gen_lips.py`), with the "MouthMath" wordmark (one word, both M capitals, all cream) in Quicksand (a thin rounded geometric sans, SIL Open Font License, converted to outlines so no font is loaded). No animation. It is 56px tall on desktop, 48px from 641 to 1239px, 40px on phones and 34px below 360px. The static `assets/logo.svg`/`logo.png`, the favicon (`favicon.svg` / 32px `favicon.png`: the lips with the math, heavier lines), the `apple-touch-icon.png` and the 1200×630 `og-image.png` (logo on black) are generated from the same source (`/workspace/logo-options/lips/gen_lips.py`, `qs_glyphs.py`, `site_assets_lips.py`). After the logo comes a compact headline block, then the red
**Super Cloud** and green **Super Math** view buttons (green = one CSS variable, `--money`; set it to a gray to switch). Each view button
has a second outer ring in its color and a raised look (top highlight, drop shadow) that presses in on tap. The Fed Chair / CEOs /
US Government category buttons sit at the top of the Who panel, with that category's people right below. Person names are red
(#ff5449 on dark; a darker red #a8201a on the light selected chip); ticker pills stay green.
**Phones (640px and below):** logo (with Share/About) on the first row, the headline on its own line, the two view buttons in a row under it (no subline); category and person
chips in single horizontal-scroll rows; the A–Z index wraps into a grid of 40px-tall tap targets with 17px letters (9 x 3, so about
37px wide at 390px, 34px at 360px and 30px at 320px; 14 x 2 from 560px; the cells touch and the visible box is drawn inside, empty letters grayed); the Timeframe row stays one line (years scroll sideways, 36px tap targets,
13px text); About starts collapsed
(the header's About link opens it). At 390×844 the red stats are at about y=310 and the table or cloud starts right below.

**Super Cloud motion (p5.js):** the starting layout is computed in plain JavaScript (canvas `measureText`,
largest words first along a spiral with box collision checks). With **Motion** on, a
[p5.js](https://p5js.org/) sketch takes over: each word is a soft physics body that drifts gently
(Perlin noise) around its spot, held by a weak spring, and boxes are pushed apart so words never overlap
(spatial hash; bigger words move less). Invisible, focusable hit boxes follow the words, so hover, click/tap
to pin, and keyboard access use the same popover as the table. p5.js **2.3.4** is loaded only when Super Cloud is
shown with Motion on, from jsDelivr with Subresource Integrity
(`sha384-Cs48F1uukMPysq29xNsf/FZL5ZNGsPfi6lDSGOxo6dypVFFiWO9Q3YbRKoXPPBii`). The sketch pauses when the
cloud is off-screen (IntersectionObserver) and is removed in Super Math view. With `prefers-reduced-motion:
reduce`, Motion off, or if the CDN can't be reached, the static layout is used.
The cloud always shows the full selected timeframe (no date slider or play button).
Up to 300 bodies (the Top 300 option).

**Design:** black line-art theme matching the logo (black header with cream text, thin black borders and
rules, black selected states; the per-category accent is a thin stripe under the header). Word-count
numbers (stats and the Count column) use one CSS variable, `--num-red` (#9e1b24, 6.8–7.8:1 contrast on
the cream backgrounds). The theme is one block at the end of the CSS in `build.py`, easy to remove.
**Typography:** one family, Arial (`Arial, "Helvetica Neue", Helvetica, sans-serif`), no webfonts, two weights
(400/700). Hierarchy comes from size, weight and spacing. Tight tracking (-0.02 to -0.035em) on the headline,
the person heading and the red stat numbers; normal tracking for body text; uppercase with +0.06em only on tiny
labels (category pill, source type, group labels). Counts use tabular numerals.

The view is kept in the URL: Super Cloud is the default (clean URL, plus `n=25|100|150|all` when not 50; old `n=300` links map to All); Super Math adds
`#mode=standard`. Old `#mode=visual` links still open the Super Cloud.

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

### CEO letters and remarks: counts + short excerpts only
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
  Jassy 28.5–28.9%, Abel 27.5%, Pichai 25.2–33.3%. `build.py` prints these numbers and stops with an error if
  any letter would go over 50%.
- The popover shows at most **10 sentences per word** for CEOs, with no "Show all", and
  a note "Showing k of N sentences — read the full letter at <source>". Some words
  show "No excerpt shown for this word"; the count is still exact.
- Earnings calls (Pichai): only his own prepared section, from his speaker label to the next executive's
  label; the operator, the IR safe-harbor text, other executives and the analyst Q&A are dropped.
- Letters are trimmed to text the CEO wrote: no signatures or titles, P.S. notes,
  epigraph quotes, reprinted letters (Amazon's 1997 Bezos letter), tables, page
  headers, or page numbers. Berkshire's PDF links open at the page the sentence is on
  (`2025ltr.pdf#page=N`).

## Files
| File | Purpose |
|---|---|
| `fetch.py` | Downloads the chair's speeches + testimony from federalreserve.gov's JSON feeds (`/json/ne-speeches.json`, `/json/ne-testimony.json`), pulls out just the body text (no nav, footnotes, or editorial notes), and saves it to `transcripts/*.txt`, with source URLs/dates in `transcripts/index.json`. |
| `fetch.py` → `transcripts/warsh/` | Cleaned text of each Fed speech, plus `index.json` metadata. |
| `fetch_ceo.py` | **Manual**, not run by `publish.sh`. Downloads the CEO letters from the companies' own sites (Palantir's letter pages, aboutamazon.com articles, and the Berkshire PDF via `pdftotext`, Alphabet's earnings-call transcript pages on abc.xyz found through its IR feed, and Apple's investor event feed for Ternus) into `local_sources/<person>/` (gitignored). Each document's metadata has a `source_type`. It's polite (about 1 request/s, identifying User-Agent) and only fetches what's missing (`--refresh` re-downloads; `--only karp` limits it to one person). Karp's 4 newest letters are discovered from palantir.com/investors (`max` in `PEOPLE`); the Amazon letter URLs are listed in the script; Berkshire's are `letters/<year>ltr.pdf` for 2025 onward (Abel's years as CEO). |
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

Every disclosure or sort arrow on the page is white: the larger "Choose documents" arrow (its label stays red; chevron on desktop, ▾/▴ on phones), the phone About toggle ▾, and the Super Math column sort ▲/▼.

**Ticker charts:** each CEO's ticker pill (in the people list and after the name in the results title) opens an in-page popup with a 1-year daily price chart from TradingView's free, official embeddable Advanced Chart widget (dark theme, 1Y range, daily candles). TradingView's attribution link stays exactly as their widget provides it (required by their terms), and no market data is scraped or stored. The widget script loads only when a pill is clicked, and the widget is removed when the popup closes. Close it with the X, Esc, or a tap on the backdrop; on phones it fills the screen. Clicking a pill inside a person button opens the chart without selecting that person. Exchange prefixes live in `ceos.json` → `tv_exchange` (e.g. NASDAQ:MSFT, NYSE:JPM, NYSE:BRK.B); each was checked to resolve in the widget.

**Links:** every link to a source document or an original source (the Choose documents list, sentence popovers, source credits, the About page) opens in a new tab with `target="_blank" rel="noopener noreferrer"`; a click handler also forces this for any other off-site link. Checkboxes and "only" buttons just change the selection.
