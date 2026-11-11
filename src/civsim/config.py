from dataclasses import dataclass


@dataclass
class SimConfig:
    seed: int = 0
    width: int = 96
    height: int = 96
    num_civs: int = 4
    end_tick: int = 8000  # the game is decided on score on this day, if nobody has won it before; 0 = never
    tick_rate: float = 2.0  # ticks per second when served over the bridge
    host: str = "127.0.0.1"
    port: int = 8765
