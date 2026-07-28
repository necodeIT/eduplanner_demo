from __future__ import annotations

import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from time import monotonic
from typing import Iterator

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
except ImportError:  # pragma: no cover - useful when diagnosing a partial image build.
    Console = None  # type: ignore[assignment]
    Progress = None  # type: ignore[assignment]


SECRET_PATTERNS = (
    re.compile(
        r"(?i)([\"']?(?:password|token|private[_-]?token|wstoken)[\"']?\s*[=:]\s*[\"']?)"
        r"([^\"'\s,&}\]]+)"
    ),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,]+)"),
)


def redact(message: object) -> str:
    result = str(message)
    for pattern in SECRET_PATTERNS:
        result = pattern.sub(lambda match: f"{match.group(1)}<redacted>", result)
    return result


class Logger:
    verbose = False
    console = Console(stderr=False) if Console else None

    @classmethod
    def init(cls, verbose: bool = False) -> None:
        cls.verbose = verbose

    @classmethod
    def _write(cls, level: str, message: object, style: str = "") -> None:
        timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        text = redact(message)
        if cls.console:
            cls.console.print(f"[dim]{timestamp}[/dim] [{style}]{level:7}[/{style}] {text}" if style else f"[dim]{timestamp}[/dim] {level:7} {text}")
        else:
            print(f"{timestamp} {level:7} {text}", flush=True)

    @classmethod
    def info(cls, message: object) -> None:
        cls._write("INFO", message, "cyan")

    @classmethod
    def success(cls, message: object) -> None:
        cls._write("SUCCESS", message, "green")

    @classmethod
    def warning(cls, message: object) -> None:
        cls._write("WARNING", message, "yellow")

    @classmethod
    def error(cls, message: object) -> None:
        cls._write("ERROR", message, "bold red")

    @classmethod
    def debug(cls, message: object) -> None:
        if cls.verbose:
            cls._write("DEBUG", message, "dim")

    @classmethod
    @contextmanager
    def stage(cls, label: str) -> Iterator[None]:
        started = monotonic()
        use_progress = bool(Progress and sys.stdout.isatty())
        if use_progress:
            progress = Progress(
                SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn(), console=cls.console
            )
            with progress:
                task = progress.add_task(label, total=None)
                try:
                    yield
                except Exception:
                    progress.update(task, description=f"[red]{label} failed[/red]")
                    raise
                else:
                    progress.update(task, description=f"[green]{label}[/green]", completed=1, total=1)
        else:
            cls.info(f"Starting: {label}")
            try:
                yield
            except Exception:
                cls.error(f"Failed after {monotonic() - started:.2f}s: {label}")
                raise
            cls.success(f"Finished in {monotonic() - started:.2f}s: {label}")
