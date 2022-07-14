import asyncio
import os
import pathlib
import time
import traceback
import logging
import aiohttp
import combined_log

logging.getLogger(__name__).setLevel(logging.DEBUG)

installed_dir = os.path.dirname(os.path.realpath(__file__))


def cleanup():
    # Look for the old_version.zip file and delete it and the recovery script
    if os.path.exists("old_version.zip"):
        os.remove("old_version.zip")
    if os.path.exists("recovery.sh"):
        os.remove("recovery.sh")


class GithubUpdater:

    def __init__(self, owner: str, repo: str, restart_callback=None,
                 update_available_callback: asyncio.coroutine = None,
                 logging: combined_log.CombinedLogger = None):
        self.repo = repo
        self.owner = owner
        self.restart_callback = restart_callback
        self.on_update_available_callback = update_available_callback
        self.new_version_available = False
        self.logging = logging
        self.ratelimit_remaining = ""
        self.ratelimit_reset = 0
        self.ratelimit_used = 0
        cleanup()

    async def _get_latest_release(self):

        if self.ratelimit_remaining == 0:
            raise Exception("Ratelimit reached")

        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest") as resp:
                # Get the ratelimit
                self.ratelimit_remaining = int(resp.headers.get("X-Ratelimit-Remaining"))
                self.ratelimit_reset = int(resp.headers.get("X-Ratelimit-Reset"))
                self.ratelimit_used = int(resp.headers.get("X-Ratelimit-Used"))
                return await resp.json()

    # async def _get_release_details(self, tag_name: str):
    #     async with aiohttp.ClientSession() as session:
    #         async with session.get(f"https://api.github.com/repos/{self.owner}/{self.repo}/git/ref/tags/{tag_name}")\
    #                 as resp:
    #             return await resp.json()

    def _get_installed_version(self):
        try:
            current_script_dir = pathlib.Path(__file__).parent.resolve()
            with open(os.path.join(current_script_dir, "version.txt")) as version_file:
                return version_file.read().strip()
        except Exception as e:
            self.logging.error(f"Failed to get installed version: {e}")
            return "unknown"

    def version(self):
        """Returns the installed version"""
        return self._get_installed_version()

    async def run(self):
        self.logging.debug("Starting auto update check")
        while True:
            try:
                self.logging.debug("Checking github for updates")
                latest_release = await self._get_latest_release()
                if latest_release is None:
                    self.logging.error("Failed to get latest release")
                    await asyncio.sleep(5)
                    continue

                if "tag_name" not in latest_release:
                    self.logging.error(f"No latest release tag found{latest_release}")
                    await asyncio.sleep(5)
                    continue

                if latest_release["tag_name"] != self._get_installed_version():
                    logging.info(f"New version available: {latest_release['tag_name']}")
                    # Get the commit hash associated with the release
                    # if "target_commitish" not in latest_release:
                    #     self.logging.error(f"No target commitish found in release: {latest_release}")
                    #     await asyncio.sleep(5)
                    #     continue
                    # details = await self._get_release_details(latest_release["tag_name"])
                    # if details is None:
                    #     self.logging.error(f"Failed to get release details for {latest_release['tag_name']}")
                    #     await asyncio.sleep(5)
                    #     continue

                    self.new_version_available = True
                    if self.on_update_available_callback is not None:
                        current_version = self._get_installed_version()
                        await self.on_update_available_callback(newest=latest_release["tag_name"],
                                                                current=current_version)
                else:
                    self.new_version_available = False
            except Exception as e:
                self.logging.error(f"Failed to check for updates: {e}\n{traceback.format_exc()}")
            finally:
                # Calculate how long to wait before checking again
                if self.ratelimit_reset is not None and isinstance(self.ratelimit_reset, int):
                    wait_time = (self.ratelimit_reset - int(round(time.time()))) + 15
                    if wait_time > 0:
                        self.logging.debug(f"Waiting {wait_time} seconds before checking again")
                        await asyncio.sleep(wait_time)
                    else:
                        self.logging.debug("Ratelimit reset in the past, checking again immediately")
                else:
                    self.logging.debug("No ratelimit reset found, waiting 120 seconds before checking again")
                    await asyncio.sleep(120)

    async def make_recovery_shell_script(self):
        """Creates a shell script that can be used to restore the old version"""
        if not self.new_version_available:
            self.logging.debug("No new version available")
            return
        self.logging.info(f"Creating recovery shell script")
        with open("recovery.sh", "w") as f:
            f.write("#!/bin/bash\n")  # Made by Copilot so it likely won't work
            f.write(f"echo 'Restoring old version'\n")
            f.write(f"mv old_version.zip new_version\n")
            f.write(f"mv new_version.zip old_version.zip\n")
            f.write(f"mv old_version old_version.zip\n")
            f.write(f"mv new_version old_version\n")
            f.write(f"echo 'Restored old version'\n")
        os.chmod("recovery.sh", 0o755)
        self.logging.info("Recovery shell script created")

    async def preform_update(self, python_home):
        """Downloads the latest version and replaces the current version"""
        try:
            # Get release info
            self.logging.info("Getting latest release")
            latest_release = await self._get_latest_release()

            if latest_release is None:
                self.logging.error("Failed to get latest release")
                return

            if "tag_name" not in latest_release:
                self.logging.error("No latest release tag found")
                return

            self.logging.info("Preforming update... (using gitpull)")
            installed_dir = os.path.dirname(os.path.realpath(__file__))

            current_script_dir = pathlib.Path(__file__).parent.resolve()
            os.chdir(installed_dir)
            result = os.popen("git pull").read()
            self.logging.info(result)
            if result.startswith("Already up to date."):
                self.logging.info("Already up to date - not updating")
                with open(os.path.join(current_script_dir, "version.txt"), "w") as f:
                    f.write(latest_release["tag_name"])
                return False
            elif result == "":
                self.logging.info("Some unknown git error occured, not updating")
                return False  # Not sure what happened
            self.logging.info("Updated")
            # Run post update requirement update
            result = os.popen(f"{python_home}\\python -m pip install -r requirements.txt").read()
            self.logging.info(result)
            self.logging.info("Post update requirement update complete")

            with open(os.path.join(current_script_dir, "version.txt"), "w") as f:
                f.write(latest_release["tag_name"])

            if self.restart_callback is not None:
                await self.restart_callback()
        except Exception as e:
            self.logging.error(f"Failed to update: {e}\n{traceback.format_exc()}")
