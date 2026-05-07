from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class CharacterRole(str, Enum):
    PROTAGONIST = "protagonist"
    ANTAGONIST = "antagonist"
    SUPPORTING = "supporting"
    MINOR = "minor"


class Character(BaseModel):
    name: str
    role: CharacterRole
    description: str
    traits: list[str]
    goals: list[str]
    fears: list[str] = Field(default_factory=list)
    alive: bool = True
    chapter_introduced: int = 1
    current_location: str = "unknown"


class WorldRule(BaseModel):
    rule: str
    category: str  # magic, physics, social, political, economic
    is_absolute: bool = True  # can it ever be broken?


class WorldState(BaseModel):
    title: str
    genre: str
    setting: str
    time_period: str
    characters: list[Character]
    world_rules: list[WorldRule]
    themes: list[str]
    central_conflict: str
    locations: list[str] = Field(default_factory=list)


class ChapterOutline(BaseModel):
    chapter_number: int
    arc: int  # 1-5
    arc_name: str
    title: str
    summary: str
    key_events: list[str]
    characters_involved: list[str]
    plot_purpose: str
    ends_on: str  # cliffhanger / resolution / transition


class StoryOutline(BaseModel):
    total_chapters: int = 100
    arc_descriptions: dict[str, str]  # arc_num -> description
    chapters: list[ChapterOutline]


class ExtractedFact(BaseModel):
    type: str  # character_state, relationship, event, location_change, death
    subject: str
    predicate: str
    object: str
    chapter: int


class ValidationResult(BaseModel):
    passed: bool
    hard_violations: list[str] = Field(default_factory=list)
    soft_score: float = 1.0
    soft_breakdown: dict[str, float] = Field(default_factory=dict)
    notes: str = ""


class Chapter(BaseModel):
    number: int
    title: str
    content: str
    word_count: int
    arc: int
    consistency_score: float = 0.0
    extracted_facts: list[ExtractedFact] = Field(default_factory=list)
    rewrite_count: int = 0


class StoryState(BaseModel):
    story_id: str
    genre: str
    intro: str
    world_state: Optional[WorldState] = None
    outline: Optional[StoryOutline] = None
    chapters: list[Chapter] = Field(default_factory=list)
    current_chapter: int = 0
    global_consistency_score: float = 1.0
    rolling_summary: str = ""
    status: str = "initializing"  # initializing / generating / complete / failed
