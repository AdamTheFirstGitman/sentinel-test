"""Anonymous, read-only Twitch chat source over IRC WebSocket.

Connects as justinfan<digits> (no credentials), requests tags, joins one channel,
feeds every PRIVMSG into the pipeline. Nothing is ever sent except the IRC
handshake and PONGs.
"""

import asyncio
import random
from typing import Any

import websockets

from app.pipeline import Hub

IRC_URL = "wss://irc-ws.chat.twitch.tv:443"

_TAG_UNESCAPE = {"\\s": " ", "\\:": ";", "\\\\": "\\", "\\r": "\r", "\\n": "\n"}


def _unescape_tag(value: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(value):
        pair = value[i:i + 2]
        if pair in _TAG_UNESCAPE:
            out.append(_TAG_UNESCAPE[pair])
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def parse_privmsg(line: str) -> dict[str, Any] | None:
    """Parse one IRC line; return {author, text} for PRIVMSG, else None."""
    tags: dict[str, str] = {}
    rest = line
    if rest.startswith("@"):
        raw_tags, _, rest = rest[1:].partition(" ")
        for kv in raw_tags.split(";"):
            key, _, value = kv.partition("=")
            tags[key] = _unescape_tag(value)
    if not rest.startswith(":") or " PRIVMSG " not in rest:
        return None
    prefix, _, after = rest[1:].partition(" PRIVMSG ")
    _channel, _, text = after.partition(" :")
    name = tags.get("display-name") or prefix.split("!", 1)[0]
    badges = [b for b in tags.get("badges", "").split(",") if b]
    return {
        "author": {
            "name": name,
            "is_new_to_stream": tags.get("first-msg") == "1",
            "badges": badges,
        },
        "text": text.rstrip("\r\n"),
    }


class TwitchSource:
    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.channel: str | None = None
        self.status = "disconnected"
        self._task: asyncio.Task[None] | None = None

    async def join(self, channel: str) -> None:
        await self.part()
        self.channel = channel.strip().lstrip("#").lower()
        self._task = asyncio.create_task(self._run())

    async def part(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.channel = None
        self._set_status("disconnected")

    def _set_status(self, status: str) -> None:
        self.status = status
        self.hub.broadcast({"type": "twitch", "status": status, "channel": self.channel})

    async def _run(self) -> None:
        while self.channel:
            try:
                self._set_status("connecting")
                async with websockets.connect(IRC_URL) as ws:
                    nick = f"justinfan{random.randint(10000, 99999)}"
                    await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
                    await ws.send(f"NICK {nick}")
                    await ws.send(f"JOIN #{self.channel}")
                    self._set_status("connected")
                    async for frame in ws:
                        for line in str(frame).split("\r\n"):
                            if not line:
                                continue
                            if line.startswith("PING"):
                                await ws.send(line.replace("PING", "PONG", 1))
                            elif " RECONNECT" in line and "PRIVMSG" not in line:
                                raise ConnectionResetError("server asked to reconnect")
                            else:
                                msg = parse_privmsg(line)
                                if msg is not None:
                                    self.hub.sentinels["twitch"].submit(msg["author"], msg["text"])
            except asyncio.CancelledError:
                raise
            except Exception:
                self._set_status("reconnecting")
                await asyncio.sleep(3)
