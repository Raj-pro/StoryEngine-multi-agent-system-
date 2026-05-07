#!/usr/bin/env python3
from __future__ import annotations
import asyncio
import logging
import os
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

load_dotenv()

console = Console()
app = typer.Typer(name="story-gen", help="Narrative Consistency Engine — generates 100-chapter stories.")


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[
            RichHandler(console=console, rich_tracebacks=True, markup=True),
            logging.FileHandler("data/logs/story_gen.log"),
        ],
    )


def check_env():
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "mistral")
    console.print(f"[dim]Ollama: {host} | model: {model}[/dim]")


@app.command()
def generate(
    genre: str = typer.Option(..., "--genre", "-g", help="Story genre (e.g. 'dark fantasy', 'sci-fi thriller')"),
    intro: str = typer.Option(..., "--intro", "-i", help="Short story introduction / premise"),
    chapters: int = typer.Option(5, "--chapters", "-n", help="Number of chapters to generate (default: 5, max: 100)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Generate a story with the Narrative Consistency Engine."""
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    setup_logging(verbose)
    check_env()

    if chapters < 1 or chapters > 100:
        console.print("[red]--chapters must be between 1 and 100[/red]")
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold cyan]Narrative Consistency Engine[/bold cyan]\n\n"
        f"Genre: [yellow]{genre}[/yellow]\n"
        f"Chapters: [yellow]{chapters}[/yellow]\n\n"
        f"[dim]{intro[:200]}{'...' if len(intro) > 200 else ''}[/dim]",
        title="Story Generator",
    ))

    from orchestrator.controller import MasterController

    controller = MasterController(target_chapters=chapters)

    async def _run():
        return await controller.run(genre=genre, intro=intro)

    with console.status("[bold green]Running convergence engine..."):
        state = asyncio.run(_run())

    # Summary table
    table = Table(title=f"'{state.world_state.title}' — Generation Complete", show_lines=True)
    table.add_column("Chapter", style="cyan", width=8)
    table.add_column("Title", style="white")
    table.add_column("Arc", style="yellow", width=6)
    table.add_column("Words", justify="right", width=7)
    table.add_column("Score", justify="right", width=7)
    table.add_column("Rewrites", justify="right", width=9)

    for ch in state.chapters:
        score_color = "green" if ch.consistency_score >= 0.85 else "yellow" if ch.consistency_score >= 0.70 else "red"
        table.add_row(
            str(ch.number),
            ch.title,
            str(ch.arc),
            str(ch.word_count),
            f"[{score_color}]{ch.consistency_score:.2f}[/{score_color}]",
            str(ch.rewrite_count),
        )

    console.print(table)
    console.print(
        f"\n[bold green]Done![/bold green] "
        f"Global consistency: [cyan]{state.global_consistency_score:.2f}[/cyan] | "
        f"Story ID: [dim]{state.story_id}[/dim]\n"
        f"Chapters saved to: [dim]data/chapters/[/dim]"
    )


@app.command()
def show(
    story_id: str = typer.Argument(..., help="Story ID (from a previous run)"),
    chapter: int = typer.Option(None, "--chapter", "-c", help="Print a specific chapter"),
):
    """Show chapters from a saved story."""
    import json
    from pathlib import Path

    data_dir = Path("data/chapters")
    if chapter is not None:
        path = data_dir / f"{story_id}_ch{chapter:03d}.json"
        if not path.exists():
            console.print(f"[red]Chapter {chapter} not found for story {story_id}[/red]")
            raise typer.Exit(1)
        data = json.loads(path.read_text())
        console.print(Panel(
            data["content"],
            title=f"Chapter {data['number']}: {data['title']} (Arc {data['arc']})",
            subtitle=f"Words: {data['word_count']} | Score: {data['consistency_score']:.2f}",
        ))
    else:
        files = sorted(data_dir.glob(f"{story_id}_ch*.json"))
        if not files:
            console.print(f"[red]No chapters found for story ID '{story_id}'[/red]")
            raise typer.Exit(1)
        table = Table(title=f"Story: {story_id}")
        table.add_column("Chapter", style="cyan")
        table.add_column("Title")
        table.add_column("Words", justify="right")
        table.add_column("Score", justify="right")
        for f in files:
            d = json.loads(f.read_text())
            table.add_row(str(d["number"]), d["title"], str(d["word_count"]), f"{d['consistency_score']:.2f}")
        console.print(table)


if __name__ == "__main__":
    app()
