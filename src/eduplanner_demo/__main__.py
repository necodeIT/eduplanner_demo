#!/usr/bin/env python3
from .logger import Logger
from . import __version__
from .config import Config, print_config
from .schemagen import schemagen
from .adapter_moodlecli import MoodleCLI
from .populate import populate
from argparse import ArgumentParser
from enum import StrEnum, auto
from pathlib import Path
from os.path import realpath

class Commands(StrEnum):
	SCHEMAGEN = auto()
	SHOWCONFIG = auto()
	POPULATE = auto()


if __name__ == '__main__':
	ap = ArgumentParser("eduplanner_demo", add_help=True)
 
	# general parameters
	ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
	ap.add_argument("-c", "--config", type=Path, help="directory to read configs from")
	ap.add_argument("-v", "--verbose", action="store_true", help="enable verbose output")
	# subcommands
	sp = ap.add_subparsers(
		metavar="<command>",
		dest="command",
		required=True,
		description="what to do (pass -h after this to see command-specific help)",
	)
	# schemagen
	schemagen_parser = sp.add_parser(Commands.SCHEMAGEN, help="generate schemas for configs")
	schemagen_parser.add_argument("-o", "--out", required=True, help="directory to put schema files in")
	# showconfig
	showconfig_parser = sp.add_parser(Commands.SHOWCONFIG, help="show current config")
	# populate
	populate_parser = sp.add_parser(Commands.POPULATE, help="reset and populate database")
	populate_parser.add_argument(
		"--moodledir",
		required=True,
		type=Path,
		help="directory where moodle is installed (e.g. /bitnami/moodle/)"
	)
	
	# read arguments
	args = ap.parse_args()
	config = Config(args.config)
	Logger.init(args.verbose)
	
	# execute subcommands
	match args.command:
		case Commands.SCHEMAGEN:
			password, users, courses, slots, plans = config.read_moodle_config()
			schemagen(realpath(args.out), courses, users)
		case Commands.SHOWCONFIG:
			print_config(config)
		case Commands.POPULATE:
			moodle_adapter = MoodleCLI(args.moodledir)
			populate(moodle_adapter, config)
		case _:
			raise NotImplementedError("should be unreachable")
