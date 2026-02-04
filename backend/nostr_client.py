import asyncio
import json
import websockets
from typing import Callable, Optional
import os

RELAY_URL = os.getenv("NOSTR_RELAY_URL", "ws://localhost:8080")


class NostrClient:
    def __init__(self, relay_url: str = RELAY_URL):
        self.relay_url = relay_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.subscriptions: dict[str, Callable] = {}
        self._lock = asyncio.Lock()

    def _is_connected(self) -> bool:
        if self.ws is None:
            return False
        try:
            return self.ws.state.name == "OPEN"
        except AttributeError:
            return False

    async def connect(self):
        async with self._lock:
            if not self._is_connected():
                self.ws = await websockets.connect(self.relay_url)

    async def close(self):
        if self.ws:
            await self.ws.close()

    async def publish_event(self, event: dict) -> bool:
        await self.connect()

        message = json.dumps(["EVENT", event])
        await self.ws.send(message)

        response = await self.ws.recv()
        data = json.loads(response)

        if data[0] == "OK":
            return data[2]
        return False

    async def subscribe(self, sub_id: str, filters: list[dict],
                       callback: Callable):
        await self.connect()

        self.subscriptions[sub_id] = callback
        message = json.dumps(["REQ", sub_id, *filters])
        await self.ws.send(message)

    async def fetch_events(self, filters: list[dict]) -> list[dict]:
        await self.connect()

        sub_id = f"fetch-{id(filters)}"
        message = json.dumps(["REQ", sub_id, *filters])
        await self.ws.send(message)

        events = []
        while True:
            response = await self.ws.recv()
            data = json.loads(response)

            if data[0] == "EVENT" and data[1] == sub_id:
                events.append(data[2])
            elif data[0] == "EOSE":
                break

        await self.ws.send(json.dumps(["CLOSE", sub_id]))
        return events

    async def listen(self):
        while True:
            try:
                if not self._is_connected():
                    await self.connect()

                message = await self.ws.recv()
                data = json.loads(message)

                if data[0] == "EVENT":
                    sub_id = data[1]
                    event = data[2]
                    if sub_id in self.subscriptions:
                        await self.subscriptions[sub_id](event)
            except websockets.ConnectionClosed:
                await asyncio.sleep(1)
                await self.connect()
            except Exception as e:
                print(f"Nostr listener error: {e}")
                await asyncio.sleep(1)
