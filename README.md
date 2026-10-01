# Fed Words

A static website that lists every word the current Federal Reserve Chair
(**Kevin Warsh**, sworn in May 22, 2026) said in his official speeches and
testimony, ranked from most to least frequent.

Open `index.html` in a browser. It's one self-contained file (inline CSS/JS, no
external dependencies) with a filter box (plain text or regex), a
"hide common stopwords" toggle (off by default, so every word is listed), and
sortable Rank / Word / Count columns.

**Timeframe selector:** check one or more speeches, use "only" to pick a single
one, tick a year to add or remove all of that year's speeches, or use All / None.
Counts, ranks, totals, the stopword toggle, and the filter all recompute in the
browser for whatever is selected. Per-transcript counts are embedded in
`index.html`, so it's still one self-contained file. The selection is kept in the
URL (`#docs=warsh20260714a,...`), so you can bookmark or share a specific view.

**Sentences on hover:** hover over a word to see every sentence where it appears
in the selected transcripts, with the word highlighted. Click or tap a word to
pin the panel (close it with × or Esc). The header shows occurrences and sentences
separately (e.g. "34 occurrences in 32 sentences"). A "×2" badge marks a sentence
that uses the word twice. The occurrence total always equals the word's count. The
first 10 sentences are shown; "Show all N" expands a scrollable list. Each sentence
has a **source ↗** link, a text-fragment URL (`…htm#:~:text=start,end`) that jumps
to and highlights that sentence on federalreserve.gov in Chrome, Edge, and Safari.
The speech title link is a plain fallback for other browsers.

## Files
| File | Purpose |
|---|---|
| `fetch.py` | Downloads the chair's speeches + testimony from federalreserve.gov's JSON feeds (`/json/ne-speeches.json`, `/json/ne-testimony.json`), pulls out just the body text (no nav, footnotes, or editorial notes), and saves it to `transcripts/*.txt`, with source URLs/dates in `transcripts/index.json`. |
| `build.py` | Splits each transcript into sentences, tokenizes and counts the words, builds the word→sentence index, prints a summary, and writes `index.html` (about 90 KB for 2 transcripts). |
| `transcripts/` | Cleaned text of each speech, plus `index.json` metadata. |
| `raw/` | Raw HTML/JSON as downloaded (for debugging only). |

Python 3.8+ standard library only; nothing to install.

## Run it
```bash
python3 fetch.py            # add any new speeches/testimony by "Chair(man) Kevin Warsh"
python3 build.py            # regenerate index.html and print totals/top words
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
This pulls the latest from GitHub, then runs `python3 fetch.py && python3 build.py`.
If `git status --porcelain` shows changes, it commits "Add new transcript(s)
<today's date>" and pushes. Otherwise it prints "No changes". GitHub Pages redeploys
on its own about 1–2 minutes after a push. The manual equivalent is
`python3 fetch.py && python3 build.py && git add -A && git commit -m 'Update' && git push`.
`.gitignore` keeps `raw/`, screenshots, and build logs out of the repo.

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
- Warsh's 2006–2011 speeches as a Governor are left out on purpose. The speaker
  filter only matches remarks given as Chair.
