# libraries
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("laplace-master")
except PackageNotFoundError:
    __version__ = "0.0.0"

# project
from .interface import MasterWindow

__all__ = [
    "__version__",
    "MasterWindow",
]

__doc__ = """
Laplace master (laplace_master)

Usage
-----
See the laplace_master.main file to get an example of entry point.
"""