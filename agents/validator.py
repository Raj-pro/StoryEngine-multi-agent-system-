from __future__ import annotations
from models import ChapterOutline, ExtractedFact, ValidationResult, WorldState
from llm_client import LLMClient

_JUDGE_SYSTEM = """\
You are a narrative consistency judge. Score a chapter draft on four dimensions. \
Be strict — accepted chapters are committed permanently. Respond with ONLY valid JSON.\
"""

_JUDGE_SCHEMA = """\
Return a JSON object:
{
  "consistency": 0.9,
  "logic": 0.85,
  "tone": 0.8,
  "outline_alignment": 0.9,
  "notes": "any issues found, or empty string"
}

Scores are 0.0 to 1.0:
  consistency      - does nothing contradict established world facts?
  logic            - are motivations and plot events internally sound?
  tone             - does tone match the genre and established voice?
  outline_alignment - did the chapter include all required key events?\
"""


class ValidatorAgent:
    def __init__(self, client: LLMClient):
        self._client = client
        self._weights = {
            "consistency": 0.40,
            "logic": 0.25,
            "tone": 0.20,
            "outline_alignment": 0.15,
        }

    def hard_validate(
        self,
        facts: list[ExtractedFact],
        characters: list[dict],
    ) -> tuple[bool, list[str]]:
        violations: list[str] = []
        char_map = {c["name"]: c for c in characters}
        for fact in facts:
            if fact.type in ("event", "location_change", "relationship"):
                subj = char_map.get(fact.subject)
                if subj and not subj.get("alive", True):
                    violations.append(
                        f"Dead character '{fact.subject}' performs action '{fact.predicate}'"
                    )
            if fact.type == "death":
                subj = char_map.get(fact.subject)
                if subj and not subj.get("alive", True):
                    violations.append(f"'{fact.subject}' is killed again but was already dead")
        return len(violations) == 0, violations

    def soft_validate(
        self,
        chapter_text: str,
        chapter_outline: ChapterOutline,
        world: WorldState,
        rolling_context: str,
    ) -> dict:
        outline_ctx = (
            f"Required events: {', '.join(chapter_outline.key_events)}\n"
            f"Characters involved: {', '.join(chapter_outline.characters_involved)}\n"
            f"Plot purpose: {chapter_outline.plot_purpose}"
        )
        world_ctx = (
            f"Genre: {world.genre} | Themes: {', '.join(world.themes)}\n"
            f"Rules: {'; '.join(r.rule for r in world.world_rules[:4])}"
        )
        prompt = (
            f"Story context (recent):\n{rolling_context[-1000:] if rolling_context else 'Start of story.'}\n\n"
            f"World:\n{world_ctx}\n\n"
            f"Chapter outline:\n{outline_ctx}\n\n"
            f"Chapter draft:\n{chapter_text[:2000]}\n\n"
            f"{_JUDGE_SCHEMA}"
        )
        return self._client.complete_json(
            messages=[{"role": "user", "content": prompt}],
            system=_JUDGE_SYSTEM,
            temperature=0.1,
        )

    def compute_final_score(self, soft: dict) -> float:
        return sum(
            float(soft.get(k, 0.0)) * w for k, w in self._weights.items()
        )

    def validate(
        self,
        chapter_text: str,
        chapter_outline: ChapterOutline,
        world: WorldState,
        facts: list[ExtractedFact],
        characters: list[dict],
        rolling_context: str,
    ) -> ValidationResult:
        hard_pass, hard_violations = self.hard_validate(facts, characters)
        soft = self.soft_validate(chapter_text, chapter_outline, world, rolling_context)
        notes = soft.pop("notes", "")
        composite = self.compute_final_score(soft)
        return ValidationResult(
            passed=hard_pass,
            hard_violations=hard_violations,
            soft_score=composite,
            soft_breakdown={k: float(v) for k, v in soft.items()},
            notes=str(notes),
        )
