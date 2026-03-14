# claudewriter

A thesis writing system built on [Claude Code](https://claude.ai/claude-code). Write informal notes in your editor — Claude converts them into a formal, properly-cited LaTeX thesis.

The idea: focus on **learning the material**, not on academic writing conventions. You write what you understand. The system handles formalization, citation formatting, LaTeX structure, fact-checking, plagiarism risk, and quality scoring.

---

## How It Works

You write markdown notes in `thesis/notes/`. When you're ready to process them, you either run a slash command in Claude Code or add a trigger line to your notes file and let the background watcher handle it automatically.

```
You write:                        The system produces:
─────────────────────────────     ──────────────────────────────────
Informal notes in markdown    →   Formal academic LaTeX
@citekey inline citations     →   \parencite{} / \cite{} + refs.bib
## Sources section            →   BibTeX entries
> Note to self: ...           →   (stripped — never in output)
Frontmatter rules             →   LaTeX packages, spacing, margins
```

### Two Ways to Trigger Processing

**Option A — Claude Code slash commands**:
```
/thesis-memory       rebuild memory from your notes
/thesis-compile      generate LaTeX (and PDF if LaTeX is installed)
/thesis-fact-check   verify claims via web search
/thesis-plagiarism   check for plagiarism risk
/thesis-qa           score quality and auto-improve (loops up to 3×)
```

**Option B — Background watcher**:

Start the watcher once:
```sh
./scripts/start-watcher.sh
```

Then write a trigger line anywhere in a notes file and save it:
```markdown
/claude:compile
```

The watcher detects the save, processes the file, and replaces the trigger with a done marker:
```markdown
<!-- claude:compile ✓ 2026-03-14 15:30 | main.tex updated -->
```

---

## Installation

### Requirements

| Tool | Purpose | Install (CachyOS/Arch) |
|------|---------|----------------------|
| [Claude Code](https://claude.ai/claude-code) | AI slash commands + watcher AI calls | See below |
| Python 3 | Zero-token preprocessing | Pre-installed |
| inotify-tools | File watching | `sudo pacman -S inotify-tools` |
| TeX Live (optional) | PDF compilation | `sudo pacman -S texlive-full` |

> TeX Live is optional. Without it, the system still generates a `.tex` file. Install it to also get a PDF.

### Install Claude Code

```sh
npm install -g @anthropic-ai/claude-code
```

Then authenticate:
```sh
claude
```

Follow the login prompt. Claude Code is required for the AI steps (language formalization, fact-checking, QA scoring). The background watcher calls it non-interactively via `claude --print`.

### Clone / Set Up This Project

```sh
git clone <repo-url> claudewriter
cd claudewriter
chmod +x scripts/*.sh
```

That's it. No `npm install`, no virtual environment, no build step.

---

## Writing Your First Chapter

### Step 1 — Copy the template

```sh
cp thesis/template.md thesis/notes/01-introduction.md
```

### Step 2 — Write your notes

Open the file in your editor. The top section (frontmatter) sets global formatting rules — fill these in once:

```markdown
---
title: "The Effect of Sleep on Memory Consolidation"
author: "Joshua"
citation_style: APA
line_spacing: 1.5
font_size: 12pt
margin: 2.5cm
language: english
university: "TU Berlin"
supervisor: "Prof. Dr. Schmidt"
date: "March 2026"
---
```

Then write your content informally. You don't need perfect sentences:

```markdown
# Chapter 1: Introduction

Sleep is really important for memory. Walker et al. showed that REM sleep
consolidates procedural memory (@walker_2017). The hippocampus replays memories
during slow-wave sleep and transfers them to the cortex.

> Note to self: Find a study on sleep deprivation and exam performance

## Sources
- walker_2017: Walker, M., "Why We Sleep", Scribner, 2017
```

**Syntax cheatsheet:**

| What you write | What it becomes |
|----------------|----------------|
| `@walker_2017` | `\parencite{walker_2017}` (APA) or `\cite{walker_2017}` (IEEE) |
| `> Note to self: ...` | Stripped entirely — never appears in output |
| `## Sources` section | Parsed into BibTeX, removed from body |
| `# Heading` | `\chapter{Heading}` |
| `## Heading` | `\section{Heading}` |
| `**bold**` | `\textbf{bold}` |
| `*italic*` | `\textit{italic}` |

Name your files with a numeric prefix so chapters compile in order:
```
01-introduction.md
02-background.md
03-methodology.md
...
```

Only the first file needs frontmatter. Other files can omit it and will inherit the settings from `memory/thesis-context.md`.

### Step 3 — Process your notes

**With the background watcher** (recommended when writing):

```sh
./scripts/start-watcher.sh   # run once, leave it running
```

Add a trigger line to your notes file and save:

```markdown
/claude:all    ← triggers: memory → compile → fact-check + plagiarism → qa
```

Or use individual triggers:

```markdown
/claude:memory    ← just rebuild memory files (fast, ~0 tokens)
/claude:compile   ← generate LaTeX only
/claude:check     ← fact-check + plagiarism only
/claude:qa        ← quality score + auto-fix only
```

**With Claude Code** (when you already have it open):

```
/thesis-memory
/thesis-compile
/thesis-fact-check
/thesis-plagiarism
/thesis-qa
```

### Step 4 — Check the output

- `thesis/output/main.tex` — generated LaTeX document
- `thesis/output/main.pdf` — compiled PDF (if LaTeX is installed)
- `thesis/output/check-report.md` — fact-check and plagiarism report
- `memory/feedback-history.md` — log of all QA scores over time

---

## Project Structure

```
claudewriter/
│
├── thesis/
│   ├── notes/              ← YOUR WRITING GOES HERE (.md files)
│   ├── template.md         ← copy this to notes/ to start a chapter
│   ├── output/             ← generated main.tex and main.pdf
│   └── bibliography/       ← generated refs.bib (auto-managed)
│
├── memory/                 ← auto-managed context files (don't edit manually)
│   ├── thesis-context.md   ← thesis metadata + formatting rules
│   ├── sources.md          ← all cited sources
│   ├── progress.md         ← chapter word counts and status
│   └── feedback-history.md ← QA and check history (append-only)
│
├── scripts/
│   ├── watcher.sh          ← background file watcher (inotifywait loop)
│   ├── preprocess.py       ← zero-token preprocessor (parsing, BibTeX, LaTeX structure)
│   ├── start-watcher.sh    ← start the watcher in the background
│   └── stop-watcher.sh     ← stop the watcher
│
├── .claude/
│   ├── commands/           ← Claude Code slash commands (thesis-*.md)
│   └── settings.local.json ← tool permissions for this project
│
└── CLAUDE.md               ← project instructions loaded into every Claude session
```

---

## How the System Saves Tokens

The watcher script (`scripts/preprocess.py`) does as much as possible in pure Python before ever calling Claude. Claude only handles the parts that actually need AI.

| Task | What Python does (0 tokens) | What Claude does |
|------|-----------------------------|-----------------|
| `memory` | Parse frontmatter, extract sources, count words, write all 3 memory files | Infer research question from content (optional) |
| `compile` | Generate full LaTeX preamble, convert markdown structure, build BibTeX | Formalize informal language to academic register |
| `check` | — | Fact-check claims + plagiarism search via WebSearch |
| `qa` | Run `latexmk` compilation | Score quality, apply fixes |

Running the full `/claude:all` pipeline costs approximately **8,000–18,000 tokens** per chapter. The naive approach (no preprocessing, loading all files every time) would cost 3–5× more.

The watcher also:
- **Debounces** saves (waits 2s after the last write event before processing)
- **Locks** against concurrent Claude calls (one at a time)
- **Tracks checksums** to detect when files actually changed
- **Replaces triggers immediately** after detection, so a trigger never fires twice

---

## Slash Commands Reference

All commands work in Claude Code when run from this project directory.

### `/thesis-memory`
Scans all notes files and rebuilds the memory context. Run this first, and after writing new content.

- Extracts thesis metadata, research question, key arguments, formatting rules
- Updates `memory/thesis-context.md`, `memory/sources.md`, `memory/progress.md`
- Never overwrites `memory/feedback-history.md` (append-only)

### `/thesis-compile [chapter-name]`
Converts notes to LaTeX and compiles to PDF (if LaTeX is installed).

- Reads all memory files for context and formatting rules
- Strips personal notes, extracts sources section, converts citations
- Converts markdown structure to LaTeX
- Rewrites informal language to formal academic register
- Generates `thesis/output/main.tex`
- Attempts `xelatex` → fallback `pdflatex` → graceful message if neither installed

Pass a chapter name to compile only that file:
```
/thesis-compile 02-background
```

### `/thesis-fact-check [chapter-name]`
Verifies factual claims in your notes using web search.

- Extracts up to 15 specific factual claims from the body text
- Searches the web for each claim
- Assigns verdicts: CONFIRMED / UNCONFIRMED / CONTRADICTED / NEEDS_CITATION
- Scores overall accuracy (0–100)
- Writes `thesis/output/fact-check-report.md`

### `/thesis-plagiarism [chapter-name]`
Checks for plagiarism risk by searching key phrases online.

- Extracts up to 20 phrases (8+ words, formal/specific language)
- Searches each phrase in quotes
- Risk levels: HIGH (>80% match, no citation) / MEDIUM / LOW
- Risk Score = 100 − (HIGH × 10) − (MEDIUM × 5)
- Writes `thesis/output/plagiarism-report.md`

### `/thesis-qa`
Quality assurance: scores the compiled LaTeX and auto-improves it.

- Scores on 4 dimensions (25 points each): Formatting, Language Quality, Structure, Citation Compliance
- If score < 75: applies fixes directly to `main.tex`, recompiles, repeats (max 3 iterations)
- If score ≥ 75 or max iterations reached: reports final score and remaining issues
- Appends all scores to `memory/feedback-history.md`

---

## Watcher Reference

### Start / Stop

```sh
./scripts/start-watcher.sh   # start in background
./scripts/stop-watcher.sh    # stop
```

The watcher log is at `scripts/.watcher-state/watcher.log`.

### Trigger Syntax

Add one of these lines to any `.md` file in `thesis/notes/` and save:

| Trigger | What happens |
|---------|-------------|
| `/claude:memory` | Rebuild memory files. Fast, usually 0 tokens. |
| `/claude:compile` | Formalize language + generate LaTeX + compile PDF |
| `/claude:check` | Fact-check + plagiarism risk report |
| `/claude:qa` | Quality score + auto-fix loop |
| `/claude:all` | Full pipeline: memory → compile → check → qa |

After processing, the trigger line is replaced with a timestamped done marker:
```
<!-- claude:compile ✓ 2026-03-14 15:30 | main.tex updated -->
```

The watcher runs in the background and survives across editor restarts. Restart it after a reboot with `./scripts/start-watcher.sh`.

---

## Citation Style Support

Set `citation_style` in your frontmatter:

| Value | biblatex package | Citation command |
|-------|-----------------|-----------------|
| `APA` | `style=apa` | `\parencite{key}` |
| `Chicago` | `style=chicago-authordate` | `\parencite{key}` |
| `IEEE` | `style=ieee` | `\cite{key}` |
| `MLA` | `style=mla` | `\cite{key}` |

---

## Troubleshooting

**Watcher doesn't start**
- Check that `inotify-tools` is installed: `which inotifywait`
- Check the log: `cat scripts/.watcher-state/watcher.log`

**`/claude:compile` fires but no Claude call is made**
- The `claude` CLI must be in your PATH: `which claude`
- If not found, the watcher still generates the `.tex` file but skips language formalization

**LaTeX compilation fails**
- Check `scripts/.watcher-state/watcher.log` for the LaTeX error
- Common fix: ensure all `@citekey` references have a matching entry in `## Sources`
- The watcher will warn about broken citekeys before attempting compilation

**`/claude:all` is too slow / too many tokens**
- Use individual triggers instead: `/claude:compile` for most saves, `/claude:check` and `/claude:qa` only when you've written a full section
- The `memory` trigger is always fast (near 0 tokens)

**PDF not generated**
- Install TeX Live: `sudo pacman -S texlive-full`
- Then run `/claude:compile` or `/claude:all` again

---

## Tips for Writing

- Write the way you'd explain it to a friend. The system handles formalization.
- Use `> Note to self: ...` freely — it never appears in the output.
- Add sources as you go in the `## Sources` section. Better to have too many than too few.
- Run `/claude:memory` frequently (it's nearly free). Run `/claude:check` and `/claude:qa` when you've finished a section.
- Don't worry about precise academic phrasing — that's the system's job. Your job is getting the ideas and citations right.
