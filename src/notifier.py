"""Mercari Bargain Hunter - Telegram Notifier

Telegram token/chat_id are read from environment variables
(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) — never from config.yaml.
"""

import aiohttp
import os


class TelegramNotifier:
    """Send bargain alerts to Telegram via Bot API"""

    ENV_TOKEN = "TELEGRAM_BOT_TOKEN"
    ENV_CHAT_ID = "TELEGRAM_CHAT_ID"

    def __init__(self, config=None):
        self.bot_token = os.environ.get(self.ENV_TOKEN, "")
        self.chat_id = os.environ.get(self.ENV_CHAT_ID, "")

        # Log config status
        if self.bot_token:
            print(f"[Notifier] Bot Token: {self.bot_token[:10]}... (configured)")
        else:
            print("[Notifier] Bot Token: NOT SET")
        if self.chat_id:
            print(f"[Notifier] Chat ID: {self.chat_id} (configured)")
        else:
            print("[Notifier] Chat ID: NOT SET")

    async def send_alert(self, item, bargain_details):
        """Send a single bargain alert to Telegram as one photo+caption message.

        Uses sendPhoto with caption when image_url is available — image and
        text are delivered as ONE message. Falls back to sendMessage if no
        image or if sendPhoto fails (so notifications are never lost).
        """
        if not self.bot_token or not self.chat_id:
            print("[Notifier] No Telegram credentials configured")
            return False

        if isinstance(item, dict):
            item_name = item.get("name", "不明")
            item_price = item.get("price", 0)
            item_url = item.get("url", "")
            item_image_url = item.get("image_url", "")
        else:
            item_name = item.name
            item_price = item.price
            item_url = item.url
            item_image_url = getattr(item, "image_url", "")

        market_median = int(bargain_details.get("market_median", 0))
        diff_yen = bargain_details.get("difference_yen") or bargain_details.get("difference", 0)
        discount_pct = bargain_details.get("discount_percent", 0) or int((1 - bargain_details.get("ratio", 1)) * 100)

        item_name_html = item_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        caption = (
            f"{item_name_html}\n\n"
            f"💰 価格: <code>¥{item_price:,}</code>\n"
            f"📊 相場中央値: <code>¥{market_median:,}</code>\n"
            f"📉 差額: -¥{diff_yen:,} (<code>{discount_pct}%OFF</code>)\n\n"
            f'<a href="{item_url}">商品ページを開く</a>'
        )

        api_base = f"https://api.telegram.org/bot{self.bot_token}"

        # Try sendPhoto with caption first (one message)
        if item_image_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{api_base}/sendPhoto",
                        json={
                            "chat_id": self.chat_id,
                            "photo": item_image_url,
                            "caption": caption,
                            "parse_mode": "HTML",
                        },
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as response:
                        if response.status in (200, 204):
                            print(f"[Notifier] Alert sent for {item_name}")
                            return True
                        else:
                            err_text = await response.text()
                            print(f"[Notifier] sendPhoto failed: {response.status} - {err_text[:200]}")
            except Exception as e:
                print(f"[Notifier] sendPhoto error: {e}")

        # Fallback: send text only
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{api_base}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": caption,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status in (200, 204):
                        print(f"[Notifier] Alert sent (text fallback) for {item_name}")
                        return True
                    else:
                        err_text = await response.text()
                        print(f"[Notifier] sendMessage failed: {response.status} - {err_text[:200]}")
                        return False
        except Exception as e:
            print(f"[Notifier] Error sending Telegram message: {e}")
            return False

    async def _send_image_reply(self, image_url: str, reply_to_msg_id: int) -> None:
        """Send product image as a reply to the text message.

        Fire-and-forget — image failure does not affect the notification.
        """
        payload = {
            "chat_id": self.chat_id,
            "photo": image_url,
            "reply_to_message_id": reply_to_msg_id,
        }
        try:
            async with aiohttp.ClientSession() as session:
                api_url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
                async with session.post(
                    api_url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    pass  # silent — success or failure doesn't matter
        except Exception:
            pass

    async def send_bargain_alerts(self, bargain_details_list: list):
        """Send multiple bargain alerts to Telegram."""
        for detail in bargain_details_list:
            item = {
                "name": detail.get("item_name", "不明"),
                "price": detail.get("price", 0),
                "url": detail.get("item_url", ""),
                "image_url": detail.get("image_url", ""),
            }
            await self.send_alert(item, detail)

    def send_bargain_alerts_sync(self, bargain_details_list: list):
        """Synchronous wrapper for send_bargain_alerts."""
        import asyncio
        try:
            asyncio.run(self.send_bargain_alerts(bargain_details_list))
        except RuntimeError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(lambda: asyncio.run(self.send_bargain_alerts(bargain_details_list))).result()

    async def close(self):
        pass
