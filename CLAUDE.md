# Thesis Writing System

This project converts informal markdown notes into a formal academic LaTeX thesis.

## Directory Layout
- `thesis/notes/` — User's chapter markdown files (source of truth; never auto-generated)
- `thesis/output/` — Generated `.tex` and `.pdf` files (do not edit manually)
- `thesis/bibliography/` — Generated `refs.bib` BibTeX file
- `memory/` — Persistent context files; **read these before any thesis work**

## Memory Files (always read before compiling or checking)
- `memory/thesis-context.md` — Thesis topic, research question, key arguments, formatting rules
- `memory/sources.md` — All cited sources with BibTeX keys and verification status
- `memory/progress.md` — Chapter status and word counts
- `memory/feedback-history.md` — Past QA/fact-check results (append-only)

## Note File Syntax
- `@citekey` — Inline citation. Converts to `\parencite{citekey}` (APA/Chicago) or `\cite{citekey}` (IEEE/MLA)
- `> Note to self: ...` — Personal reminder. Strip entirely from output; never appears in LaTeX
- `## Sources` section at end of file — Parse into BibTeX entries; remove from body text
- Name files like `01-introduction.md`, `02-background.md` for correct chapter ordering

## Frontmatter Keys → LaTeX Mapping
| Key | LaTeX Effect |
|-----|-------------|
| `citation_style: APA` | `\usepackage[style=apa]{biblatex}` |
| `citation_style: Chicago` | `\usepackage[style=chicago-authordate]{biblatex}` |
| `citation_style: IEEE` | `\usepackage[style=ieee]{biblatex}` |
| `citation_style: MLA` | `\usepackage[style=mla]{biblatex}` |
| `line_spacing: 1.5` | `\setstretch{1.5}` via `setspace` package |
| `font_size: 12pt` | `\documentclass[12pt,...]{report}` |
| `margin: 2.5cm` | `\geometry{margin=2.5cm}` |
| `language: english` | `\usepackage[english]{babel}` |

## LaTeX Engine
- Preferred: `xelatex` (handles UTF-8 and umlauts natively via `fontspec`)
- Fallback: `pdflatex`
- Build: `cd thesis/output && latexmk -xelatex -interaction=nonstopmode main.tex`
- Install on CachyOS/Arch: `sudo pacman -S texlive-full`

## Quality Standards
- Formal academic register: no contractions, no colloquialisms
- Every factual claim must have an inline citation
- Each chapter needs an introductory and a concluding paragraph
- LaTeX must compile without errors before declaring success

## Available Commands
| Command | Purpose |
|---------|---------|
| `/thesis-memory` | Build/refresh memory from notes (run first after writing) |
| `/thesis-compile` | Convert notes → LaTeX thesis |
| `/thesis-fact-check` | Verify claims via web search |
| `/thesis-plagiarism` | Check phrases for plagiarism risk |
| `/thesis-qa` | Quality score + auto-improve loop (threshold: 75/100) |
