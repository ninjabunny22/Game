import argparse
import asyncio
import logging
import random

from .bridge import SimServer
from .config import SimConfig
from .economy.rules import RESOURCES
from .simulation import Simulation
from .strategy import LLMBrain, make_brain


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="civsim", description="Run the civilization simulation.")
    parser.add_argument("--seed", type=int, help="world seed (default: random)")
    parser.add_argument("--host", default=SimConfig.host)
    parser.add_argument("--port", type=int, default=SimConfig.port)
    parser.add_argument("--tick-rate", type=float, default=SimConfig.tick_rate, help="ticks per second")
    parser.add_argument("--paused", action="store_true", help="start paused; a viewer can resume or step")
    parser.add_argument("--headless", action="store_true", help="no server: run --ticks at full speed and report")
    parser.add_argument("--ticks", type=int, default=1000, help="ticks to run with --headless")
    parser.add_argument("--llm", default="ollama", metavar="PROVIDER",
                        help='who answers the strategic check-ins: "ollama" (default) or "rules" for the '
                             "built-in deterministic policy, which needs no model")
    parser.add_argument("--model", help="model name for the LLM provider (default: llama3.1:8b for ollama)")
    parser.add_argument("--llm-url", help="base URL of the LLM provider (default: http://localhost:11434 for ollama)")
    args = parser.parse_args(argv)

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    config = SimConfig(seed=seed, host=args.host, port=args.port, tick_rate=args.tick_rate)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    brain = make_brain(args.llm, args.model, args.llm_url)
    if isinstance(brain, LLMBrain) and hasattr(brain.client, "check"):
        problem = brain.client.check()
        if problem:
            logging.warning("%s. Civs will keep their previous stances until it answers; "
                            "use --llm rules to run without a model.", problem)

    sim = Simulation(config)
    if args.headless:
        # Check-ins are answered before the next tick, so the run waits on the model.
        for _ in range(args.ticks):
            sim.step_with(brain)
        print(summary(sim))
        return
    try:
        asyncio.run(SimServer(sim, brain, config.host, config.port, config.tick_rate, args.paused).run())
    except KeyboardInterrupt:
        pass


def summary(sim: Simulation) -> str:
    lines = [f"seed {sim.config.seed}, tick {sim.tick}"]
    for civ in sim.civs:
        era = sim.tech_tree.eras[sim.tech_tree.era_of(civ.known_techs)]
        stock = " ".join(f"{res}={civ.resources[res]:.0f}" for res in RESOURCES)
        built: dict[str, int] = {}
        for building in civ.buildings:
            built[building.type] = built.get(building.type, 0) + 1
        lines += [
            f"{civ.name} ({civ.personality.name}) - {era}",
            f"  pop {civ.population:.0f}/{sim.modifiers[civ.id].housing:.0f}  soldiers {civ.soldiers:.0f}  "
            f"territory {len(civ.territory)}  {stock}",
            f"  buildings: {', '.join(f'{n} {t}' for t, n in sorted(built.items())) or 'none'}",
            f"  techs ({len(civ.known_techs)}): {', '.join(sim.tech_tree.techs[t].name for t in civ.known_techs) or 'none'}",
            f"  stances: {', '.join(f'{sim.civs[o].name}={sim.diplomacy.intent(civ.id, o).stance.value}' for o in sim.diplomacy.others(civ.id))}",
        ]
    lines.append("recent history:")
    lines += [f"  {entry['tick']:5d}  {entry['text']}" for entry in sim.diplomacy.history[-15:]]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
