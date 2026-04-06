#!/bin/bash
# Claude Workflows — Install Script
# Sets up symlinks and prints manual registration steps.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

echo "Installing claude-workflows from: $REPO_DIR"
echo ""

# ── Statusline symlink ──────────────────────────────────────────────
STATUSLINE_SRC="$REPO_DIR/scripts/statusline.sh"
STATUSLINE_DST="$CLAUDE_DIR/statusline.sh"

if [ -L "$STATUSLINE_DST" ]; then
    echo "[ok] Statusline symlink already exists: $STATUSLINE_DST"
elif [ -f "$STATUSLINE_DST" ]; then
    echo "[!!] $STATUSLINE_DST exists but is a regular file."
    echo "     Back it up and re-run, or manually symlink:"
    echo "     ln -sf $STATUSLINE_SRC $STATUSLINE_DST"
else
    ln -s "$STATUSLINE_SRC" "$STATUSLINE_DST"
    echo "[ok] Symlinked statusline: $STATUSLINE_DST -> $STATUSLINE_SRC"
fi

chmod +x "$STATUSLINE_SRC"
echo ""

# ── Plugin registration ──────────────────────────────────────────────
echo "To register as a Claude Code plugin, run inside Claude Code:"
echo ""
echo "  /plugin marketplace add $REPO_DIR"
echo "  /plugin install claude-workflows@claude-workflows"
echo ""
echo "Or add manually to $CLAUDE_DIR/settings.json:"
echo ""
echo '  "enabledPlugins": {'
echo "    \"claude-workflows@claude-workflows\": true"
echo '  }'
echo ""

# ── Session audit script ─────────────────────────────────────────────
AUDIT_SCRIPT="$REPO_DIR/scripts/claude-session-audit.py"
echo "Session audit script available at:"
echo "  python3 $AUDIT_SCRIPT"
echo "  python3 $AUDIT_SCRIPT --detail <session-id>"
echo "  python3 $AUDIT_SCRIPT --window 5h"
echo ""

echo "Done."
