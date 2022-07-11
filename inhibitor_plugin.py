import asyncio
import datetime
import logging

from helpers import APIMessageTX, APIMessageRX

logging.basicConfig(level=logging.INFO,
                    format=r"[%(asctime)s - %(levelname)s - %(threadName)s - %(name)s - %(funcName)s - %(message)s]")


class InhibitorState:

    def __init__(self):
        self.inhibiting = False
        self.inhibit_sources = []
        self.overridden = False
        self.connected_to_qbt = False
        self.connected_to_plex = False
        self.connected_to_inhibitor = False
        self.message = None
        self.last_update = datetime.datetime.now()

    def __str__(self):
        """Format the inhibitor state for use in Rainmeter"""
        string = "U.Speed:"
        if self.message is not "" and self.message is not None:
            return string + self.message
        if not self.connected_to_inhibitor:
            string += "Disconnected"
            return string
        if not self.connected_to_qbt:
            string += "No QBT connection"
            return string
        if not self.connected_to_plex:
            string += "No Plex connection"
            return string

        if self.inhibiting:
            string += " Inhibited -"
            for source in self.inhibit_sources:
                string += f" {source}"
        else:
            string += " Uninhibited"
            if not self.overridden:
                string += " Auto"

    def __bool__(self):
        return self.inhibiting


class InhibitorPlugin:

    def __init__(self, *args, **kwargs):
        self.url = kwargs.get("url")
        self.main_port = kwargs.get("main_port")
        self.alt_port = kwargs.get("alt_port")
        self.reader = None
        self.write_lock = asyncio.Lock()
        self.writer = None
        self.terminate = False
        self.token = None
        self.state = InhibitorState()
        pass

    async def execute(self, **kwargs) -> None:
        """Send a command to the api server"""
        msg = APIMessageTX(msg_type="command", **kwargs)
        async with self.write_lock:
            self.writer.write(msg.encode('utf-8'))
            await self.writer.drain()

    async def get_inhibitor_status(self) -> str:
        """Does like magic or something, I don't know"""
        return str(self.state)

    async def get_inhibitor_state(self) -> bool:
        """Get the current state of the inhibitor"""
        return bool(self.state)

    async def run(self):
        """Run the plugin"""
        while True:
            if not self.state.connected_to_inhibitor:
                logging.info("Connecting to inhibitor server")
                await self._connect()
            else:
                if self.state.last_update < datetime.datetime.now() - datetime.timedelta(seconds=10):
                    logging.info("Sending refresh message")
                    msg = APIMessageTX(msg_type="refresh", token=self.token)
                    async with self.write_lock:
                        self.writer.write(msg.encode('utf-8'))
                        await self.writer.drain()
            await asyncio.sleep(1)

    async def _connect(self):
        """Establish a connection to the inhibitor server"""
        if self.state.connected_to_inhibitor:
            logging.info("Already connected to inhibitor server")
            return

        if self.reader is not None:
            self.reader.feed_eof()
        if self.writer is not None:
            self.writer.close()

        try:
            self.reader, self.writer = await asyncio.open_connection(self.url, self.main_port)
            self.connected = True
            logging.info(f"Connecting to inhibitor server {self.url}:{self.main_port}")
        except OSError:
            try:
                logging.error(f"Failed to connect to inhibitor server {self.url}:{self.main_port}")
                self.reader, self.writer = await asyncio.open_connection(self.url, self.alt_port)
                self.connected = True
            except Exception as e:
                logging.error(f"Failed to connect to inhibitor server {self.url}:{self.alt_port}")
                logging.error(e)
                self.connected = False
                return

        # Send the wave message
        # if self.token is not None:
        #     msg = APIMessageTX(msg_type="renew", token=self.token)
        #     self.writer.write(msg.encode('utf-8'))
        #     await self.writer.drain()
        else:
            msg = APIMessageTX(msg_type="handshake")
            self.writer.write(msg.encode('utf-8'))
            await self.writer.drain()
        try:
            response = await self.reader.readuntil(b'\n\r')
            msg = APIMessageRX(response)
            if msg.msg_type == "renew_conn" or msg.msg_type == "new_conn":
                self.token = msg.token
            self.state.connected_to_inhibitor = True
        except Exception as e:
            logging.error(e)
            self.state.connected_to_inhibitor = False
            return
        logging.info(f"Received token {self.token}")

        # Start listening for messages
        asyncio.get_event_loop().create_task(self._listener()).add_done_callback(self._listener_done)

    def _listener_done(self, future):
        """Called when the listener is done"""
        if future.exception() is not None:
            logging.error(f"Listener error: {future.exception()}")
        else:
            logging.info("Listener done")
        self.state.connected_to_inhibitor = False

    async def _listener(self):
        """Listen to the assigned client"""
        while not self.terminate and self.state.connected_to_inhibitor:
            try:
                new_message = await self.reader.readuntil(b'\n\r')
            except OSError as e:
                logging.error(f"Lost connection to inhibitor server {e}")
                self.state.connected_to_inhibitor = False
            except asyncio.exceptions.IncompleteReadError:
                logging.error("Incomplete read from inhibitor server")
                self.state.connected_to_inhibitor = False
            else:
                try:
                    msg = APIMessageRX(new_message)
                    if msg.msg_type == "state_update":
                        logging.info(f"Received update message {msg}")
                        self.state.inhibiting = msg.inhibiting
                        self.state.inhibit_sources = msg.inhibited_by
                        self.state.connected_to_qbt = msg.qbt_connection
                        self.state.connected_to_plex = msg.plex_connection
                        self.state.connected_to_inhibitor = self.connected
                        self.state.last_update = datetime.datetime.now()
                    elif msg.msg_type == "ack":
                        logging.info(f"Received ack message")
                    else:
                        logging.warning(f"Unknown message type {msg.msg_type}")
                except Exception as e:
                    logging.error(e)
                    logging.error(new_message)
                    self.state.connected_to_inhibitor = False
                    await asyncio.sleep(1)
            await asyncio.sleep(0.5)


# inhibitor_plugin = InhibitorPlugin(url="localhost", main_port=47675, alt_port=47676)
# asyncio.get_event_loop().run_until_complete(inhibitor_plugin.run())
