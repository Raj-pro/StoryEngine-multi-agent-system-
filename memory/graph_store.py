"""
In-memory graph store — drop-in replacement for Neo4jClient when
Neo4j is unavailable. Stores characters, events, and world rules
as plain Python dicts with the same async interface.
"""
from __future__ import annotations
from models import ExtractedFact, WorldState


class InMemoryGraphStore:
    def __init__(self):
        self._characters: dict[str, dict] = {}
        self._events: list[dict] = []
        self._rules: list[dict] = []

    async def close(self):
        pass

    async def setup_schema(self):
        pass

    async def init_world(self, story_id: str, world: WorldState):
        for char in world.characters:
            self._characters[char.name] = {
                "name": char.name,
                "role": char.role.value,
                "description": char.description,
                "traits": char.traits,
                "goals": char.goals,
                "fears": char.fears,
                "alive": True,
                "chapter_introduced": char.chapter_introduced,
                "current_location": char.current_location,
            }
        self._rules = [
            {"rule": r.rule, "category": r.category, "is_absolute": r.is_absolute}
            for r in world.world_rules
        ]

    async def get_all_characters(self) -> list[dict]:
        return list(self._characters.values())

    async def get_living_characters(self) -> list[dict]:
        return [c for c in self._characters.values() if c.get("alive", True)]

    async def is_character_alive(self, name: str) -> bool:
        return self._characters.get(name, {}).get("alive", True)

    async def get_world_rules(self) -> list[dict]:
        return self._rules

    async def apply_facts(self, facts: list[ExtractedFact]):
        for fact in facts:
            if fact.type == "death":
                if fact.subject in self._characters:
                    self._characters[fact.subject]["alive"] = False
            elif fact.type == "location_change":
                if fact.subject in self._characters:
                    self._characters[fact.subject]["current_location"] = fact.object
            else:
                self._events.append({
                    "type": fact.type,
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                    "object": fact.object,
                    "chapter": fact.chapter,
                })

    async def get_chapter_events(self, chapter: int) -> list[dict]:
        return [e for e in self._events if e.get("chapter") == chapter]

    async def get_recent_events(self, since_chapter: int) -> list[dict]:
        return [e for e in self._events if e.get("chapter", 0) >= since_chapter]
