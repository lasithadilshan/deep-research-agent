"""Command-line interface for the AI Deep Research Agent powered by Typer and Rich."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from deep_research.config.logging import configure_logging
from deep_research.config.settings import get_settings
from deep_research.core.orchestrator import ResearchOrchestrator
from deep_research.models.plan import ResearchMode
from deep_research.providers.llm.factory import get_llm_provider
from deep_research.providers.search.factory import get_search_provider

app = typer.Typer(
    name="deep-research",
    help="Autonomous scientific research agent powered by Google Gemini 3.8 Flash",
    no_args_is_help=True,
)
console = Console()


@app.command()
def main(
    query: str = typer.Argument(..., help="Research question or topic to investigate"),
    mode: str = typer.Option(
        "standard",
        "--mode",
        "-m",
        help="Research mode: 'quick' (1 iter), 'standard' (2 iters), or 'deep' (3-5 iters)",
    ),
    llm: str | None = typer.Option(
        None,
        "--llm",
        help="LLM provider override: 'gemini', 'mock'",
    ),
    search: str | None = typer.Option(
        None,
        "--search",
        "-s",
        help="Search provider override: 'tavily', 'duckduckgo', 'mock'",
    ),
    budget: float | None = typer.Option(
        None,
        "--budget",
        "-b",
        help="Maximum financial budget ceiling in USD",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="File path to save the generated markdown research report",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress intermediate progress logs",
    ),
) -> None:
    """Execute autonomous deep research and produce cited reports."""
    settings = get_settings()
    configure_logging(level="ERROR" if quiet else settings.log_level, structured=False)

    try:
        research_mode = ResearchMode(mode.lower())
    except ValueError:
        console.print(
            f"[bold red]Error:[/] Invalid research mode '{mode}'. Use 'quick', 'standard', or 'deep'."
        )
        raise typer.Exit(code=1) from None

    console.print(
        Panel(
            f"[bold cyan]Deep Research Agent[/]\n"
            f"[dim]Topic:[/] {query}\n"
            f"[dim]Mode:[/] {research_mode.value.upper()} | "
            f"[dim]Budget Ceiling:[/] ${budget or settings.max_budget_usd_per_run:.2f}",
            border_style="cyan",
        )
    )

    # Initialize providers
    llm_provider = get_llm_provider(llm, model_name=settings.gemini_model) if llm else None
    search_provider = get_search_provider(search) if search else None

    orchestrator = ResearchOrchestrator(
        llm=llm_provider,
        search_provider=search_provider,
        settings=settings,
    )

    with console.status("[bold green]Starting deep research inquiry...", spinner="dots") as status:

        def update_status(message: str) -> None:
            status.update(f"[bold green]{message}")

        state = asyncio.run(
            orchestrator.execute_research(
                query=query,
                mode=research_mode,
                max_budget_usd=budget,
                status_callback=update_status,
            )
        )

    if not state.final_report:
        console.print("[bold red]Research pipeline completed without producing a final report.[/]")
        raise typer.Exit(code=1)

    # Render Report
    report_md = state.final_report.to_markdown()
    console.print()
    console.print(Markdown(report_md))

    # Render Telemetry / Statistics Table
    console.print()
    stat_table = Table(title="Research Session Telemetry", border_style="dim")
    stat_table.add_column("Metric", style="cyan")
    stat_table.add_column("Value", style="green")

    stat_table.add_row("Session ID", state.session_id)
    stat_table.add_row("Sources Consulted", str(len(state.sources)))
    stat_table.add_row("Evidence Items Extracted", str(len(state.evidence_pool)))
    stat_table.add_row("Verified Citations", str(len(state.final_report.bibliography)))
    stat_table.add_row("Prompt Tokens", f"{state.budget.prompt_tokens:,}")
    stat_table.add_row("Completion Tokens", f"{state.budget.completion_tokens:,}")
    stat_table.add_row("Search API Calls", str(state.budget.search_api_calls))
    stat_table.add_row("Total Cost", f"${state.budget.current_cost_usd:.4f} USD")

    console.print(stat_table)

    # Save to file if output specified
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report_md, encoding="utf-8")
        console.print(f"\n[bold green]Report successfully written to:[/] {output}")


if __name__ == "__main__":
    app()
