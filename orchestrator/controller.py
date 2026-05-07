from __future__ import annotations
import uuid
import json
import logging
import asyncio
from pathlib import Path
from typing import Callable, Any
from llm_client import LLMClient
from models import StoryState
from agents.world_initializer import WorldInitializer
from agents.outline_generator import OutlineGenerator
from agents.writer import WriterAgent
from agents.extractor import ExtractorAgent
from agents.validator import ValidatorAgent
from memory.neo4j_client import Neo4jClient
from memory.graph_store import InMemoryGraphStore
from memory.vector_store import VectorStore
from memory.summary_manager import SummaryManager
from pipelines.chapter_loop import ChapterLoop

logger = logging.getLogger(__name__)


async def _make_graph_store():
    """Try Neo4j; fall back to in-memory store if unavailable."""
    try:
        client = Neo4jClient()
        await client.setup_schema()
        logger.info("Graph store: Neo4j")
        return client
    except Exception as exc:
        logger.warning(f"Neo4j unavailable ({exc}); using in-memory graph store")
        return InMemoryGraphStore()

DATA_DIR = Path("data/chapters")


class MasterController:
    """
    Lifecycle owner. Drives the full pipeline from input to final story.
    Owns all agents and memory clients; nothing else creates these.

    progress_callback(event_type, *data) is called at key milestones so the
    caller (CLI or GUI) can display live updates without polling files.

    Events emitted:
        ("status",        message: str)
        ("world_ready",   world_dict: dict)
        ("outline_ready", chapter_count: int)
        ("chapter_start", chapter_num: int, title: str)
        ("chapter_done",  chapter_dict: dict)
        ("complete",      story_id: str)
        ("error",         message: str)
    """

    def __init__(
        self,
        target_chapters: int = 5,
        progress_callback: Callable[..., Any] | None = None,
    ):
        self._client = LLMClient()
        self._target_chapters = target_chapters
        self._cb = progress_callback or (lambda *_: None)

        self._world_init = WorldInitializer(self._client)
        self._outline_gen = OutlineGenerator(self._client)
        self._writer = WriterAgent(self._client, target_words=700)
        self._extractor = ExtractorAgent(self._client)
        self._validator = ValidatorAgent(self._client)

        self._graph = None          # resolved async in run()
        self._vector_store = VectorStore()
        self._summary = SummaryManager(window=3)

        DATA_DIR.mkdir(parents=True, exist_ok=True)

    async def run(self, genre: str, intro: str) -> StoryState:
        story_id = str(uuid.uuid4())[:8]
        state = StoryState(story_id=story_id, genre=genre, intro=intro)

        logger.info(f"Story {story_id}: starting ({self._target_chapters} chapters)")

        # ── Phase 0: Graph store (Neo4j or in-memory fallback) ────────────────
        self._graph = await _make_graph_store()
        graph_label = "Neo4j" if isinstance(self._graph, Neo4jClient) else "in-memory"
        self._cb("status", f"Graph store: {graph_label}")
        self._chapter_loop = ChapterLoop(
            writer=self._writer,
            extractor=self._extractor,
            validator=self._validator,
            neo4j=self._graph,
            vector_store=self._vector_store,
            summary_manager=self._summary,
        )

        # ── Phase 1: World ─────────────────────────────────────────────────────
        state.status = "world_init"
        self._cb("status", "Initializing world…")
        logger.info("Initializing world...")

        state.world_state = self._world_init.initialize(genre, intro)
        self._cb("world_ready", state.world_state.model_dump())
        logger.info(
            f"World: '{state.world_state.title}' — "
            f"{len(state.world_state.characters)} characters, "
            f"{len(state.world_state.world_rules)} rules"
        )
        await self._graph.init_world(story_id, state.world_state)
        self._save_state(state, "world")

        # ── Phase 2: Outline ───────────────────────────────────────────────────
        state.status = "outline_gen"
        self._cb("status", "Generating 100-chapter outline (5 arcs)…")
        logger.info("Generating 100-chapter outline...")

        state.outline = self._outline_gen.generate(state.world_state)
        self._cb("outline_ready", len(state.outline.chapters))
        logger.info(f"Outline ready: {len(state.outline.chapters)} chapters across 5 arcs")
        self._save_state(state, "outline")

        # ── Phase 3: Convergence loop ──────────────────────────────────────────
        state.status = "generating"
        for ch_num in range(1, self._target_chapters + 1):
            ch_outline = state.outline.chapters[ch_num - 1]
            self._cb("status", f"Writing chapter {ch_num}/{self._target_chapters}: '{ch_outline.title}'…")
            self._cb("chapter_start", ch_num, ch_outline.title)

            chapter = await self._chapter_loop.run(ch_num, state)
            state.chapters.append(chapter)
            state.current_chapter = ch_num
            self._save_chapter(chapter, story_id)
            self._update_global_score(state)

            self._cb("chapter_done", {
                "number": chapter.number,
                "title": chapter.title,
                "arc": chapter.arc,
                "word_count": chapter.word_count,
                "consistency_score": chapter.consistency_score,
                "rewrite_count": chapter.rewrite_count,
                "content": chapter.content,
            })

        state.status = "complete"
        self._save_state(state, "final")
        self._cb("complete", story_id)
        logger.info(
            f"Story {story_id} complete. "
            f"Global consistency: {state.global_consistency_score:.2f}"
        )
        await self._graph.close()
        return state

    def _update_global_score(self, state: StoryState):
        if not state.chapters:
            return
        state.global_consistency_score = sum(
            c.consistency_score for c in state.chapters
        ) / len(state.chapters)

    def _save_chapter(self, chapter, story_id: str):
        path = DATA_DIR / f"{story_id}_ch{chapter.number:03d}.json"
        path.write_text(
            json.dumps(
                {
                    "number": chapter.number,
                    "title": chapter.title,
                    "arc": chapter.arc,
                    "word_count": chapter.word_count,
                    "consistency_score": chapter.consistency_score,
                    "rewrite_count": chapter.rewrite_count,
                    "content": chapter.content,
                },
                indent=2,
            )
        )

    def _save_state(self, state: StoryState, tag: str):
        path = DATA_DIR / f"{state.story_id}_state_{tag}.json"
        path.write_text(state.model_dump_json(indent=2))
