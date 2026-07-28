from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import __version__
from .adapter_moodlecli import MoodleCLI
from .agent import watch
from .config import Config, ConfigError
from .logger import Logger
from .populate import StateStore, apply, base_url, config_hash, doctor
from .schemagen import generate_schemas


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="demo", description="Manage the EduPlanner Moodle demo")
    result.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    result.add_argument("-c", "--config", type=Path, help="configuration directory")
    result.add_argument(
        "--schema-dir", type=Path, default=Path(os.getenv("DEMO_SCHEMA_DIR", "/opt/eduplanner-demo/schema"))
    )
    result.add_argument("--moodle-dir", type=Path, help="Moodle installation directory")
    result.add_argument("-v", "--verbose", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    apply_parser = commands.add_parser("apply", help="validate and repopulate Moodle")
    apply_parser.add_argument("--force", action="store_true", help="apply even if the hash is unchanged")
    apply_parser.add_argument("--bootstrap-only", action="store_true", help=argparse.SUPPRESS)
    commands.add_parser("validate", help="validate configuration without changing Moodle")
    commands.add_parser("schema", help="regenerate JSON schemas")
    status_parser = commands.add_parser("status", help="show the latest watcher/apply status")
    status_parser.add_argument(
        "--check", action="store_true", help="exit unsuccessfully unless the demo is ready"
    )
    commands.add_parser("doctor", help="exercise all token-authenticated sync endpoints")
    commands.add_parser("credentials", help="print demo usernames and the shared password")
    commands.add_parser("watch", help="watch configuration and run the editor agent")
    return result


def main(arguments: list[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    Logger.init(args.verbose)
    try:
        config = Config(args.config)
        adapter = MoodleCLI(args.moodle_dir)
        state = StateStore()
        schema_dir = args.schema_dir
        if args.command == "validate":
            parsed = config.read()
            Logger.success(
                f"Valid: {len(parsed.users)} users, {len(parsed.courses)} courses, "
                f"{len(parsed.activities)} activities"
            )
        elif args.command == "schema":
            generated = generate_schemas(schema_dir, config.read())
            for path in generated:
                Logger.success(path)
        elif args.command == "apply":
            if args.bootstrap_only:
                with Logger.stage("Configure Moodle and purge caches"):
                    adapter.configure(base_url())
                    adapter.purge_caches()
            else:
                apply(config, adapter, schema_dir, state, force=args.force)
        elif args.command == "status":
            current = state.read()
            socket_path = Path(os.getenv("DEMO_AGENT_SOCKET", "/run/eduplanner-demo/agent.sock"))
            current["watcher"] = {"running": socket_path.is_socket()}
            current["lastApply"] = current.get("updatedAt")
            current["appliedHash"] = current.get("hash")
            try:
                current["currentHash"] = config_hash(config)
            except Exception as error:
                current["currentHashError"] = str(error)
            print(json.dumps(current, indent=2, ensure_ascii=False, sort_keys=True))
            if args.check and (
                current.get("state") != "ready" or not current["watcher"]["running"]
            ):
                return 1
        elif args.command == "doctor":
            print(json.dumps(doctor(config, adapter), indent=2, ensure_ascii=False, sort_keys=True))
        elif args.command == "credentials":
            parsed = config.read()
            print(f"Shared password: {parsed.password}")
            for user in parsed.users:
                print(f"{user.name}: {user.id}")
        elif args.command == "watch":
            watch(config, adapter, schema_dir, state)
        return 0
    except KeyboardInterrupt:
        Logger.warning("Interrupted")
        return 130
    except (ConfigError, RuntimeError, OSError, ValueError) as error:
        Logger.error(error)
        return 1
