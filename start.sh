#!/bin/bash
# ── Auto-sync: Replit → GitHub → Railway ────────────────────────────────────
# Runs before every bot start. Commits + pushes any code changes to GitHub.
# If RAILWAY_WEBHOOK_URL secret is set, also triggers Railway redeploy.
# ────────────────────────────────────────────────────────────────────────────
set -uo pipefail

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄  Auto-sync: Replit → GitHub → Railway"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Git identity required for commits
git config user.email "idx-bot@auto-sync.local" 2>/dev/null || true
git config user.name  "IDX Bot Auto-Sync"       2>/dev/null || true

# Stage everything (bot code + configs)
git add -A 2>/dev/null || true

# Only push if there are actual changes
if git diff --cached --quiet 2>/dev/null; then
    echo "✅  No changes — GitHub already up to date"
else
    TIMESTAMP=$(TZ='Asia/Jakarta' date '+%Y-%m-%d %H:%M WIB')
    git commit -m "auto-sync: ${TIMESTAMP}" 2>/dev/null \
        && echo "✅  Committed: ${TIMESTAMP}" \
        || echo "⚠️  Commit failed (non-fatal)"

    # Authenticate push with GITHUB_PAT
    if [ -n "${GITHUB_PAT:-}" ]; then
        REMOTE="https://${GITHUB_PAT}@github.com/adityadkk06-commits/Telegram-bot.git"
        if git push "${REMOTE}" main 2>/dev/null; then
            echo "✅  Pushed to GitHub → adityadkk06-commits/Telegram-bot"

            # Trigger Railway webhook if configured
            if [ -n "${RAILWAY_WEBHOOK_URL:-}" ]; then
                STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
                    -X POST "${RAILWAY_WEBHOOK_URL}" 2>/dev/null || echo "000")
                if [ "$STATUS" = "200" ] || [ "$STATUS" = "201" ]; then
                    echo "✅  Railway redeploy triggered (HTTP ${STATUS})"
                else
                    echo "⚠️  Railway webhook HTTP ${STATUS} — check RAILWAY_WEBHOOK_URL secret"
                fi
            else
                echo "ℹ️  Add RAILWAY_WEBHOOK_URL secret to also trigger Railway redeploy"
            fi
        else
            echo "⚠️  GitHub push failed — check GITHUB_PAT secret (bot will still start)"
        fi
    else
        echo "⚠️  GITHUB_PAT not set — skipping GitHub push"
    fi
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀  Starting IDX Stock Screener Bot…"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exec python -m bot.main
