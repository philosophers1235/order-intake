from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .export import to_csv, to_dict
from .extract import ClaudeExtractor, ExtractionError, FixtureExtractor
from .models import OrderResult
from .pipeline import process
from .sources import load
from .workspace import Workspace

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
console = Console()


def _extractor(workspace: Workspace, fixtures: bool):
    return FixtureExtractor(workspace.path / "fixtures") if fixtures else ClaudeExtractor()


def show(result: OrderResult) -> None:
    order = result.order
    who = result.customer_name or f"[yellow]unknown: {order.customer_name or '?'}[/]"
    console.print(f"\n[bold]{result.source}[/]  →  {who}"
                  f"{'  ·  ref ' + order.customer_reference if order.customer_reference else ''}"
                  f"{'  ·  ' + order.delivery if order.delivery else ''}")

    table = Table(show_edge=False, header_style="dim", pad_edge=False)
    for column in ("#", "as written", "item", "qty", ""):
        table.add_column(column)
    for line in result.lines:
        qty = "?" if line.quantity is None else f"{line.quantity:g} {line.unit or ''}"
        item = f"{line.code} {line.name}" if line.code else "[dim]—[/]"
        if line.status == "ok":
            note = "[green]ready[/]"
        else:
            first = line.issues[0]
            note = f"[yellow]{first.message}[/]"
            if first.suggestion:
                note += f"\n[cyan]→ {first.suggestion.reason}[/]"
        table.add_row(str(line.number), line.extracted.raw, item, qty, note)
    console.print(table)
    for issue in result.issues:
        console.print(f"[yellow]! {issue.message}[/]")
    ready = len(result.lines) - sum(1 for line in result.lines if line.status == "review")
    console.print(f"[dim]{ready}/{len(result.lines)} lines ready · {result.mode} · {result.seconds}s[/]")


def cmd_run(args) -> int:
    workspace = Workspace.load(args.workspace)
    try:
        result = process(load(args.file), workspace, _extractor(workspace, args.fixtures))
    except ExtractionError as e:
        console.print(f"[red]{e}[/]")
        return 1
    show(result)
    if args.json:
        Path(args.json).write_text(json.dumps(to_dict(result), indent=2, ensure_ascii=False), encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(to_csv(result), encoding="utf-8")
    return 0


def cmd_demo(args) -> int:
    for folder in sorted(p for p in SAMPLES.iterdir() if (p / "workspace.json").exists()):
        workspace = Workspace.load(folder)
        console.rule(f"[bold]{workspace.seller}[/]", style="dim")
        for file in sorted((folder / "inbox").iterdir()):
            show(process(load(file), workspace, FixtureExtractor(folder / "fixtures")))
    console.print("\n[dim]Fixture mode: extractions are replayed from samples/*/fixtures. "
                  "Everything after extraction ran for real.[/]")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .web import create_app

    app = create_app(Path(args.samples), fixtures=args.fixtures)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="intake", description="Turn messy orders into ERP-ready lines.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="process one file")
    run.add_argument("file")
    run.add_argument("-w", "--workspace", required=True, help="folder with catalog.csv, customers.csv, history.csv")
    run.add_argument("--fixtures", action="store_true", help="replay a saved extraction instead of calling the model")
    run.add_argument("--json", help="write the full result as JSON")
    run.add_argument("--csv", help="write ERP import lines as CSV")
    run.set_defaults(func=cmd_run)

    demo = sub.add_parser("demo", help="process every sample offline")
    demo.set_defaults(func=cmd_demo)

    serve = sub.add_parser("serve", help="review screen in the browser")
    serve.add_argument("--samples", default=str(SAMPLES))
    serve.add_argument("--fixtures", action="store_true", help="samples only, no API calls")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
