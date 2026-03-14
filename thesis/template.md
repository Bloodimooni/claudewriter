---
title: "Your Thesis Title Here"
author: "Your Name"
citation_style: APA
line_spacing: 1.5
font_size: 12pt
margin: 2.5cm
language: english
university: "Your University"
faculty: "Your Faculty"
supervisor: "Prof. Dr. Supervisor Name"
date: "March 2026"
---

# Abstract

[Write a short summary of your thesis here — what you researched, how, and what you found. 150–300 words.]

> Note to self: Write abstract last, after all chapters are done.

# Chapter 1: Introduction

Provide context for your research here. Explain what the problem is and why it matters.
Use `@citekey` to cite sources inline, like this: according to @smith_2023, the problem
has been growing over the past decade.

> Note to self: Add statistics on the scale of the problem here.

## 1.1 Research Question

This thesis investigates the following question: *[Your research question here]*.

The remainder of this thesis is structured as follows. Chapter 2 provides background on...

## 1.2 Scope and Limitations

This thesis focuses on [narrow the scope]. It does not address [what is excluded].

# Chapter 2: Background

Introduce the theoretical foundations and related work here. Every factual claim needs a citation.

## 2.1 [First Background Topic]

[Your notes on this topic. Be informal — write what you know and understand.
The `/thesis-compile` command will convert this to formal academic language.]

## 2.2 [Second Background Topic]

[Continue...]

# Chapter 3: Methodology

Explain what you did and how. Be specific.

# Chapter 4: Results

Present your findings.

# Chapter 5: Discussion

Interpret your results. Connect them back to your research question and the literature.

# Chapter 6: Conclusion

Summarize the thesis, restate the main findings, discuss implications and future work.

## Sources

- smith_2023: Smith, J., Jones, A., "Title of the Paper", Journal of Important Things, 2023
- author_2020: Author, F.M., "Book Title", Publisher Name, 2020
- conference_2022: Researcher, N., "Conference Paper Title", Proceedings of CONF 2022, 2022

---

## How to Use This File

1. **Copy** this file to `thesis/notes/01-introduction.md` (and make more files for each chapter, e.g. `02-background.md`)
2. **Write your notes** in the body — be informal, write what you understand
3. Use `@citekey` for citations (must also appear in `## Sources` section)
4. Use `> Note to self: ...` for personal reminders (stripped from output automatically)
5. **Run `/thesis-memory`** to build the context memory from your notes
6. **Run `/thesis-compile`** to generate the LaTeX document
7. **Run `/thesis-fact-check`** to verify your claims
8. **Run `/thesis-plagiarism`** to check for plagiarism risk
9. **Run `/thesis-qa`** to score and auto-improve the output

Only the first file (or a `metadata.md`) needs the full YAML frontmatter. Other chapter files can omit it.
