from typing import Any


RED = "[91m"
YELLOW = "[93m"
GREEN = "[92m"
GRAY = "[37m"
DARK_GRAY = "[90m"




class Logger:
    """A simple logger class for printing colored messages to the console."""
    
    verbose: bool = False
    
    
    @staticmethod
    def init( verbose: bool = False):
        """Initializes the logger with the specified verbosity.

        :param bool verbose: Whether to enable verbose output
        """
        Logger.verbose = verbose
    
    @staticmethod
    def color( string: str, color: str) -> str:
        """Returns a colored string

        :param str string: The string to color
        :param str color: The color code to use for the string
        :return str: The colored string
        """
        return f"\033{color}{string}\033[0m"


    @staticmethod
    def info(message: str):
        """Prints an info message

        :param str message: The message to print
        """
        print(f"[INFO] {message}")

    @staticmethod
    def debug( message: str):
        if Logger.verbose:
            print(Logger.color(f"[DEBUG] {message}", GRAY))

    @staticmethod
    def error( message: str, error: Any = None):
        """Prints an error message with an optional error object

        :param str message: The message to print
        :param Any error: The error that caused the message, defaults to None
        """
        print(Logger.color(f"[ERROR]", RED), message)
        
    @staticmethod
    def warning( message: str):
        """Prints a warning message"""
        print(Logger.color(f"[WARNING]", YELLOW), message)
    
    @staticmethod
    def success( message: str):
        """Prints a success message"""
        print(Logger.color(f"[SUCCESS]", GREEN), message)
    
    @staticmethod
    def code( code: str, debug: bool = True):
        """Prints a block of code with numbered lines

        :param str code: The code block to print
        """

        if debug and not Logger.verbose:
            return
            
        for i, line in enumerate(code.split('\n')):
            print(Logger.color(f"{i+1} |".rjust(2),DARK_GRAY), Logger.color(line, GRAY))