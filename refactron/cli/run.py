"""
Refactron CLI - Run Module.
Provides the 'run' command to execute Refactron as a connected pipeline.
"""
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
def run(target: Optional[str], incremental: bool) -> None:
    """
    Run Refactron as a connected pipeline session.
    """
    console.print()
    _auth_banner("Pipeline Run")
    console.print()

    target_path = _validate_path(target) if target else Path.cwd()
    
    with console.status("[primary]Executing pipeline run...[/primary]"):
        try:
            pipeline = RefactronPipeline()
            result = pipeline.analyze(target_path, use_incremental=incremental)
            
            console.print(f"[green]Pipeline analysis completed successfully.[/green]")
            console.print(f"Total files analyzed: {result.total_files}")
            console.print(f"Total issues found: {result.total_issues}")
            
        except Exception as e:
            console.print(f"[red]Pipeline run failed: {e}[/red]")
            raise SystemExit(1)
