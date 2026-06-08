from __future__ import annotations
from models import ExtractedFact
from llm_client import LLMClient

_SYSTEM = """\
You are a fact extractor. Extract state-changing facts from a story chapter as JSON. \
Only extract facts that represent a CHANGE from before the chapter. \
Respond with ONLY valid JSON.\
"""

_SCHEMA = """\
Return a JSON object:
{
  "facts": [
    {
      "type": "death",
      "subject": "Character Name",
      "predicate": "is killed by",
      "object": "killer or cause"
    }
  ]
}

type must be one of:
  death          - a character dies
  location_change - a character moves to a new place
  relationship   - a new bond, alliance, or enmity forms
  event          - a significant plot event occurs
  character_state - a character's goal, belief, or status changes

Extract ALL state changes. Return {"facts": []} if nothing changed.\
"""


class ExtractorAgent:
    def __init__(self, client: LLMClient):
        self._client = client

    def extract(self, chapter_number: int, chapter_text: str) -> list[ExtractedFact]:
        prompt = (
            f"Chapter {chapter_number}:\n\n{chapter_text}\n\n"
            f"{_SCHEMA}"
        )
        data = self._client.complete_json(
            messages=[{"role": "user", "content": prompt}],
            system=_SYSTEM,
        )
        return [
            ExtractedFact(
                type=f.get("type") or "event",
                subject=f.get("subject") or "",
                predicate=f.get("predicate") or "",
                object=f.get("object") or "",
                chapter=chapter_number,
            )
            for f in data.get("facts", [])
            if f.get("subject")  
        ]
