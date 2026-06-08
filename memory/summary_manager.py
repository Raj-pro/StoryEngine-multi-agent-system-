from __future__ import annotations
from models import Chapter


class SummaryManager:
    """
    Maintains a rolling narrative summary of the last N chapters.
    This is passed verbatim into the writer's context window to give
    immediate continuity without consuming tokens on full chapter text.
    """

    def __init__(self, window: int = 3):
        self._window = window
        self._recent: list[Chapter] = []
        self._cumulative_summary: str = ""

    def add_chapter(self, chapter: Chapter):
        self._recent.append(chapter)
        if len(self._recent) > self._window:
            oldest = self._recent.pop(0)
            self._cumulative_summary = (
                f"{self._cumulative_summary}\n"
                f"[Ch {oldest.number} – {oldest.title}]: "
                f"{self._extract_summary(oldest.content)}"
            ).strip()

    def _extract_summary(self, content: str, max_sentences: int = 3) -> str:
        sentences = [s.strip() for s in content.split(".") if len(s.strip()) > 20]
        return ". ".join(sentences[:max_sentences]) + "."

    def get_rolling_context(self) -> str:
        parts = []
        if self._cumulative_summary:
            parts.append(f"=== Story So Far (summarized) ===\n{self._cumulative_summary}")
        if self._recent:
            parts.append("=== Recent Chapters (full) ===")
            for ch in self._recent:
                parts.append(f"--- Chapter {ch.number}: {ch.title} ---\n{ch.content}")
        return "\n\n".join(parts)

    def get_total_summary(self) -> str:
        return self._cumulative_summary

    @property
    def chapters_seen(self) -> int:
        return len(self._recent) + (
            len(self._cumulative_summary.splitlines()) if self._cumulative_summary else 0
        )
