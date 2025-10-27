
import os
import logging
from logging.handlers import TimedRotatingFileHandler

class Logger:
    def __init__(self,
        log_name: str,
        log_file: str,
        log_dir: str = "logs",
        format: str = "%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(message)s",
        interval: int = 1,
        backup_count: int = 7,
        log_level: int = logging.INFO,
        file_level: int = logging.DEBUG,
        console_level: int = logging.DEBUG,
    ):
        """
        Generates a logger instance with both file and console handlers, meant to be used by individual modules and independent scripts.
        After initializing, call get_logger() to retrieve the logger instance.
        Args:
            log_name (str): Name of the logger instance.
            log_file (str): Name of the log file.
            log_dir (str): Directory where log files will be stored. Default is "logs".
            format (str): Format of the log messages. Default includes timestamp, level, name, module, and message.
            interval (int): Interval in days for rotating the log file. Default is 1 day.
            backup_count (int): Number of backup log files to keep. Default is 7.
            log_level (int): Overall logging level for the logger. Default is logging.INFO.
            file_level (int): Logging level for the file handler. Default is logging.DEBUG.
            console_level (int): Logging level for the console handler. Default is logging.DEBUG. logging.DEBUG = 10, logging.INFO = 20, logging.WARNING = 30, logging.ERROR = 40, logging.CRITICAL = 50
        """
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        self.formatter = logging.Formatter(format)
        file_handler = TimedRotatingFileHandler(
            filename=os.path.join(log_dir, log_file),
            when="midnight",
            interval=interval,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(self.formatter)
        file_handler.setLevel(file_level)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(self.formatter)
        console_handler.setLevel(console_level)

        self.logger = logging.getLogger(log_name)
        self.logger.setLevel(log_level)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        self.logger.propagate = False

        self.logger.debug("Logger initialized")

    def get_logger(self):
        """
        Returns the logger instance.
        """
        return self.logger