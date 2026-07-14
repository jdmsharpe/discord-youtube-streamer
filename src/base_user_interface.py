import logging
from asyncio import Lock
from abc import ABC, abstractmethod

from discord import Bot, TextChannel, Guild, Embed
from discord.ui import View
from discord.errors import NotFound, HTTPException
from discord.ext import tasks

import config.logger


class UserInterface(ABC):
    def __init__(self):
        self.current_ui = None
        self.lock = Lock()

    @tasks.loop(seconds=2.5)
    async def _auto_refresh_ui(self) -> None:
        # tasks.loop stops permanently on an unhandled exception — one transient
        # HTTP error must not kill the refresher for the rest of the session
        try:
            await self.refresh_ui()
        except Exception as error:
            logging.error('Auto refresh failed: %s', error)

    def start_auto_refresh(self) -> None:
        if not self._auto_refresh_ui.is_running():
            self._auto_refresh_ui.start()

    def stop_auto_refresh(self) -> None:
        self._auto_refresh_ui.stop()

    def restart_auto_refresh(self) -> None:
        self._auto_refresh_ui.restart()

    async def new_ui(self, text_channel: TextChannel) -> None:
        self.start_auto_refresh()
        if text_channel is None:
            logging.warning('Invalid text channel, attempting refresh')
            await self.refresh_ui()
            return

        logging.info('Creating new UI')
        async with self.lock:
            view = await self.get_view()
            embed = await self.get_embed()

            if self.current_ui:
                try:
                    await self.current_ui.delete()
                except NotFound:
                    logging.warning('Previous UI message already deleted')
                except HTTPException as http_error:
                    logging.error('Unable to delete previous UI: %s', http_error)

            try:
                self.current_ui = await text_channel.send(embed=embed, view=view)
            except HTTPException as http_error:
                logging.error('Unable to create UI: %s', http_error)
                self.current_ui = None

    async def refresh_ui(self) -> None:
        if self.lock.locked():
            logging.debug('UI busy, skipping refresh')
            return

        async with self.lock:
            if self.current_ui is None:
                return

            view = await self.get_view()
            embed = await self.get_embed()

            try:
                await self.current_ui.edit(embed=embed, view=view)
            except NotFound:
                # Message deleted out from under us — drop the reference so the
                # auto-refresh loop stops editing a ghost every 2.5 seconds
                logging.warning('UI message deleted externally, dropping reference')
                self.current_ui = None

    async def delete_ui(self, bot: Bot, guild: Guild, ignore_msg_ids: set[int | None] | None = None) -> None:
        self.stop_auto_refresh()

        async with self.lock:
            # Only delete the current UI message, not all bot messages
            if self.current_ui is not None:
                try:
                    await self.current_ui.delete()
                    logging.info('Deleted current UI message')
                except NotFound:
                    logging.warning('Current UI message already deleted')
                except HTTPException as http_error:
                    logging.error('Error deleting current UI message: %s', http_error)

            self.current_ui = None

    @abstractmethod
    async def get_embed(self) -> Embed:
        pass

    @abstractmethod
    async def get_view(self) -> View:
        pass
