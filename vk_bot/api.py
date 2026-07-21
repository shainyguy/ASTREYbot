"""VK API client + VKMessage — без vkbottle, только aiohttp."""
import json
import random
import logging
import aiohttp
from dataclasses import dataclass, field
from typing import List, Optional, Any

logger = logging.getLogger(__name__)
VK_API_BASE = "https://api.vk.com/method"
VK_API_VERSION = "5.199"


@dataclass
class UserInfo:
    first_name: str = ""
    last_name: str = ""


class UsersAPI:
    def __init__(self, api: "VKAPI"):
        self._api = api

    async def get(self, user_ids: List[int]) -> List[UserInfo]:
        try:
            result = await self._api.call(
                "users.get", user_ids=",".join(str(i) for i in user_ids)
            )
            return [UserInfo(u.get("first_name", ""), u.get("last_name", ""))
                    for u in (result or [])]
        except Exception as e:
            logger.warning(f"users.get error: {e}")
            return []


class CtxAPI:
    def __init__(self, api: "VKAPI"):
        self.users = UsersAPI(api)


class VKAPI:
    def __init__(self, token: str):
        self.token = token

    async def call(self, method: str, **params) -> Any:
        params["access_token"] = self.token
        params["v"] = VK_API_VERSION
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{VK_API_BASE}/{method}", data=params,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json(content_type=None)
        if "error" in data:
            e = data["error"]
            raise RuntimeError(f"VK [{e.get('error_code')}]: {e.get('error_msg')}")
        return data.get("response", {})

    async def send_message(self, peer_id: int, text: str, keyboard: str = None) -> None:
        params = {
            "peer_id": peer_id,
            "message": text[:4096],
            "random_id": random.randint(1, 2 ** 31),
        }
        if keyboard:
            params["keyboard"] = keyboard
        await self.call("messages.send", **params)

    async def send_photo(self, peer_id: int, image_bytes: bytes,
                         text: str = "", keyboard: str = None) -> None:
        """Отправляет картинку в ВК.

        VK не принимает файл напрямую в messages.send — сначала картинку
        нужно залить на их сервер и получить attachment-идентификатор.
        """
        upload = await self.call("photos.getMessagesUploadServer", peer_id=peer_id)
        upload_url = upload.get("upload_url")
        if not upload_url:
            raise RuntimeError("VK не выдал upload_url для картинки")

        form = aiohttp.FormData()
        form.add_field("photo", image_bytes, filename="mockup.jpg",
                       content_type="image/jpeg")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                upload_url, data=form,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                uploaded = await resp.json(content_type=None)

        saved = await self.call(
            "photos.saveMessagesPhoto",
            photo=uploaded.get("photo"),
            server=uploaded.get("server"),
            hash=uploaded.get("hash"),
        )
        if not saved:
            raise RuntimeError("VK не сохранил картинку")

        photo = saved[0] if isinstance(saved, list) else saved
        attachment = f"photo{photo['owner_id']}_{photo['id']}"

        params = {
            "peer_id": peer_id,
            "message": text[:4096],
            "attachment": attachment,
            "random_id": random.randint(1, 2 ** 31),
        }
        if keyboard:
            params["keyboard"] = keyboard
        await self.call("messages.send", **params)

    async def resolve_group_id(self, screen_name: str) -> Optional[int]:
        try:
            result = await self.call("utils.resolveScreenName", screen_name=screen_name)
            if result and result.get("type") == "group":
                return int(result["object_id"])
        except Exception as e:
            logger.error(f"resolveScreenName error: {e}")
        return None


class VKMessage:
    """Совместим с интерфейсом vkbottle Message — drop-in замена."""

    def __init__(self, data: dict, api: VKAPI):
        self.from_id: int = data.get("from_id", 0)
        self.peer_id: int = data.get("peer_id", 0)
        self.text: str = data.get("text", "")
        self._payload_raw = data.get("payload")
        self._api = api

    @property
    def payload(self):
        if self._payload_raw is None:
            return None
        if isinstance(self._payload_raw, dict):
            return self._payload_raw
        try:
            return json.loads(self._payload_raw)
        except Exception:
            return None

    @property
    def ctx_api(self) -> CtxAPI:
        return CtxAPI(self._api)

    async def answer(self, message: str = "", keyboard: str = None) -> None:
        await self._api.send_message(self.peer_id, message, keyboard)
