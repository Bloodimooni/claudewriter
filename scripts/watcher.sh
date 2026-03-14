#!/usr/bin/env sh
# watcher.sh — Background file watcher for the thesis writing system.
#
# Watches thesis/notes/ for saves. When a /claude:COMMAND trigger is found
# in a notes file, it:
#   1. Runs preprocess.py (zero tokens) to handle all deterministic work
#   2. Calls `claude --print` with a minimal, targeted prompt for AI-only tasks
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
MAX_LOG_BYTES=5242880  # 5 MB

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

rotate_log() {
    if [ -f "$LOG_FILE" ]; then
        log_size=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
        if [ "$log_size" -gt "$MAX_LOG_BYTES" ]; then
            mv "$LOG_FILE" "$LOG_FILE.old"
            log "Log rotated (previous log: $LOG_FILE.old)"
        fi
    fi
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
find_trigger() {
    file="$1"
    grep -m1 -oP '(?<=/claude:)\w+' "$file" 2>/dev/null || echo ""
}

# Replace the trigger line with a "processing" marker immediately.
mark_processing() {
    file="$1"
    cmd="$2"
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
    f'<!-- claude:{cmd} done {ts} | {note} -->',
    text, count=1
)
open(path, 'w').write(text)
PYEOF
}

# Clean up stale "processing..." markers (e.g. after a crash).
cleanup_stale_markers() {
    for f in "$NOTES_DIR"/*.md; do
        [ -f "$f" ] || continue
        if grep -q '<!-- claude:\w\+ processing\.\.\. -->' "$f" 2>/dev/null; then
            log "Cleaning stale processing marker in $(basename "$f")"
            python3 - "$f" <<'PYEOF'
import sys, re
path = sys.argv[1]
text = open(path).read()
text = re.sub(
    r'<!-- claude:(\w+) processing\.\.\. -->',
    r'<!-- claude:\1 stale (watcher restarted) -->',
    text
)
open(path, 'w').write(text)
PYEOF
        fi
    done
}

# ─── JSON field extractor (parse once, extract many) ─────────────────────
# Usage: extract_json "$json_string" field1 field2 ...
# Sets variables: _field1, _field2, etc.
extract_json() {
    _json="$1"
    shift
    eval "$(echo "$_json" | python3 -c "
import sys, json
fields = sys.argv[1:]
try:
    d = json.load(sys.stdin)
    for f in fields:
        val = d.get(f, '')
        if isinstance(val, list):
            val = ', '.join(str(x) for x in val) if val else 'none'
        elif isinstance(val, bool):
            val = 'true' if val else 'false'
        elif isinstance(val, dict):
            val = json.dumps(val)
        # Shell-safe: replace single quotes and newlines
        val = str(val)
        print(f'_{f}={chr(39)}{val}{chr(39)}')
except Exception as e:
    print(f'_error={chr(39)}{e}{chr(39)}')
" "$@")"
}

# ─── Handler: memory ─────────────────────────────────────────────────────
# preprocess.py already writes all memory files. Zero tokens.
handle_memory() {
    file="$1"
    _skip_mark="$2"  # "skip" if called from handle_all

    log "  [memory] Running preprocess.py..."
    ctx=$(python3 "$PREPROCESS" "$file" --trigger memory 2>&1)

    extract_json "$ctx" word_count sources_count error warnings
    if [ -n "$_error" ] && [ "$_error" != "" ]; then
        log "  [memory] ERROR: $_error"
        [ "$_skip_mark" != "skip" ] && mark_done "$file" "memory" "ERROR — check watcher.log"
        return 1
    fi

    if [ -n "$_warnings" ] && [ "$_warnings" != "none" ] && [ "$_warnings" != "" ]; then
        log "  [memory] Warnings: $_warnings"
    fi

    log "  [memory] Memory files updated. Words: $_word_count, Sources: $_sources_count (0 tokens)"
    [ "$_skip_mark" != "skip" ] && mark_done "$file" "memory" "updated (${_sources_count} sources, ~${_word_count} words)"
    return 0
}

# ─── Handler: compile ────────────────────────────────────────────────────
handle_compile() {
    file="$1"
    _skip_mark="$2"

    log "  [compile] Running preprocess.py (all chapters)..."
    ctx=$(python3 "$PREPROCESS" --compile-all 2>&1)

    extract_json "$ctx" latex_preamble latex_body latex_suffix broken_citekeys \
                        word_count changed chapters_cached chapters_processed error warnings

    if [ -n "$_error" ] && [ "$_error" != "" ]; then
        log "  [compile] ERROR: $_error"
        [ "$_skip_mark" != "skip" ] && mark_done "$file" "compile" "ERROR — $_error"
        return 1
    fi

    if [ -n "$_warnings" ] && [ "$_warnings" != "none" ] && [ "$_warnings" != "" ]; then
        log "  [compile] Frontmatter warnings: $_warnings"
    fi

    log "  [compile] Chapters: $_chapters_processed processed, $_chapters_cached cached"

    # Warn about broken citekeys
    if [ "$_broken_citekeys" != "none" ] && [ -n "$_broken_citekeys" ]; then
        log "  [compile] WARNING: Unresolved @citekeys: $_broken_citekeys"
    fi

    if [ "$CLAUDE_AVAILABLE" = "1" ]; then
        log "  [compile] Calling Claude (haiku) for language formalization..."
        formalized=$(claude --print --model haiku <<PROMPT
Formalize this LaTeX body to academic register. No contractions, no colloquialisms, third person. Keep all LaTeX commands, \\parencite{}, \\cite{}, \\chapter{}, etc. unchanged. Return ONLY the LaTeX body — no explanation, no code fences.

$_latex_body
PROMPT
)
    else
        log "  [compile] Claude not available. Using unformalized body."
        formalized="$_latex_body"
    fi

    mkdir -p "$OUTPUT_DIR"
    printf '%s\n%s\n%s' "$_latex_preamble" "$formalized" "$_latex_suffix" > "$OUTPUT_DIR/main.tex"
    log "  [compile] Written thesis/output/main.tex"

    # Attempt LaTeX compilation
    compile_result="main.tex written"
    if command -v latexmk >/dev/null 2>&1; then
        log "  [compile] Running latexmk..."
        if cd "$OUTPUT_DIR" && latexmk -xelatex -interaction=nonstopmode main.tex >/dev/null 2>&1; then
            compile_result="main.tex + PDF generated"
            log "  [compile] PDF compiled: thesis/output/main.pdf"
        else
            compile_result="main.tex written, LaTeX errors — see watcher.log"
            log "  [compile] LaTeX compilation had errors"
        fi
        cd "$PROJECT_ROOT"
    elif command -v xelatex >/dev/null 2>&1; then
        log "  [compile] Running xelatex..."
        if cd "$OUTPUT_DIR" && xelatex -interaction=nonstopmode main.tex >/dev/null 2>&1; then
            compile_result="main.tex + PDF generated"
        else
            compile_result="main.tex written, LaTeX errors"
        fi
        cd "$PROJECT_ROOT"
    else
        log "  [compile] No LaTeX installed. Install: sudo pacman -S texlive-full"
        compile_result="main.tex written (no LaTeX installed)"
    fi

    [ "$_skip_mark" != "skip" ] && mark_done "$file" "compile" "$compile_result"
    return 0
}

# ─── Handler: check ──────────────────────────────────────────────────────
handle_check() {
    file="$1"
    _skip_mark="$2"

    if [ "$CLAUDE_AVAILABLE" != "1" ]; then
        log "  [check] Claude not available. Skipping."
        [ "$_skip_mark" != "skip" ] && mark_done "$file" "check" "skipped — claude CLI not found"
        return 1
    fi

    log "  [check] Extracting clean body..."
    ctx=$(python3 "$PREPROCESS" "$file" --trigger check 2>/dev/null)
    extract_json "$ctx" body_text error

    if [ -n "$_error" ] && [ "$_error" != "" ]; then
        log "  [check] ERROR: $_error"
        [ "$_skip_mark" != "skip" ] && mark_done "$file" "check" "ERROR — $_error"
        return 1
    fi

    log "  [check] Calling Claude for fact-check + plagiarism..."
    report=$(claude --print <<PROMPT
Fact-check and plagiarism-check this thesis section. Use WebSearch.
Output markdown with two sections:
## Fact Check (Score: 0-100, then issues list)
## Plagiarism Risk (Score: 0-100, then risky phrases)
No preamble. Issues only.

$_body_text
PROMPT
)

    mkdir -p "$OUTPUT_DIR"
    printf '# Check Report\nDate: %s\nFile: %s\n\n%s\n' \
        "$(date '+%Y-%m-%d %H:%M')" "$(basename "$file")" "$report" \
        > "$OUTPUT_DIR/check-report.md"

    echo "[$(date '+%Y-%m-%d')] check on $(basename "$file") — see thesis/output/check-report.md" \
        >> "$PROJECT_ROOT/memory/feedback-history.md"

    log "  [check] Report: thesis/output/check-report.md"
    [ "$_skip_mark" != "skip" ] && mark_done "$file" "check" "check-report.md written"
    return 0
}

# ─── Handler: qa ─────────────────────────────────────────────────────────
handle_qa() {
    file="$1"
    _skip_mark="$2"
    tex_file="$OUTPUT_DIR/main.tex"

    if [ ! -f "$tex_file" ]; then
        log "  [qa] thesis/output/main.tex not found. Run /claude:compile first."
        [ "$_skip_mark" != "skip" ] && mark_done "$file" "qa" "ERROR — compile first"
        return 1
    fi

    # Run latexmk first (watcher handles compilation, not Claude)
    if command -v latexmk >/dev/null 2>&1; then
        log "  [qa] Pre-compiling with latexmk..."
        cd "$OUTPUT_DIR" && latexmk -xelatex -interaction=nonstopmode main.tex >/dev/null 2>&1 || true
        cd "$PROJECT_ROOT"
    fi

    if [ "$CLAUDE_AVAILABLE" != "1" ]; then
        log "  [qa] Claude not available. Skipping."
        [ "$_skip_mark" != "skip" ] && mark_done "$file" "qa" "skipped — claude CLI not found"
        return 1
    fi

    tex_content=$(cat "$tex_file")
    log "  [qa] Calling Claude for quality scoring..."

    result=$(claude --print <<PROMPT
Score this LaTeX thesis (0-25 each): Formatting, Language, Structure, Citations.
Fix all issues in the document. Return the corrected LaTeX, then:
SCORE:[total]/100
FIXED: [bullet list]
REMAINING: [bullet list]

$tex_content
PROMPT
)

    # Extract corrected LaTeX (before SCORE:) and summary (from SCORE: onward)
    eval "$(echo "$result" | python3 -c "
import sys
text = sys.stdin.read()
idx = text.find('SCORE:')
if idx > 0:
    tex = text[:idx].strip()
    summary = text[idx:]
else:
    tex = text
    summary = 'SCORE:unknown'
# Shell-safe output
tex = tex.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))
summary = summary.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))
print(f'_corrected_tex={chr(39)}{tex}{chr(39)}')
print(f'_summary={chr(39)}{summary}{chr(39)}')
")"

    if [ -n "$_corrected_tex" ] && [ ${#_corrected_tex} -gt 100 ]; then
        printf '%s' "$_corrected_tex" > "$tex_file"
        log "  [qa] main.tex updated with QA fixes"
        if command -v latexmk >/dev/null 2>&1; then
            cd "$OUTPUT_DIR" && latexmk -xelatex -interaction=nonstopmode main.tex >/dev/null 2>&1 || true
            cd "$PROJECT_ROOT"
        fi
    fi

    score_line=$(echo "$_summary" | grep "^SCORE:" | head -1)
    echo "[$(date '+%Y-%m-%d')] QA: $score_line | File: $(basename "$file")" \
        >> "$PROJECT_ROOT/memory/feedback-history.md"

    log "  [qa] $score_line"
    [ "$_skip_mark" != "skip" ] && mark_done "$file" "qa" "$score_line"
    return 0
}

# ─── Handler: all ────────────────────────────────────────────────────────
# Calls each handler with "skip" flag so they don't touch the trigger marker.
# Only handle_all writes the final done marker.
handle_all() {
    file="$1"
    log "  [all] Running full pipeline: memory -> compile -> check -> qa"
    pipeline_notes=""

    handle_memory "$file" "skip"
    pipeline_notes="memory:ok"

    handle_compile "$file" "skip"
    pipeline_notes="$pipeline_notes, compile:ok"

    handle_check "$file" "skip"
    pipeline_notes="$pipeline_notes, check:ok"

    handle_qa "$file" "skip"
    pipeline_notes="$pipeline_notes, qa:ok"

    mark_done "$file" "all" "$pipeline_notes"
    log "  [all] Pipeline complete: $pipeline_notes"
}

# ─── Main dispatch ────────────────────────────────────────────────────────
dispatch() {
    file="$PROJECT_ROOT/thesis/notes/$1"

    if [ ! -f "$file" ]; then
        return
    fi

    trigger=$(find_trigger "$file")

    if [ -z "$trigger" ]; then
        python3 "$PREPROCESS" --checksums-only "$file" 2>/dev/null || true
        return
    fi

    log "Trigger '/claude:$trigger' detected in: $1"

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

    # Clean up any stale "processing..." markers from a previous crash
    cleanup_stale_markers

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

        # Rotate log if too large
        rotate_log

        dispatch "$fname"
    done
}

main "$@"
