"""VK Group Long Poll — без vkbottle, чистый aiohttp."""
import asyncio
import logging
import aiohttp
from typing import AsyncIterator

from .api import VKAPI, VKMessage

logger = logging.getLogger(__name__)


class VKGroupLongPoll:
    def __init__(self, api: VKAPI, group_id: int):
        self.api = api
        self.group_id = group_id
        self._server: str = ""
        self._key: str = ""
        self._ts: str = ""

    async def _init_server(self) -> None:
        data = await self.api.call("groups.getLongPollServer", group_id=self.group_id)
        self._server = data["server"]
        self._key = data["key"]
        self._ts = str(data["ts"])
        logger.info(f"VK Long Poll initialized (group={self.group_id}, ts={self._ts})")

    async def listen(self) -> AsyncIterator[VKMessage]:
        await self._init_server()
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    url = (
                        f"{self._server}"
                        f"?act=a_check&key={self._key}&ts={self._ts}&wait=25"
                    )
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        data = await resp.json(content_type=None)

                    failed = data.get("failed")
                    if failed == 1:
                        self._ts = str(data["ts"])
                        continue
                    if failed in (2, 3):
                        await self._init_server()
                        continue

                    self._ts = str(data.get("ts", self._ts))

                    for update in data.get("updates", []):
                        if update.get("type") != "message_new":
                            continue
                        msg_data = update.get("object", {}).get("message", {})
                        # from_id > 0 — сообщение от пользователя (не от сообщества)
                        if msg_data.get("from_id", 0) > 0:
                            yield VKMessage(msg_data, self.api)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"VK LP error: {e}")
                    await asyncio.sleep(5)
