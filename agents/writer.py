from __future__ import annotations
from models import ChapterOutline, WorldState
from llm_client import LLMClient

_SYSTEM_TEMPLATE = """\
You are a literary author writing chapter {chapter_num} of a 100-chapter {genre} novel.

WORLD FACTS (never contradict):
{world_facts}

WORLD RULES (inviolable):
{world_rules}

CHARACTER ROSTER:
{characters}

WRITING DIRECTIVES:
- Target {target_words} words. Write scene-level prose, not summary.
- Do NOT revive dead characters. Do NOT violate world rules.
- End the chapter with: {ends_on}.
- Show, don't tell. Use dialogue and action.
- Write ONLY the chapter text — no title line, no author notes.\
"""


class WriterAgent:
    def __init__(self, client: LLMClient, target_words: int = 700):
        self._client = client
        self._target_words = target_words

    def _system(self, chapter_outline: ChapterOutline, world: WorldState, characters: list[dict]) -> str:
        world_facts = (
            f"Title: {world.title} | Genre: {world.genre}\n"
            f"Setting: {world.setting[:400]}\n"
            f"Central Conflict: {world.central_conflict}"
        )
        world_rules = "\n".join(f"[{r.category}] {r.rule}" for r in world.world_rules)
        char_lines = []
        for c in characters:
            status = "ALIVE" if c.get("alive", True) else "DEAD — must NOT appear"
            char_lines.append(f"- {c['name']} ({c.get('role','?')}) [{status}] @ {c.get('current_location','?')}")
        return _SYSTEM_TEMPLATE.format(
            chapter_num=chapter_outline.chapter_number,
            genre=world.genre,
            world_facts=world_facts,
            world_rules=world_rules,
            characters="\n".join(char_lines),
            target_words=self._target_words,
            ends_on=chapter_outline.ends_on,
        )

    def _user_prompt(
        self,
        chapter_outline: ChapterOutline,
        rolling_context: str,
        relevant_past: list[dict],
        outline_window: list[ChapterOutline],
    ) -> str:
        parts: list[str] = []
        if rolling_context:
            parts.append(rolling_context[-2000:])

        if relevant_past:
            parts.append("=== Relevant Past Chapters ===")
            for p in relevant_past[:2]:
                parts.append(f"[Ch {p['chapter']} – {p['title']}]\n{p['content'][:500]}...")

        outline_ctx = "\n".join(
            f"Ch {o.chapter_number}: {o.title} — {o.summary}" for o in outline_window
        )
        events = "\n".join(f"  • {e}" for e in chapter_outline.key_events)
        parts.append(
            f"=== Chapter {chapter_outline.chapter_number}: \"{chapter_outline.title}\" ===\n"
            f"Required events:\n{events}\n"
            f"Characters who must appear: {', '.join(chapter_outline.characters_involved)}\n"
            f"Plot purpose: {chapter_outline.plot_purpose}\n\n"
            f"Nearby outline context:\n{outline_ctx}\n\n"
            f"Write the chapter now."
        )
        return "\n\n".join(parts)

    def write(
        self,
        chapter_outline: ChapterOutline,
        world: WorldState,
        characters: list[dict],
        rolling_context: str,
        relevant_past: list[dict],
        outline_window: list[ChapterOutline],
    ) -> str:
        system = self._system(chapter_outline, world, characters)
        user = self._user_prompt(chapter_outline, rolling_context, relevant_past, outline_window)
        return self._client.complete(
            messages=[{"role": "user", "content": user}],
            system=system,
            temperature=0.75,
            num_ctx=4096,
        ).strip()

    def rewrite(
        self,
        draft: str,
        violations: list[str],
        chapter_outline: ChapterOutline,
        world: WorldState,
        characters: list[dict],
        rolling_context: str,
        outline_window: list[ChapterOutline],
    ) -> str:
        system = self._system(chapter_outline, world, characters)
        violation_text = "\n".join(f"  ✗ {v}" for v in violations)
        user = (
            f"{rolling_context[-1500:] if rolling_context else ''}\n\n"
            f"=== REJECTED DRAFT ===\n{draft}\n\n"
            f"=== VIOLATIONS ===\n{violation_text}\n\n"
            f"Rewrite Chapter {chapter_outline.chapter_number}: \"{chapter_outline.title}\" "
            f"fixing ALL violations. Begin directly with the revised chapter text."
        )
        return self._client.complete(
            messages=[{"role": "user", "content": user}],
            system=system,
            temperature=0.65,
            num_ctx=4096,
        ).strip()
