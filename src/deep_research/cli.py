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
from deep_research.core.exceptions import ResearchCancelledError
from deep_research.core.interactive import review_plan_interactively
from deep_research.core.orchestrator import ResearchOrchestrator
from deep_research.models.plan import ResearchMode, ResearchPlan
from deep_research.providers.llm.factory import get_llm_provider
from deep_research.providers.search.factory import get_search_provider
from deep_research.storage.session_store import SessionStore

app = typer.Typer(
    name="deep-research",
    help="Autonomous scientific research agent powered by Google Gemini 3.8 Flash",
    no_args_is_help=True,
)
sessions_app = typer.Typer(
    name="sessions",
    help="Inspect, list, and export saved research sessions",
    no_args_is_help=True,
)
app.add_typer(sessions_app, name="sessions")
console = Console()


@app.command("run")
def run_command(
    query: str = typer.Argument("", help="Research question or topic to investigate"),
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
        help="Search provider override: 'tavily', 'duckduckgo', 'arxiv', 'brave', 'mock'",
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
        help="File path to save the generated research report",
    ),
    report_format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format: 'markdown', 'html', or 'json'",
    ),
    resume: str | None = typer.Option(
        None,
        "--resume",
        help="Resume an existing research session by ID (e.g. ses-1234abcd)",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Review and edit the research plan interactively before executing searches",
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

    if not query and not resume:
        console.print(
            "[bold red]Error:[/] Please provide a research query or use --resume <session_id>."
        )
        raise typer.Exit(code=1)

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
            f"[dim]Topic:[/] {query or f'Resuming {resume}'}\n"
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

    try:
        with console.status("[bold green]Executing research inquiry...", spinner="dots") as status:

            def update_status(message: str) -> None:
                status.update(f"[bold green]{message}")

            def plan_approver_cb(plan: ResearchPlan) -> ResearchPlan | None:
                status.stop()
                try:
                    return review_plan_interactively(plan, console=console)
                finally:
                    status.start()

            approver = plan_approver_cb if interactive else None

            if resume:
                state = asyncio.run(
                    orchestrator.resume_research(
                        session_id=resume,
                        status_callback=update_status,
                        plan_approver=approver,
                    )
                )
            else:
                state = asyncio.run(
                    orchestrator.execute_research(
                        query=query,
                        mode=research_mode,
                        max_budget_usd=budget,
                        status_callback=update_status,
                        plan_approver=approver,
                    )
                )
    except ResearchCancelledError:
        console.print("[yellow]Research run cancelled by user during plan review.[/]")
        raise typer.Exit(code=0) from None

    if not state.final_report:
        console.print("[bold red]Research pipeline completed without producing a final report.[/]")
        raise typer.Exit(code=1)

    # Format report
    fmt = report_format.lower().strip()
    if fmt == "html":
        report_content = state.final_report.to_html()
    elif fmt == "json":
        report_content = state.final_report.to_json()
    else:
        report_content = state.final_report.to_markdown()

    # Render to console
    console.print()
    if fmt == "markdown":
        console.print(Markdown(report_content))
    elif fmt == "json":
        console.print(f"[dim]Structured JSON report ({len(report_content)} bytes generated)[/]")
    elif fmt == "html":
        console.print(f"[dim]Standalone HTML report ({len(report_content)} bytes generated)[/]")

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
        output.write_text(report_content, encoding="utf-8")
        console.print(f"\n[bold green]Report ({fmt.upper()}) successfully written to:[/] {output}")


@sessions_app.command("list")
def list_sessions_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum sessions to display"),
) -> None:
    """List all saved research sessions."""
    store = SessionStore()
    sessions = store.list_sessions(limit=limit)
    if not sessions:
        console.print("[dim]No saved research sessions found.[/]")
        return

    table = Table(title="Saved Research Sessions", border_style="cyan")
    table.add_column("Session ID", style="bold cyan")
    table.add_column("Query", style="white", max_width=40, overflow="ellipsis")
    table.add_column("Mode", style="yellow")
    table.add_column("Status", style="green")
    table.add_column("Sources", justify="right")
    table.add_column("Evidence", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Saved At", style="dim")

    for s in sessions:
        table.add_row(
            s.session_id,
            s.initial_query,
            s.mode.value.upper(),
            s.status.value,
            str(s.sources_count),
            str(s.evidence_count),
            f"${s.cost_usd:.4f}",
            s.saved_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


@sessions_app.command("show")
def show_session_cmd(
    session_id: str = typer.Argument(..., help="Session ID (e.g. ses-1234abcd)"),
) -> None:
    """Display details and report for a saved session."""
    store = SessionStore()
    try:
        state = store.load_session(session_id)
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(code=1) from None

    console.print(
        Panel(
            f"[bold cyan]Research Session: {state.session_id}[/]\n"
            f"[dim]Topic:[/] {state.initial_query}\n"
            f"[dim]Status:[/] {state.status.value.upper()} | "
            f"[dim]Mode:[/] {state.mode.value.upper()} | "
            f"[dim]Cost:[/] ${state.budget.current_cost_usd:.4f}",
            border_style="cyan",
        )
    )

    if state.final_report:
        console.print(Markdown(state.final_report.to_markdown()))
    else:
        console.print("[yellow]Session has not generated a final report.[/]")


@sessions_app.command("export")
def export_session_cmd(
    session_id: str = typer.Argument(..., help="Session ID (e.g. ses-1234abcd)"),
    output: Path = typer.Option(..., "--output", "-o", help="Destination file path"),
    report_format: str = typer.Option(
        "markdown", "--format", "-f", help="Format: 'markdown', 'html', or 'json'"
    ),
) -> None:
    """Export a session report to Markdown, HTML, or JSON."""
    store = SessionStore()
    try:
        content = store.export_report(session_id, format_type=report_format)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        console.print(f"[bold green]Session report successfully exported to:[/] {output}")
    except Exception as e:
        console.print(f"[bold red]Export error:[/] {e}")
        raise typer.Exit(code=1) from None


@sessions_app.command("delete")
def delete_session_cmd(
    session_id: str = typer.Argument(..., help="Session ID to delete"),
) -> None:
    """Delete a saved research session."""
    store = SessionStore()
    if store.delete_session(session_id):
        console.print(f"[green]Session '{session_id}' deleted successfully.[/]")
    else:
        console.print(f"[yellow]Session '{session_id}' was not found.[/]")


def run_cli() -> None:
    """CLI entry point supporting both 'deep-research query' and 'deep-research run query'."""
    import sys

    known_subcommands = {
        "run",
        "sessions",
        "--help",
        "-h",
        "--install-completion",
        "--show-completion",
    }

    # If user executes 'deep-research "query" ...' without 'run' keyword, auto-insert 'run'
    if (
        len(sys.argv) > 1
        and sys.argv[1] not in known_subcommands
        and not sys.argv[1].startswith("-")
    ):
        sys.argv.insert(1, "run")

    app()


if __name__ == "__main__":
    run_cli()
