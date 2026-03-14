---
description: Convert thesis markdown notes into a LaTeX document (and PDF if LaTeX is installed)
argument-hint: [chapter-name or omit for all chapters]
allowed-tools: Read, Write, Edit, Glob, Bash
---

## Task: Compile Thesis to LaTeX

Read `memory/thesis-context.md`, `memory/sources.md`, and `memory/progress.md` before doing anything else. These files contain the formatting rules and context needed for compilation.

## Step 1: Find Input Files

Use Glob to list all `.md` files in `thesis/notes/` sorted by filename (so `01-*.md` comes before `02-*.md`).

If $ARGUMENTS is provided, only process files whose name contains $ARGUMENTS.

If no files are found, stop and tell the user to place notes in `thesis/notes/` using `thesis/template.md` as a guide.

## Step 2: Parse Each File

For each notes file, do the following:

**a) Extract frontmatter**: Read the YAML block between the opening and closing `---`. Collect all key-value pairs. If a file has no frontmatter, use the values from `memory/thesis-context.md`.

**b) Extract sources section**: Find the `## Sources` heading and everything below it. Save these lines separately for Step 3. Remove this entire section from the body text.

**c) Strip personal notes**: Remove every line that matches `> Note to self:.*` — do not include these in any output.

**d) Convert inline citations**:
- For APA or Chicago citation style: replace `@citekey` with `\parencite{citekey}`
- For IEEE, MLA, or numeric styles: replace `@citekey` with `\cite{citekey}`
- The citation style comes from the `citation_style` frontmatter value (or memory/thesis-context.md)

**e) Convert markdown to LaTeX body**:
- `# Heading` → `\chapter{Heading}`
- `## Heading` → `\section{Heading}`
- `### Heading` → `\subsection{Heading}`
- `#### Heading` → `\subsubsection{Heading}`
- `**text**` → `\textbf{text}`
- `*text*` → `\textit{text}`
- Unordered list (`- item`) → `\begin{itemize}\n  \item item\n\end{itemize}`
- Ordered list (`1. item`) → `\begin{enumerate}\n  \item item\n\end{enumerate}`
- Fenced code block → `\begin{lstlisting}\n...\n\end{lstlisting}`
- Inline code → `\texttt{code}`
- `---` horizontal rule → `\hrule`
- `> blockquote` (that is NOT a Note to self) → `\begin{quote}...\end{quote}`
- Blank lines between paragraphs → `\n\n` (LaTeX paragraph break)

**f) Formalize language**: Review the converted body text. Replace informal phrasing with formal academic language:
- Remove contractions (don't→do not, can't→cannot, it's→it is, etc.)
- Replace colloquialisms with precise academic alternatives
- Ensure third-person perspective unless discipline convention requires first-person
- Keep the meaning and all citations intact — only improve register

## Step 3: Build Bibliography

Parse the `## Sources` section lines from all files. Each line has the format:
```
- citekey: Author(s), "Title", Venue, Year
```

For each entry, generate a BibTeX record. Use these heuristics to pick the entry type:
- Contains "journal", "proceedings", or appears to be a journal article → `@article`
- Contains "book" or is clearly a monograph → `@book`
- Contains "conference", "workshop", "symposium" → `@inproceedings`
- Otherwise → `@misc`

Read `thesis/bibliography/refs.bib` if it exists. Append only new entries (deduplicate by citekey — do not overwrite existing entries).

Write the result to `thesis/bibliography/refs.bib`.

## Step 4: Determine LaTeX Settings

Use these values from frontmatter (or memory/thesis-context.md as fallback):

| Setting | Value | Default |
|---------|-------|---------|
| `font_size` | from frontmatter | `12pt` |
| `margin` | from frontmatter | `2.5cm` |
| `line_spacing` | from frontmatter | `1.5` |
| `language` | from frontmatter | `english` |
| `citation_style` | from frontmatter | `APA` |
| `title`, `author`, `university`, `supervisor`, `date` | from frontmatter | — |

Citation style → biblatex style:
- APA → `apa`
- Chicago → `chicago-authordate`
- IEEE → `ieee`
- MLA → `mla`
- (any other) → `apa`

## Step 5: Generate main.tex

Write `thesis/output/main.tex` with this structure (substitute all [PLACEHOLDERS] with actual values):

```latex
\documentclass[[FONT_SIZE],a4paper]{report}

% Encoding and fonts (xelatex)
\usepackage{fontspec}
\usepackage{microtype}

% Language
\usepackage[[LANGUAGE]]{babel}

% Page geometry
\usepackage{geometry}
\geometry{margin=[MARGIN]}

% Line spacing
\usepackage{setspace}
\setstretch{[LINE_SPACING]}

% Bibliography
\usepackage[style=[BIBLATEX_STYLE],backend=biber]{biblatex}
\addbibresource{../bibliography/refs.bib}

% Links
\usepackage[hidelinks]{hyperref}

% Code listings
\usepackage{listings}
\usepackage{xcolor}
\lstset{basicstyle=\ttfamily\small,breaklines=true,frame=single}

% Graphics
\usepackage{graphicx}
\usepackage{booktabs}

% Title metadata
\title{[TITLE]}
\author{[AUTHOR]}
\date{[DATE]}

\begin{document}

% Title page
\begin{titlepage}
  \centering
  \vspace*{3cm}
  {\Huge\bfseries [TITLE]\par}
  \vspace{2cm}
  {\large Bachelor's Thesis\par}
  \vspace{1cm}
  {\large [AUTHOR]\par}
  \vspace{0.5cm}
  {\large [UNIVERSITY]\par}
  \vspace{0.5cm}
  {Supervisor: [SUPERVISOR]\par}
  \vfill
  {\large [DATE]\par}
\end{titlepage}

\tableofcontents
\newpage

% ---- CHAPTERS ----
[ALL COMPILED CHAPTER BODIES, in file order]
% ---- END CHAPTERS ----

\printbibliography[heading=bibintoc]

\end{document}
```

## Step 6: Attempt Compilation

Check for a LaTeX engine:
```
which xelatex 2>/dev/null || which pdflatex 2>/dev/null || echo "NOT_FOUND"
```

**If a LaTeX engine is found:**
Run: `cd thesis/output && latexmk -xelatex -interaction=nonstopmode main.tex 2>&1 | tail -30`

If compilation succeeds (exit code 0):
- Report the PDF path: `thesis/output/main.tex`
- If warnings exist, summarize them briefly

If compilation fails:
- Read the error output, identify the specific problem
- Fix it in `main.tex` using Edit
- Retry compilation once
- If it still fails, report the error to the user with the exact LaTeX error message

**If no LaTeX engine is found:**
Write the `.tex` file as planned, then tell the user:
> LaTeX is not installed. `thesis/output/main.tex` has been generated. To compile it to PDF, install TeX Live:
> - CachyOS/Arch: `sudo pacman -S texlive-full`
> - Debian/Ubuntu: `sudo apt install texlive-full`
> Then run `/thesis-compile` again.

## Step 7: Update Progress

Append a line to `memory/progress.md`:
```
[DATE] Compiled: [list of chapter files] → thesis/output/main.tex
```

Report to the user: which files were compiled, total chapters, whether a PDF was produced, and any warnings.
