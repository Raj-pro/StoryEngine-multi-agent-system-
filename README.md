# Narrative Consistency Engine

A multi-agent system that generates 100-chapter stories from a genre and a single paragraph premise, using a convergence loop to maintain strict global consistency across every chapter.

> **Core principle: Consistency is the only boundary.**
> The engine does not generate chapters sequentially — it iteratively converges toward a globally stable narrative state.

---

## How it works

```
INPUT (genre + premise)
    │
    ▼
WORLD INITIALIZER ──────── expands premise into characters, rules, locations
    │
    ▼
OUTLINE GENERATOR ──────── builds 100-chapter arc structure (5 × 20 chapters)
    │
    ▼
CONVERGENCE LOOP (per chapter)
    │
    ├── 1. Context Assembly   load graph facts + vector memory + rolling summary
    ├── 2. Writer Agent       generate chapter draft (~700 words)
    ├── 3. Extractor Agent    convert prose → structured facts (deaths, moves, events)
    ├── 4. Hard Validation    check facts against graph (dead chars can't act, etc.)
    ├── 5. Soft Validation    LLM judge scores consistency / logic / tone / alignment
    ├── 6. Rewrite if needed  up to 3 attempts to reach score ≥ 0.85
    └── 7. Commit             update graph, store embedding, advance rolling summary
```

---

## Stack

| Component | Technology |
|---|---|
| LLM | [Ollama](https://ollama.com) — local 7B model (Mistral, LLaMA 3, Phi-3) |
| Canonical truth (graph) | Neo4j via Docker — or **in-memory fallback** (no Docker required) |
| Semantic memory | ChromaDB (in-process, no server needed) |
| GUI | Streamlit |
| CLI | Typer |

---

## Quick start

### 1. Install Ollama and pull a model

```bash
# Install from https://ollama.com
ollama pull mistral        # recommended
# or: ollama pull llama3, phi3, mistral-nemo
```

### 2. Install Python dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — only OLLAMA_MODEL and OLLAMA_HOST are required
```

### 4. Run the GUI

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501), fill in the sidebar, and click **🚀 Generate Story**.

---

## GUI

```
Sidebar                     Tabs
────────────────────        ──────────────────────────────────────────────
Genre                       ⚡ Generate  — live chapter feed, world state card
Premise (text area)         📚 Library   — browse all saved stories
Chapters (slider 1–100)     📖 Read      — full chapter text with navigation
Ollama settings
🚀 Generate Story
```

Chapters appear live as they complete. Each card shows word count, consistency score, and rewrite count.

---

## CLI

```bash
# Generate 5 chapters
python3 main.py generate \
  --genre "dark fantasy" \
  --intro "A court assassin discovers she has been eliminating the last resistance against a god-emperor who rewrote history." \
  --chapters 5

# Read a saved story
python3 main.py show <story-id>
python3 main.py show <story-id> --chapter 3
```

---

## Optional: Neo4j (persistent graph)

By default the engine uses an **in-memory graph store** — no setup required. For persistent cross-session memory, start Neo4j with Docker:

```bash
cd infra && docker compose up -d
```

The engine detects Neo4j automatically on startup. If unavailable, it falls back silently.

---

## Project structure

```
├── app.py                        Streamlit GUI
├── main.py                       CLI entry point (Typer)
├── llm_client.py                 Ollama wrapper (complete / complete_json)
├── models.py                     Pydantic data models
│
├── agents/
│   ├── world_initializer.py      genre + premise → WorldState
│   ├── outline_generator.py      WorldState → 100-chapter outline (arc by arc)
│   ├── writer.py                 chapter draft + rewrite
│   ├── extractor.py              prose → ExtractedFacts (JSON mode)
│   └── validator.py              hard (graph rules) + soft (LLM judge) validation
│
├── memory/
│   ├── graph_store.py            in-memory graph (default)
│   ├── neo4j_client.py           Neo4j graph (optional, same interface)
│   ├── vector_store.py           ChromaDB semantic search over past chapters
│   └── summary_manager.py        rolling 3-chapter context window
│
├── orchestrator/
│   └── controller.py             MasterController — owns all agents, drives pipeline
│
├── pipelines/
│   └── chapter_loop.py           per-chapter convergence loop
│
├── infra/
│   └── docker-compose.yml        Neo4j service
│
├── data/
│   ├── chapters/                 saved chapter JSON + story state files
│   └── logs/                     generation logs
│
└── configs/
    └── config.yaml               generation settings
```

---

## Memory layers

| Layer | Store | What it holds |
|---|---|---|
| Canonical truth | Graph (Neo4j / in-memory) | Characters, alive/dead state, locations, relationships, events |
| Semantic memory | ChromaDB | Chapter embeddings — retrieves relevant past chapters by meaning |
| Rolling context | In-process | Full text of the last 3 chapters + cumulative summary of earlier ones |
| Outline | In-process | Fixed 100-chapter arc structure — hard constraint, never drifts |

---

## Consistency scoring

Each chapter is scored on four dimensions by an LLM judge:

| Dimension | Weight | What it checks |
|---|---|---|
| Consistency | 40% | Does anything contradict established world facts? |
| Logic | 25% | Are character motivations and plot events sound? |
| Tone | 20% | Does the writing match the genre and established voice? |
| Outline alignment | 15% | Were all required key events included? |

If score < 0.85 or any hard violation is found, the chapter is rewritten (up to 3 attempts). The best draft is always committed.

---

## Development phases

- [x] Phase 1 — World init → outline → chapter generation loop
- [x] Phase 2 — LLM judge soft validation
- [x] Phase 3 — Fact extraction → graph updates
- [x] Phase 4 — Graph memory (Neo4j + in-memory fallback)
- [ ] Phase 5 — Multi-draft consensus (generate A/B/C, merge best)
- [ ] Phase 6 — Global consistency engine + arc-level rollback
- [ ] Phase 7 — Kubernetes deployment
