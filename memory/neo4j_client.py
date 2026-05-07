from __future__ import annotations
import os
from neo4j import AsyncGraphDatabase, AsyncDriver
from models import Character, WorldRule, ExtractedFact, WorldState


class Neo4jClient:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self):
        await self._driver.close()

    async def setup_schema(self):
        async with self._driver.session() as session:
            await session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Character) REQUIRE c.name IS UNIQUE")
            await session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (l:Location) REQUIRE l.name IS UNIQUE")
            await session.run("CREATE INDEX IF NOT EXISTS FOR (e:Event) ON (e.chapter)")

    async def init_world(self, story_id: str, world: WorldState):
        async with self._driver.session() as session:
            await session.run(
                "MERGE (w:World {story_id: $sid}) SET w.title = $title, w.genre = $genre, "
                "w.setting = $setting, w.conflict = $conflict",
                sid=story_id, title=world.title, genre=world.genre,
                setting=world.setting, conflict=world.central_conflict,
            )
            for loc in world.locations:
                await session.run("MERGE (:Location {name: $name})", name=loc)
            for rule in world.world_rules:
                await session.run(
                    "MERGE (:WorldRule {rule: $rule, category: $cat, is_absolute: $abs})",
                    rule=rule.rule, cat=rule.category, abs=rule.is_absolute,
                )
            for char in world.characters:
                await self._upsert_character(session, char)

    async def _upsert_character(self, session, char: Character):
        await session.run(
            """
            MERGE (c:Character {name: $name})
            SET c.role = $role,
                c.description = $desc,
                c.traits = $traits,
                c.goals = $goals,
                c.fears = $fears,
                c.alive = $alive,
                c.chapter_introduced = $ch,
                c.current_location = $loc
            """,
            name=char.name, role=char.role.value, desc=char.description,
            traits=char.traits, goals=char.goals, fears=char.fears,
            alive=char.alive, ch=char.chapter_introduced, loc=char.current_location,
        )

    async def get_all_characters(self) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run("MATCH (c:Character) RETURN c")
            records = await result.data()
            return [r["c"] for r in records]

    async def get_living_characters(self) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run("MATCH (c:Character {alive: true}) RETURN c")
            records = await result.data()
            return [r["c"] for r in records]

    async def is_character_alive(self, name: str) -> bool:
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (c:Character {name: $name}) RETURN c.alive AS alive", name=name
            )
            record = await result.single()
            if record is None:
                return False
            return record["alive"]

    async def get_world_rules(self) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run("MATCH (r:WorldRule) RETURN r")
            records = await result.data()
            return [r["r"] for r in records]

    async def apply_facts(self, facts: list[ExtractedFact]):
        async with self._driver.session() as session:
            for fact in facts:
                if fact.type == "death":
                    await session.run(
                        "MATCH (c:Character {name: $name}) SET c.alive = false",
                        name=fact.subject,
                    )
                elif fact.type == "location_change":
                    await session.run(
                        "MATCH (c:Character {name: $name}) SET c.current_location = $loc",
                        name=fact.subject, loc=fact.object,
                    )
                elif fact.type == "relationship":
                    await session.run(
                        """
                        MERGE (a:Character {name: $subj})
                        MERGE (b:Character {name: $obj})
                        MERGE (a)-[r:RELATED {type: $pred, chapter: $ch}]->(b)
                        """,
                        subj=fact.subject, pred=fact.predicate,
                        obj=fact.object, ch=fact.chapter,
                    )
                elif fact.type == "event":
                    await session.run(
                        "CREATE (:Event {subject: $subj, action: $pred, object: $obj, chapter: $ch})",
                        subj=fact.subject, pred=fact.predicate,
                        obj=fact.object, ch=fact.chapter,
                    )

    async def get_chapter_events(self, chapter: int) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (e:Event {chapter: $ch}) RETURN e", ch=chapter
            )
            records = await result.data()
            return [r["e"] for r in records]

    async def get_recent_events(self, since_chapter: int) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (e:Event) WHERE e.chapter >= $ch RETURN e ORDER BY e.chapter",
                ch=since_chapter,
            )
            records = await result.data()
            return [r["e"] for r in records]
