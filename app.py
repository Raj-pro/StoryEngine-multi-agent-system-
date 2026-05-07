"""
Narrative Consistency Engine — Streamlit GUI
Run: streamlit run app.py
"""
from __future__ import annotations
import asyncio
import json
import os
import queue as _queue
import sys
import threading
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Narrative Consistency Engine",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .chapter-card { padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem; }
    .score-good   { color: #22c55e; font-weight: 600; }
    .score-mid    { color: #f59e0b; font-weight: 600; }
    .score-bad    { color: #ef4444; font-weight: 600; }
    .chapter-body { line-height: 1.8; font-size: 1.05rem; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; }
</style>
""", unsafe_allow_html=True)

DATA_DIR = Path("data/chapters")

# ── Session state init ─────────────────────────────────────────────────────────
_DEFAULTS: dict = {
    "generating":      False,
    "q":               None,
    "thread":          None,
    "chapters":        [],
    "world":           None,
    "outline_count":   0,
    "story_id":        None,
    "story_title":     "—",
    "current_status":  "idle",
    "current_ch":      0,
    "total_ch":        5,
    "error":           None,
    "read_story_id":   None,
    "read_ch":         1,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Helpers ────────────────────────────────────────────────────────────────────

def _score_badge(score: float) -> str:
    if score >= 0.85:
        return f'<span class="score-good">● {score:.2f}</span>'
    if score >= 0.70:
        return f'<span class="score-mid">● {score:.2f}</span>'
    return f'<span class="score-bad">● {score:.2f}</span>'


def _load_library() -> list[dict]:
    if not DATA_DIR.exists():
        return []
    stories = []
    for path in sorted(DATA_DIR.glob("*_state_final.json"), reverse=True):
        try:
            d = json.loads(path.read_text())
            world = d.get("world_state") or {}
            stories.append({
                "story_id":  d.get("story_id", path.stem[:8]),
                "title":     world.get("title", "Untitled"),
                "genre":     world.get("genre", "—"),
                "chapters":  d.get("current_chapter", 0),
                "score":     round(d.get("global_consistency_score", 0.0), 2),
            })
        except Exception:
            pass
    return stories


def _load_chapters_from_disk(story_id: str) -> list[dict]:
    chapters = []
    for path in sorted(DATA_DIR.glob(f"{story_id}_ch*.json")):
        try:
            chapters.append(json.loads(path.read_text()))
        except Exception:
            pass
    return chapters


# ── Progress queue consumer ────────────────────────────────────────────────────

def _drain_queue():
    q = st.session_state.q
    if q is None:
        return
    while True:
        try:
            event = q.get_nowait()
        except _queue.Empty:
            break
        kind = event[0]
        if kind == "status":
            st.session_state.current_status = event[1]
        elif kind == "world_ready":
            st.session_state.world = event[1]
            st.session_state.story_title = event[1].get("title", "Untitled")
        elif kind == "outline_ready":
            st.session_state.outline_count = event[1]
        elif kind == "chapter_done":
            ch = event[1]
            # avoid duplicates on rerun
            existing = {c["number"] for c in st.session_state.chapters}
            if ch["number"] not in existing:
                st.session_state.chapters.append(ch)
            st.session_state.current_ch = ch["number"]
        elif kind == "complete":
            st.session_state.generating = False
            st.session_state.story_id = event[1]
            st.session_state.current_status = "complete"
        elif kind == "error":
            st.session_state.generating = False
            st.session_state.error = event[1]
            st.session_state.current_status = "error"

    # Mark done if thread finished
    t = st.session_state.thread
    if t and not t.is_alive() and st.session_state.generating:
        st.session_state.generating = False


# ── Background generation thread ───────────────────────────────────────────────

def _start_generation(genre: str, intro: str, num_chapters: int):
    # reset state
    st.session_state.q         = _queue.Queue()
    st.session_state.chapters  = []
    st.session_state.world     = None
    st.session_state.outline_count = 0
    st.session_state.current_ch = 0
    st.session_state.total_ch  = num_chapters
    st.session_state.story_id  = None
    st.session_state.error     = None
    st.session_state.generating = True
    st.session_state.current_status = "Starting…"

    q = st.session_state.q

    def _cb(*args):
        q.put(args)

    def _run():
        # Ensure project root is on sys.path when running from thread
        root = str(Path(__file__).parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        from orchestrator.controller import MasterController
        controller = MasterController(
            target_chapters=num_chapters,
            progress_callback=_cb,
        )
        try:
            asyncio.run(controller.run(genre=genre, intro=intro))
        except Exception as exc:
            q.put(("error", str(exc)))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    st.session_state.thread = t


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📖 NCE")
    st.caption("Narrative Consistency Engine")
    st.divider()

    genre = st.text_input(
        "Genre",
        value="dark fantasy",
        disabled=st.session_state.generating,
    )
    intro = st.text_area(
        "Story Premise",
        height=180,
        placeholder="A court assassin discovers she has been eliminating the last resistance against a god-emperor who rewrote history…",
        disabled=st.session_state.generating,
    )
    num_chapters = st.slider(
        "Chapters to generate",
        min_value=1, max_value=100, value=5,
        disabled=st.session_state.generating,
    )

    with st.expander("⚙ Ollama Settings"):
        model_val = st.text_input("Model", value=os.getenv("OLLAMA_MODEL", "mistral"))
        host_val  = st.text_input("Host",  value=os.getenv("OLLAMA_HOST",  "http://localhost:11434"))
        os.environ["OLLAMA_MODEL"] = model_val
        os.environ["OLLAMA_HOST"]  = host_val

    st.divider()

    can_generate = bool(intro.strip()) and not st.session_state.generating
    if st.button("🚀 Generate Story", use_container_width=True,
                 type="primary", disabled=not can_generate):
        _start_generation(genre, intro, num_chapters)
        st.rerun()

    if st.session_state.generating:
        st.caption(f"⏳ {st.session_state.current_status}")


# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_gen, tab_lib, tab_read = st.tabs(["⚡ Generate", "📚 Library", "📖 Read"])


# ── Generate tab ───────────────────────────────────────────────────────────────
with tab_gen:

    # Welcome screen (only shown before first generation)
    if not st.session_state.generating and not st.session_state.chapters and not st.session_state.error:
        st.markdown("""
        ### Welcome

        Configure your story in the sidebar, then click **🚀 Generate Story**.

        **What happens:**
        | Phase | What the engine does |
        |---|---|
        | 🌍 World Init | Expands your premise into characters, world rules, locations |
        | 🗺 Outline | Builds a 100-chapter arc structure (5 arcs × 20 chapters) |
        | 🔁 Convergence Loop | Writes → extracts facts → validates → rewrites until consistent |

        > Neo4j is **optional** — the engine uses an in-memory graph store automatically
        > if Docker is not running.
        """)

    # Live feed fragment — reruns every second; owns all dynamic status output
    @st.fragment(run_every=1)
    def _live_feed():
        _drain_queue()

        # ── Error / complete banners (must be inside fragment to update live) ──
        if st.session_state.error:
            st.error(f"**Generation failed:** {st.session_state.error}")
            return

        if st.session_state.current_status == "complete" and st.session_state.chapters:
            world_d = st.session_state.world or {}
            title = world_d.get("title", "Story")
            st.success(
                f"✅ **{title}** — generation complete  ·  ID: `{st.session_state.story_id}`"
            )
            chapters_c = st.session_state.chapters
            avg_score = sum(c["consistency_score"] for c in chapters_c) / len(chapters_c)
            avg_words = int(sum(c["word_count"] for c in chapters_c) / len(chapters_c))
            rewrites_c = sum(c.get("rewrite_count", 0) for c in chapters_c)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Chapters", len(chapters_c))
            c2.metric("Avg Score", f"{avg_score:.2f}")
            c3.metric("Avg Words", avg_words)
            c4.metric("Total Rewrites", rewrites_c)

        elif st.session_state.generating:
            st.info(f"**{st.session_state.current_status}**")
            prog = st.session_state.current_ch / max(st.session_state.total_ch, 1)
            st.progress(prog, text=f"Chapter {st.session_state.current_ch} / {st.session_state.total_ch}")

        # ── World state card ────────────────────────────────────────────────────
        world = st.session_state.world
        if world:
            with st.expander("🌍 World State", expanded=False):
                col_l, col_r = st.columns(2)
                with col_l:
                    st.markdown(f"**{world.get('title', '—')}**")
                    st.caption(f"{world.get('genre', '—')} · {world.get('time_period', '—')}")
                    st.markdown(world.get("setting", "")[:400])
                    st.markdown(f"**Conflict:** {world.get('central_conflict', '—')}")
                with col_r:
                    chars = world.get("characters", [])
                    st.markdown(f"**Characters ({len(chars)})**")
                    for c in chars:
                        alive = "🟢" if c.get("alive", True) else "💀"
                        st.markdown(f"{alive} **{c['name']}** — {c.get('role', '?')}")
                    rules = world.get("world_rules", [])
                    if rules:
                        st.markdown(f"**Rules ({len(rules)})**")
                        for r in rules[:4]:
                            st.caption(f"[{r.get('category','?')}] {r['rule']}")

        # Chapter cards
        chapters = st.session_state.chapters
        if not chapters:
            return

        st.markdown(f"### Chapters ({len(chapters)} / {st.session_state.total_ch})")
        for ch in reversed(chapters):
            score = ch.get("consistency_score", 0.0)
            badge = _score_badge(score)
            rewrites = ch.get("rewrite_count", 0)
            rewrite_note = f" ·  ↺ {rewrites}" if rewrites else ""
            header = (
                f"Ch {ch['number']} · Arc {ch.get('arc','?')} · "
                f"**{ch['title']}** — {ch['word_count']} words · "
                f"{badge}{rewrite_note}"
            )
            with st.expander(f"Ch {ch['number']}: {ch['title']}", expanded=(ch == chapters[-1])):
                st.markdown(header, unsafe_allow_html=True)
                st.divider()
                st.markdown(
                    f'<div class="chapter-body">{ch.get("content", "").replace(chr(10), "<br>")}</div>',
                    unsafe_allow_html=True,
                )

    _live_feed()


# ── Library tab ────────────────────────────────────────────────────────────────
with tab_lib:
    st.markdown("### 📚 Saved Stories")
    library = _load_library()

    if not library:
        st.info("No completed stories yet. Generate one to see it here.")
    else:
        for story in library:
            with st.container(border=True):
                ca, cb, cc, cd = st.columns([4, 1, 1, 1])
                ca.markdown(
                    f"**{story['title']}**  \n"
                    f"`{story['story_id']}` · _{story['genre']}_"
                )
                cb.metric("Chapters", story["chapters"])
                cc.metric("Score", story["score"])
                if cd.button("Read →", key=f"lib_{story['story_id']}"):
                    st.session_state.read_story_id = story["story_id"]
                    st.session_state.read_ch = 1
                    st.toast(f"Switch to the 📖 Read tab to read '{story['title']}'")


# ── Read tab ───────────────────────────────────────────────────────────────────
with tab_read:
    library_read = _load_library()

    # Build option map: saved stories + current in-session story
    story_opts: dict[str, str] = {}
    for s in library_read:
        story_opts[s["story_id"]] = f"{s['title']}  ({s['story_id']})"
    if (
        st.session_state.chapters
        and st.session_state.story_id
        and st.session_state.story_id not in story_opts
    ):
        story_opts[st.session_state.story_id] = (
            f"{st.session_state.story_title}  (current session)"
        )

    if not story_opts:
        st.info("No stories available yet. Generate one first.")
    else:
        default_idx = (
            list(story_opts).index(st.session_state.read_story_id)
            if st.session_state.read_story_id in story_opts
            else 0
        )
        selected_id = st.selectbox(
            "Story",
            options=list(story_opts.keys()),
            format_func=lambda k: story_opts[k],
            index=default_idx,
        )
        st.session_state.read_story_id = selected_id

        # Resolve chapters
        if selected_id == st.session_state.story_id and st.session_state.chapters:
            all_chapters = st.session_state.chapters
        else:
            all_chapters = _load_chapters_from_disk(selected_id)

        if not all_chapters:
            st.warning("No chapters found for this story.")
        else:
            ch_map = {c["number"]: c for c in all_chapters}
            ch_nums = sorted(ch_map.keys())

            # Navigation row
            col_p, col_s, col_n = st.columns([1, 5, 1])
            with col_s:
                selected_num = st.selectbox(
                    "Chapter",
                    options=ch_nums,
                    format_func=lambda n: f"Ch {n}: {ch_map[n]['title']}",
                    index=min(
                        st.session_state.read_ch - 1,
                        len(ch_nums) - 1,
                    ),
                )
                st.session_state.read_ch = selected_num
            with col_p:
                st.write("")
                st.write("")
                if st.button("◀", disabled=selected_num <= ch_nums[0], use_container_width=True):
                    st.session_state.read_ch = selected_num - 1
                    st.rerun()
            with col_n:
                st.write("")
                st.write("")
                if st.button("▶", disabled=selected_num >= ch_nums[-1], use_container_width=True):
                    st.session_state.read_ch = selected_num + 1
                    st.rerun()

            ch = ch_map[selected_num]
            score = ch.get("consistency_score", 0.0)

            st.markdown(f"## Chapter {ch['number']}: {ch['title']}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Arc",      ch.get("arc", "—"))
            m2.metric("Words",    ch.get("word_count", "—"))
            m3.metric("Score",    f"{score:.2f}")
            m4.metric("Rewrites", ch.get("rewrite_count", 0))
            st.divider()
            st.markdown(
                f'<div class="chapter-body">{ch.get("content", "").replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )
