#!/bin/bash
# ── Auto-sync: Replit → GitHub → Railway ────────────────────────────────────
# Runs before every bot start. Commits + force-pushes to GitHub so Replit
# is always the authoritative source. Railway auto-redeploys on push.
# ────────────────────────────────────────────────────────────────────────────

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄  Auto-sync: Replit → GitHub → Railway"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PAT="${GITHUB_PAT:-}"
if [ -z "$PAT" ]; then
    echo "⚠️  GITHUB_PAT not set — skipping sync"
else
    git config user.email "idx-bot@auto-sync.local"
    git config user.name  "IDX Bot Auto-Sync"
    export GIT_TERMINAL_PROMPT=0

    REMOTE="https://${PAT}@github.com/adityadkk06-commits/Telegram-bot.git"

    # Stage all changes
    git add -A

    # Commit only if there are staged changes
    if git diff --cached --quiet; then
        echo "✅  No changes — nothing to push"
    else
        TIMESTAMP=$(TZ='Asia/Jakarta' date '+%Y-%m-%d %H:%M WIB')
        git commit -m "auto-sync: ${TIMESTAMP}"
        echo "✅  Committed: ${TIMESTAMP}"
    fi

    # Force-push — Replit is the authoritative source for this repo
    echo "📤  Pushing to GitHub..."
    PUSH_OUT=$(git push "$REMOTE" main --force 2>&1)
    if [ $? -eq 0 ]; then
        echo "✅  Pushed → adityadkk06-commits/Telegram-bot"

        # Trigger Railway webhook if configured
        WEBHOOK="${RAILWAY_WEBHOOK_URL:-}"
        if [ -n "$WEBHOOK" ]; then
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$WEBHOOK")
            [ "$STATUS" = "200" ] || [ "$STATUS" = "201" ] \
                && echo "✅  Railway redeploy triggered" \
                || echo "⚠️  Railway webhook HTTP ${STATUS}"
        else
            echo "ℹ️  Set RAILWAY_WEBHOOK_URL secret to also trigger Railway redeploy"
        fi
    else
        echo "❌  Push failed: $PUSH_OUT"
    fi
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀  Starting IDX Stock Screener Bot…"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exec python -m bot.main
