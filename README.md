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
| CEOs (former) | **Tim Cook** (Apple, AAPL; CEO Aug 2011 to Aug 2026, then Executive Chairman) | 67 documents: his quotes in 63 Apple press releases filed as 8-K exhibits (Oct 2011 to Jul 2026), his Jan 2, 2019 letter to investors (8-K), Apple's own partial transcript of his Feb 2013 Goldman Sachs conference remarks (DEFA14A), and his spoken turns in two congressional hearings (Senate PSI, May 21, 2013; House Judiciary antitrust, Jul 29, 2020) | sec.gov (EDGAR), govinfo.gov |
| CEOs (former) | **Steve Jobs** (Apple, AAPL; CEO Sept 1997 to Aug 2011) | 42 texts Apple filed with the SEC, 2003–2011: his quotes in 39 press releases (8-K exhibits) and 3 emails to employees (2003 option exchange, 2009 and 2011 medical leaves) | sec.gov (EDGAR) |
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

**Apple's former CEOs (Tim Cook, Steve Jobs):** Apple publishes no call transcripts or prepared remarks, and its webcast
replay comes down after about two weeks, so neither man's earnings calls are used. Instead `fetch_ceo_filings.py` builds
them only from texts Apple itself filed with the SEC (found with EDGAR full-text search) and from official hearing records on
govinfo.gov. Each document is labelled by type: `Press release quote` (only the quoted words attributed to him in an
8-K exhibit press release, within his tenure), `Investor letter`, `Email to employees`, `Conference transcript` (his
answers only) and `Congressional hearing` (his own spoken turns; other speakers, inserted statements and bracketed notes
removed). They are treated like company text (counts plus capped excerpts, linked to the filing), not as public-domain
government text. Not used: keynotes, the Stanford speech, the Steve Jobs Archive, apple.com pages, and third-party
transcripts. The Jan 5, 2009 letter and the Aug 24, 2011 resignation letter were never filed with the SEC (they appear
only on apple.com), so they are left out. SEC asks automated clients to send a User-Agent with a contact address; the
script takes it only from the `SEC_CONTACT` environment variable (no address is stored in the repo; downloads stop with a message if it is unset) and makes about 1 request/s. Both show in the CEO list (Former CEO · Apple,
AAPL pill); `kind: filings` + `fetcher` in `ceos.json` mark them, and `fetch_ceo.py` skips them.

The page header is site-wide and slim (mm24): just the logo and Share/About (the Super Math / Super Cloud buttons are tabs under the red stats now). The logo is 25% bigger than before (70px tall on desktop, 60px on tablets, up to 50px on phones; on phones it is sized to the space next to Share/About, about 40px at 320px, so it stays on one row). The tagline "Every Word Out Of Their Mouth Counts" and the short "Word counts from official ..." line now live in About. The page's one visible `<h1>` is the person heading ("From the mouth of ..."), styled exactly as before (no hidden text).

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

**Documents (mm32, was a small link in mm26):** a full-width outlined button right under the red stats, capped at 560px and
left-aligned on wider screens. It shows "42 documents" in red ("12 of 42 documents" for a partial selection) and "View ▾" in cream, plus a faint
second line, "Latest · Jul 19, 2011 · <title>" (the date comes first so it always shows; a long title is cut off with "…"). It is 62px tall on phones,
with a 1px gray border that turns cream on hover or while open. The red docs stat has a small ▾ and a dotted underline as a tap cue, and tapping it
opens the list too. On phones it opens a bottom sheet, and from 641px a popover
under the link. Either one holds All / None, the per-year chips and the document list, and closes on the ×, the backdrop or Esc (`details#docPick`;
the page behind does not scroll while the phone sheet is open).
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

**Ad slots:** four reserved, text-free placeholder blocks at their final sizes: a `between` unit inside the results card,
below the Super Math / Super Cloud views (728x90, 320x100 on phones; for a future relevant ad unit), a leaderboard below the results card
(728x90, 320x50 on phones), a 300x250 sidebar unit below Who (desktop only) and a 300x250 in-content unit between the
method note and About. Until AdSense is approved each block is purely decorative: a faint tile of math marks (+ = ± × in
cream, one red minus, ~9% opacity) on a hairline border, with no words, links or `ins.adsbygoogle` tags. Each slot carries
invisible metadata only: an HTML comment naming the slot and its sizes, `data-slot` / `data-ad-slot-name`, `data-ad-size`
and `data-ad-size-phone` (on the aside and the inner block), and `aria-hidden="true"` + `role="presentation"` so screen
readers skip it. They never sit above the red stats or next to controls. To switch to AdSense, fill in the single `ADS`
config block in `build.py` (`client` = `ca-pub-5930727143587260`, plus each slot's `id`); real units then replace the
placeholders (with an "Advertisement" label and `aria-label`). The AdSense script (publisher `ca-pub-5930727143587260`)
is already in the `<head>` of every page (index.html and privacy.html), and `/ads.txt` lists
`google.com, pub-5930727143587260, DIRECT, f08c47fec0942fa0`.

**SEO:** descriptive `<title>` and meta description (Fed Chair speeches, CEO earnings calls, US government), meta
keywords, canonical `https://mouthmath.com/`, Open Graph + Twitter title/description, and schema.org JSON-LD
(`WebSite`, `WebApplication`, `Dataset`). `build.py` also writes `robots.txt` (allow all + sitemap) and `sitemap.xml`
(`/` and `/privacy.html`). No hidden text or keyword blocks anywhere; the About section has one visible plain-language
summary sentence.

**Readable names (mm24):** in every category's people list the unselected names are cream (#f3eee4) and 2px bigger
(14.5px on phones, 15px on desktop; tighter chip padding on phones keeps two names per row at 390px), the selected person
stays dark red on its light pill, and the role label under the name ("CEO · JPMorgan Chase", "Former CEO · Apple") is
white and a size up (10.5px on phones, 11.5px on desktop).

**Minimalist pass (mm24):** no decorative icons on the category tabs, no "Ranked table" / "Bigger = said more"
captions, no "CEO" / "FED CHAIR" label in the name row (the tab already says it), stat boxes without borders, no "Showing the top N" /
"Top N of M words" status lines (the table-limit note still appears when ALL hits the 2,000-row cap), and phone text at 14px or more for
body copy (person line, "From the mouth of", timeframe, Choose documents, stopwords, form labels). The documents quick-select (All / None / year chips)
are plain cream 15px text buttons (no fill; a thin cream outline marks the selected one; no checkbox box). The years fade at the right edge only when they overflow,
inside the documents sheet. On phones (480px and narrower) category names like "US Government" wrap to two lines rather than shrink below 14px or get clipped.
One Show row only (the duplicate above the cloud is gone). Arial throughout; black, cream/white, red and green.

**Slim page text (mm23):** the page carries no methodology prose. About is short, in this order (mm24): the red lead "Out of the Mouth, into the Math.", the tagline "Every Word Out Of Their Mouth Counts", the short "Word counts from official ..." line, the transparency-and-truth line, the plain SEO sentence (Federal Reserve, banks, earnings calls), then the Contact form (Web3Forms; no email address anywhere on the site) and the Privacy Policy link. The fine print (not financial advice; not affiliated with anyone listed) is in the site footer. The note under
the cloud is just "Data through <date>" (plus the keyboard shortcuts on desktop). Helper captions are gone: no "Tick one
or more" line in Choose documents, a shorter popover hint (hidden on touch screens), and on phones the "Showing the top N"
line under the table and the cloud's "Top N of M words" line are hidden (the stats row already shows the count). The
counting rules, source details and licensing approach below remain the reference (this README).

**People list on phones (CEOs and US Government):** every multi-person category folds its people list behind one
disclosure on phones (≤640px), right under the category tiles: closed, it shows the group (CEO / Cabinet / Congress /
Supreme Court) and the selected person's name in red at 20px (19px at ≤360px, where the small group label is dropped; long names wrap
to a second line), plus the ticker pill for CEOs, with the white ▾ arrow. Tapping opens the list: for CEOs the search,
index chips, A–Z and all 22 CEOs (wrapped, not a sideways row); for US Government the search and the grouped list (all 17
names; no A–Z needed there). A–Z taps keep it open; picking a person folds it again. Fed Chair (one person) has nothing to fold, but its selected name uses the same look (dark row with a thin border, "FED CHAIR" label, name in red #ff5449, no arrow) so all three categories match: red underline under the selected category tile and the selected name in red. Desktop is unchanged (selected names are dark red on a cream chip in every category).

**Polish:** the red stats count up when a person loads (skipped with prefers-reduced-motion); a **Share** button in the
header copies the exact view's URL (person, documents, view; the native share sheet on phones); keyboard shortcuts
`/` (filter words), `V` (switch between the Super Math and Super Cloud tabs; nothing to do side by side), `S` (share), `?` (hint).

**Speaker search (mm24, label mm27):** on phones the selected speaker is one big row (red name, ticker, a large white triangle and a cream
**Search** label; "Close" while the list is open). Tapping it opens the speaker list with the search box focused. Once the red stats scroll away, a slim
sticky top bar shows the speaker, the triangle and **Search**. Tapping it goes back to the top with the list open and the search box focused.
After a pick the list folds and the name and red stats come into view.

**Common words line (mm28):** with "Hide common stopwords" checked (the default), the Super Math table always shows the full N real
(non-stopword) words for the chosen Show count (20 / 100 / ALL). It ends with ONE faint gray italic line, e.g. **+42 common words**, giving the
number of stopwords that would rank within the top N. Tap it to expand those gray rows, each with its real rank in parentheses (e.g. "the (#3)") and
no bar. The line then reads "Hide 42 common words", and tapping it again collapses them (Enter/Space work too). Right below the table, **View words
in actual order** unchecks Hide common stopwords, puts them back in their true ranks (italic) and scrolls back up to the red stats. The cloud never shows stopwords while hidden. The bar column header reads FREQUENCY.

**Stopwords (mm27):** with "Hide common stopwords" unchecked, stopwords (the, and, to ...) are shown in italics in both the Super Math table
and the Super Cloud (DOM and the live canvas), so they stand apart from the meaningful words.

**Fed Chair label (mm30):** the Fed Chair page uses the same results heading as every CEO and US Government speaker:
"From the mouth of <name>" (e.g. "From the mouth of Chairman Kevin Warsh"), with the same wording, style and placement. The mm25
"What the Fed Said" label was removed because it sat in that same slot.

**Super Math / Super Cloud tabs (mm24):** right under the red stats sit two tabs, red **Super Math** (left, the default) and green
**Super Cloud** (right). Tapping one swaps the view in place, in the same spot, with no scrolling. Both views are always rendered; the hidden
one is laid out at zero height and invisible, so the swap is instant. The same person, documents, Show chips, word filter
and stopword setting feed both. From **1100px wide** both views sit **side by side** (table left, cloud right, each under a small cream
heading, `h3.secth`; the cloud is sticky so it stays in view next to a long table) and the tabs are hidden. The faint `between` ad placeholder sits below the views. Font size scales with the square root of the count, from 12px to 72px
(the largest size is smaller on narrow screens). One shared **Show 20 / 100 / ALL** chip row (stair steps: bottom-aligned, each chip a little taller than the last, 20 shortest and ALL tallest; 36/41/46px tall on phones, 30/35/40px on desktop)
(Arial, red outline; the selected chip is filled red) sits right under the tabs and sets how many words both sections show; the default is **100** on every device (mm27). Super Math lists the top N most frequent words
(after the word filter) and then applies the column sort; All lists every word (table limit 2,000). The cloud draws
at most 300 words, so All means the top 300 in the cloud. "Hide common stopwords" (on by default) applies to both.
Sorting a table column only reorders the table (the cloud is left as is). Hover a word for its count and the same sentence popover as the table
(source links, CEO 10-sentence caps); click or tap to pin it.

**Layout order (every screen size):** the person's name ("From the mouth of <person>"), then the
red stats (documents, total words, unique words, words shown), the Choose documents link, the Super Math / Super Cloud tabs, the Show / filter rows, then the view (or both side by side from 1100px) and the `between` ad slot. The stats
live inside the results card, right under the name, so nothing can push them below the cloud or table. On wide
screens (900px and up) the Who panel sits in a left sidebar in both views.
**Privacy Policy:** `privacy.html` (generated by `build.py` from the `PRIVACY` template, same black/cream Arial look) covers Google AdSense cookies and personalized ads (links to Google's "How Google uses information from sites or apps that use our services" and adssettings.google.com), third-party vendor cookies, no accounts/logins and no personal data collected by the site itself, the TradingView chart embed, hosting and jsDelivr. Contact is a small form (Name optional, Email, Message, red Send button) in About and on the privacy page. It posts to Web3Forms (`https://api.web3forms.com/submit`, public access key in the HTML, `botcheck` honeypot, no hCaptcha), shows an inline thank-you or error and never leaves the page. Web3Forms forwards messages by email, so no email address appears anywhere on the site or in the repo. The policy discloses the form and the one local-storage flag (`mm_cloud_tried`). It is linked from the page footer and the About section.

**Header:** the logo is an inline SVG (`assets/logo-inline.svg`, inlined by `build.py`; `assets/logo.svg` is the same drawing for the privacy page's `<img>`), variant **H5** from `/workspace/logo-options/work/mix/power2.py`, generated by `work/mix/h5_site.py`. It has the line-art lips with "+ − = 1" inside and three sound waves, all at stroke width 7.5 (lips in red #ff5449, the math and waves cream #f3eee4). Then comes **MOUTH** in red Arial Bold caps (tracking −0.02em), its caps centered on the icon's center line. **Math** is an exponent in cream Arial Bold at 55% of MOUTH's cap height, tucked right after the H, with its top 40% of its own cap height above MOUTH's cap line. The text is live SVG text in the system stack `Arial, 'Helvetica Neue', Helvetica, 'Liberation Sans', sans-serif` (no font file). Font sizes are set from real Arial Bold's cap height (1467/2048), and the viewBox is `144 238 1140.2 234`. Its alt / aria-label is "MouthMath". Header sizes: 70px tall on desktop, 60px from 641 to 1239px, and 50px on phones (`--lh`, down to ~39px at 320px wide), on one row with Share / About. `og-image.png` and `logo.png` were re-rendered with the new wordmark; the favicon and apple-touch icon are lips only and were unchanged.
**Super Math** and **Super Cloud** tabs (both red since mm32; `--money` green is only for ticker pills). Each one
match the category buttons (mm30): unselected = card black with a thin border and red text; selected = the category's medium gray with dark text and a 3px red underline (both tabs red since mm32). The Fed Chair / CEOs /
US Government category buttons sit at the top of the Who panel, with that category's people right below. Person names are red
(#ff5449 on dark; a darker red #a8201a on the light selected chip); ticker pills stay green.
**Phones (640px and below):** logo (with Share/About) on the first row, the two view buttons in a row under it (no headline in the header since mm24); category and person
chips in single horizontal-scroll rows; the A–Z index wraps into a grid of 40px-tall tap targets with 17px letters (9 x 3, so about
37px wide at 390px, 34px at 360px and 30px at 320px; 14 x 2 from 560px; the cells touch and the visible box is drawn inside, empty letters grayed); the Timeframe row stays one line (years scroll sideways, 36px tap targets,
13px text); About starts collapsed
(the header's About link opens it). At 390×844 the red stats are at about y=332 (y=160 at 1366 wide) and the table or cloud starts right below.

**Super Math table columns:** Rank, Word and Count shrink to their content (`width:1%`), so the count sits a short, fixed gap after the longest word in the list (numbers right-aligned and lined up); the frequency bar fills the rest of the row.

**Show N words chips:** compact, content-sized red chips (desktop 32px tall, 13px text; phones 36px tall, 14px text, no longer stretched across the row). Below 375px wide the padding tightens (and the gap shrinks) so SHOW + all five chips stay on one row down to 320px.

**Top word pulse:** the #1 word of the current selection (speaker, documents, word count) is drawn in the stat red and pulses slowly (2.2 s ease-in-out glow with a slight brighten and 2.5% scale; canvas `paint()` while words float, CSS `@keyframes mmTopPulse` in the static fallback). No pulse under `prefers-reduced-motion`.

**Super Cloud motion (p5.js):** the starting layout is computed in plain JavaScript (canvas `measureText`,
largest words first along a spiral with box collision checks). Words always float (there is no Motion toggle): a
[p5.js](https://p5js.org/) sketch takes over: words float like on water. Each word follows layered, eased sine waves around its
spot (a slow ~6 s vertical bob, a slower ~12 s sideways sway up to ~15 px, and a tilt of at most ~1.3°), riding a shared swell that
travels across the cloud so neighbours move together; bigger words and narrow or very dense clouds float less. Positions ease
toward their target (frame-rate independent), overlaps feed a smoothed separation offset (at most ~3 px of overlap), and targets stay
inside the cloud, so there is no jitter (spatial hash for neighbour checks). Invisible, focusable hit boxes follow the words, so hover, click/tap
to pin, and keyboard access use the same popover as the table. p5.js **2.3.4** is loaded only when the Super Cloud first
scrolls into view (IntersectionObserver; and motion isn't reduced), from jsDelivr with Subresource Integrity
(`sha384-Cs48F1uukMPysq29xNsf/FZL5ZNGsPfi6lDSGOxo6dypVFFiWO9Q3YbRKoXPPBii`). The sketch pauses when the
cloud is off-screen (IntersectionObserver), so the cloud only animates while it is on screen. With `prefers-reduced-motion:
reduce` (no float and no pulse) or if the CDN can't be reached, the static layout is used.
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

URL state: the default is a clean URL, plus `person=`, `docs=` and `n=20|all` when not 100 (old links: `n=300` maps to All, `n=150` to 100, and `n=10`, `n=25`, `n=50` to 20). The Super Cloud
tab adds `view=cloud` (not side by side). `#view=cloud`, old `#mode=cloud` / `#mode=visual` links and the plain `#cloud` anchor open the Super Cloud tab;
old `#mode=standard` links open on Super Math.

**Tabs:** `#vtabs` (`role="tablist"`, arrow keys move between them). Super Cloud's thin outer ring (the outline) slowly fades to black and back (2.8 s ease-in-out; border and label steady)
until it is tapped once (remembered in `localStorage` key `mm_cloud_tried`); none with `prefers-reduced-motion`. The red stats, the red #1 word pulse and other site reds are unchanged.

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
| `fetch_ceo_filings.py` | **Manual**, not run by `publish.sh`. Former CEOs from SEC filings and hearing records (`ceos.json` entries with `"fetcher": "fetch_ceo_filings.py"`; now Tim Cook and Steve Jobs). Discovers press releases quoting the person through EDGAR full-text search (8-K EX-99.x, inside since/until), plus the letters, transcripts and hearings listed under `filings.docs`; cuts only the person's own words; raw downloads cached in `local_sources/<slug>/raw/`, text in `local_sources/<slug>/` (gitignored). SEC-requested User-Agent with contact; ~1 request/s. `--only cook`, `--refresh`. |
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

Every disclosure or sort arrow on the page is white: the larger "Choose documents" arrow (in the label only the word "Choose" is white, "documents" stays red; chevron on desktop, ▾/▴ on phones), the phone About toggle ▾, and the Super Math column sort ▲/▼.

**Ticker charts:** each CEO's ticker pill (in the people list and after the name in the results title) opens an in-page popup with a 1-year daily price chart from TradingView's free, official embeddable Advanced Chart widget (dark theme, 1Y range, daily candles). TradingView's attribution link stays exactly as their widget provides it (required by their terms), and no market data is scraped or stored. The widget script loads only when a pill is clicked, and the widget is removed when the popup closes. Close it with the X, Esc, or a tap on the backdrop; on phones it fills the screen. Clicking a pill inside a person button opens the chart without selecting that person. Exchange prefixes live in `ceos.json` → `tv_exchange` (e.g. NASDAQ:MSFT, NYSE:JPM, NYSE:BRK.B); each was checked to resolve in the widget.

**Links:** every link to a source document or an original source (the Choose documents list, sentence popovers, source credits, the About page) opens in a new tab with `target="_blank" rel="noopener noreferrer"`; a click handler also forces this for any other off-site link. Checkboxes and "only" buttons just change the selection.

**Copyright line (mm28):** the footer of index.html and privacy.html ends with one faint gray, small (12px Arial), centered line, "© 2026 MouthMath", right under the Privacy link. There is no name and no "All rights reserved"; the old "© 2026 Mouth Math ·" prefix was removed from the footer link line so the © appears once.

**Tap a word, read its sentences (mm29):** tapping or clicking a word in Super Math or Super Cloud (or Enter on the #1 word) opens its excerpts panel and smoothly scrolls the page so the panel's top sits near the top of the screen, just under the sticky speaker bar when that bar is showing. The panel's own text is never scrolled. Hovering on desktop never scrolls. With prefers-reduced-motion the page jumps instantly.

**Selected category tab (mm29):** the selected category tab (e.g. "Fed Chair" on the default load, `#cats button.cat.on`) is a medium warm gray (#9a958c) instead of bright cream. Its dark label keeps about 6.6:1 contrast, the count (#26231f) about 5.3:1, and the red underline stays. Selected speaker names stay red.

**Super Cloud background (mm30):** plain #0b0b0b with its thin border; the background grid lines were removed.

**Empty ticker pills (mm31):** a ticker pill with no ticker (Fed Chair, US Government) is never shown. The sticky speaker bar used to show an empty green pill for them.

**Super Cloud tab (mm32):** no green. It looks exactly like Super Math: red text when unselected, the category gray with a red underline when selected. The first-visit fading border hint and the green keyboard-focus ring on cloud words were removed. Ticker pills stay green.
