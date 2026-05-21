"""
Scoring-based filter engine.

Every screener returns a FilterResult instead of a plain bool.

Scoring tiers
─────────────
  score ≥ PASS_THRESHOLD  →  status = "pass"   ✅  (shown first)
  score ≥ NEAR_THRESHOLD  →  status = "near"   🔶  (near-miss section)
  score <  NEAR_THRESHOLD →  status = "fail"   (hidden)

Each criterion contributes full_pts when exactly met, partial_pts when
"close" (within a tolerance), and 0 otherwise.
"""

PASS_THRESHOLD = 82   # ≥82 → full match
NEAR_THRESHOLD = 58   # ≥58 → near miss


class FilterResult:
    __slots__ = ("status", "score", "max_score", "details", "near_details")

    def __init__(self):
        self.score       = 0
        self.max_score   = 0
        self.details     = []   # list of (name, pts_earned, pts_max, note)
        self.near_details= []   # criteria that are close but failed

    # ── helpers ──────────────────────────────────────────────────────────────

    def _pct(self, value, scale=100) -> float:
        return round(self.score / self.max_score * scale, 1) if self.max_score else 0

    def add(self, name: str, full_pts: int, partial_pts: int,
            full_cond: bool, partial_cond: bool, note_fail: str = ""):
        self.max_score += full_pts
        if full_cond:
            self.score += full_pts
            self.details.append((name, full_pts, full_pts, "✅"))
        elif partial_cond:
            self.score += partial_pts
            self.details.append((name, partial_pts, full_pts, "🔸 close"))
            self.near_details.append(f"🔸 {name}: almost — {note_fail}")
        else:
            self.details.append((name, 0, full_pts, "❌"))
            if note_fail:
                self.near_details.append(f"❌ {name}: {note_fail}")

    # ── finalise ──────────────────────────────────────────────────────────────

    def finalise(self) -> "FilterResult":
        pct = self.score / self.max_score * 100 if self.max_score else 0
        if pct >= PASS_THRESHOLD:
            self.status = "pass"
        elif pct >= NEAR_THRESHOLD:
            self.status = "near"
        else:
            self.status = "fail"
        return self

    @property
    def pct(self) -> float:
        return round(self.score / self.max_score * 100, 1) if self.max_score else 0

    def status_emoji(self) -> str:
        return {"pass": "✅", "near": "🔶", "fail": "❌"}.get(self.status, "")

    def near_summary(self, max_items: int = 3) -> str:
        items = self.near_details[:max_items]
        return "\n".join(items) if items else ""
