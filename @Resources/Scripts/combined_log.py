import logging
from logging import LogRecord
from logging.handlers import RotatingFileHandler

logging.getLogger(__name__).setLevel(logging.DEBUG)


class CombinedRotatingFileHandler(RotatingFileHandler):

    def emit(self, record: LogRecord) -> None:
        logging.debug(f"Emit: {record.msg}")
        super().emit(record)
        if self.rainmeter is not None:
            if record.levelname == "ERROR":
                self.rainmeter.RmLog(self.rainmeter.LOG_ERROR, record.msg)
            elif record.levelname == "WARNING":
                self.rainmeter.RmLog(self.rainmeter.LOG_WARNING, record.msg)
            elif record.levelname == "INFO":
                self.rainmeter.RmLog(self.rainmeter.LOG_NOTICE, record.msg)
            elif record.levelname == "DEBUG":
                self.rainmeter.RmLog(self.rainmeter.LOG_DEBUG, record.msg)
            else:
                self.rainmeter.RmLog(self.rainmeter.LOG_NOTICE, record.msg)
        logging.debug(f"Emitted: {record.msg}")

    def flush(self) -> None:
        super().flush()
        if self.rainmeter is not None:
            self.rainmeter.RmLog(self.rainmeter.LOG_NOTICE, "Flushed log.log")

    def __init__(self, filename: str = None, mode=None, encoding=None, delay=None, formatter=None, **kwargs):
        super().__init__(filename=filename, mode=mode, encoding=encoding, delay=delay,
                         maxBytes=1024 * 1024, **kwargs)
        super().setFormatter(formatter)
        self.backupCount = 10
        self.rainmeter = None

    def setRMObject(self, rainmeter: object):
        self.rainmeter = rainmeter


class CombinedLogger(logging.Logger):

    def __init__(self, name, level=logging.NOTSET, **kwargs):
        super().__init__(name, level)
        self.filename = kwargs.get("filename", None)
        self.mode = kwargs.get("mode", "w")
        self.encoding = kwargs.get("encoding", "utf-8")
        self.delay = kwargs.get("delay", False)
        self.formatter = logging.Formatter(kwargs.get("formatter", "%(asctime)s - %(levelname)s - %(message)s"))
        if self.filename is not None:
            self.addHandler(CombinedRotatingFileHandler(filename=self.filename, mode=self.mode, encoding=self.encoding,
                                                        delay=self.delay,
                                                        formatter=self.formatter))

    def setRMObject(self, rainmeter: object):
        for handler in self.handlers:
            if isinstance(handler, CombinedRotatingFileHandler):
                handler.setRMObject(rainmeter)
                break

    def change_log_file(self, filename: str):
        for handler in self.handlers:
            if isinstance(handler, CombinedRotatingFileHandler):
                self.removeHandler(handler)
                break
        self.filename = filename
        self.addHandler(CombinedRotatingFileHandler(filename=filename, mode=self.mode, encoding=self.encoding,
                                                    delay=self.delay,
                                                    formatter=self.formatter))
        self.info("Changed log file to %s", filename)
