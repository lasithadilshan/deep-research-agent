"""Interactive human-in-the-loop plan review and refinement interface."""

from collections.abc import Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from deep_research.models.plan import ResearchPlan, SubQuestion

InputFunc = Callable[[str], str]


def display_plan_summary(plan: ResearchPlan, console: Console) -> None:
    """Render a structured visual summary of the research plan."""
    # Display Primary Objective & Hypotheses
    hypotheses_text = (
        "\n".join(f"  • {h}" for h in plan.hypotheses)
        if plan.hypotheses
        else "  [dim]None specified[/]"
    )
    header_content = (
        f"[bold cyan]Primary Objective:[/] {plan.primary_objective}\n\n"
        f"[bold cyan]Hypotheses to Test:[/]\n{hypotheses_text}\n\n"
        f"[dim]Planned Mode:[/] {plan.planned_mode.value.upper()} | "
        f"[dim]Max Iterations:[/] {plan.max_iterations}"
    )
    console.print(
        Panel(header_content, title="[bold]Research Plan Overview[/]", border_style="cyan")
    )

    # Sub-Questions Table
    table = Table(
        title="Formulated Sub-Questions & Target Search Queries",
        border_style="dim",
        expand=True,
    )
    table.add_column("ID", style="bold cyan", width=8)
    table.add_column("Sub-Question & Rationale", style="white")
    table.add_column("Target Queries", style="green")

    for sq in plan.sub_questions:
        rationale_str = f"\n[dim italic]Rationale: {sq.rationale}[/]" if sq.rationale else ""
        queries_str = "\n".join(f"• {q}" for q in sq.target_queries)
        table.add_row(
            sq.question_id,
            f"{sq.question}{rationale_str}",
            queries_str or "[dim]None[/]",
        )
    console.print(table)

    # Initial Global Search Queries
    if plan.initial_search_queries:
        query_list = ", ".join(f"'{q}'" for q in plan.initial_search_queries[:8])
        if len(plan.initial_search_queries) > 8:
            query_list += f" [dim](+{len(plan.initial_search_queries) - 8} more)[/]"
        console.print(
            f"[bold]Initial Search Queue ({len(plan.initial_search_queries)}):[/] {query_list}\n"
        )


def review_plan_interactively(
    plan: ResearchPlan,
    console: Console | None = None,
    input_fn: InputFunc | None = None,
) -> ResearchPlan | None:
    """Prompt the user to review, edit, or approve the research plan interactively.

    Args:
        plan: The initial ResearchPlan proposed by PlannerAgent.
        console: Optional Rich Console instance.
        input_fn: Optional input function for test automation. Defaults to Rich Prompt.ask.

    Returns:
        The revised and approved ResearchPlan, or None if the user cancelled.
    """
    c = console or Console()
    working_plan = plan.model_copy(deep=True)

    def ask(prompt_text: str, default: str = "") -> str:
        if input_fn is not None:
            return input_fn(prompt_text)
        return Prompt.ask(prompt_text, default=default, console=c)

    c.print("\n[bold yellow]=== Human-in-the-Loop Research Plan Review ===[/]")
    display_plan_summary(working_plan, c)

    while True:
        c.print(
            "[bold]Actions:[/] [bold green][A][/]pprove  "
            "[bold cyan][+][/] Add Sub-Question  "
            "[bold red][-][/] Remove Sub-Question  "
            "[bold magenta][Q][/] Edit Queries  "
            "[bold yellow][V][/]iew Plan  "
            "[bold red][C][/]ancel"
        )
        choice = ask("[bold]Select an action[/]", default="a").strip().lower()

        if choice in {"a", "approve", "yes", "y"}:
            c.print("[bold green]Plan approved. Proceeding with research execution...[/]\n")
            return working_plan

        if choice in {"c", "cancel", "abort", "exit", "n"}:
            c.print("[bold red]Research plan rejected. Session cancelled.[/]\n")
            return None

        if choice in {"v", "view", "show"}:
            display_plan_summary(working_plan, c)
            continue

        if choice in {"+", "add"}:
            q_text = ask("Enter sub-question text").strip()
            if not q_text:
                c.print("[yellow]Sub-question cannot be empty.[/]")
                continue
            rationale = ask("Enter rationale (optional)").strip()
            queries_raw = ask("Enter target search queries (comma-separated)").strip()
            target_queries = [q.strip() for q in queries_raw.split(",") if q.strip()]

            new_id = f"SQ-{len(working_plan.sub_questions) + 1}"
            new_sq = SubQuestion(
                question_id=new_id,
                question=q_text,
                rationale=rationale,
                target_queries=target_queries,
            )
            working_plan.sub_questions.append(new_sq)

            # Sync queries with initial search list
            for q in target_queries:
                if q not in working_plan.initial_search_queries:
                    working_plan.initial_search_queries.append(q)

            c.print(f"[bold green]Added sub-question '{new_id}':[/] {q_text}")
            continue

        if choice in {"-", "remove"}:
            if not working_plan.sub_questions:
                c.print("[yellow]No sub-questions available to remove.[/]")
                continue

            target_id = ask("Enter sub-question ID to remove (e.g. SQ-1)").strip().upper()
            found_idx = next(
                (
                    i
                    for i, sq in enumerate(working_plan.sub_questions)
                    if sq.question_id == target_id
                ),
                None,
            )
            if found_idx is not None:
                removed = working_plan.sub_questions.pop(found_idx)
                c.print(f"[bold green]Removed sub-question {removed.question_id}.[/]")
            else:
                c.print(f"[yellow]Sub-question '{target_id}' not found.[/]")
            continue

        if choice in {"q", "queries"}:
            c.print("\n[bold]Current Initial Search Queries:[/]")
            for idx, query in enumerate(working_plan.initial_search_queries, start=1):
                c.print(f"  [{idx}] {query}")

            q_action = (
                ask("[1] Add query | [2] Remove query | [b] Back", default="b").strip().lower()
            )
            if q_action == "1":
                new_q = ask("Enter search query").strip()
                if new_q and new_q not in working_plan.initial_search_queries:
                    working_plan.initial_search_queries.append(new_q)
                    c.print(f"[green]Added query:[/] '{new_q}'")
            elif q_action == "2":
                idx_str = ask("Enter query number to remove").strip()
                try:
                    remove_idx = int(idx_str) - 1
                    if 0 <= remove_idx < len(working_plan.initial_search_queries):
                        removed_q = working_plan.initial_search_queries.pop(remove_idx)
                        c.print(f"[green]Removed query:[/] '{removed_q}'")
                    else:
                        c.print("[yellow]Invalid query number.[/]")
                except ValueError:
                    c.print("[yellow]Please enter a valid integer.[/]")
            continue

        c.print(f"[yellow]Unrecognized action '{choice}'. Please select from the menu.[/]")
