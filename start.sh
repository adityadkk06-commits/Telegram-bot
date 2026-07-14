#!/bin/bash
# ── Auto-sync: Replit → GitHub → Railway ────────────────────────────────────
# Runs before every bot start. Commits + pushes any code changes to GitHub.
# If RAILWAY_WEBHOOK_URL secret is set, also triggers Railway redeploy.
# ────────────────────────────────────────────────────────────────────────────

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄  Auto-sync: Replit → GitHub → Railway"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Git identity required for commits
git config user.email "idx-bot@auto-sync.local"
git config user.name  "IDX Bot Auto-Sync"
export GIT_TERMINAL_PROMPT=0

PAT="${GITHUB_PAT:-}"
REMOTE="https://${PAT}@github.com/adityadkk06-commits/Telegram-bot.git"

if [ -z "$PAT" ]; then
    echo "⚠️  GITHUB_PAT not set — skipping sync, starting bot directly"
else
    # Sync local git with remote first (API pushes may have added commits we lack)
    echo "📥  Pulling remote changes..."
    git fetch "$REMOTE" main 2>&1 | grep -v "^$" || true
    git rebase FETCH_HEAD 2>&1 | tail -3 || true

    # Stage all local changes
    git add -A

    if git diff --cached --quiet; then
        echo "✅  No local changes — GitHub already up to date"
    else
        TIMESTAMP=$(TZ='Asia/Jakarta' date '+%Y-%m-%d %H:%M WIB')
        git commit -m "auto-sync: ${TIMESTAMP}"
        echo "✅  Committed: ${TIMESTAMP}"
    fi

    # Push (local is now ahead of or equal to remote)
    echo "📤  Pushing to GitHub..."
    PUSH_OUT=$(git push "$REMOTE" main 2>&1)
    PUSH_CODE=$?
    if [ $PUSH_CODE -eq 0 ]; then
        echo "✅  Pushed → adityadkk06-commits/Telegram-bot"

        # Trigger Railway webhook if configured
        WEBHOOK="${RAILWAY_WEBHOOK_URL:-}"
        if [ -n "$WEBHOOK" ]; then
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$WEBHOOK")
            if [ "$STATUS" = "200" ] || [ "$STATUS" = "201" ]; then
                echo "✅  Railway redeploy triggered"
            else
                echo "⚠️  Railway webhook HTTP ${STATUS}"
            fi
        else
            echo "ℹ️  Add RAILWAY_WEBHOOK_URL secret to also auto-deploy to Railway"
        fi
    else
        echo "❌  Push failed: $PUSH_OUT"
    fi
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀  Starting IDX Stock Screener Bot…"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exec python -m bot.main
