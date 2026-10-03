"""Generic extraction of a CEO's own words from company-published documents (used by fetch_ceo.py).

transcript_section(text, ceo):  the CEO's prepared section of an earnings-call transcript: from the CEO's
    first speaker label up to the next speaker label (another executive, the operator) or the Q&A heading.
letter_body(text, signer):      a signed shareholder letter: from the salutation ("Dear ...") to the
    signature/closing, without tables, page headers/footers, page numbers and headings.
"""
import re
from collections import Counter

NAME = r"[A-Z][A-Za-z.'\u2019\-]+(?: [A-Z][A-Za-z.'\u2019\-]+){1,3}"
ROLE = r"(?:CEO|CFO|COO|Chief|President|Officer|Chair|Chairman|Vice|VP|EVP|SVP|Head|Director|Treasurer|Investor|Relations|Analyst|Finance|Founder|Executive|Manager|Strategy|Partner|Inc\.?|Corp\.?|Company|Group|Securities|Capital|Research|Bank|LLC|Ltd)"
QA = re.compile(r"^(?:QUESTION[- ]AND[- ]ANSWER|QUESTIONS? AND ANSWERS?|Q&A|QUESTION AND ANSWER SESSION|Question-and-Answer Session|Questions and Answers)\b", re.I)
NOT_NAME = re.compile(r"(?i)\b(transcript|corrected|earnings|call|quarter|conference|results|fiscal|inc|corp|company|presentation|webcast|management|discussion|participants|page|copyright|q[1-4]|fy\d*|20\d\d)\b")
def _namepart(s): return re.split(r"\s+[-\u2013\u2014]+\s+|:|,", s, 1)[0][:60]
END_SECTIONS = re.compile(r"^(?:Disclaimer|DISCLAIMER|Forward-Looking Statements|Safe Harbor)\s*$")

def _clean_lines(text):
    lines = [l.rstrip() for l in text.replace("\f", "\n\f\n").split("\n")]
    norm = lambda l: re.sub(r"\d+", "#", l.strip())
    rep = Counter(norm(l) for l in lines if l.strip())
    out = []
    for l in lines:
        s = l.strip()
        if s == "\f": out.append(""); continue
        if (rep[norm(l)] >= 3 and len(s) < 140 and not re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+)?\s*:", s) and (NOT_NAME.search(_namepart(s)) or not re.match(r"^(" + NAME + r")\s*([-\u2013\u2014,:]|$)", s))) \
                or re.fullmatch(r"\.{5,}|[-_=]{5,}|[QA]|\d{1,3}|Page \d+( of \d+)?|\d+ of \d+", s) \
                or re.search(r"(?i)copyright ©|©\s*20\d\d|all rights reserved|www\.callstreet\.com|factset|refinitiv|lseg streetevents", s):
            continue
        out.append(s)
    return out

def _label(s, ceo_re, known):
    """Return (name, rest) if line s is a speaker label, else None."""
    if NOT_NAME.search(_namepart(s)) and not ceo_re.search(_namepart(s)): return None
    m = re.match(r"^((?:" + NAME + r")|[A-Z][A-Z.'\u2019\- ]{2,40}|OPERATOR|Operator)\s*:\s*(.*)$", s)
    if m and (m.group(1).isupper() or m.group(1) in known or ceo_re.search(m.group(1)) or m.group(1).lower() == "operator"):
        return m.group(1), m.group(2)
    if re.fullmatch(r"(?i)operator", s): return "Operator", ""
    m = re.fullmatch(r"([A-Z][a-z]+(?: [A-Z][a-z]+)?)\s*:", s)          # first-name-only label on its own line ("Robin:")
    if m and not NOT_NAME.search(m.group(1)): return m.group(1), ""
    if len(s) < 140:
        m = re.match(r"^(" + NAME + r")\s+[-\u2013\u2014]+\s+(.+)$", s)
        if m and re.search(ROLE, m.group(2)): return m.group(1), ""
        m = re.match(r"^(" + NAME + r"),\s+(.+)$", s)
        if m and re.search(ROLE, m.group(2)) and not re.search(r"[.!?]$", s) and len(s.split()) <= 14: return m.group(1), ""
        m = re.fullmatch(NAME, s)
        if m and (s in known or ceo_re.search(s)): return s, ""
    return None

def transcript_section(text, ceo):
    """ceo: regex matching the CEO's name as printed in labels, e.g. r"Huang"."""
    ceo_re = re.compile(ceo, re.I)
    lines = _clean_lines(text)
    head = " ".join(lines[:120])
    known = {n for n in re.findall(NAME, head) if not NOT_NAME.search(n)}
    paras, on, cur, skip_title = [], False, [], False
    def speech_follows(i):
        """True if real speech follows the label at line i (not a participants list)."""
        seen = 0
        for s in lines[i + 1:i + 8]:
            if not s: continue
            if _label(s, ceo_re, known): return False
            if len(s) < 140 and re.search(r"\s[-\u2013\u2014]+\s", s) and re.search(ROLE, s) and not re.search(r"[.!?]$", s): return False   # participants list
            if s.isupper() and len(s.split()) <= 5: return False          # e.g. CORPORATE PARTICIPANTS
            if len(s.split()) >= 8: return True
            seen += 1
            if seen > 2: return False
        return False
    for i, s in enumerate(lines):
        if not s:
            if on and cur: paras.append(" ".join(cur)); cur = []
            continue
        if on and (QA.match(s) or END_SECTIONS.match(s)): break
        lab = _label(s, ceo_re, known)
        if lab:
            name, rest = lab
            if ceo_re.search(name):
                if on: continue                    # repeated label (page break) inside the section
                if not rest and not speech_follows(i): continue     # participants list, not a turn
                on, skip_title = True, True
                if rest: cur.append(rest); skip_title = False
                continue
            if on: break                           # next speaker -> end of the CEO's prepared section
            continue
        if not on: continue
        if skip_title:                             # FactSet style: title line under the name
            skip_title = False
            if re.search(ROLE, s) and not re.search(r"[.!?\u201d\"]$", s) and len(s.split()) <= 16: continue
        if cur and cur[-1].endswith("-") and s[:1].islower(): cur[-1] = cur[-1][:-1] + s
        else: cur.append(s)
    if cur: paras.append(" ".join(cur))
    # merge paragraph fragments split by page breaks (previous does not end a sentence)
    out = []
    for p in paras:
        p = re.sub(r"\s+", " ", p).strip()
        if not p: continue
        if out and not re.search(r"[.!?:;\u201d\"')]$", out[-1]): out[-1] += " " + p
        else: out.append(p)
    return out

def letter_body(text, signer, start=r"^Dear\b"):
    lines = _clean_lines(text)
    st = next((i for i, s in enumerate(lines) if re.match(start, s)), None)
    if st is None: raise ValueError("salutation not found")
    sig = re.compile(r"^(Sincerely|Respectfully|With (gratitude|appreciation)|Best regards|Warm regards|Thank you,?$)|^" + signer + r"\s*$", re.I)
    paras, cur = [], []
    for s in lines[st + 1:]:
        if sig.match(s): break
        if not s:
            if cur: paras.append(" ".join(cur)); cur = []
            continue
        if re.search(r"\S {3,}\S", s): continue                 # table rows
        if cur and cur[-1].endswith("-") and s[:1].islower(): cur[-1] = cur[-1][:-1] + s
        else: cur.append(s)
    if cur: paras.append(" ".join(cur))
    out = []
    for p in paras:
        p = re.sub(r"\s+", " ", p).strip()
        w = p.split()
        if not re.search(r"[A-Za-z]{2}", p) or (len(w) <= 8 and not re.search(r"[.!?:;,\u201d\"')]$", p)): continue   # headings, numbers
        if out and not re.search(r"[.!?:;\u201d\"')]$", out[-1]) and p[:1].islower(): out[-1] += " " + p
        else: out.append(p)
    return out
