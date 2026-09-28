# libraries
import sys
import logging

from PyQt6.QtWidgets import QApplication
from laplace_log import LoggerLHC, log
from laplace_server.protocol import LOGGER_NAME

LoggerLHC("laplace.master", log_root="", file_level="debug", console_level="info")
log.info("Starting MasterWindow...")

logging.getLogger(LOGGER_NAME).setLevel(logging.INFO)
from laplace_log import uncaught_exception

# project
from interface.masterWindow import MasterWindow


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MasterWindow(flag="scan") # initialize the window
    window.show()           # run the main loop

    log.info("Window opened.")

    # end the process
    exit_code = app.exec()
    log.info(f"Application is exiting with code {exit_code}.")
    sys.exit(exit_code)