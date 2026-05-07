from __future__ import annotations
import logging
from models import Chapter, ChapterOutline, StoryState, ValidationResult
from agents.writer import WriterAgent
from agents.extractor import ExtractorAgent
from agents.validator import ValidatorAgent
from memory.neo4j_client import Neo4jClient
from memory.vector_store import VectorStore
from memory.summary_manager import SummaryManager

logger = logging.getLogger(__name__)

OUTLINE_WINDOW = 5   # chapters before + after for outline context
CONSISTENCY_THRESHOLD = 0.85
MAX_REWRITE_ATTEMPTS = 3


class ChapterLoop:
    """
    Core convergence loop for a single chapter.
    Runs: write → extract → hard-validate → soft-validate → rewrite if needed → commit
    """

    def __init__(
        self,
        writer: WriterAgent,
        extractor: ExtractorAgent,
        validator: ValidatorAgent,
        neo4j: Neo4jClient,
        vector_store: VectorStore,
        summary_manager: SummaryManager,
    ):
        self._writer = writer
        self._extractor = extractor
        self._validator = validator
        self._neo4j = neo4j
        self._vector_store = vector_store
        self._summary = summary_manager

    def _outline_window(
        self, outline_chapters: list[ChapterOutline], current_num: int
    ) -> list[ChapterOutline]:
        start = max(0, current_num - 3)
        end = min(len(outline_chapters), current_num + OUTLINE_WINDOW)
        return outline_chapters[start:end]

    async def run(self, chapter_num: int, state: StoryState) -> Chapter:
        outline = state.outline
        world = state.world_state
        chapter_outline = outline.chapters[chapter_num - 1]

        logger.info(f"Chapter {chapter_num}: '{chapter_outline.title}' — generating")

        # --- Context Assembly ---
        characters = await self._neo4j.get_all_characters()
        rolling_context = self._summary.get_rolling_context()
        relevant_past = self._vector_store.query_relevant(
            query=f"{chapter_outline.summary} {chapter_outline.title}",
            top_k=5,
            exclude_chapter=chapter_num,
        )
        outline_window = self._outline_window(outline.chapters, chapter_num - 1)

        best_draft: str | None = None
        best_result: ValidationResult | None = None
        best_score: float = -1.0

        for attempt in range(MAX_REWRITE_ATTEMPTS):
            # --- Generation ---
            if attempt == 0 or best_draft is None:
                draft = self._writer.write(
                    chapter_outline=chapter_outline,
                    world=world,
                    characters=characters,
                    rolling_context=rolling_context,
                    relevant_past=relevant_past,
                    outline_window=outline_window,
                )
            else:
                all_violations = best_result.hard_violations + (
                    [best_result.notes] if best_result.notes else []
                )
                draft = self._writer.rewrite(
                    draft=best_draft,
                    violations=all_violations,
                    chapter_outline=chapter_outline,
                    world=world,
                    characters=characters,
                    rolling_context=rolling_context,
                    outline_window=outline_window,
                )

            # --- Fact Extraction ---
            facts = self._extractor.extract(chapter_num, draft)

            # --- Validation ---
            result = self._validator.validate(
                chapter_text=draft,
                chapter_outline=chapter_outline,
                world=world,
                facts=facts,
                characters=characters,
                rolling_context=rolling_context,
            )

            composite = result.soft_score if result.passed else result.soft_score * 0.5

            logger.info(
                f"  Attempt {attempt + 1}: hard={'PASS' if result.passed else 'FAIL'} "
                f"soft={result.soft_score:.2f} composite={composite:.2f}"
            )

            if composite > best_score:
                best_score = composite
                best_draft = draft
                best_result = result
                # Store the facts alongside the best draft
                best_facts = facts

            if result.passed and result.soft_score >= CONSISTENCY_THRESHOLD:
                logger.info(f"  Chapter {chapter_num}: accepted on attempt {attempt + 1}")
                break
        else:
            logger.warning(
                f"  Chapter {chapter_num}: max attempts reached, committing best draft "
                f"(score={best_score:.2f})"
            )

        # --- Commit Phase ---
        chapter = Chapter(
            number=chapter_num,
            title=chapter_outline.title,
            content=best_draft,
            word_count=len(best_draft.split()),
            arc=chapter_outline.arc,
            consistency_score=best_score,
            extracted_facts=best_facts,
            rewrite_count=max(0, attempt),
        )

        await self._neo4j.apply_facts(best_facts)
        self._vector_store.add_chapter(
            chapter_number=chapter_num,
            title=chapter_outline.title,
            content=best_draft,
            arc=chapter_outline.arc,
        )
        self._summary.add_chapter(chapter)

        logger.info(
            f"Chapter {chapter_num} committed: {chapter.word_count} words, "
            f"score={chapter.consistency_score:.2f}"
        )
        return chapter
