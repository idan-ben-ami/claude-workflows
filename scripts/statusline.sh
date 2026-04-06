#!/bin/bash
# Claude Code Statusline — Max Plan Quota Focus
# Shows: model | context % | waste factor | rate limits (5h/7d)
#
# Waste factor = current context / baseline context (from first turns in transcript)
# Reads the actual JSONL transcript to find the real baseline, even for old sessions.

input=$(cat)

# ── Extract fields (single jq call for speed) ────────────────────────────────
eval "$(echo "$input" | jq -r '
  "MODEL=" + (.model.display_name // "Claude" | @sh),
  "CTX_PCT=" + ((.context_window.used_percentage // 0 | floor) | tostring),
  "SESSION_ID=" + (.session_id // "" | @sh),
  "TRANSCRIPT=" + (.transcript_path // "" | @sh),
  "CURRENT_CTX=" + (((.context_window.current_usage // {}) | ((.input_tokens // 0) + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0))) | tostring),
  "FIVE_H_PCT=" + (.rate_limits.five_hour.used_percentage // empty | tostring),
  "FIVE_H_RESET=" + (.rate_limits.five_hour.resets_at // empty | tostring),
  "SEVEN_D_PCT=" + (.rate_limits.seven_day.used_percentage // empty | tostring)
' 2>/dev/null)"

# ── Colors ───────────────────────────────────────────────────────────────────
G='\033[32m'; Y='\033[33m'; R='\033[31m'; D='\033[2m'; B='\033[1m'; Z='\033[0m'

# ── Format context tokens ───────────────────────────────────────────────────
if [ "${CURRENT_CTX:-0}" -ge 1000000 ] 2>/dev/null; then
    CTX_FMT=$(awk "BEGIN{printf \"%.1fM\", $CURRENT_CTX/1000000}")
elif [ "${CURRENT_CTX:-0}" -ge 1000 ] 2>/dev/null; then
    CTX_FMT=$(awk "BEGIN{printf \"%.0fk\", $CURRENT_CTX/1000}")
else
    CTX_FMT="${CURRENT_CTX:-0}"
fi

# ── Waste factor ─────────────────────────────────────────────────────────────
# Strategy: cache baseline per session. If no cached baseline, read it from
# the JSONL transcript (first assistant message with usage data).
WASTE_STR=""
if [ -n "$SESSION_ID" ] && [ "${CURRENT_CTX:-0}" -gt 0 ] 2>/dev/null; then
    STATE_DIR="/tmp/claude-statusline"
    mkdir -p "$STATE_DIR" 2>/dev/null
    STATE_FILE="$STATE_DIR/$SESSION_ID"

    BASELINE=0
    if [ -f "$STATE_FILE" ]; then
        read -r BASELINE < "$STATE_FILE"
    fi

    # If no baseline yet, extract from transcript
    if [ "$BASELINE" -le 0 ] 2>/dev/null && [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
        # Read first ~100 lines, find first assistant message with usage, extract context size
        BASELINE=$(head -100 "$TRANSCRIPT" 2>/dev/null | jq -r '
            select(.type == "assistant")
            | .message.usage // empty
            | ((.input_tokens // 0) + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0))
        ' 2>/dev/null | awk '$1 > 1000 {print $1; exit}')

        # Save if we found one
        if [ -n "$BASELINE" ] && [ "$BASELINE" -gt 0 ] 2>/dev/null; then
            echo "$BASELINE" > "$STATE_FILE" 2>/dev/null
        fi
    fi

    # Fallback: if still no baseline, use current (new session)
    if [ "${BASELINE:-0}" -le 0 ] 2>/dev/null; then
        BASELINE=$CURRENT_CTX
        echo "$BASELINE" > "$STATE_FILE" 2>/dev/null
    fi

    # Calculate and format waste factor
    if [ "$BASELINE" -gt 0 ] 2>/dev/null; then
        WASTE=$(awk "BEGIN{printf \"%.1f\", $CURRENT_CTX/$BASELINE}")
        WASTE_INT=$(awk "BEGIN{printf \"%.0f\", $CURRENT_CTX/$BASELINE}")

        if [ "$WASTE_INT" -ge 10 ] 2>/dev/null; then
            WASTE_STR="${R}${B}${WASTE}x${Z}${D}/clear${Z}"
        elif [ "$WASTE_INT" -ge 5 ] 2>/dev/null; then
            WASTE_STR="${Y}${WASTE}x${Z}${D}/compact${Z}"
        elif [ "$WASTE_INT" -ge 3 ] 2>/dev/null; then
            WASTE_STR="${D}${WASTE}x${Z}"
        fi
        # <3x: not shown (healthy)
    fi
fi

# ── Context color ────────────────────────────────────────────────────────────
if [ "${CTX_PCT:-0}" -ge 80 ] 2>/dev/null; then CTX_C="$R"
elif [ "${CTX_PCT:-0}" -ge 50 ] 2>/dev/null; then CTX_C="$Y"
else CTX_C="$G"; fi

# ── Rate limits ──────────────────────────────────────────────────────────────
LIMITS=""
if [ -n "$FIVE_H_PCT" ]; then
    FIVE_INT=$(printf '%.0f' "$FIVE_H_PCT" 2>/dev/null || echo "0")
    if [ "$FIVE_INT" -ge 80 ] 2>/dev/null; then LC="$R"
    elif [ "$FIVE_INT" -ge 50 ] 2>/dev/null; then LC="$Y"
    else LC="$G"; fi

    RST=""
    if [ -n "$FIVE_H_RESET" ]; then
        REM=$(( FIVE_H_RESET - $(date +%s) ))
        if [ "$REM" -gt 0 ] 2>/dev/null; then
            H=$((REM / 3600)); M=$(( (REM % 3600) / 60 ))
            if [ "$H" -gt 0 ]; then RST="${D}(${H}h${M}m)${Z}"
            else RST="${D}(${M}m)${Z}"; fi
        fi
    fi
    LIMITS="${LC}5h:${FIVE_INT}%${Z}${RST}"
fi

if [ -n "$SEVEN_D_PCT" ]; then
    SEVEN_INT=$(printf '%.0f' "$SEVEN_D_PCT" 2>/dev/null || echo "0")
    if [ "$SEVEN_INT" -ge 80 ] 2>/dev/null; then LC7="$R"
    elif [ "$SEVEN_INT" -ge 50 ] 2>/dev/null; then LC7="$Y"
    else LC7="$G"; fi
    [ -n "$LIMITS" ] && LIMITS="$LIMITS "
    LIMITS="${LIMITS}${LC7}7d:${SEVEN_INT}%${Z}"
fi

# ── Output ───────────────────────────────────────────────────────────────────
OUT="${MODEL} | ${CTX_C}ctx:${CTX_PCT}%${Z} ${CTX_FMT}"
[ -n "$WASTE_STR" ] && OUT="$OUT ${WASTE_STR}"
[ -n "$LIMITS" ] && OUT="$OUT | $LIMITS"

printf '%b\n' "$OUT"
