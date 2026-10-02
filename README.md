# Fed Words

A static website that lists every word a public figure said in their official
documents, ranked from most to least frequent. Choose a **category**, then a **person**:

| Category | Person | Documents | Source |
|---|---|---|---|
| Fed Chair | **Kevin Warsh** (sworn in May 22, 2026) | official speeches + testimony as Chair (full text) | federalreserve.gov |
| CEOs | **Alex Karp** (Palantir) | 4 most recent quarterly letters to shareholders | palantir.com |
| CEOs | **Andy Jassy** (Amazon) | 2025 and 2024 annual shareholder letters | aboutamazon.com |
| CEOs | **Greg Abel** (Berkshire Hathaway) | his 2025 letter (his first as CEO) | berkshirehathaway.com |

Open `index.html` in a browser. It's one self-contained file (inline CSS/JS, no
external dependencies) with a filter box (plain text or regex), a
"hide common stopwords" toggle (off by default, so every word is listed), and
sortable Rank / Word / Count columns. People and their metadata are listed in
`people.json`.

**Timeframe selector:** check one or more speeches, use "only" to pick a single
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
  Jassy 28.9%, Abel 27.8%. `build.py` prints these numbers and stops with an error if
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
| `people.json` | Categories, people, display names, sources, and `policy` (`full` = embed all sentences, `excerpt` = derived data only). |
| `derived/` | Committed derived data for each CEO: per-letter word counts and the excerpt sentences. No full text. |
| `build.py` | Splits each document into sentences, tokenizes and counts the words, builds the word→sentence index, prints a summary per person, and writes `index.html` (about 270 KB with all 4 people). If the page would go over 1.5 MB (or with `--split`), the non-default people are written to `data/<person>.json` and loaded on demand. |
| `raw/`, `local_sources/` | Downloads and raw CEO text (gitignored). |

Python 3.8+ standard library only; nothing to install.

## Run it
```bash
python3 fetch.py            # add any new speeches/testimony by "Chair(man) Kevin Warsh"
python3 fetch_ceo.py        # (manual, occasional) refresh CEO letters into local_sources/
python3 build.py            # regenerate derived/ + index.html and print totals/top words
python3 -m http.server 8000 # then open http://localhost:8000/
```
Options: `fetch.py --refresh` (download existing items again), `fetch.py --speaker "^Chair Jerome H\\. Powell$"`
(a regex matched against the feed's speaker field), `build.py --keep-numbers` (count tokens like `2026`).

### Tokenization rules
Text is lowercased. Punctuation, hyphens, and dashes split words. Contractions stay
whole (`don't`, `it's`, `we're`). Possessive `'s` is dropped (`Fed's` → `fed`). Curly
apostrophes are normalized. Tokens that are only digits are skipped by default.
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
(Fed only; CEO letters come from the committed `derived/` files, or from `local_sources/`
if it exists and you ran `fetch_ceo.py`).
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
- The tokenizer splits "U.S." into "u" and "s", so "s" appears among Karp's top words.
- Only Greg Abel's own letter is used for Berkshire; Warren Buffett's earlier letters
  aren't included. Older Karp letters (back to 2022) exist but only the 4 most recent are used.
- SEC EDGAR blocks automated access from the build machine, so letters come from the
  companies' own websites instead.
- Warsh's 2006–2011 speeches as a Governor are left out on purpose. The speaker
  filter only matches remarks given as Chair.
