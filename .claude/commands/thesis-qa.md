---
description: Quality assurance — score the compiled thesis and auto-improve until it meets the 75/100 threshold
argument-hint: [chapter-name or omit for full thesis]
allowed-tools: Read, Write, Edit, Bash, Glob
---

## Task: Quality Assurance

Read `memory/thesis-context.md`, `memory/sources.md`, and `memory/feedback-history.md` before doing anything else.

## Setup

```
ITERATION = 1
MAX_ITERATIONS = 3
THRESHOLD = 75
```

---

## ITERATION LOOP

Repeat the following block, incrementing ITERATION each cycle, until the score meets the threshold or MAX_ITERATIONS is reached.

---

### Phase A: Ensure a Compiled Document Exists

Read `thesis/output/main.tex`.

If the file does not exist or is empty:
- Tell the user that `/thesis-compile` needs to be run first (or run it now if you have permission), then stop.

### Phase B: Score the Compiled Document

Read `thesis/output/main.tex` in full. Score it on **four dimensions of 25 points each** (total = 100):

---

#### Dimension 1: Formatting (0–25 points)

Start at 25. Deduct for each issue found:

- Missing `\documentclass` declaration: −10
- Missing `\begin{document}` / `\end{document}`: −10
- Missing title page: −5
- Missing `\tableofcontents`: −3
- Missing `\printbibliography`: −5
- Wrong or missing biblatex style (should match `citation_style` from memory): −5
- Line spacing (`\setstretch`) not set per frontmatter: −3
- Margin (`\geometry`) not set per frontmatter: −3
- Font size not set in `\documentclass` options: −2
- Unclosed LaTeX environments or obvious syntax errors: −5 each (cap at −10)
- `\usepackage{fontspec}` missing (required for xelatex): −3

Floor at 0.

---

#### Dimension 2: Language Quality (0–25 points)

Start at 25. Deduct for each issue found:

- Each contraction found (don't, can't, it's, won't, I'm, etc.): −2 each (cap at −10)
- Each colloquialism or informal phrase: −2 each (cap at −8)
- Inconsistent tense within a chapter: −3
- First-person singular ("I think", "I believe") used outside abstract/introduction where discipline allows it: −3
- Unclear or run-on sentences: −1 each (cap at −5)

Floor at 0.

---

#### Dimension 3: Structure (0–25 points)

Start at 25. Deduct for each issue found:

- A chapter (`\chapter`) with no introductory paragraph (first paragraph should orient the reader): −5
- A chapter with no concluding/summary paragraph: −5
- Heading hierarchy broken (e.g. `\subsection` appears without a parent `\section`): −5
- Table of contents present but chapters are missing content: −3
- Logical flow issues: a section references something not yet introduced: −3 each (cap at −6)
- Abstract missing (if the document has more than 1 chapter): −4

Floor at 0.

---

#### Dimension 4: Citation Compliance (0–25 points)

Start at 25. Deduct for each issue found:

- Factual claim (number, named study, specific result) with no `\parencite{}` or `\cite{}`: −3 each (cap at −12)
- A `\parencite{key}` or `\cite{key}` whose `key` does not appear in `thesis/bibliography/refs.bib`: −4 each (cap at −12)
- Inconsistent citation command usage (mixing `\cite` and `\parencite` without reason): −3
- `\printbibliography` missing: −5

Cross-check citekeys by reading `thesis/bibliography/refs.bib`.

Floor at 0.

---

### Phase C: Record Scores

Total score = Dimension 1 + Dimension 2 + Dimension 3 + Dimension 4.

Append to `memory/feedback-history.md`:
```
[DATE] QA Iteration [ITERATION]/[MAX_ITERATIONS]:
  Total=[SCORE]/100 | Formatting=[D1]/25 | Language=[D2]/25 | Structure=[D3]/25 | Citations=[D4]/25
  Issues: [one-line summary of the main problems]
```

---

### Phase D: Decision

**If SCORE ≥ THRESHOLD:**
- Report success with the breakdown
- Tell the user the thesis meets quality standards
- Stop the loop entirely

**If SCORE < THRESHOLD AND ITERATION ≥ MAX_ITERATIONS:**
- Report the final score with breakdown
- List every specific remaining issue that needs manual attention
- Tell the user these items require manual revision in their notes or in `thesis/output/main.tex`
- Stop the loop entirely

**If SCORE < THRESHOLD AND ITERATION < MAX_ITERATIONS:**
- Proceed to Phase E (fix and retry)

---

### Phase E: Apply Fixes

Generate a specific fix plan for every deduction identified in Phase B. For each fix:

1. Identify the **exact location** in `main.tex` (section name, line content, or surrounding text)
2. State the **specific change** to make
3. Apply the change using Edit on `thesis/output/main.tex`

Fix all identified issues in a single pass. After all edits:

- Check if LaTeX is available: `which xelatex 2>/dev/null || which pdflatex 2>/dev/null || echo "NOT_FOUND"`
- If available: `cd thesis/output && latexmk -xelatex -interaction=nonstopmode main.tex 2>&1 | tail -20`
  - If new compilation errors appear, fix them in `main.tex` and recompile once more

Increment ITERATION. Return to Phase A.

---

## Final Summary to User

After the loop ends (for any reason), output:

- Total iterations run
- Score at each iteration (showing improvement)
- List of all improvements made automatically
- Any remaining issues that require the user to update their notes or manually revise the LaTeX
- Next recommended action (e.g. "Run `/thesis-fact-check` to verify claims" or "Add more content to Chapter 2")
