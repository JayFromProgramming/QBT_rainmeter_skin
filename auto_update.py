import asyncio
# import logging
import json
import os
import traceback
import zipfile
import logging
import aiohttp

logging.getLogger(__name__).setLevel(logging.DEBUG)
import combined_log

installed_dir = os.path.dirname(os.path.realpath(__file__))


async def _get_installed_version():
    try:
        with open("version.txt") as version_file:
            return version_file.read().strip()
    except Exception as e:
        logging.error(f"Failed to get installed version: {e}")
        return "unknown"


def cleanup():
    # Look for the old_version.zip file and delete it and the recovery script
    if os.path.exists("old_version.zip"):
        os.remove("old_version.zip")
    if os.path.exists("recovery.sh"):
        os.remove("recovery.sh")


class GithubUpdater:

    def __init__(self, owner: str, repo: str, restart_callback=None, update_available_callback=None,
                 logging: combined_log.CombinedLogger = None):
        self.repo = repo
        self.owner = owner
        self.restart_callback = restart_callback
        self.on_update_available_callback = update_available_callback
        self.new_version_available = False
        self.logging = logging
        cleanup()

    async def _get_latest_release(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest") as resp:
                return await resp.json()

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

                self.logging.info(json.dumps(latest_release, indent=4))

                if "tag_name" not in latest_release:
                    self.logging.error("No latest release tag found")
                    await asyncio.sleep(5)
                    continue

                if latest_release["tag_name"] != await _get_installed_version():
                    logging.info(f"New version available: {latest_release['tag_name']}")
                    self.new_version_available = True
                    if self.on_update_available_callback is not None:
                        await self.on_update_available_callback()
                else:
                    self.new_version_available = False
            except Exception as e:
                self.logging.error(f"Failed to check for updates: {e}\n{traceback.format_exc()}")
            finally:
                await asyncio.sleep(60)

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

    async def preform_update(self):
        """Downloads new version and replaces current version"""
        if not self.new_version_available:
            logging.info("No new version available")
            return
        self.logging.info(f"Downloading new version: {self.repo}")
        release = await self._get_latest_release()
        # Download the zip file from github and extract it
        async with aiohttp.ClientSession() as session:
            req = await session.get(release["zipball_url"])
            with open("new_version.zip", "wb") as f:
                while True:
                    chunk = await req.content.read(1024)
                    if not chunk:
                        break
                    f.write(chunk)

        # Zip the current version as a backup
        with zipfile.ZipFile("old_version.zip", "w") as f:
            for root, dirs, files in os.walk(installed_dir):
                for file in files:  # Make we don't include the file we are currently writing to
                    if file == "old_version.zip":
                        continue
                    f.write(os.path.join(root, file))

        await self.make_recovery_shell_script()  # Create recovery script

        # Replace the current version with the new version
        self.logging.info("Extracting new version")
        with zipfile.ZipFile("new_version.zip", "r") as zip_ref:
            zip_ref.extractall()
        self.logging.info("New version extracted")
        # Replace the current version with the new version
        self.logging.info("New version installed")
        with open("version.txt", "w") as f:
            f.write(release["tag_name"])
        # Delete the zip file
        os.remove("new_version.zip")
        self.logging.info("New version zip file deleted")
        # Run PIP on requirements.txt
        self.logging.info("Installing new version requirements")
        os.system("pip install -r requirements.txt")
        self.logging.info("New version requirements installed")
        # Restart the server
        await self.restart_callback()
