import asyncio
import configparser
import logging
import traceback
import json
import os
import pathlib
from os.path import exists

import humanize
import qbittorrent.client
import requests
from qbittorrent import Client

import auto_update
import combined_log
from inhibitor_plugin import InhibitorPlugin
from torrent_formatter import torrent_format, no_torrent_template


class RainMeterInterface:

    def __init__(self, rainmeter, event_loop, logging: combined_log.CombinedLogger):
        try:
            self.logging = logging
            self.logging.change_log_file(os.path.join(pathlib.Path(__file__).parent.resolve(), "Logs/Log.log"))
            # logging.debug(f"Initial working directory: {os.getcwd()}")
            # os.chdir(os.path.dirname(os.path.abspath(__file__)))
            # logging.debug(f"Changed working directory to: {os.getcwd()}")

            self.logging.debug("Initializing RainMeterInterface")
            self.rainmeter = rainmeter
            self.event_loop = event_loop

            self.running = True
            self.torrents = {}
            self.rainmeter_values = {}
            self.torrent_progress = ""

            # ini_parser = configparser.ConfigParser()
            # logging.info("Loading qbt_ini.ini")
            # ini_parser.read(r"..\..\qbt_ini.ini")
            # logging.info("qbt_ini.ini loaded")

            # self.rainmeter_meters = \
            #     [x for x in ini_parser.sections() if "Torrent" in x and "Measure" not in x and "style" not in x]

            # self.rainmeter.RmExecute(f"[!SetOption Title Text \"BlockBust Viewer {self.version}\"]")

            self.page_start = 0
            self.torrent_num = 0
            self.page_num = 1
            self.torrent_sort = lambda d: d['added_on']
            self.torrent_filter = lambda d: True
            self.torrent_reverse = True
            self.changing_state = False
            self.logging.debug("Loading secrets.json")
            current_script_dir = pathlib.Path(__file__).parent.resolve()

            if not exists(os.path.join(current_script_dir, "secrets.json")):
                with open(os.path.join(current_script_dir, "secrets.json"), "w") as f:
                    json.dump({}, f)
            with open(os.path.join(current_script_dir, "secrets.json"), "r") as secrets_file:
                secrets = json.load(secrets_file)

            if not exists(os.path.join(current_script_dir, "settings.json")):
                with open(os.path.join(current_script_dir, "settings.json"), "w") as settings_file:
                    new_settings = {
                        "filter": [],
                        "sort_by": "added_on",
                        "reverse": True
                    }
                    json.dump(new_settings, settings_file)
            with open(os.path.join(current_script_dir, "settings.json"), "r") as settings_file:
                self.settings = json.load(settings_file)

            self.load_settings()

            self.logging.debug("secrets.json loaded")
            self.qb_user = secrets['Username']
            self.qb_pass = secrets['Password']
            self.qb_host = secrets['Host']
            self.qb = Client(self.qb_host)
            self.qb_connected = False
            self.qb_data = {}
            self.getting_banged = False
            self.bang_string = ""
            self.logging.debug("Launching background tasks")
            self.inhibitor_plugin = InhibitorPlugin(url="172.17.0.1", main_port=47675, alt_port=47676,
                                                    logging=self.logging,
                                                    on_update_available=self.inhibitor_update_available)
            self.rainmeter.RmLog(self.rainmeter.LOG_NOTICE, "Launching background tasks")
            self.inhibitor_plug_task = self.event_loop.create_task(self.inhibitor_plugin.run(self.event_loop))
            self.refresh_task = self.event_loop.create_task(self.refresh_torrents())

            self.auto_updater = auto_update.GithubUpdater("JayFromProgramming", "QBT_rainmeter_skin",
                                                          restart_callback=self.on_update_installed,
                                                          update_available_callback=self.on_update_available,
                                                          logging=self.logging)
            self.auto_update_task = self.event_loop.create_task(self.auto_updater.run())
            self.update_type_queued = None  # None, "local", "inhibitor"
            self.version = self.auto_updater.version()
            # self.inhibitor_plugin.get_state_change().set()
            self.first_run_flag = False
            self.change_waitress = self.event_loop.create_task(self.wait_for_change())

            self.logging.debug("Background tasks launched")
            self.refresh_task.add_done_callback(self._on_refresh_task_finished)
            self.logging.debug("Background tasks launched")
        except Exception as e:
            self.logging.critical(f"Unable to initialize RainMeterInterface: {e}\n{traceback.format_exc()}")

    def load_settings(self):
        """Loads the settings from the settings.json file"""
        # Combine all filters into one lambda expression
        try:
            self.logging.debug("Loading settings")
            if len(self.settings['filter']) == 0:
                self.logging.debug("No filters set")
                self.torrent_filter = lambda d: True
            elif 'filter_all' in self.settings['filter']:
                self.logging.debug("All torrents filter set")
                self.torrent_filter = lambda d: True
            elif 'filter_active' in self.settings['filter']:
                self.logging.debug("Filtering active torrents")
                self.torrent_filter = lambda d: d['state'] != "stalledUP" and d['state'] != "missingFiles"
            self.torrent_sort = lambda d: d[self.settings['sort_by']]
            self.torrent_reverse = self.settings['reverse']
        except Exception as e:
            self.logging.critical(f"Unable to load settings: {e}\n{traceback.format_exc()}")

    def set_settings(self, **kwargs):
        try:
            if 'filter_by' in kwargs:
                self.settings['filter'] = kwargs['filter_by']
            if 'sort_by' in kwargs:
                self.settings['sort_by'] = kwargs['sort_by']
            if 'reverse' in kwargs:
                self.settings['reverse'] = kwargs['reverse']
            with open(os.path.join(pathlib.Path(__file__).parent.resolve(), "settings.json"), "w") as settings_file:
                json.dump(self.settings, settings_file, indent=4)
        except Exception as e:
            self.logging.critical(f"Unable to set settings: {e}\n{traceback.format_exc()}")

    async def on_update_installed(self):
        """Called when the update is installed"""
        self.logging.info("Refreshing all rainmeter skins...")
        self.rainmeter.RmExecute("[!RefreshApp]")
        self.logging.error("Oh fuck, oh fuck")

    async def inhibitor_update_available(self, newest=None, current=None):
        try:
            if self.update_type_queued is not None:
                return
            await self.generate_update_popup(newest, current, source="QBT_inhibitor", u_type="inhibitor")
        except Exception as e:
            self.logging.critical(f"Unable to generate update popup: {e}\n{traceback.format_exc()}")

    async def on_update_available(self, newest=None, current=None):
        """Called when an update is available""
        Called when an update is available
        :return: Nothing
        """
        if self.update_type_queued is not None:
            return
        self.auto_update_task.cancel()  # Stop the auto updater so the user doesn't get multiple update prompts
        await self.generate_update_popup(newest, current, source="QBT_rainmeter_skin", u_type="local")

    async def generate_update_popup(self, newest=None, current=None, source=None, u_type=None):
        """Generates a popup to ask the user if they want to update"""
        try:
            ini_parser = configparser.ConfigParser()
            with open(os.path.join(os.getenv('APPDATA'), 'Rainmeter\\Rainmeter.ini'), 'r', encoding='utf-16-le') as f:
                ini_string = f.read()[1:]
            ini_parser.read_string(ini_string)
            if "QBT_rainmeter_skin" not in ini_parser:
                self.logging.error("Unable to find qbittorrent skin.")
                return 0
            source_text = f"An update is available for {source}\nWould you like to update?"
            qbt_x = ini_parser['QBT_rainmeter_skin']['WindowX']
            qbt_y = ini_parser['QBT_rainmeter_skin']['WindowY']
            bang = f"[!ActivateConfig \"QBT_rainmeter_skin\\update-popup\"]" \
                   f"[!ZPos \"2\" \"QBT_rainmeter_skin\\update-popup\"]" \
                   f"[!Move \"{int(qbt_x) + 172}\" \"{int(qbt_y) + 100}\" \"QBT_rainmeter_skin\\update-popup\"]" \
                   f"[!SetOption UpdateText Text \"{source_text}\" \"QBT_rainmeter_skin\\update-popup\"]" \
                   f"[!SetOption CurrentVersion Text \"Current version: {current}\" \"QBT_rainmeter_skin\\update" \
                   f"-popup\"]" \
                   f"[!SetOption NewVersion Text \"New version: {newest}\" \"QBT_rainmeter_skin\\update-popup\"]"
            self.rainmeter.RmExecute(bang)
            self.update_type_queued = u_type
        except Exception as e:
            self.logging.error(f"Unable to show update popup: {e}\n{traceback.format_exc()}")

    async def update_self(self):
        """Updates the rainmeter skin"""
        try:
            self.logging.info("Updating...")
            self.running = False
            self.inhibitor_plug_task.cancel()
            self.rainmeter.RmExecute("[!SetOption ConnectionMeter Text \"Performing update...\"]")
            self.rainmeter.RmExecute("[!Redraw]")
            python_home = self.rainmeter.RmReadString("PythonHome", r"C:\Program Files\Python36", False)
            self.logging.info(f"Python home: {python_home}, preforming update")
            refresh = await self.auto_updater.preform_update(python_home)
            self.logging.info("Update complete")
            if not refresh:
                self.rainmeter.RmExecute("[!RefreshApp]")
        except Exception as e:
            self.logging.error(f"Unable to update: {e}\n{traceback.format_exc()}")

    async def update_popup_callback(self, confirmed=None):
        try:
            self.rainmeter.RmExecute("[!DeactivateConfig \"QBT_rainmeter_skin\\update-popup\"]")
            if confirmed:
                if self.update_type_queued == "local":
                    await self.update_self()
                elif self.update_type_queued == "inhibitor":
                    await self.inhibitor_plugin.send_sys_command(command="pref_update")
            else:
                if self.update_type_queued == "inhibitor":
                    await self.inhibitor_plugin.send_sys_command(command="deny_update")
            self.update_type_queued = None
        except Exception as e:
            self.logging.error(f"Unable to update popup callback: {e}\n{traceback.format_exc()}")

    def _on_refresh_task_finished(self):
        self.rainmeter.RmLog(self.rainmeter.LOG_NOTICE, "Refresh task finished")
        self.logging.critical("Refresh task finished")

    def get_bang(self) -> str:
        """Called by the rainmeter plugin to get the current display string"""
        return self.bang_string

    def _connect(self):
        try:
            self.qb.login(self.qb_user, self.qb_pass)
            self.qb_connected = True
        except Exception as e:
            self.logging.critical(f"Unable to connect to server {e}\n{traceback.format_exc()}")
            self.rainmeter.RmLog(self.rainmeter.LOG_ERROR, f"Unable to connect to server {e}")
            self.qb_connected = False

    async def refresh_torrents(self):
        while self.running:
            try:
                if not self.qb_connected:
                    self._connect()
                try:
                    torrents = self.qb.torrents()
                    qb_data = self.qb.sync_main_data()
                    self.qb_data['url'] = self.qb.url.split("/")[2]
                    self.qb_data['version'] = self.qb.qbittorrent_version
                except qbittorrent.client.LoginRequired:
                    self.qb_connected = False
                    self.logging.critical("Login required")
                except requests.exceptions.HTTPError as e:
                    self.qb_connected = False
                    self.logging.critical(f"HTTP error: {e}")
                except Exception as e:
                    self.qb_connected = False
                    self.logging.error(f"Unable to get torrents: {e}\n{traceback.format_exc()}")
                else:
                    self.qb_data['free_space'] = qb_data['server_state']['free_space_on_disk']
                    self.qb_data['global_dl'] = qb_data['server_state']['dl_info_speed']
                    self.qb_data['global_up'] = qb_data['server_state']['up_info_speed']
                    self.qb_data['total_peers'] = qb_data['server_state']['total_peer_connections']
                    torrents = filter(self.torrent_filter, torrents)
                    torrents = sorted(torrents, key=self.torrent_sort)
                    if self.torrent_reverse:
                        torrents.reverse()
                    # self.logging.debug(f"Sort by: {self.torrent_sort} first torrent: {torrents[0]}")
                    self.torrent_num = len(torrents)
                    self.torrents = torrents
            except Exception as e:
                logging.error(f"Failed to get torrents: {e}\n{traceback.format_exc()}")
            finally:
                await self.parse_rm_values()
                await asyncio.sleep(2)

    async def first_run(self):
        if self.settings['sort_by'] == 'name':
            self.rainmeter.RmExecute("[!SetOption SortDropdownBoxText Text \"Sort by: Name\"]")
        elif self.settings['sort_by'] == 'added_on':
            self.rainmeter.RmExecute("[!SetOption SortDropdownBoxText Text \"Sort by: Added Date\"]")
        elif self.settings['sort_by'] == 'upspeed':
            self.rainmeter.RmExecute("[!SetOption SortDropdownBoxText Text \"Sort by: UL Speed\"]")
        elif self.settings['sort_by'] == 'dlspeed':
            self.rainmeter.RmExecute("[!SetOption SortDropdownBoxText Text \"Sort by: DL Speed\"]")
        if 'filter_all' in self.settings['filter']:
            self.rainmeter.RmExecute("[!SetOption FilterDropdownBoxText Text \"Filter by: All\"]")
        elif 'filter_active' in self.settings['filter']:
            self.rainmeter.RmExecute("[!SetOption FilterDropdownBoxText Text \"Filter by: Active\"]")
        return True

    async def parse_rm_values(self):
        """Parse the rainmeter values"""
        if not self.first_run_flag:
            self.first_run_flag = True
            await self.first_run()
        logging.info("Parsing rainmeter values")

        try:
            if not self.qb_connected:
                """Set all torrent slots to an error state"""
                self.rainmeter_values = no_torrent_template()
                self.rainmeter_values["ConnectionMeter"] = {"Text": f"Not connected to {self.qb_data['url']}"}
                self.rainmeter_values["GlobalDownload"] = {"Text": "0B/s"}
                self.rainmeter_values["GlobalUpload"] = {"Text": "0B/s"}
                self.rainmeter_values['GlobalPeers'] = {"Text": "Connected peers: ???"}
                self.rainmeter_values['FreeSpace'] = {"Text": "Free space: ???"}
                self.rainmeter_values['PageNumber'] = {'Text': "1/1"}
            else:
                torrents = self.torrents[self.page_start:self.page_start + 4]
                tprogress = {'progress': []}
                for torrent in torrents:
                    tprogress['progress'].append(torrent['progress'] * 100.0)
                self.torrent_progress = json.dumps(tprogress)
                self.rainmeter_values = torrent_format(torrents)
                self.rainmeter_values['Title'] = {'Text': f"BlockBust Viewer {self.version}"}
                self.rainmeter_values['ConnectionMeter'] = {'Text': f"Connected to {self.qb_data['url']} "
                                                                    f"qBittorrent {self.qb_data['version']}"}
                self.rainmeter_values['GlobalDownload'] = {
                    'Text': f"DL: {humanize.naturalsize(self.qb_data['global_dl'])}/s"}
                self.rainmeter_values['GlobalUpload'] = {
                    'Text': f"UP: {humanize.naturalsize(self.qb_data['global_up'])}/s"}
                self.rainmeter_values['GlobalPeers'] = {'Text': f"Connected peers: {self.qb_data['total_peers']}"}
                self.rainmeter_values['FreeSpace'] = \
                    {'Text': f"Free space: {humanize.naturalsize(self.qb_data['free_space'])}"}
                self.rainmeter_values['PageNumber'] = {'Text': f"{self.page_num}/{self.torrent_num // 4}"}
                self.rainmeter_values['InhibitorMeter'] = \
                    {'ToolTipText': 'Version: ' + await self.inhibitor_plugin.get_inhibitor_version()}

                if self.inhibitor_plugin.should_cycle_status():
                    self.rainmeter_values['InhibitorMeter'] = {'Text': self.inhibitor_plugin.get_ticker_text()}

        except Exception as e:
            logging.error(f"Failed to parse rainmeter values: {e}\n{traceback.format_exc()}")
            self.rainmeter_values = {}
        else:
            self.getting_banged = True
            self.bang_string = ""
            for meter in self.rainmeter_values.keys():
                for key, value in self.rainmeter_values[meter].items():
                    self.bang_string += f"[!SetOption {meter} {key} \"{value}\"]"
                torrents = self.torrents[self.page_start:self.page_start + 4]
                for i in range(len(torrents)):
                    if 'better_rss' in torrents[i]['tags']:
                        self.bang_string += f"[!ShowMeter RSSIcon{i}]"
                    else:
                        self.bang_string += f"[!HideMeter RSSIcon{i}]"
            self.getting_banged = False

    def get_string(self) -> str:
        """Called by the rainmeter plugin to get the current display string"""
        return self.torrent_progress

    async def execute_bang(self, bang):
        """Called by the rainmeter plugin"""
        try:
            if bang == "updater_no":
                await self.update_popup_callback(confirmed=False)
            if bang == "updater_yes":
                await self.update_popup_callback(confirmed=True)

            if 'sort_' in bang:
                if bang == 'sort_name':
                    self.torrent_sort = lambda d: d['name']
                    self.torrent_reverse = False
                    self.set_settings(sort_by='name', reverse=False)
                if bang == 'sort_added_date':
                    self.torrent_sort = lambda d: d['added_on']
                    self.torrent_reverse = True
                    self.set_settings(sort_by='added_on', reverse=True)
                if bang == 'sort_dl_speed':
                    self.torrent_sort = lambda d: d['dlspeed']
                    self.torrent_reverse = True
                    self.set_settings(sort_by='dlspeed', reverse=True)
                if bang == 'sort_ul_speed':
                    self.torrent_sort = lambda d: d['upspeed']
                    self.torrent_reverse = True
                    self.set_settings(sort_by='upspeed', reverse=True)
                self.page_start = 0
            if 'filter_' in bang:
                if bang == 'filter_all':
                    self.torrent_filter = lambda d: True
                    self.set_settings(filter_by='filter_all')
                if bang == 'filter_active':
                    self.torrent_filter = lambda d: d['state'] != "stalledUP" and d['state'] != "missingFiles"
                    self.set_settings(filter_by='filter_active')
                self.page_start = 0

            if 'inhibit_' in bang:
                self.inhibitor_plugin.get_state_change().clear()
            self.changing_state = True
            self.bang_string = ""
            if bang == 'inhibit_true':
                await self.inhibitor_plugin.execute(inhibit=True, override=False)
                self.logging.debug("Inhibitor set to true")
            if bang == 'inhibit_false':
                await self.inhibitor_plugin.execute(inhibit=False, override=True)
                self.logging.debug("Inhibitor set to false")

            if 'page_' in bang:
                if bang == 'page_right':
                    if not self.page_start + 4 == self.torrent_num:
                        self.page_start += 4
                        self.page_num += 1
                        if self.page_start > self.torrent_num - 4:
                            self.page_start = self.torrent_num - 4
                if bang == 'page_left':
                    if not self.page_start == 0:
                        self.page_start -= 4
                        self.page_num -= 1
                        if self.page_start < 0:
                            self.page_start = 0
                if bang == 'page_reset':
                    self.page_start = 0
                    self.page_num = 1
                await self.parse_rm_values()
                self.rainmeter.RmExecute(self.bang_string)
        except Exception as e:
            logging.error(f"Failed to execute bang: {e}\n{traceback.format_exc()}")

    async def wait_for_change(self):
        while self.running:
            try:
                await self.inhibitor_plugin.get_state_change().wait()
                self.logging.debug("Wait for change has been triggered")
                self.rainmeter.RmExecute("[!HideMeter MeterLoadingAnimation]")
                if await self.inhibitor_plugin.get_inhibitor_state():
                    self.rainmeter.RmExecute("[!ShowMeter PlayButton][!HideMeter PauseButton]")
                else:
                    self.rainmeter.RmExecute("[!ShowMeter PauseButton][!HideMeter PlayButton]")
                self.rainmeter.RmExecute(
                    f"[!SetOption InhibitorMeter Text \"" + await self.inhibitor_plugin.get_inhibitor_status() + "\"]")
                self.changing_state = False
                self.inhibitor_plugin.get_state_change().clear()
            except Exception as e:
                self.logging.error(f"Failed to execute bang: {e}\n{traceback.format_exc()}")
            finally:
                await asyncio.sleep(1)

    async def tear_down(self):
        """Call this when the plugin is being unloaded"""
        self.refresh_task.cancel()
        self.inhibitor_plug_task.cancel()
        self.auto_update_task.cancel()
