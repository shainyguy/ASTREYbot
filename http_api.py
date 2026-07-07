import asyncio
import logging
from aiohttp import web

import config
import database as db
import notifier

logger = logging.getLogger(__name__)


# ── Health ──

async def health(_request):
    return web.json_response({"ok": True})


# ── Subscribe ──

async def subscribe(request):
    data = await request.json()
    chat_id = data.get("chat_id")
    platform = data.get("platform", "telegram")
    order_id = data.get("order_id")
    email = data.get("email")

    if not chat_id or not order_id:
        return web.json_response({"error": "chat_id and order_id required"}, status=400)

    await db.add_subscription(int(chat_id), platform, int(order_id), email)
    logger.info(f"Subscribed {platform}:{chat_id} to order #{order_id}")
    return web.json_response({"ok": True})


# ── Unsubscribe ──

async def unsubscribe(request):
    data = await request.json()
    chat_id = data.get("chat_id")
    order_id = data.get("order_id")

    if not chat_id or not order_id:
        return web.json_response({"error": "chat_id and order_id required"}, status=400)

    await db.remove_subscription(int(chat_id), int(order_id))
    logger.info(f"Unsubscribed {chat_id} from order #{order_id}")
    return web.json_response({"ok": True})


# ── Subscribers for an order ──

async def subscribers(request):
    order_id = request.match_info.get("order_id")
    if not order_id:
        return web.json_response({"error": "order_id required"}, status=400)

    subs = await db.get_subscribers(int(order_id))
    return web.json_response(subs)


# ── All subscribers ──

async def all_subscribers(_request):
    subs = await db.get_all_subscribers()
    return web.json_response(subs)


# ── Send message to a chat ──

async def send_message(request):
    data = await request.json()
    chat_id = data.get("chat_id")
    platform = data.get("platform", "telegram")
    text = data.get("message")
    parse_mode = data.get("parse_mode", "Markdown")

    if not chat_id or not text:
        return web.json_response({"error": "chat_id and message required"}, status=400)

    if platform == "telegram":
        if not notifier._bot:
            return web.json_response({"error": "TG bot not initialized"}, status=500)
        try:
            await notifier._bot.send_message(int(chat_id), text, parse_mode=parse_mode)
            return web.json_response({"ok": True})
        except Exception as e:
            logger.error(f"TG send to {chat_id} failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    elif platform == "vk":
        if not notifier._vk_api:
            return web.json_response({"error": "VK API not initialized"}, status=500)
        try:
            text_plain = text.replace("*", "").replace("_", "").replace("`", "")
            await notifier._vk_api.send_message(int(chat_id), text_plain)
            return web.json_response({"ok": True})
        except Exception as e:
            logger.error(f"VK send to {chat_id} failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

    return web.json_response({"error": f"Unknown platform: {platform}"}, status=400)


# ── Auth middleware ──

@web.middleware
async def auth_middleware(request, handler):
    if request.path == "/health":
        return await handler(request)
    api_key = request.headers.get("X-Api-Key", "")
    if api_key != config.BOT_API_SECRET:
        return web.json_response({"error": "Unauthorized"}, status=401)
    return await handler(request)


# ── Runner ──

async def run_http_server():
    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get("/health", health)
    app.router.add_post("/api/bot/subscribe", subscribe)
    app.router.add_post("/api/bot/unsubscribe", unsubscribe)
    app.router.add_get("/api/bot/subscribers/{order_id}", subscribers)
    app.router.add_get("/api/bot/subscribers", all_subscribers)
    app.router.add_post("/api/bot/send", send_message)

    port = config.HTTP_PORT
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"HTTP API server started on port {port}")

    stop_event = asyncio.Event()
    await stop_event.wait()
