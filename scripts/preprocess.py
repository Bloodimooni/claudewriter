#!/usr/bin/env python3
"""
preprocess.py — Zero-token preprocessor for the thesis watcher.

Handles all deterministic work before any Claude API call:
  - Parse YAML frontmatter (with validation)
  - Strip "Note to self" lines
  - Remove common contractions (don't→do not, etc.)
  - Extract ## Sources section → BibTeX
  - Convert @citekey → LaTeX citation commands
  - Convert markdown structure → LaTeX structure
  - Generate full LaTeX preamble from frontmatter
  - Update memory files (thesis-context.md, sources.md, progress.md)
  - Check for broken citekeys
  - Cache unchanged chapters via checksums

Usage:
  python3 scripts/preprocess.py <notes-file> [--trigger COMMAND]
  python3 scripts/preprocess.py --checksums-only <notes-file>
  python3 scripts/preprocess.py --compile-all

Outputs JSON to stdout. Writes memory files as side effects.
"""

import sys
import os
import re
import json
import hashlib
import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# ─── Contraction removal (zero-token work, saves Claude effort) ──────────

CONTRACTIONS = {
    r"\bdon't\b": "do not",
    r"\bdon't\b": "do not",
    r"\bcan't\b": "cannot",
    r"\bcan't\b": "cannot",
    r"\bwon't\b": "will not",
    r"\bwon't\b": "will not",
    r"\bshouldn't\b": "should not",
    r"\bshouldn't\b": "should not",
    r"\bcouldn't\b": "could not",
    r"\bcouldn't\b": "could not",
    r"\bwouldn't\b": "would not",
    r"\bwouldn't\b": "would not",
    r"\bisn't\b": "is not",
    r"\bisn't\b": "is not",
    r"\baren't\b": "are not",
    r"\baren't\b": "are not",
    r"\bwasn't\b": "was not",
    r"\bwasn't\b": "was not",
    r"\bweren't\b": "were not",
    r"\bweren't\b": "were not",
    r"\bhasn't\b": "has not",
    r"\bhasn't\b": "has not",
    r"\bhaven't\b": "have not",
    r"\bhaven't\b": "have not",
    r"\bhadn't\b": "had not",
    r"\bhadn't\b": "had not",
    r"\bdoesn't\b": "does not",
    r"\bdoesn't\b": "does not",
    r"\bdidn't\b": "did not",
    r"\bdidn't\b": "did not",
    r"\blet's\b": "let us",
    r"\blet's\b": "let us",
    r"\bthat's\b": "that is",
    r"\bthat's\b": "that is",
    r"\bthere's\b": "there is",
    r"\bthere's\b": "there is",
    r"\bhere's\b": "here is",
    r"\bhere's\b": "here is",
    r"\bwhat's\b": "what is",
    r"\bwhat's\b": "what is",
    r"\bwho's\b": "who is",
    r"\bwho's\b": "who is",
    r"\bI'm\b": "I am",
    r"\bI'm\b": "I am",
    r"\bI've\b": "I have",
    r"\bI've\b": "I have",
    r"\bI'll\b": "I will",
    r"\bI'll\b": "I will",
    r"\bI'd\b": "I would",
    r"\bI'd\b": "I would",
    r"\bit's\b": "it is",
    r"\bit's\b": "it is",
    r"\bwe're\b": "we are",
    r"\bwe're\b": "we are",
    r"\bthey're\b": "they are",
    r"\bthey're\b": "they are",
    r"\byou're\b": "you are",
    r"\byou're\b": "you are",
    r"\bwe've\b": "we have",
    r"\bwe've\b": "we have",
    r"\bthey've\b": "they have",
    r"\bthey've\b": "they have",
    r"\bwe'll\b": "we will",
    r"\bwe'll\b": "we will",
    r"\bthey'll\b": "they will",
    r"\bthey'll\b": "they will",
}

def remove_contractions(text: str) -> str:
    """Pre-remove English contractions. Handles both straight and curly apostrophes."""
    for pattern, replacement in CONTRACTIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

# ─── Frontmatter validation ──────────────────────────────────────────────

VALID_FONT_SIZES = {"10pt", "11pt", "12pt"}
VALID_CITATION_STYLES = {"apa", "chicago", "ieee", "mla", "harvard", "vancouver"}
VALID_LANGUAGES = {
    "english", "german", "ngerman", "french", "spanish", "italian",
    "portuguese", "dutch", "polish", "russian", "chinese", "japanese",
    "british", "american", "australian", "canadian",
}

def validate_frontmatter(fm: dict) -> list[str]:
    """Returns a list of warning strings for invalid frontmatter values."""
    warnings = []

    if "font_size" in fm and fm["font_size"] not in VALID_FONT_SIZES:
        warnings.append(
            f"font_size '{fm['font_size']}' is not standard LaTeX. "
            f"Valid: {', '.join(sorted(VALID_FONT_SIZES))}. Defaulting to 12pt."
        )
        fm["font_size"] = "12pt"

    if "line_spacing" in fm:
        try:
            val = float(fm["line_spacing"])
            if not (0.5 <= val <= 3.0):
                warnings.append(f"line_spacing {val} is out of range [0.5, 3.0]. Using 1.5.")
                fm["line_spacing"] = "1.5"
        except ValueError:
            warnings.append(f"line_spacing '{fm['line_spacing']}' is not a number. Using 1.5.")
            fm["line_spacing"] = "1.5"

    if "citation_style" in fm:
        style = fm["citation_style"].lower()
        if style not in VALID_CITATION_STYLES:
            warnings.append(
                f"citation_style '{fm['citation_style']}' is not recognized. "
                f"Valid: {', '.join(sorted(VALID_CITATION_STYLES))}. Defaulting to APA."
            )
            fm["citation_style"] = "APA"

    if "language" in fm:
        lang = fm["language"].lower()
        if lang not in VALID_LANGUAGES:
            warnings.append(
                f"language '{fm['language']}' may not be a valid babel language. "
                f"Common: english, german, french, spanish."
            )

    if "margin" in fm:
        m = re.match(r"^[\d.]+\s*(cm|mm|in|pt|em)$", fm["margin"])
        if not m:
            warnings.append(f"margin '{fm['margin']}' looks invalid. Expected e.g. '2.5cm'. Using 2.5cm.")
            fm["margin"] = "2.5cm"

    return warnings

# ─── YAML frontmatter parser ───────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Returns (frontmatter_dict, body_text). No external dependencies."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end].strip()
    body = content[end + 4:].lstrip("\n")
    fm = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, body

# ─── Source section parser ─────────────────────────────────────────────────

def parse_sources_section(body: str) -> tuple[list[dict], str]:
    """
    Finds '## Sources' heading and parses entries below it.
    Returns (sources_list, body_without_sources_section).
    """
    sources_match = re.search(r"\n## Sources\s*\n", body)
    if not sources_match:
        return [], body

    pre_sources = body[:sources_match.start()]
    sources_text = body[sources_match.end():]

    sources = []
    remaining_lines = []
    in_sources = True

    for line in sources_text.splitlines():
        if line.startswith("## ") or line.startswith("# "):
            in_sources = False
        if not in_sources:
            remaining_lines.append(line)
            continue

        m = re.match(r"^-\s+(\S+?):\s+(.+)$", line)
        if m:
            citekey = m.group(1)
            rest = m.group(2)
            sources.append({"citekey": citekey, "raw": rest})

    clean_body = pre_sources
    if remaining_lines:
        clean_body += "\n" + "\n".join(remaining_lines)
    return sources, clean_body.rstrip()

# ─── BibTeX generation ─────────────────────────────────────────────────────

def escape_bibtex(text: str) -> str:
    """Escape special LaTeX/BibTeX characters in user-provided text."""
    # Protect existing braces, then escape special chars
    replacements = [
        ("&", r"\&"),
        ("%", r"\%"),
        ("#", r"\#"),
        ("_", r"\_"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text

def source_to_bibtex(source: dict) -> str:
    """
    Converts a parsed source dict to a BibTeX entry.
    Heuristic type detection: article / book / inproceedings / misc.
    """
    citekey = source["citekey"]
    raw = source["raw"]

    entry_type = "misc"
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ["journal", "review", "letters", "nature ", "science ", "ieee trans"]):
        entry_type = "article"
    elif any(k in raw_lower for k in ["conference", "proceedings", "workshop", "symposium", "icml", "neurips", "iclr", "cvpr"]):
        entry_type = "inproceedings"
    elif any(k in raw_lower for k in ["press", "publisher", "edition", "book"]):
        entry_type = "book"

    year = ""
    year_m = re.search(r"\b(19|20)\d{2}\b", raw)
    if year_m:
        year = year_m.group(0)

    title = ""
    title_m = re.search(r'"([^"]+)"', raw)
    if not title_m:
        title_m = re.search(r'\u201c([^\u201d]+)\u201d', raw)
    if title_m:
        title = title_m.group(1)

    authors_part = raw.split(',"')[0].split(',"')[0].strip().rstrip(",").strip()
    if title_m:
        authors_part = raw[:title_m.start()].strip().rstrip(",").strip()

    venue = ""
    if title_m and year_m:
        between = raw[title_m.end():year_m.start()].strip().strip(",").strip()
        venue = between

    # Escape special characters
    authors_part = escape_bibtex(authors_part)
    title = escape_bibtex(title or raw)
    venue = escape_bibtex(venue)

    venue_field = {
        "article": "journal",
        "inproceedings": "booktitle",
        "book": "publisher",
    }.get(entry_type, "note")

    return (f"@{entry_type}{{{citekey},\n"
            f"  author = {{{authors_part}}},\n"
            f"  title  = {{{title}}},\n"
            f"  {venue_field} = {{{venue or 'UNKNOWN'}}},\n"
            f"  year   = {{{year or 'XXXX'}}},\n}}")

def update_bib_file(sources: list[dict]) -> None:
    """Writes all BibTeX entries to refs.bib, rebuilding from source list."""
    bib_path = PROJECT_ROOT / "thesis" / "bibliography" / "refs.bib"
    bib_path.parent.mkdir(parents=True, exist_ok=True)

    # Full rebuild from sources to avoid append-based dedup bugs
    seen_keys = set()
    entries = []
    for src in sources:
        if src["citekey"] not in seen_keys:
            entries.append(source_to_bibtex(src))
            seen_keys.add(src["citekey"])

    bib_path.write_text("\n\n".join(entries) + "\n" if entries else "")

# ─── Note stripping ────────────────────────────────────────────────────────

def strip_personal_notes(body: str) -> str:
    """Remove lines matching '> Note to self: ...'"""
    lines = [l for l in body.splitlines()
             if not re.match(r"^\s*>\s*[Nn]ote to self:", l)]
    return "\n".join(lines)

# ─── Citation conversion ───────────────────────────────────────────────────

STYLE_TO_CMD = {
    "apa": r"\parencite",
    "chicago": r"\parencite",
    "chicago-authordate": r"\parencite",
    "harvard": r"\parencite",
    "ieee": r"\cite",
    "mla": r"\cite",
    "vancouver": r"\cite",
}

def convert_citations(body: str, citation_style: str) -> str:
    """Replace @citekey with the appropriate LaTeX citation command."""
    style = citation_style.lower()
    cmd = STYLE_TO_CMD.get(style, r"\parencite")
    return re.sub(r"@(\w+)", lambda m: f"{cmd}{{{m.group(1)}}}", body)

def find_broken_citekeys(body: str, sources: list[dict]) -> list[str]:
    """Return @citekeys in body that have no ## Sources entry."""
    in_text = set(re.findall(r"@(\w+)", body))
    defined = {s["citekey"] for s in sources}
    return sorted(in_text - defined)

# ─── Word count (single implementation) ──────────────────────────────────

def count_body_words(body: str) -> int:
    """Count words in body text, excluding headings and blank lines."""
    word_lines = [l for l in body.splitlines()
                  if l.strip() and not l.startswith("#")]
    return sum(len(l.split()) for l in word_lines)

# ─── Markdown → LaTeX structural conversion ───────────────────────────────

def md_to_latex_body(md: str) -> str:
    """
    Mechanical markdown-to-LaTeX conversion. Does NOT formalize language.
    Handles: headings, bold, italic, lists, code blocks, inline code, blockquotes.
    """
    lines = md.splitlines()
    out = []
    in_itemize = False
    in_enumerate = False
    in_code = False

    for line in lines:
        # Fenced code blocks
        if line.strip().startswith("```"):
            if not in_code:
                out.append(r"\begin{lstlisting}")
                in_code = True
            else:
                out.append(r"\end{lstlisting}")
                in_code = False
            continue
        if in_code:
            out.append(line)
            continue

        # Close open lists when we hit a non-list line
        stripped = line.lstrip()
        is_bullet = re.match(r"^[-*]\s+", stripped)
        is_numbered = re.match(r"^\d+\.\s+", stripped)

        if in_itemize and not is_bullet:
            out.append(r"\end{itemize}")
            in_itemize = False
        if in_enumerate and not is_numbered:
            out.append(r"\end{enumerate}")
            in_enumerate = False

        # Headings (check longest first to avoid false matches)
        h4 = re.match(r"^####\s+(.*)", line)
        h3 = re.match(r"^###\s+(.*)", line)
        h2 = re.match(r"^##\s+(.*)", line)
        h1 = re.match(r"^#\s+(.*)", line)
        if h4:
            out.append(f"\\subsubsection{{{h4.group(1)}}}")
            continue
        if h3:
            out.append(f"\\subsection{{{h3.group(1)}}}")
            continue
        if h2:
            out.append(f"\\section{{{h2.group(1)}}}")
            continue
        if h1:
            out.append(f"\\chapter{{{h1.group(1)}}}")
            continue

        # Lists
        if is_bullet:
            if not in_itemize:
                out.append(r"\begin{itemize}")
                in_itemize = True
            item_text = re.sub(r"^[-*]\s+", "", stripped)
            item_text = inline_md_to_latex(item_text)
            out.append(f"  \\item {item_text}")
            continue
        if is_numbered:
            if not in_enumerate:
                out.append(r"\begin{enumerate}")
                in_enumerate = True
            item_text = re.sub(r"^\d+\.\s+", "", stripped)
            item_text = inline_md_to_latex(item_text)
            out.append(f"  \\item {item_text}")
            continue

        # Blockquote (non-personal-note — those were already stripped)
        bq = re.match(r"^>\s+(.*)", line)
        if bq:
            out.append(f"\\begin{{quote}}\n{inline_md_to_latex(bq.group(1))}\n\\end{{quote}}")
            continue

        # Horizontal rule
        if re.match(r"^---+\s*$", line):
            out.append(r"\hrule")
            continue

        # Blank line → paragraph break
        if not line.strip():
            out.append("")
            continue

        # Normal paragraph text
        out.append(inline_md_to_latex(line))

    # Close any open lists
    if in_itemize:
        out.append(r"\end{itemize}")
    if in_enumerate:
        out.append(r"\end{enumerate}")

    return "\n".join(out)

def inline_md_to_latex(text: str) -> str:
    """Convert inline markdown (bold, italic, code) to LaTeX.
    Handles nested formatting: **bold with *italic* inside** works correctly
    because we process bold first (greedy for outer), then italic on the inner."""
    # Inline code first (protect from bold/italic processing)
    code_parts = []
    def save_code(m):
        code_parts.append(m.group(1))
        return f"\x00CODE{len(code_parts)-1}\x00"
    text = re.sub(r"`(.+?)`", save_code, text)

    # Bold (** and __)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"__(.+?)__", r"\\textbf{\1}", text)
    # Italic (* and _) — only match if not preceded/followed by word chars for _
    text = re.sub(r"\*(.+?)\*", r"\\textit{\1}", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\\textit{\1}", text)

    # Restore code
    for i, code in enumerate(code_parts):
        text = text.replace(f"\x00CODE{i}\x00", f"\\texttt{{{code}}}")

    return text

# ─── LaTeX preamble generator ──────────────────────────────────────────────

STYLE_MAP = {
    "apa": "apa",
    "chicago": "chicago-authordate",
    "harvard": "authoryear",
    "ieee": "ieee",
    "mla": "mla",
    "vancouver": "numeric",
}

def generate_preamble(fm: dict) -> str:
    font_size = fm.get("font_size", "12pt")
    margin = fm.get("margin", "2.5cm")
    line_spacing = fm.get("line_spacing", "1.5")
    language = fm.get("language", "english")
    citation_style_raw = fm.get("citation_style", "APA").lower()
    biblatex_style = STYLE_MAP.get(citation_style_raw, "apa")
    title = fm.get("title", "Untitled Thesis")
    author = fm.get("author", "Author")
    university = fm.get("university", "")
    supervisor = fm.get("supervisor", "")
    date = fm.get("date", datetime.date.today().strftime("%B %Y"))

    return f"""\\documentclass[{font_size},a4paper]{{report}}

% Encoding and fonts (xelatex)
\\usepackage{{fontspec}}
\\usepackage{{microtype}}

% Language
\\usepackage[{language}]{{babel}}

% Page layout
\\usepackage{{geometry}}
\\geometry{{margin={margin}}}

% Line spacing
\\usepackage{{setspace}}
\\setstretch{{{line_spacing}}}

% Bibliography
\\usepackage[style={biblatex_style},backend=biber]{{biblatex}}
\\addbibresource{{../bibliography/refs.bib}}

% Hyperlinks
\\usepackage[hidelinks]{{hyperref}}

% Code listings
\\usepackage{{listings}}
\\usepackage{{xcolor}}
\\lstset{{basicstyle=\\ttfamily\\small,breaklines=true,frame=single}}

% Graphics and tables
\\usepackage{{graphicx}}
\\usepackage{{booktabs}}

\\begin{{document}}

\\begin{{titlepage}}
  \\centering
  \\vspace*{{3cm}}
  {{\\Huge\\bfseries {title}\\par}}
  \\vspace{{2cm}}
  {{\\large Bachelor's Thesis\\par}}
  \\vspace{{1cm}}
  {{\\large {author}\\par}}
  \\vspace{{0.5cm}}
  {{\\large {university}\\par}}
  \\vspace{{0.5cm}}
  {{Supervisor: {supervisor}\\par}}
  \\vfill
  {{\\large {date}\\par}}
\\end{{titlepage}}

\\tableofcontents
\\newpage
"""

def generate_suffix() -> str:
    return "\n\\printbibliography[heading=bibintoc]\n\n\\end{document}\n"

# ─── Memory file writers ───────────────────────────────────────────────────

def update_thesis_context(fm: dict) -> None:
    path = PROJECT_ROOT / "memory" / "thesis-context.md"
    today = datetime.date.today().isoformat()
    content = f"""# Thesis Context
Last updated: {today}

## Metadata
- Title: {fm.get('title', '(not set)')}
- Author: {fm.get('author', '(not set)')}
- University: {fm.get('university', '(not set)')}
- Supervisor: {fm.get('supervisor', '(not set)')}
- Submission date: {fm.get('date', '(not set)')}

## Research Question
(Run /thesis-memory in Claude Code to infer this from your notes content)

## Formatting Rules
- Citation style: {fm.get('citation_style', 'APA')}
- Line spacing: {fm.get('line_spacing', '1.5')}
- Font size: {fm.get('font_size', '12pt')}
- Margin: {fm.get('margin', '2.5cm')}
- Language: {fm.get('language', 'english')}
"""
    path.write_text(content)

def update_sources_memory(all_sources: list[dict]) -> None:
    path = PROJECT_ROOT / "memory" / "sources.md"
    today = datetime.date.today().isoformat()
    rows = []
    for s in all_sources:
        raw = s["raw"]
        year_m = re.search(r"\b(19|20)\d{2}\b", raw)
        year = year_m.group(0) if year_m else "?"
        title_m = re.search(r'"([^"]+)"', raw)
        title = title_m.group(1)[:50] if title_m else raw[:50]
        rows.append(f"| {s['citekey']} | {title} | {year} | UNVERIFIED |")

    table = "\n".join(rows) if rows else "| (none yet) | | | |"
    content = f"""# Sources Registry
Last updated: {today}

## Source Table
| Citekey | Title (truncated) | Year | Status |
|---------|-------------------|------|--------|
{table}

## BibTeX Entries
See `thesis/bibliography/refs.bib` for full BibTeX entries.
"""
    path.write_text(content)

def update_progress(notes_files: list[Path]) -> None:
    path = PROJECT_ROOT / "memory" / "progress.md"
    today = datetime.date.today().isoformat()
    rows = []
    total_words = 0

    for nf in sorted(notes_files):
        text = nf.read_text()
        _, body = parse_frontmatter(text)
        _, clean_body = parse_sources_section(body)
        clean_body = strip_personal_notes(clean_body)
        words = count_body_words(clean_body)
        total_words += words

        title_m = re.search(r"^#\s+(.+)", clean_body, re.MULTILINE)
        chapter_title = title_m.group(1) if title_m else nf.stem

        if words < 200:
            status = "DRAFT"
        elif words < 800:
            status = "IN_PROGRESS"
        else:
            status = "COMPLETE"

        rows.append(f"| {nf.name} | {chapter_title} | ~{words} | {status} |")

    table = "\n".join(rows) if rows else "| (no notes yet) | | | |"
    content = f"""# Writing Progress
Last updated: {today}

## Chapter Status
| File | Chapter Title | Word Count | Status |
|------|--------------|------------|--------|
{table}

## Totals
- Total chapters: {len(notes_files)}
- Total body word count: ~{total_words}
"""
    path.write_text(content)

# ─── Checksum helpers ──────────────────────────────────────────────────────

def file_checksum(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()

def load_checksums(state_dir: Path) -> dict:
    ckfile = state_dir / "checksums.md5"
    if not ckfile.exists():
        return {}
    result = {}
    for line in ckfile.read_text().splitlines():
        if "  " in line:
            md5, fname = line.split("  ", 1)
            result[fname] = md5
    return result

def save_checksums(state_dir: Path, checksums: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    content = "\n".join(f"{v}  {k}" for k, v in sorted(checksums.items()))
    (state_dir / "checksums.md5").write_text(content + "\n")

# ─── Chapter cache ────────────────────────────────────────────────────────

def load_chapter_cache(state_dir: Path) -> dict:
    """Load cached LaTeX bodies keyed by file checksum."""
    cache_file = state_dir / "chapter_cache.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def save_chapter_cache(state_dir: Path, cache: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "chapter_cache.json").write_text(json.dumps(cache))

# ─── Compile all chapters ────────────────────────────────────────────────

def compile_all_chapters(state_dir: Path) -> dict:
    """
    Process ALL notes files and return combined result.
    Uses chapter cache to skip unchanged files.
    Returns the same JSON structure as single-file mode but with all chapters combined.
    """
    notes_dir = PROJECT_ROOT / "thesis" / "notes"
    all_notes = sorted(notes_dir.glob("*.md"))

    if not all_notes:
        return {"error": "No notes files found in thesis/notes/"}

    checksums = load_checksums(state_dir)
    chapter_cache = load_chapter_cache(state_dir)

    # Merge frontmatter from all files
    merged_fm = {}
    for nf in all_notes:
        nf_fm, _ = parse_frontmatter(nf.read_text())
        for k, v in nf_fm.items():
            if k not in merged_fm:
                merged_fm[k] = v

    # Validate
    fm_warnings = validate_frontmatter(merged_fm)

    # Collect all sources
    all_sources = []
    seen_keys = set()
    for nf in all_notes:
        _, nf_body = parse_frontmatter(nf.read_text())
        srcs, _ = parse_sources_section(nf_body)
        for s in srcs:
            if s["citekey"] not in seen_keys:
                all_sources.append(s)
                seen_keys.add(s["citekey"])

    # Process each chapter, using cache for unchanged ones
    combined_latex_body = []
    combined_body_text = []
    all_broken = []
    total_words = 0
    chapters_cached = 0
    chapters_processed = 0

    for nf in all_notes:
        ck = file_checksum(nf)
        cache_key = f"{nf.name}:{ck}"

        if cache_key in chapter_cache:
            # Use cached LaTeX body
            cached = chapter_cache[cache_key]
            combined_latex_body.append(cached["latex_body"])
            combined_body_text.append(cached["body_text"])
            total_words += cached["word_count"]
            chapters_cached += 1
        else:
            # Process this chapter
            raw = nf.read_text()
            fm, body = parse_frontmatter(raw)
            sources_this, body_no_sources = parse_sources_section(body)
            body_clean = strip_personal_notes(body_no_sources)
            body_clean = remove_contractions(body_clean)
            words = count_body_words(body_clean)
            total_words += words

            citation_style = merged_fm.get("citation_style", "APA")
            body_cited = convert_citations(body_clean, citation_style)
            broken = find_broken_citekeys(body_clean, all_sources)
            all_broken.extend(broken)

            latex_body = md_to_latex_body(body_cited)

            # Cache this chapter
            chapter_cache[cache_key] = {
                "latex_body": latex_body,
                "body_text": body_clean,
                "word_count": words,
            }
            combined_latex_body.append(latex_body)
            combined_body_text.append(body_clean)
            chapters_processed += 1

        # Update checksum
        checksums[str(nf)] = file_checksum(nf)

    save_checksums(state_dir, checksums)
    save_chapter_cache(state_dir, chapter_cache)

    # Update bib + memory
    update_bib_file(all_sources)
    update_thesis_context(merged_fm)
    update_sources_memory(all_sources)
    update_progress(all_notes)

    return {
        "file": "thesis/notes/ (all)",
        "trigger": "compile",
        "frontmatter": merged_fm,
        "body_text": "\n\n".join(combined_body_text),
        "latex_preamble": generate_preamble(merged_fm),
        "latex_body": "\n\n".join(combined_latex_body),
        "latex_suffix": generate_suffix(),
        "broken_citekeys": sorted(set(all_broken)),
        "word_count": total_words,
        "sources_count": len(all_sources),
        "changed": chapters_processed > 0,
        "chapters_cached": chapters_cached,
        "chapters_processed": chapters_processed,
        "warnings": fm_warnings,
    }

# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(json.dumps({"error": "Usage: preprocess.py <file> [--trigger CMD] | --checksums-only <file> | --compile-all"}))
        sys.exit(1)

    state_dir = PROJECT_ROOT / "scripts" / ".watcher-state"

    # Checksums-only mode
    if "--checksums-only" in args:
        target = Path(args[-1])
        if not target.is_absolute():
            target = PROJECT_ROOT / target
        if target.exists():
            checksums = load_checksums(state_dir)
            checksums[str(target)] = file_checksum(target)
            save_checksums(state_dir, checksums)
        return

    # Compile-all mode: process every notes file with caching
    if "--compile-all" in args:
        result = compile_all_chapters(state_dir)
        print(json.dumps(result, ensure_ascii=False))
        return

    # Normal single-file mode
    trigger = None
    if "--trigger" in args:
        idx = args.index("--trigger")
        trigger = args[idx + 1]
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    target_file = Path(args[0])
    if not target_file.is_absolute():
        target_file = PROJECT_ROOT / target_file

    notes_dir = PROJECT_ROOT / "thesis" / "notes"
    all_notes = sorted(notes_dir.glob("*.md"))

    if not target_file.exists():
        print(json.dumps({"error": f"File not found: {target_file}. Place your .md files in thesis/notes/"}))
        sys.exit(1)

    raw = target_file.read_text()

    # Empty file guard
    fm, body = parse_frontmatter(raw)
    body_stripped = body.strip()
    if not body_stripped:
        print(json.dumps({
            "error": "empty_body",
            "message": f"File {target_file.name} has no body text (only frontmatter or whitespace).",
            "file": target_file.name,
        }))
        sys.exit(0)  # Not a crash — just nothing to process

    # Check if file actually changed
    checksums = load_checksums(state_dir)
    current_ck = file_checksum(target_file)
    changed = checksums.get(str(target_file)) != current_ck
    checksums[str(target_file)] = current_ck
    save_checksums(state_dir, checksums)

    # Merge frontmatter from all notes files
    merged_fm = {}
    for nf in all_notes:
        nf_fm, _ = parse_frontmatter(nf.read_text())
        for k, v in nf_fm.items():
            if k not in merged_fm:
                merged_fm[k] = v
    merged_fm.update({k: v for k, v in fm.items() if v})  # current file overrides

    # Validate frontmatter
    fm_warnings = validate_frontmatter(merged_fm)

    # Collect all sources from all notes
    all_sources = []
    seen_keys = set()
    for nf in all_notes:
        nf_text = nf.read_text()
        _, nf_body = parse_frontmatter(nf_text)
        srcs, _ = parse_sources_section(nf_body)
        for s in srcs:
            if s["citekey"] not in seen_keys:
                all_sources.append(s)
                seen_keys.add(s["citekey"])

    # Also include sources from target file if it's not in notes/
    if target_file.parent != notes_dir:
        target_srcs, _ = parse_sources_section(body)
        for s in target_srcs:
            if s["citekey"] not in seen_keys:
                all_sources.append(s)
                seen_keys.add(s["citekey"])

    # Process target file body
    _, body_no_sources = parse_sources_section(body)
    body_no_notes = strip_personal_notes(body_no_sources)
    body_no_notes = remove_contractions(body_no_notes)

    citation_style = merged_fm.get("citation_style", "APA")
    body_citations_converted = convert_citations(body_no_notes, citation_style)
    broken_keys = find_broken_citekeys(body_no_notes, all_sources)

    latex_body = md_to_latex_body(body_citations_converted)
    latex_preamble = generate_preamble(merged_fm)

    update_bib_file(all_sources)
    update_thesis_context(merged_fm)
    update_sources_memory(all_sources)
    update_progress(all_notes)

    word_count = count_body_words(body_no_notes)

    result = {
        "file": str(target_file.relative_to(PROJECT_ROOT)),
        "trigger": trigger,
        "frontmatter": merged_fm,
        "body_text": body_no_notes,
        "latex_preamble": latex_preamble,
        "latex_body": latex_body,
        "latex_suffix": generate_suffix(),
        "broken_citekeys": broken_keys,
        "word_count": word_count,
        "sources_count": len(all_sources),
        "changed": changed,
        "warnings": fm_warnings,
    }

    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
