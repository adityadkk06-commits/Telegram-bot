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

Data completeness
─────────────────
  If >20% of criteria were scored on missing data (via add_missing()),
  the status is capped at "near" even if score ≥ PASS_THRESHOLD.
  This prevents inflated passes when key indicators like MA20/RSI are
  unavailable (e.g. insufficient history or bad data fetch).
"""

PASS_THRESHOLD = 82   # ≥82 → full match
NEAR_THRESHOLD = 58   # ≥58 → near miss

MAX_MISSING_RATIO = 0.20   # >20% missing criteria → cap at "near"


class FilterResult:
    __slots__ = ("status", "score", "max_score", "details", "near_details",
                 "_total_criteria", "_missing_criteria")

    def __init__(self):
        self.score             = 0
        self.max_score         = 0
        self.details           = []   # list of (name, pts_earned, pts_max, note)
        self.near_details      = []   # criteria that are close but failed
        self._total_criteria   = 0
        self._missing_criteria = 0

    # ── helpers ──────────────────────────────────────────────────────────────

    def add(self, name: str, full_pts: int, partial_pts: int,
            full_cond: bool, partial_cond: bool, note_fail: str = ""):
        """Add a scored criterion (data is available)."""
        self._total_criteria += 1
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

    def add_missing(self, name: str, full_pts: int, partial_credit: int | None = None):
        """
        Record a criterion where the underlying data is unavailable.
        Gives a conservative partial credit (default: 40% of full_pts).
        Increments the missing-criteria counter used for completeness check.
        """
        self._total_criteria   += 1
        self._missing_criteria += 1
        credit = partial_credit if partial_credit is not None else int(full_pts * 0.40)
        self.max_score += full_pts
        self.score     += credit
        self.details.append((name, credit, full_pts, "⚪ no data"))

    # ── finalise ──────────────────────────────────────────────────────────────

    def finalise(self) -> "FilterResult":
        pct = self.score / self.max_score * 100 if self.max_score else 0

        # Data completeness gate — cap "pass" → "near" if too much missing data
        missing_ratio = (self._missing_criteria / self._total_criteria
                         if self._total_criteria else 0)
        capped = missing_ratio > MAX_MISSING_RATIO

        if pct >= PASS_THRESHOLD and not capped:
            self.status = "pass"
        elif pct >= NEAR_THRESHOLD:
            self.status = "near"
        else:
            self.status = "fail"

        return self

    @property
    def pct(self) -> float:
        return round(self.score / self.max_score * 100, 1) if self.max_score else 0

    @property
    def data_completeness(self) -> float:
        """Returns 0.0–1.0: fraction of criteria with real data (not missing)."""
        if not self._total_criteria:
            return 1.0
        return round(1.0 - self._missing_criteria / self._total_criteria, 2)

    def status_emoji(self) -> str:
        return {"pass": "✅", "near": "🔶", "fail": "❌"}.get(self.status, "")

    def near_summary(self, max_items: int = 3) -> str:
        items = self.near_details[:max_items]
        return "\n".join(items) if items else ""
