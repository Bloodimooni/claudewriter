#!/usr/bin/env sh
# watcher.sh — Background file watcher for the thesis writing system.
#
# Watches thesis/notes/ for saves. When a /claude:COMMAND trigger is found
# in a notes file, it:
#   1. Runs preprocess.py (zero tokens) to handle all deterministic work
#   2. Calls `claude -p` with a minimal, targeted prompt for AI-only tasks
#
# Usage: ./scripts/watcher.sh (or use start-watcher.sh to run in background)
#
# Trigger syntax (write in any notes file, then save):
#   /claude:memory    — rebuild memory files (usually 0 tokens)
#   /claude:compile   — formalize + generate LaTeX for current file
#   /claude:check     — fact-check + plagiarism on current file
#   /claude:qa        — quality score + auto-fix loop on main.tex
#   /claude:all       — full pipeline: memory → compile → check → qa

set -e

# ─── Paths ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
NOTES_DIR="$PROJECT_ROOT/thesis/notes"
OUTPUT_DIR="$PROJECT_ROOT/thesis/output"
STATE_DIR="$SCRIPT_DIR/.watcher-state"
LOCK_FILE="$STATE_DIR/claude.lock"
LOG_FILE="$STATE_DIR/watcher.log"
PREPROCESS="$SCRIPT_DIR/preprocess.py"

# ─── Prerequisites ────────────────────────────────────────────────────────
check_deps() {
    for cmd in inotifywait python3; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            echo "[watcher] ERROR: '$cmd' is required but not found." >&2
            if [ "$cmd" = "inotifywait" ]; then
                echo "  Install with: sudo pacman -S inotify-tools" >&2
            fi
            exit 1
        fi
    done
    if ! command -v claude >/dev/null 2>&1; then
        echo "[watcher] WARNING: 'claude' CLI not found. AI tasks will be skipped." >&2
        CLAUDE_AVAILABLE=0
    else
        CLAUDE_AVAILABLE=1
    fi
}

# ─── Logging ─────────────────────────────────────────────────────────────
log() {
    msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

# ─── Lock helpers ─────────────────────────────────────────────────────────
acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        old_pid=$(cat "$LOCK_FILE" 2>/dev/null)
        if kill -0 "$old_pid" 2>/dev/null; then
            log "Claude is already running (PID $old_pid). Skipping trigger."
            return 1
        fi
        rm -f "$LOCK_FILE"
    fi
    echo $$ > "$LOCK_FILE"
    return 0
}

release_lock() {
    rm -f "$LOCK_FILE"
}

# ─── Trigger detection ────────────────────────────────────────────────────
# Returns the command name from the first /claude:CMD line in the file,
# or empty string if none found.
find_trigger() {
    file="$1"
    grep -m1 -oP '(?<=/claude:)\w+' "$file" 2>/dev/null || echo ""
}

# Replace the trigger line with a "processing" marker immediately.
mark_processing() {
    file="$1"
    cmd="$2"
    # Use python3 for safe in-place replacement (sed -i varies across systems)
    python3 - "$file" "$cmd" <<'PYEOF'
import sys, re
path, cmd = sys.argv[1], sys.argv[2]
text = open(path).read()
text = re.sub(
    rf'/claude:{re.escape(cmd)}',
    f'<!-- claude:{cmd} processing... -->',
    text, count=1
)
open(path, 'w').write(text)
PYEOF
}

# Replace the "processing" marker with a "done" marker.
mark_done() {
    file="$1"
    cmd="$2"
    note="$3"
    timestamp=$(date '+%Y-%m-%d %H:%M')
    python3 - "$file" "$cmd" "$timestamp" "$note" <<'PYEOF'
import sys, re
path, cmd, ts, note = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
text = open(path).read()
text = re.sub(
    rf'<!-- claude:{re.escape(cmd)} processing\.\.\. -->',
    f'<!-- claude:{cmd} ✓ {ts} | {note} -->',
    text, count=1
)
open(path, 'w').write(text)
PYEOF
}

# ─── Handler: memory ─────────────────────────────────────────────────────
# preprocess.py already wrote all memory files.
# Only calls Claude if research question needs to be inferred.
handle_memory() {
    file="$1"
    log "  [memory] Running preprocess.py..."
    ctx=$(python3 "$PREPROCESS" "$file" --trigger memory 2>&1)
    if echo "$ctx" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('sources_count',0) >= 0 else 1)" 2>/dev/null; then
        wc=$(echo "$ctx" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('word_count',0))")
        sc=$(echo "$ctx" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('sources_count',0))")
        log "  [memory] Memory files updated. Words: $wc, Sources: $sc (0 tokens used)"
        mark_done "$file" "memory" "memory files updated (${sc} sources, ~${wc} words)"
    else
        log "  [memory] ERROR: preprocess.py failed: $ctx"
        mark_done "$file" "memory" "ERROR — check watcher.log"
    fi
}

# ─── Handler: compile ────────────────────────────────────────────────────
# preprocess.py generates the LaTeX structure. Claude only formalizes language.
# After Claude returns, watcher assembles and writes main.tex, then runs latexmk.
handle_compile() {
    file="$1"
    log "  [compile] Running preprocess.py..."
    ctx=$(python3 "$PREPROCESS" "$file" --trigger compile 2>&1)

    if ! echo "$ctx" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        log "  [compile] ERROR: preprocess.py failed: $ctx"
        mark_done "$file" "compile" "ERROR in preprocess — check watcher.log"
        return
    fi

    preamble=$(echo "$ctx" | python3 -c "import sys,json; print(json.load(sys.stdin)['latex_preamble'])")
    latex_body=$(echo "$ctx" | python3 -c "import sys,json; print(json.load(sys.stdin)['latex_body'])")
    suffix=$(echo "$ctx" | python3 -c "import sys,json; print(json.load(sys.stdin)['latex_suffix'])")
    broken=$(echo "$ctx" | python3 -c "import sys,json; d=json.load(sys.stdin); print(', '.join(d['broken_citekeys']) or 'none')")

    if [ "$CLAUDE_AVAILABLE" = "1" ]; then
        log "  [compile] Calling Claude for language formalization..."
        formalized=$(claude --print <<PROMPT
You are an academic writing assistant. Formalize the following LaTeX body text to a formal, academic register: no contractions, no colloquialisms, third person where appropriate. Do NOT change LaTeX commands, citations (\\parencite{...} or \\cite{...}), or structural elements (\\chapter, \\section, etc.). Return ONLY the reformatted LaTeX body, nothing else — no explanation, no code fences.

$latex_body
PROMPT
)
    else
        log "  [compile] Claude not available. Using unformalized body."
        formalized="$latex_body"
    fi

    mkdir -p "$OUTPUT_DIR"
    printf '%s\n%s\n%s' "$preamble" "$formalized" "$suffix" > "$OUTPUT_DIR/main.tex"
    log "  [compile] Written thesis/output/main.tex"

    # Warn about broken citekeys
    if [ "$broken" != "none" ]; then
        log "  [compile] WARNING: Unresolved @citekeys: $broken"
    fi

    # Attempt LaTeX compilation
    if command -v latexmk >/dev/null 2>&1 || command -v xelatex >/dev/null 2>&1; then
        log "  [compile] Running latexmk..."
        result=$(cd "$OUTPUT_DIR" && latexmk -xelatex -interaction=nonstopmode main.tex 2>&1 | tail -5)
        if [ $? -eq 0 ]; then
            log "  [compile] PDF compiled successfully: thesis/output/main.pdf"
            mark_done "$file" "compile" "main.tex + PDF generated"
        else
            log "  [compile] LaTeX errors: $result"
            mark_done "$file" "compile" "main.tex written, LaTeX errors — see watcher.log"
        fi
    else
        log "  [compile] LaTeX not installed. main.tex written. Install: sudo pacman -S texlive-full"
        mark_done "$file" "compile" "main.tex written (no LaTeX installed)"
    fi
}

# ─── Handler: check ──────────────────────────────────────────────────────
# Sends only the clean body text to Claude. No memory/frontmatter overhead.
handle_check() {
    file="$1"
    if [ "$CLAUDE_AVAILABLE" != "1" ]; then
        log "  [check] Claude not available. Skipping."
        mark_done "$file" "check" "skipped — claude CLI not found"
        return
    fi

    log "  [check] Extracting clean body..."
    body=$(python3 "$PREPROCESS" "$file" --trigger check 2>/dev/null | \
           python3 -c "import sys,json; print(json.load(sys.stdin)['body_text'])")

    log "  [check] Calling Claude for fact-check + plagiarism..."
    report=$(claude --print <<PROMPT
Check the following thesis section for (1) factual accuracy and (2) plagiarism risk. Use WebSearch for both. Output a markdown report with exactly two sections:

## Fact Check
Score: [0-100]
[List each issue: claim → verdict (CONFIRMED/UNCONFIRMED/CONTRADICTED) → evidence]

## Plagiarism Risk
Score: [0-100]
[List each risky phrase → match found or not → recommendation]

Be concise. No preamble. Issues only — if a section is clean, write "No issues found."

--- THESIS SECTION ---
$body
PROMPT
)

    mkdir -p "$OUTPUT_DIR"
    {
        echo "# Check Report"
        echo "Date: $(date '+%Y-%m-%d %H:%M')"
        echo "File: $(basename "$file")"
        echo ""
        echo "$report"
    } > "$OUTPUT_DIR/check-report.md"

    # Append summary to feedback history
    echo "[$(date '+%Y-%m-%d')] check on $(basename "$file") — see thesis/output/check-report.md" \
        >> "$PROJECT_ROOT/memory/feedback-history.md"

    log "  [check] Report written to thesis/output/check-report.md"
    mark_done "$file" "check" "check-report.md written"
}

# ─── Handler: qa ─────────────────────────────────────────────────────────
handle_qa() {
    file="$1"
    tex_file="$OUTPUT_DIR/main.tex"

    if [ ! -f "$tex_file" ]; then
        log "  [qa] thesis/output/main.tex not found. Run /claude:compile first."
        mark_done "$file" "qa" "ERROR — compile first"
        return
    fi

    # Run latexmk first (watcher handles compilation, not Claude)
    if command -v latexmk >/dev/null 2>&1; then
        log "  [qa] Running latexmk before QA..."
        cd "$OUTPUT_DIR" && latexmk -xelatex -interaction=nonstopmode main.tex >/dev/null 2>&1 || true
        cd "$PROJECT_ROOT"
    fi

    if [ "$CLAUDE_AVAILABLE" != "1" ]; then
        log "  [qa] Claude not available. Skipping."
        mark_done "$file" "qa" "skipped — claude CLI not found"
        return
    fi

    tex_content=$(cat "$tex_file")
    log "  [qa] Calling Claude for quality scoring..."

    result=$(claude --print <<PROMPT
Score this LaTeX thesis document on four dimensions (0–25 each, total 100):
1. Formatting — correct LaTeX structure, packages, spacing/margin/font per document settings
2. Language Quality — formal academic register, no contractions, sentence clarity
3. Structure — chapters have intro+conclusion paragraphs, logical flow, correct heading hierarchy
4. Citation Compliance — every factual claim has a citation, all citekeys exist in the bibliography

Apply ALL fixes you identify directly to the document. Return the complete corrected LaTeX.

Then, after the LaTeX, output a summary block:
SCORE:[total]/100
FIXED:
- [bullet list of what was fixed]
REMAINING:
- [bullet list of issues not auto-fixable]

--- DOCUMENT ---
$tex_content
PROMPT
)

    # Extract SCORE line and everything before it as the corrected LaTeX
    corrected_tex=$(echo "$result" | python3 -c "
import sys
text = sys.stdin.read()
score_idx = text.find('SCORE:')
if score_idx > 0:
    print(text[:score_idx].strip())
else:
    print(text)
")
    summary=$(echo "$result" | python3 -c "
import sys
text = sys.stdin.read()
score_idx = text.find('SCORE:')
if score_idx >= 0:
    print(text[score_idx:])
")

    if [ -n "$corrected_tex" ] && [ ${#corrected_tex} -gt 100 ]; then
        echo "$corrected_tex" > "$tex_file"
        log "  [qa] main.tex updated with QA fixes"
        if command -v latexmk >/dev/null 2>&1; then
            cd "$OUTPUT_DIR" && latexmk -xelatex -interaction=nonstopmode main.tex >/dev/null 2>&1 || true
            cd "$PROJECT_ROOT"
        fi
    fi

    score_line=$(echo "$summary" | grep "^SCORE:" | head -1)
    echo "[$(date '+%Y-%m-%d')] QA: $score_line | File: $(basename "$file")" \
        >> "$PROJECT_ROOT/memory/feedback-history.md"

    log "  [qa] $score_line"
    mark_done "$file" "qa" "$score_line"
}

# ─── Handler: all ────────────────────────────────────────────────────────
handle_all() {
    file="$1"
    log "  [all] Running full pipeline: memory → compile → check → qa"

    # Re-mark as processing for each step (the trigger was already replaced)
    handle_memory "$file"
    # Re-acquire: handle_memory replaced the trigger line with a done marker.
    # For subsequent steps, we just call the handlers directly.
    handle_compile "$file"
    handle_check "$file"
    handle_qa "$file"

    log "  [all] Full pipeline complete."
}

# ─── Main dispatch ────────────────────────────────────────────────────────
dispatch() {
    file="$PROJECT_ROOT/thesis/notes/$1"

    if [ ! -f "$file" ]; then
        return
    fi

    trigger=$(find_trigger "$file")

    if [ -z "$trigger" ]; then
        # No trigger: silently update checksums
        python3 "$PREPROCESS" --checksums-only "$file" 2>/dev/null || true
        return
    fi

    log "Trigger '/$trigger' detected in: $1"

    mark_processing "$file" "$trigger"

    if ! acquire_lock; then
        return
    fi

    case "$trigger" in
        memory)  handle_memory  "$file" ;;
        compile) handle_compile "$file" ;;
        check)   handle_check   "$file" ;;
        qa)      handle_qa      "$file" ;;
        all)     handle_all     "$file" ;;
        *)
            log "  Unknown trigger: /claude:$trigger. Valid: memory, compile, check, qa, all"
            mark_done "$file" "$trigger" "unknown trigger"
            ;;
    esac

    release_lock
    log "Done: /claude:$trigger on $1"
}

# ─── Entry point ─────────────────────────────────────────────────────────
main() {
    check_deps
    mkdir -p "$STATE_DIR"
    touch "$LOG_FILE"

    log "=== Thesis Watcher started (PID $$) ==="
    log "Watching: $NOTES_DIR"
    log "State:    $STATE_DIR"
    log "Log:      $LOG_FILE"
    log "Claude:   $([ "$CLAUDE_AVAILABLE" = "1" ] && echo available || echo NOT FOUND)"
    echo ""
    echo "Watching thesis/notes/ — add /claude:COMMAND to a notes file and save to trigger."
    echo "Commands: memory | compile | check | qa | all"
    echo "Stop with: ./scripts/stop-watcher.sh  (or Ctrl+C)"
    echo ""

    # Debounce state
    last_file=""
    last_time=0

    inotifywait -m -e close_write --format '%f' "$NOTES_DIR" 2>/dev/null | while read -r fname; do
        # Skip non-markdown files
        case "$fname" in
            *.md) ;;
            *) continue ;;
        esac

        # Debounce: ignore repeated events on the same file within 2 seconds
        now=$(date +%s)
        if [ "$fname" = "$last_file" ] && [ $((now - last_time)) -lt 2 ]; then
            continue
        fi
        last_file="$fname"
        last_time=$now

        # Small sleep to let the editor finish writing
        sleep 0.3

        dispatch "$fname"
    done
}

main "$@"
