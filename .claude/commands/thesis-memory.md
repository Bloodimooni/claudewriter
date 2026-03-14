---
description: Scan thesis notes and build/refresh all memory context files
argument-hint: [notes-file or omit for all]
allowed-tools: Read, Write, Edit, Glob
---

## Task: Build Thesis Memory

Read and synthesize all thesis notes to populate the memory files that every other thesis command depends on. Run this after writing or significantly changing any notes file.

## Step 1: Find Notes

Use Glob to find all `.md` files in `thesis/notes/`. If $ARGUMENTS is provided, filter to files matching that name.

If no files are found in `thesis/notes/`, tell the user to place their chapter markdown files there (using `thesis/template.md` as a guide) and stop.

Read every found notes file completely.

Also read the existing memory files if they exist:
- `memory/thesis-context.md`
- `memory/sources.md`
- `memory/progress.md`

## Step 2: Extract Thesis Context

From the notes, identify:

- **Title**: `title` key in any YAML frontmatter
- **Author**: `author` frontmatter key
- **University, supervisor, date**: corresponding frontmatter keys
- **Formatting rules**: all frontmatter keys (`citation_style`, `line_spacing`, `font_size`, `margin`, `language`)
- **Research question**: Look for it explicitly stated (often in the introduction, e.g. "This thesis investigates..." or "The research question is..."). If not explicit, infer it from the chapter topics.
- **Key arguments**: The 3–5 main claims the thesis makes. Look for thesis statements, section topic sentences, and conclusions.
- **Academic discipline**: Infer from topic, terminology, and citation patterns.

Write (overwrite) `memory/thesis-context.md`:

```
# Thesis Context
Last updated: [TODAY'S DATE]

## Metadata
- Title: [title]
- Author: [author]
- University: [university]
- Supervisor: [supervisor]
- Submission date: [date]

## Research Question
[The central research question, explicit or inferred]

## Key Arguments
1. [Argument 1]
2. [Argument 2]
3. [Argument 3]

## Formatting Rules
- Citation style: [value]
- Line spacing: [value]
- Font size: [value]
- Margin: [value]
- Language: [value]

## Academic Discipline
[e.g. Computer Science, Medicine, Economics]
```

## Step 3: Extract and Update Sources

Scan all `## Sources` sections across all notes files. Each entry has the format:
```
- citekey: Author(s), "Title", Venue, Year
```

Compile a deduplicated list (by citekey). For each source, generate a BibTeX entry. Infer `@article`, `@book`, `@inproceedings`, or `@misc` from the venue description.

Preserve any entries already in `memory/sources.md` that are marked VERIFIED. Mark all new entries UNVERIFIED.

Write (overwrite) `memory/sources.md`:

```
# Sources Registry
Last updated: [TODAY'S DATE]

## Source Table
| Citekey | Authors | Title | Venue | Year | Status |
|---------|---------|-------|-------|------|--------|
| [key] | [authors] | [title] | [venue] | [year] | UNVERIFIED |

## BibTeX Entries
[bibtex entries here, one per source]
```

## Step 4: Update Progress

For each notes file, count approximate body word count (exclude frontmatter lines, `> Note to self:` lines, `## Sources` section lines, and blank lines).

Determine chapter status:
- DRAFT: file exists but has fewer than 200 body words
- IN_PROGRESS: 200–800 body words
- COMPLETE: 800+ body words

Write (overwrite) `memory/progress.md`:

```
# Writing Progress
Last updated: [TODAY'S DATE]

## Chapter Status
| File | Chapter Title | Word Count | Status |
|------|--------------|------------|--------|
| [filename] | [first # heading text] | [~N words] | DRAFT/IN_PROGRESS/COMPLETE |

## Totals
- Total chapters: [N]
- Total body word count: [N]
```

## Step 5: Preserve Feedback History

Do NOT overwrite `memory/feedback-history.md`. It is strictly append-only. If it does not exist, create it with just this header:

```
# Feedback History
Append-only log of QA, fact-check, and plagiarism check results.
```

## Step 6: Report

Tell the user:
- How many notes files were scanned
- Total unique sources found
- Total body word count across all chapters
- Any inconsistencies noticed (e.g. conflicting frontmatter values across files, citekeys used in text but missing from `## Sources`)
- The path to each updated memory file
