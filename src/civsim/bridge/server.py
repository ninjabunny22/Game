"""WebSocket server that runs the sim on a fixed, controllable clock and pushes state to viewers.

Strategic check-ins are answered in the background: the sim keeps ticking while a
brain thinks, and each answer is applied on the tick
after it arrives."""

import asyncio
import logging
import random

from websockets.asyncio.server import ServerConnection, broadcast, serve
from websockets.exceptions import ConnectionClosed

from ..config import DIFFICULTIES, game_config
from ..simulation import Simulation
from ..strategy import Brain, CheckinRequest
from . import protocol

log = logging.getLogger(__name__)

MIN_SPEED = 0.25
MAX_SPEED = 60.0


class SimServer:
    def __init__(self, sim: Simulation, brain: Brain, host: str = "127.0.0.1", port: int = 8765,
                 tick_rate: float = 2.0, paused: bool = False, lobby: bool = False):
        self.sim = sim
        # In the lobby no game has been started: `sim` is a game playing itself behind the main
        # menu, replaced when the player starts one (new_game) and begun again when they leave it.
        self.lobby = lobby
        self.brain = brain
        self.host = host
        self.port = port
        self.speed = _clamp_speed(tick_rate)
        self.paused = paused
        self.clients: set[ServerConnection] = set()
        self.ready = asyncio.Event()  # set once the socket is listening
        self._wake = asyncio.Event()  # a command changed pause/speed/steps
        self._pending_steps = 0
        self._thinking: set[asyncio.Task] = set()
        self._waiting: list[int] = []  # civs whose late answer the clock is being held for

    async def run(self) -> None:
        async with serve(self._handle_client, self.host, self.port) as server:
            self.port = server.sockets[0].getsockname()[1]
            log.info("listening on ws://%s:%d (seed %d, %.2f ticks/s%s, strategy: %s)", self.host, self.port,
                     self.sim.config.seed, self.speed, ", paused" if self.paused else "", self.brain.name)
            self.ready.set()
            await self._tick_loop()

    # -- clock ---------------------------------------------------------------

    async def _tick_loop(self) -> None:
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        while True:
            # A civ must never miss a decision: if its next check-in is due and its last is still
            # unanswered, hold the clock (for everyone, so nobody acts against a frozen opponent).
            waiting = self.sim.waiting_for()
            if waiting != self._waiting:
                self._waiting = waiting
                self._broadcast(protocol.status_message(self.sim, self.paused, self.speed))
            if waiting:
                await asyncio.sleep(0.05)
                next_tick = loop.time()
                continue
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
            if self.sim.victory and self.sim.victory["tick"] == self.sim.tick:
                if self.lobby:
                    self._start(_backdrop(), lobby=True)  # the game behind the menu is over: another
                    continue
                self.paused = True  # the game is decided: stop for the moment; play can be resumed
            for request in self.sim.take_requests():
                self._answer(request)
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

    def _answer(self, request: CheckinRequest) -> None:
        """Answer a check-in on the spot; the sim applies the answer on its next tick."""
        reply = None
        try:
            reply = self.brain.decide(request)
        except Exception:
            log.exception("strategy brain failed on the check-in for civ %d", request.civ_id)
        self.sim.submit(request, reply)

    # -- clients -------------------------------------------------------------

    async def _handle_client(self, ws: ServerConnection) -> None:
        log.info("viewer connected: %s", ws.remote_address)
        try:
            await ws.send(protocol.init_message(self.sim, self.lobby))
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

    def _apply_command(self, action: str, value: float | dict | None) -> None:
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
        elif action == "new_game":
            value = value if isinstance(value, dict) else {}
            seed = value.get("seed")
            if isinstance(seed, bool) or not isinstance(seed, int):
                seed = random.SystemRandom().randrange(2**31)
            try:
                chosen = value.get("map")
                level = value.get("difficulty")
                sim = Simulation(game_config(value.get("size", "medium"), value.get("civs"), seed,
                                             chosen if isinstance(chosen, str) and chosen else None,
                                             difficulty=level if level in DIFFICULTIES else "normal"))
            except ValueError as exc:
                self._broadcast(protocol.error_message(self.sim, str(exc)))
                return
            # A game to be ruled starts paused, so the player can choose a civ before a day passes.
            self._start(sim, lobby=False, paused=value.get("mode") == "rule")
            return
        elif action == "end_game":
            self._start(_backdrop(), lobby=True)
            return
        elif action in protocol.RULER_COMMANDS:
            problem = self.sim.ruler.command(action, value)
            if problem:
                self._broadcast(protocol.error_message(self.sim, problem))
            # Show the order at once, even while the game is paused.
            self._broadcast(protocol.tick_message(self.sim, self.paused, self.speed))
            return
        if not self.paused:
            self._pending_steps = 0
        self._wake.set()
        self._broadcast(protocol.status_message(self.sim, self.paused, self.speed))

    def _start(self, sim: Simulation, lobby: bool, paused: bool = False) -> None:
        """Put a new game in place of the current one and show it to every viewer."""
        self.sim, self.lobby, self.paused = sim, lobby, paused
        self._pending_steps = 0
        self._waiting = []
        log.info("%s: %s, seed %d, %dx%d, %d civs", "back to the menu" if lobby else "new game",
                 sim.config.map_name or "a random map", sim.config.seed, sim.config.width, sim.config.height,
                 sim.config.num_civs)
        self._broadcast(protocol.init_message(sim, lobby))
        self._broadcast(protocol.tick_message(sim, self.paused, self.speed))
        self._wake.set()

    def _broadcast(self, message: str) -> None:
        if self.clients:
            broadcast(self.clients, message)


def _backdrop() -> Simulation:
    """A game to play itself behind the main menu."""
    return Simulation(game_config("medium", seed=random.SystemRandom().randrange(2**31)))


def _clamp_speed(speed: float) -> float:
    return max(MIN_SPEED, min(MAX_SPEED, float(speed)))
