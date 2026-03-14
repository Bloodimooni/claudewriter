---
description: Check thesis text for plagiarism risk by searching key phrases online
argument-hint: [chapter-filename or omit for all]
allowed-tools: Read, Write, WebSearch, Glob
---

## Task: Plagiarism Risk Check

Read `memory/thesis-context.md` and `memory/sources.md` before proceeding.

## Step 1: Find Input Files

Use Glob to find all `.md` files in `thesis/notes/`.

If $ARGUMENTS is provided, filter to files whose name contains $ARGUMENTS.

Read each target file completely.

## Step 2: Extract Candidate Phrases

From the body text (skip frontmatter, `> Note to self:` lines, and everything under `## Sources`), identify phrases that are most at risk of matching published text:

**High priority candidates:**
- Any sentence or phrase of 8+ consecutive words that sounds polished, formal, or like a definition
- Sentences that directly introduce a concept or theory without a `@citekey` citation
- Technical definitions (e.g. "X is defined as...", "X refers to...")
- Any sentence that seems "too perfect" or doesn't match the informal surrounding text

**Lower priority (still check):**
- Specific statistics or data points
- Named results or theorems

Select up to **20 phrases**. Prefer longer and more specific phrases (they have higher discrimination power).

## Step 3: Search for Matches

For each phrase:

1. Use WebSearch with the phrase in double quotes for exact matching: `"[phrase]"`
2. Also try a broader version without quotes if the exact search returns nothing

Check the top results for:
- Exact or near-exact matches in academic papers, textbooks, or websites
- The source domain (academic journals and publishers are most relevant)

Record:
- **Phrase**: The text from the notes (first 80 characters)
- **Match found**: YES / NO / PARTIAL
- **Source**: If a match is found: publication/website name
- **URL**: If available from search results
- **Similarity estimate**: 0–100% (how closely the text matches)

## Step 4: Assign Risk Levels

For each phrase:

- **HIGH**: Match ≥80% AND no `@citekey` for this source in the surrounding text → potential unattributed copying
- **MEDIUM**: Match 40–79% OR match found but a `@citekey` is present nearby → may need paraphrasing or better attribution
- **LOW**: Match <40% OR no match found → acceptable

**Cross-reference `memory/sources.md`**: If a matched source already appears in the sources registry, the risk drops by one level (HIGH→MEDIUM, MEDIUM→LOW), because the student is aware of the source and likely just needs a proper inline citation.

## Step 5: Calculate Risk Score

```
Risk Score = 100 - (HIGH_count × 10) - (MEDIUM_count × 5)
Risk Score = max(0, min(100, Risk Score))
```

Risk category:
- 90–100: LOW risk — good
- 70–89: MODERATE risk — some attention needed
- 0–69: HIGH risk — significant revision required before submission

## Step 6: Write Report

Write to `thesis/output/plagiarism-report.md`:

```markdown
# Plagiarism Risk Report
Date: [TODAY]
File(s) checked: [filenames]
Risk Score: [X]/100 ([LOW/MODERATE/HIGH] overall risk)

## Summary
[2–3 sentences: how many phrases checked, how many at risk, overall assessment]

## Phrase Analysis

### Phrase 1
- **Text**: "[phrase, first 80 chars]"
- **Risk Level**: HIGH / MEDIUM / LOW
- **Match**: [source name, or "No significant match found"]
- **URL**: [if available]
- **Recommendation**: [Add @citekey citation / Paraphrase this passage / No action needed]

[repeat for all phrases checked]

## Required Actions
[Prioritized list of passages that MUST be addressed before submission]
```

## Step 7: Update Feedback History

Append to `memory/feedback-history.md`:
```
[DATE] Plagiarism check risk score: [X]/100. HIGH-risk phrases: [N], MEDIUM-risk: [N]. Action needed: [summary]
```

Report the risk score and path to `thesis/output/plagiarism-report.md` to the user.
