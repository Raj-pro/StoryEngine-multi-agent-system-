from __future__ import annotations
import logging
from models import WorldState, StoryOutline, ChapterOutline
from llm_client import LLMClient

logger = logging.getLogger(__name__)

_ARC_NAMES = {
    1: "The Ordinary World Shattered",
    2: "The Rising Darkness",
    3: "The Point of No Return",
    4: "The Descent and Reckoning",
    5: "The Final Convergence",
}

_ARC_BRIEFS = {
    1: "Establish world, introduce all key characters, deliver the inciting incident. Chapters 1-20.",
    2: "Stakes escalate, alliances form and fracture, a major setback occurs. Chapters 21-40.",
    3: "Protagonist crosses an irreversible threshold. The world changes permanently. Chapters 41-60.",
    4: "Darkest hour — losses, failures, internal transformation. Chapters 61-80.",
    5: "All threads converge. Climax, resolution, denouement. Chapters 81-100.",
}

_SYSTEM = """\
You are a story architect. Generate a detailed chapter-by-chapter outline for the arc \
described. Each chapter must have a clear plot purpose. Respond with ONLY valid JSON.\
"""

_ARC_SCHEMA = """\
Return a JSON object:
{
  "arc_description": "one-sentence arc summary",
  "chapters": [
    {
      "chapter_number": 1,
      "arc": 1,
      "arc_name": "The Ordinary World Shattered",
      "title": "chapter title",
      "summary": "2-3 sentence chapter summary",
      "key_events": ["event 1", "event 2"],
      "characters_involved": ["Name1", "Name2"],
      "plot_purpose": "why this chapter must exist",
      "ends_on": "cliffhanger"
    }
  ]
}

ends_on must be one of: cliffhanger, resolution, transition, revelation\
"""


class OutlineGenerator:
    def __init__(self, client: LLMClient):
        self._client = client

    def _world_brief(self, world: WorldState) -> str:
        chars = ", ".join(
            f"{c.name} ({c.role.value})" for c in world.characters
        )
        rules = " | ".join(r.rule for r in world.world_rules[:5])
        return (
            f"Title: {world.title} | Genre: {world.genre}\n"
            f"Setting: {world.setting[:300]}\n"
            f"Central Conflict: {world.central_conflict}\n"
            f"Themes: {', '.join(world.themes)}\n"
            f"Characters: {chars}\n"
            f"Key Rules: {rules}"
        )

    def _generate_arc(
        self, arc_num: int, world_brief: str, world: WorldState
    ) -> tuple[str, list[ChapterOutline]]:
        start = (arc_num - 1) * 20 + 1
        count = 20
        arc_name = _ARC_NAMES[arc_num]
        arc_brief = _ARC_BRIEFS[arc_num]

        prompt = (
            f"{world_brief}\n\n"
            f"Arc {arc_num}: {arc_name}\n"
            f"Arc goal: {arc_brief}\n\n"
            f"Characters who must resolve in this arc (if arc 5): "
            f"{', '.join(c.name for c in world.characters)}\n\n"
            f"{_ARC_SCHEMA}\n"
            f"Generate exactly {count} chapters starting at chapter {start}."
        )

        data = self._client.complete_json(
            messages=[{"role": "user", "content": prompt}],
            system=_SYSTEM,
            num_ctx=4096,
        )

        arc_desc = data.get("arc_description", arc_brief)
        chapters = [
            ChapterOutline(
                chapter_number=c.get("chapter_number", start + i),
                arc=arc_num,
                arc_name=arc_name,
                title=c.get("title", f"Chapter {start + i}"),
                summary=c.get("summary", ""),
                key_events=c.get("key_events", []),
                characters_involved=c.get("characters_involved", []),
                plot_purpose=c.get("plot_purpose", ""),
                ends_on=c.get("ends_on", "transition"),
            )
            for i, c in enumerate(data.get("chapters", []))
        ]
        return arc_desc, chapters

    def generate(self, world: WorldState) -> StoryOutline:
        world_brief = self._world_brief(world)
        arc_descriptions: dict[str, str] = {}
        all_chapters: list[ChapterOutline] = []

        for arc_num in range(1, 6):
            logger.info(f"  Generating arc {arc_num}/5: {_ARC_NAMES[arc_num]}")
            arc_desc, chapters = self._generate_arc(arc_num, world_brief, world)
            arc_descriptions[str(arc_num)] = arc_desc
            all_chapters.extend(chapters)

        all_chapters.sort(key=lambda c: c.chapter_number)
        return StoryOutline(
            total_chapters=100,
            arc_descriptions=arc_descriptions,
            chapters=all_chapters,
        )
