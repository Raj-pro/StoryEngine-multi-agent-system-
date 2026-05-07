from __future__ import annotations
from models import WorldState, Character, CharacterRole, WorldRule
from llm_client import LLMClient

_SYSTEM = """\
You are a master world-builder. Expand the given genre and story intro into a \
rich, internally consistent fictional world. All rules must be specific enough \
to be mechanically validated (e.g. "magic costs one year of life per spell cast" \
not "magic is dangerous"). Respond with ONLY a valid JSON object.\
"""

_SCHEMA = """\
Return a JSON object with exactly these fields:
{
  "title": "compelling story title",
  "genre": "genre string",
  "setting": "rich multi-sentence world description",
  "time_period": "era or date range",
  "central_conflict": "the primary dramatic tension driving all 100 chapters",
  "themes": ["theme1", "theme2", "theme3"],
  "locations": ["place1", "place2", "place3", "place4", "place5"],
  "characters": [
    {
      "name": "Full Name",
      "role": "protagonist",
      "description": "physical and personality description",
      "traits": ["trait1", "trait2"],
      "goals": ["goal1", "goal2"],
      "fears": ["fear1"],
      "current_location": "place name"
    }
  ],
  "world_rules": [
    {
      "rule": "specific inviolable rule",
      "category": "magic",
      "is_absolute": true
    }
  ]
}

role must be one of: protagonist, antagonist, supporting, minor
category must be one of: magic, physics, social, political, economic
Include 3-7 characters and 5-8 world rules.\
"""


class WorldInitializer:
    def __init__(self, client: LLMClient):
        self._client = client

    def initialize(self, genre: str, intro: str) -> WorldState:
        prompt = (
            f"Genre: {genre}\n\n"
            f"Story Introduction:\n{intro}\n\n"
            f"{_SCHEMA}"
        )
        data = self._client.complete_json(
            messages=[{"role": "user", "content": prompt}],
            system=_SYSTEM,
        )

        characters = [
            Character(
                name=c["name"],
                role=CharacterRole(c.get("role", "supporting")),
                description=c.get("description", ""),
                traits=c.get("traits", []),
                goals=c.get("goals", []),
                fears=c.get("fears", []),
                current_location=c.get("current_location", "unknown"),
            )
            for c in data.get("characters", [])
        ]

        rules = [
            WorldRule(
                rule=r["rule"],
                category=r.get("category", "social"),
                is_absolute=r.get("is_absolute", True),
            )
            for r in data.get("world_rules", [])
        ]

        return WorldState(
            title=data.get("title", "Untitled"),
            genre=data.get("genre", genre),
            setting=data.get("setting", ""),
            time_period=data.get("time_period", "unknown"),
            characters=characters,
            world_rules=rules,
            themes=data.get("themes", []),
            central_conflict=data.get("central_conflict", ""),
            locations=data.get("locations", []),
        )
