"""
Refactron CLI - Verification Module.
Command to run the Verification Engine on a code change and emit either a
human-readable report or a stable, machine-readable JSON object for CI gates.
"""

from pathlib import Path
from typing import Optional

import click

from refactron.cli.ui import _auth_banner, console
from refactron.verification.engine import VerificationEngine
from refactron.verification.report import (
    format_verification_result,
    format_verification_result_json,
)


@click.command()
@click.argument("target", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--against",
    "-a",
    "candidate",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help=(
        "Path to the proposed/modified version of TARGET. "
        "If omitted, TARGET is verified against itself."
    ),
)
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Project root used by the test-suite gate. Defaults to the current directory.",
)
@click.option(
    "--all-checks",
    is_flag=True,
    default=False,
    help=(
        "Run every check even after one fails (no short-circuit), so all "
        "failure categories surface in a single run."
    ),
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit a stable, machine-readable JSON report instead of formatted text.",
)
def verify(
    target: str,
    candidate: Optional[str],
    project_root: Optional[str],
    all_checks: bool,
    as_json: bool,
) -> None:
    """
    Verify that a code change is safe to apply.

    TARGET is the file as it currently lives in the project. With --against,
    the proposed new content is checked against it (syntax, import integrity,
    test suite). Exit code is 0 when safe to apply, 1 when blocked — and with
    --json a versioned JSON object is printed for CI dashboards and bots.
    """
    target_path = Path(target)
    original = target_path.read_text(encoding="utf-8")
    transformed = Path(candidate).read_text(encoding="utf-8") if candidate else original

    root = Path(project_root) if project_root else Path.cwd()
    engine = VerificationEngine(project_root=root)
    result = engine.verify(
        original, transformed, target_path, short_circuit=not all_checks
    )

    if as_json:
        # JSON mode prints only the JSON object so consumers can parse stdout.
        click.echo(format_verification_result_json(result))
    else:
        console.print()
        _auth_banner("Verification")
        format_verification_result(result, console)

    raise SystemExit(0 if result.safe_to_apply else 1)
