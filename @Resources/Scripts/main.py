import logging
import traceback
from threading import Thread
import asyncio

import rm_interface
from combined_log import CombinedLogger


# logging.basicConfig(level=logging.DEBUG,
#                     format=r"[%(asctime)s - %(levelname)s - %(threadName)s - %(name)s - %(funcName)s - %(message)s]",
#                     filename=r"D:\Rainmeter\Logs\old_log.log")

class Rain:
    """This whole class is just a pass-through to the rainmeter interface"""

    def __init__(self):
        """Never actually called, reload is the actual entry point"""
        # logging.info("Initializing Rainmeter Script")
        self.rainmeter = None
        self.rainmeter_interface = None
        self.updater = None
        self.event_loop = None
        self.task = None
        self.background_thread = None
        self.logging = None

    async def on_new_version(self):
        pass

    async def on_update_restart(self):
        pass

    def _task_done(self, task):
        """Called when the rainmeter plugin is done with the task"""
        pass

    def Reload(self, rm, maxValue) -> None:
        try:
            # logfile = rm.RmReadString("Logfile")
            try:
                logging.info("Initializing CombinedLogger")
                self.logging = CombinedLogger(
                    name="Rainmeter", level=logging.INFO,
                    formatter=
                    r"%(asctime)s - %(levelname)s - Thread: %(threadName)s - %(name)s - %(funcName)s - %(message)s")
                self.logging.setRMObject(rm)
                logging.debug("Initialized CombinedLogger, creating rainmeter interface")
                # logging.setLoggerClass(CombinedLogger)
            except Exception as e:
                logging.error(f"Error in CombinedLogger Init: {e}\n{traceback.format_exc()}")
                return

            self.logging.info("Reload called, creating asyncio event loop")

            self.rainmeter = rm
            self.event_loop = asyncio.new_event_loop()
            self.task = self.event_loop.create_task(self.true_init())

            self.logging.debug("Created asyncio event loop, starting background asyncio thread...")

            self.background_thread = Thread(target=self._start_asyncio, name="Dear god I am sorry")
            self.background_thread.start()

            self.logging.debug("Started background asyncio thread")

            # Log info about the task
            self.logging.debug(f"Task: {self.task}")
            self.logging.debug(f"Task.done: {self.task.get_stack()}")

            self.logging.debug(f"Thread: {self.background_thread}")
            self.logging.debug(f"Thread alive: {self.background_thread.is_alive()}")

        except Exception as e:
            logging.error(f"Error in Reload: {e}\n{traceback.format_exc()}")

    def _start_asyncio(self):
        """Start the asyncio event loop"""
        try:
            self.logging.info("Starting asyncio event loop")
            self.event_loop.run_forever()
            self.logging.error("Well shit")
        except Exception as e:
            self.logging.error(f"Error in _start_asyncio: {e}")

    async def true_init(self):
        """This is the actual initialization of the plugin"""
        logging.info("Initializing rainmeter interface")
        try:
            self.rainmeter.RmLog(self.rainmeter.LOG_NOTICE, "Creating Rainmeter Interface")
            self.logging.debug("Creating rainmeter interface")
            self.rainmeter_interface = rm_interface.RainMeterInterface(self.rainmeter, self.event_loop, self.logging)
            self.logging.debug("Initialized rainmeter interface")
            self.rainmeter.RmLog(self.rainmeter.LOG_NOTICE, "Created Rainmeter Interface, creating updater")
        except Exception as e:
            self.logging.error(f"Error in true_init: {e}\n{traceback.format_exc()}")

    def Update(self) -> None:
        """Called by the rainmeter plugin"""
        try:
            if self.rainmeter_interface is None:
                self.logging.warning("rainmeter_interface initializing")
                self.rainmeter.RmExecute(f"[!SetOption ConnectionMeter Text \"Script initializing...\"]")
            else:
                if not self.rainmeter_interface.getting_banged:
                    self.rainmeter.RmExecute(self.rainmeter_interface.get_bang())
        except Exception as e:
            self.logging.error(f"Error in Update: {e}\n{traceback.format_exc()}")

    def GetString(self) -> str:
        return self.rainmeter_interface.get_string()

    def ExecuteBang(self, args) -> None:
        """Called by the rainmeter plugin"""
        try:
            task = self.event_loop.create_task(self.rainmeter_interface.execute_bang(args))
        except Exception as e:
            self.logging.error(f"Error in ExecuteBang: {e}\n{traceback.format_exc()}")

    def Finalize(self) -> None:
        """Called by the rainmeter plugin"""
        try:
            task = self.event_loop.create_task(self.rainmeter_interface.tear_down())
            # Wait for the task to finish
            task.add_done_callback(lambda _: task.result())
        except Exception as e:
            self.logging.error(f"Error in Finalize: {e}\n{traceback.format_exc()}")
