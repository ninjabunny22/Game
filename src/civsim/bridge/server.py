"""WebSocket server that runs the sim on a fixed, controllable clock and pushes state to viewers."""

import asyncio
import logging

from websockets.asyncio.server import ServerConnection, broadcast, serve
from websockets.exceptions import ConnectionClosed

from ..simulation import Simulation
from . import protocol

log = logging.getLogger(__name__)

MIN_SPEED = 0.25
MAX_SPEED = 60.0


class SimServer:
    def __init__(self, sim: Simulation, host: str = "127.0.0.1", port: int = 8765,
                 tick_rate: float = 2.0, paused: bool = False):
        self.sim = sim
        self.host = host
        self.port = port
        self.speed = _clamp_speed(tick_rate)
        self.paused = paused
        self.clients: set[ServerConnection] = set()
        self.ready = asyncio.Event()  # set once the socket is listening
        self._wake = asyncio.Event()  # a command changed pause/speed/steps
        self._pending_steps = 0

    async def run(self) -> None:
        async with serve(self._handle_client, self.host, self.port) as server:
            self.port = server.sockets[0].getsockname()[1]
            log.info("listening on ws://%s:%d (seed %d, %.2f ticks/s%s)", self.host, self.port,
                     self.sim.config.seed, self.speed, ", paused" if self.paused else "")
            self.ready.set()
            await self._tick_loop()

    # -- clock ---------------------------------------------------------------

    async def _tick_loop(self) -> None:
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        while True:
            if self.paused:
                if self._pending_steps == 0:
                    await self._sleep(None)
                    next_tick = loop.time()
                    continue
                self._pending_steps -= 1
            else:
                delay = next_tick - loop.time()
                if delay > 0 and await self._sleep(delay):
                    # Woken by a command: re-evaluate, never waiting longer than one new interval.
                    next_tick = min(next_tick, loop.time() + 1 / self.speed)
                    continue

            self.sim.step()
            self._broadcast(protocol.tick_message(self.sim, self.paused, self.speed))
            # Keep a steady cadence, but don't try to catch up after a stall.
            next_tick = max(next_tick, loop.time() - 1 / self.speed) + 1 / self.speed
            await asyncio.sleep(0)

    async def _sleep(self, delay: float | None) -> bool:
        """Sleep until `delay` passes or a command arrives. True if woken by a command."""
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), delay)
            return True
        except TimeoutError:
            return False

    # -- clients -------------------------------------------------------------

    async def _handle_client(self, ws: ServerConnection) -> None:
        log.info("viewer connected: %s", ws.remote_address)
        try:
            await ws.send(protocol.init_message(self.sim))
            await ws.send(protocol.tick_message(self.sim, self.paused, self.speed))
            self.clients.add(ws)
            async for raw in ws:
                try:
                    action, value = protocol.parse_command(raw)
                except protocol.ProtocolError as exc:
                    await ws.send(protocol.error_message(self.sim, str(exc)))
                    continue
                self._apply_command(action, value)
        except ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)
            log.info("viewer disconnected: %s", ws.remote_address)

    def _apply_command(self, action: str, value: float | None) -> None:
        if action == "pause":
            self.paused = True
        elif action == "resume":
            self.paused = False
        elif action == "toggle_pause":
            self.paused = not self.paused
        elif action == "step":
            self.paused = True
            self._pending_steps += 1
        elif action == "set_speed":
            self.speed = _clamp_speed(value)
        if not self.paused:
            self._pending_steps = 0
        self._wake.set()
        self._broadcast(protocol.status_message(self.sim, self.paused, self.speed))

    def _broadcast(self, message: str) -> None:
        if self.clients:
            broadcast(self.clients, message)


def _clamp_speed(speed: float) -> float:
    return max(MIN_SPEED, min(MAX_SPEED, float(speed)))
