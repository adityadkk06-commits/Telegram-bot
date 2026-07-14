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

# Prevent git from prompting for credentials
export GIT_TERMINAL_PROMPT=0

# Stage everything
git add -A

# Only push if there are actual changes
if git diff --cached --quiet; then
    echo "✅  No changes — GitHub already up to date"
else
    TIMESTAMP=$(TZ='Asia/Jakarta' date '+%Y-%m-%d %H:%M WIB')
    if git commit -m "auto-sync: ${TIMESTAMP}"; then
        echo "✅  Committed: ${TIMESTAMP}"
    else
        echo "⚠️  Commit failed"
    fi

    # Push using GITHUB_PAT for authentication
    PAT="${GITHUB_PAT:-}"
    if [ -z "$PAT" ]; then
        echo "⚠️  GITHUB_PAT secret not set — skipping push"
    else
        REMOTE="https://${PAT}@github.com/adityadkk06-commits/Telegram-bot.git"
        echo "📤  Pushing to GitHub..."
        PUSH_OUT=$(git push "$REMOTE" main 2>&1)
        PUSH_CODE=$?
        if [ $PUSH_CODE -eq 0 ]; then
            echo "✅  Pushed to GitHub → adityadkk06-commits/Telegram-bot"

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
            echo "❌  Push failed (exit $PUSH_CODE):"
            echo "    $PUSH_OUT"
        fi
    fi
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀  Starting IDX Stock Screener Bot…"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exec python -m bot.main
