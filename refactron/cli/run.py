"""
Refactron CLI - Run Module.
Provides the 'run' command to execute Refactron as a connected pipeline.
"""

import os
from typing import Optional
from pathlib import Path
import click

from refactron.cli.ui import console, _auth_banner
from refactron.cli.utils import _validate_path
from refactron.core.pipeline import RefactronPipeline


@click.command()
@click.argument("target", type=click.Path(exists=True), required=False)
@click.option(
    "--incremental/--no-incremental",
    default=False,
    help="Enable or disable incremental analysis for the pipeline run (off by default)",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show detailed timing information for each pipeline phase",
)
@click.option(
    "--fail-fast",
    is_flag=True,
    help="Stop processing if an error occurs during fix application",
)
def run(target: Optional[str], incremental: bool, verbose: bool, fail_fast: bool) -> None:
    """
    Run Refactron as a connected pipeline session.
    """
    console.print()
    _auth_banner("Pipeline Run")
    console.print()

    target_path = _validate_path(target) if target else Path.cwd()
    debug_mode = os.getenv("REFACTRON_DEBUG") == "1"

    with console.status("[primary]Executing pipeline run...[/primary]"):
        try:
            pipeline = RefactronPipeline()
            # 1. Analyze
            result = pipeline.analyze(target_path, use_incremental=incremental)

            # 2. Queue
            queued = pipeline.queue_issues(result.all_issues)

            # 3. Apply (simulated for now in 'run' command unless --apply added,
            # but we'll show the summary infrastructure)
            # For this task, we assume 'run' might be extended to apply fixes.
            # If we don't apply, session counts remain 0.

            console.print(f"[green]Pipeline session completed successfully.[/green]")
            console.print(f"Session ID: [dim]{pipeline.session.id}[/dim]")
            console.print(f"Total files analyzed: {result.total_files}")
            console.print(f"Total issues found: {result.total_issues}")
            console.print(f"Issues queued for fix: {len(queued)}")

            if pipeline.session.files_attempted > 0:
                console.print(f"Files attempted: {pipeline.session.files_attempted}")
                console.print(f"Files succeeded: [green]{pipeline.session.files_succeeded}[/green]")
                console.print(f"Files failed: [red]{pipeline.session.files_failed}[/red]")
                if pipeline.session.backup_session_id:
                    console.print(
                        f"Backup Session ID: [cyan]{pipeline.session.backup_session_id}[/cyan]"
                    )

                if pipeline.session.blocked_fixes:
                    console.print("\n[warning]Blocked Fixes:[/warning]")
                    for block in pipeline.session.blocked_fixes:
                        file = block.get("file", "Unknown")
                        reason = block.get("reason") or block.get("error", "Unknown error")
                        console.print(f"  [red]✗[/red] {file}: {reason}")

            if verbose or debug_mode:
                console.print("\n[highlight]Pipeline Phase Timings:[/highlight]")
                console.print(
                    f"  󰄰 [secondary]Analysis:[/secondary] {pipeline.session.analyze_ms:.2f}ms"
                )
                console.print(
                    f"  󰄰 [secondary]Queuing:[/secondary]  {pipeline.session.queue_ms:.2f}ms"
                )
                if pipeline.session.apply_ms > 0:
                    console.print(
                        f"  󰄰 [secondary]Applying:[/secondary] {pipeline.session.apply_ms:.2f}ms"
                    )
                if pipeline.session.verify_ms > 0:
                    console.print(
                        f"  󰄰 [secondary]Verify:[/secondary]   {pipeline.session.verify_ms:.2f}ms"
                    )

        except Exception as e:
            console.print(f"[red]Pipeline run failed: {e}[/red]")
            if debug_mode:
                import traceback

                console.print(traceback.format_exc())
            raise SystemExit(1)
