---
description: Verify factual claims in thesis notes using web search and produce a scored report
argument-hint: [chapter-filename or omit for all]
allowed-tools: Read, Write, WebSearch, Glob
---

## Task: Fact-Check Thesis Claims

Read `memory/thesis-context.md` and `memory/sources.md` before proceeding.

## Step 1: Find Input Files

Use Glob to find all `.md` files in `thesis/notes/`.

If $ARGUMENTS is provided, filter to files whose name contains $ARGUMENTS.

Read each target file completely.

## Step 2: Extract Verifiable Claims

From the body text of each file, identify sentences that make factual assertions — statements about the world that can be looked up. Good candidates:

- Statistics and percentages ("X% of patients...")
- Named research results ("LeCun et al. showed that...")
- Historical claims ("The first neural network was built in...")
- Technical claims ("Algorithm X runs in O(n log n) time...")
- Definitions of terms ("Overfitting refers to...")

**Skip:**
- Lines starting with `> Note to self:` — these are personal reminders
- Lines in the `## Sources` section — these are bibliography entries, not claims
- Pure structural text (headings, "This chapter will discuss...", transition sentences)

Collect up to **15** of the most specific and checkable claims. Prioritize claims with numbers, specific author names, or concrete results.

## Step 3: Verify Each Claim via Web Search

For each claim:

1. Formulate a search query from the key elements of the claim (don't just paste the sentence — extract the key terms)
2. Use WebSearch to find corroborating or contradicting sources
3. Examine the results

Assign a verdict:
- **CONFIRMED**: Multiple reliable sources support the claim as stated
- **UNCONFIRMED**: No clear sources found; the claim may be true but could not be verified
- **CONTRADICTED**: Sources found that directly contradict the claim
- **NEEDS_CITATION**: Claim appears correct but has no `@citekey` attached to it in the notes

Assign a **confidence score** (0–100):
- 90–100: Found directly in an authoritative source (journal, textbook, official documentation)
- 70–89: Found in credible secondary sources
- 50–69: Partially supported; some evidence but not conclusive
- 0–49: Contradicted, or no relevant sources found

## Step 4: Calculate Overall Score

```
Score = round((confirmed_count / total_checked) × 100) - (contradicted_count × 5)
Score = max(0, min(100, Score))
```

Where `confirmed_count` = number of CONFIRMED verdicts, `contradicted_count` = number of CONTRADICTED verdicts.

## Step 5: Write Report

Write to `thesis/output/fact-check-report.md`:

```markdown
# Fact-Check Report
Date: [TODAY]
File(s) checked: [filenames]
Overall Score: [X]/100

## Summary
[2–3 sentences summarizing the findings: how many claims checked, how many confirmed, key issues]

## Claim-by-Claim Results

### Claim 1
- **Text**: "[first 80 chars of the claim from the notes]"
- **Status**: CONFIRMED / UNCONFIRMED / CONTRADICTED / NEEDS_CITATION
- **Confidence**: [0–100]
- **Evidence**: [brief summary of what was found, with source name]
- **Action needed**: [None / Add citation @citekey / Revise claim / Investigate further]

[repeat for each claim checked]

## Priority Actions
[Numbered list of the most important fixes, ordered by severity]
```

## Step 6: Update Feedback History

Append to `memory/feedback-history.md`:
```
[DATE] Fact-check score: [X]/100. Confirmed: [N], Unconfirmed: [N], Contradicted: [N], Needs citation: [N].
Main issues: [one-line summary]
```

Report the overall score and the path to `thesis/output/fact-check-report.md` to the user.
