#!/usr/bin/env python3
"""
preprocess.py — Zero-token preprocessor for the thesis watcher.

Handles all deterministic work before any Claude API call:
  - Parse YAML frontmatter
  - Strip "Note to self" lines
  - Extract ## Sources section → BibTeX
  - Convert @citekey → LaTeX citation commands
  - Convert markdown structure → LaTeX structure
  - Generate full LaTeX preamble from frontmatter
  - Update memory files (thesis-context.md, sources.md, progress.md)
  - Check for broken citekeys

Usage:
  python3 scripts/preprocess.py <notes-file> [--trigger COMMAND] [--all-files]
  python3 scripts/preprocess.py --checksums-only <notes-file>

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
    Entry format: "- citekey: Author(s), "Title", Venue, Year"
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
        # A new ## heading ends the sources section
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

def source_to_bibtex(source: dict) -> str:
    """
    Converts a parsed source dict to a BibTeX entry.
    Heuristic type detection: article / book / inproceedings / misc
    """
    citekey = source["citekey"]
    raw = source["raw"]

    # Detect entry type from venue keywords
    entry_type = "misc"
    raw_lower = raw.lower()
    if any(k in raw_lower for k in ["journal", "review", "letters", "nature ", "science ", "ieee trans"]):
        entry_type = "article"
    elif any(k in raw_lower for k in ["conference", "proceedings", "workshop", "symposium", "icml", "neurips", "iclr", "cvpr"]):
        entry_type = "inproceedings"
    elif any(k in raw_lower for k in ["press", "publisher", "edition", "book"]):
        entry_type = "book"

    # Try to parse: Author(s), "Title", Venue, Year
    # Pattern: anything, "quoted title", venue, year
    year = ""
    year_m = re.search(r"\b(19|20)\d{2}\b", raw)
    if year_m:
        year = year_m.group(0)

    title = ""
    title_m = re.search(r'"([^"]+)"', raw)
    if title_m:
        title = title_m.group(1)

    # Authors: everything before the first comma+space+"  or the title
    authors_part = raw.split(',"')[0].split(',"')[0].strip().rstrip(",").strip()
    if title_m:
        authors_part = raw[:title_m.start()].strip().rstrip(",").strip()

    # Venue: between title and year
    venue = ""
    if title_m and year:
        between = raw[title_m.end():year_m.start()].strip().strip(",").strip()
        venue = between

    if entry_type == "article":
        return (f"@article{{{citekey},\n"
                f"  author  = {{{authors_part}}},\n"
                f"  title   = {{{title or raw}}},\n"
                f"  journal = {{{venue or 'UNKNOWN'}}},\n"
                f"  year    = {{{year or 'XXXX'}}},\n}}")
    elif entry_type == "inproceedings":
        return (f"@inproceedings{{{citekey},\n"
                f"  author    = {{{authors_part}}},\n"
                f"  title     = {{{title or raw}}},\n"
                f"  booktitle = {{{venue or 'UNKNOWN'}}},\n"
                f"  year      = {{{year or 'XXXX'}}},\n}}")
    elif entry_type == "book":
        return (f"@book{{{citekey},\n"
                f"  author    = {{{authors_part}}},\n"
                f"  title     = {{{title or raw}}},\n"
                f"  publisher = {{{venue or 'UNKNOWN'}}},\n"
                f"  year      = {{{year or 'XXXX'}}},\n}}")
    else:
        return (f"@misc{{{citekey},\n"
                f"  author = {{{authors_part}}},\n"
                f"  title  = {{{title or raw}}},\n"
                f"  year   = {{{year or 'XXXX'}}},\n"
                f"  note   = {{{venue}}},\n}}")

def update_bib_file(sources: list[dict]) -> None:
    """Appends new BibTeX entries to refs.bib; skips existing citekeys."""
    bib_path = PROJECT_ROOT / "thesis" / "bibliography" / "refs.bib"
    bib_path.parent.mkdir(parents=True, exist_ok=True)

    existing_keys = set()
    if bib_path.exists():
        content = bib_path.read_text()
        existing_keys = set(re.findall(r"@\w+\{(\S+?),", content))

    new_entries = []
    for src in sources:
        if src["citekey"] not in existing_keys:
            new_entries.append(source_to_bibtex(src))
            existing_keys.add(src["citekey"])

    if new_entries:
        with open(bib_path, "a") as f:
            f.write("\n" + "\n\n".join(new_entries) + "\n")

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
    "ieee": r"\cite",
    "mla": r"\cite",
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

        # Headings
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

        # Blockquote (non-personal-note)
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
    """Convert inline markdown (bold, italic, code) to LaTeX."""
    # Bold before italic (greedy issue otherwise)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"__(.+?)__", r"\\textbf{\1}", text)
    text = re.sub(r"\*(.+?)\*", r"\\textit{\1}", text)
    text = re.sub(r"_(.+?)_", r"\\textit{\1}", text)
    text = re.sub(r"`(.+?)`", r"\\texttt{\1}", text)
    return text

# ─── LaTeX preamble generator ──────────────────────────────────────────────

STYLE_MAP = {
    "apa": "apa",
    "chicago": "chicago-authordate",
    "ieee": "ieee",
    "mla": "mla",
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
        sources, clean_body = parse_sources_section(body)
        clean_body = strip_personal_notes(clean_body)
        # Strip headings and blank lines for word count
        word_lines = [l for l in clean_body.splitlines()
                      if l.strip() and not l.startswith("#")]
        words = sum(len(l.split()) for l in word_lines)
        total_words += words

        # Get chapter title from first # heading
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

# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(json.dumps({"error": "No arguments provided"}))
        sys.exit(1)

    state_dir = PROJECT_ROOT / "scripts" / ".watcher-state"

    # Checksums-only mode: just update checksums, no output
    if "--checksums-only" in args:
        target = Path(args[-1])
        if not target.is_absolute():
            target = PROJECT_ROOT / target
        checksums = load_checksums(state_dir)
        checksums[str(target)] = file_checksum(target)
        save_checksums(state_dir, checksums)
        return

    # Normal mode
    trigger = None
    if "--trigger" in args:
        idx = args.index("--trigger")
        trigger = args[idx + 1]
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    all_files_mode = "--all-files" in args
    args = [a for a in args if a != "--all-files"]

    target_file = Path(args[0])
    if not target_file.is_absolute():
        target_file = PROJECT_ROOT / target_file

    # Collect all notes files for memory updates
    notes_dir = PROJECT_ROOT / "thesis" / "notes"
    all_notes = sorted(notes_dir.glob("*.md"))

    # Read target file
    if not target_file.exists():
        print(json.dumps({"error": f"File not found: {target_file}"}))
        sys.exit(1)

    raw = target_file.read_text()

    # Check if file actually changed
    checksums = load_checksums(state_dir)
    current_ck = file_checksum(target_file)
    changed = checksums.get(str(target_file)) != current_ck
    checksums[str(target_file)] = current_ck
    save_checksums(state_dir, checksums)

    # Parse
    fm, body = parse_frontmatter(raw)

    # Collect frontmatter from all files (first file with a key wins)
    merged_fm = {}
    for nf in all_notes:
        nf_fm, _ = parse_frontmatter(nf.read_text())
        for k, v in nf_fm.items():
            if k not in merged_fm:
                merged_fm[k] = v
    merged_fm.update({k: v for k, v in fm.items() if v})  # current file overrides

    # Extract sources from ALL notes files
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

    # Process target file body
    sources_this_file, body_no_sources = parse_sources_section(body)
    body_no_notes = strip_personal_notes(body_no_sources)

    citation_style = merged_fm.get("citation_style", "APA")
    body_citations_converted = convert_citations(body_no_notes, citation_style)
    broken_keys = find_broken_citekeys(body_no_notes, all_sources)

    # Convert markdown structure to LaTeX (NOT language formalized)
    latex_body = md_to_latex_body(body_citations_converted)

    # Generate preamble
    latex_preamble = generate_preamble(merged_fm)

    # Update BibTeX file
    update_bib_file(all_sources)

    # Update memory files
    update_thesis_context(merged_fm)
    update_sources_memory(all_sources)
    update_progress(all_notes)

    # Word count (body only, no headings/blank lines)
    word_lines = [l for l in body_no_notes.splitlines()
                  if l.strip() and not l.startswith("#")]
    word_count = sum(len(l.split()) for l in word_lines)

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
    }

    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
