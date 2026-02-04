import asyncio
import json
import websockets
from typing import Callable, Optional
import os

RELAY_URL = os.getenv("NOSTR_RELAY_URL", "ws://localhost:8080")


class NostrClient:
    """
    Nostr relay client with proper concurrency handling.
    Uses a single receiver loop and queues for responses.
    """

    def __init__(self, relay_url: str = RELAY_URL):
        self.relay_url = relay_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.subscriptions: dict[str, Callable] = {}
        self._connect_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._pending_publishes: dict[str, asyncio.Future] = {}
        self._receiver_task: Optional[asyncio.Task] = None
        self._running = False

    def _is_connected(self) -> bool:
        if self.ws is None:
            return False
        try:
            return self.ws.state.name == "OPEN"
        except AttributeError:
            return False

    async def connect(self):
        async with self._connect_lock:
            if not self._is_connected():
                self.ws = await websockets.connect(self.relay_url)
                self._running = True
                # Start receiver loop if not already running
                if self._receiver_task is None or self._receiver_task.done():
                    self._receiver_task = asyncio.create_task(self._receiver_loop())

    async def close(self):
        self._running = False
        if self._receiver_task:
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            await self.ws.close()

    async def _receiver_loop(self):
        """Single receiver loop that handles all incoming messages."""
        while self._running:
            try:
                if not self._is_connected():
                    await asyncio.sleep(1)
                    continue

                message = await self.ws.recv()
                data = json.loads(message)

                msg_type = data[0]

                if msg_type == "EVENT":
                    # Subscription event
                    sub_id = data[1]
                    event = data[2]
                    if sub_id in self.subscriptions:
                        try:
                            await self.subscriptions[sub_id](event)
                        except Exception as e:
                            print(f"Subscription callback error: {e}")

                elif msg_type == "OK":
                    # Publish response
                    event_id = data[1]
                    success = data[2]
                    if event_id in self._pending_publishes:
                        self._pending_publishes[event_id].set_result(success)

                elif msg_type == "EOSE":
                    # End of stored events - handled by fetch_events
                    pass

                elif msg_type == "NOTICE":
                    print(f"Relay notice: {data[1]}")

            except websockets.ConnectionClosed:
                print("WebSocket connection closed, reconnecting...")
                await asyncio.sleep(1)
                try:
                    await self.connect()
                except Exception as e:
                    print(f"Reconnection failed: {e}")

            except asyncio.CancelledError:
                break

            except Exception as e:
                print(f"Receiver error: {e}")
                await asyncio.sleep(0.1)

    async def publish_event(self, event: dict, timeout: float = 5.0) -> bool:
        """Publish an event and wait for OK response."""
        await self.connect()

        event_id = event.get("id")
        if not event_id:
            return False

        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self._pending_publishes[event_id] = future

        try:
            async with self._send_lock:
                message = json.dumps(["EVENT", event])
                await self.ws.send(message)

            # Wait for OK response
            success = await asyncio.wait_for(future, timeout=timeout)
            return success

        except asyncio.TimeoutError:
            print(f"Publish timeout for event {event_id[:8]}...")
            return False

        except Exception as e:
            print(f"Publish error: {e}")
            return False

        finally:
            self._pending_publishes.pop(event_id, None)

    async def subscribe(self, sub_id: str, filters: list[dict], callback: Callable):
        """Subscribe to events matching filters."""
        await self.connect()

        self.subscriptions[sub_id] = callback

        async with self._send_lock:
            message = json.dumps(["REQ", sub_id, *filters])
            await self.ws.send(message)

    async def unsubscribe(self, sub_id: str):
        """Close a subscription."""
        if sub_id in self.subscriptions:
            del self.subscriptions[sub_id]

        if self._is_connected():
            async with self._send_lock:
                await self.ws.send(json.dumps(["CLOSE", sub_id]))
