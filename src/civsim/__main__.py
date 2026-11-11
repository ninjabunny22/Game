import argparse
import asyncio
import logging
import random

from .bridge import SimServer
from .config import MAP_SIZES, MAX_CIVS, SimConfig, game_config
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
    parser.add_argument("--llm", default="utility", metavar="PROVIDER",
                        help='who answers the strategic check-ins: "utility" (default), the built-in '
                             'strategist, which needs no model; "rules" for the simple policy the tests '
                             'use; or "ollama" to ask a local language model')
    parser.add_argument("--size", choices=list(MAP_SIZES), help="map size (default: medium); "
                        "small is 64x64, medium 96x96, large 128x128")
    parser.add_argument("--civs", type=int, help=f"number of civs, 2 to {MAX_CIVS} depending on the map "
                        "(default: what suits the map)")
    parser.add_argument("--rule", type=int, metavar="CIV", help="start with this civ (0, 1, ...) in the player's "
                        "hands; any civ can also be taken up or handed back from the viewer")
    parser.add_argument("--model", help="model name for the LLM provider (default: llama3.1:8b for ollama)")
    parser.add_argument("--llm-url", help="base URL of the LLM provider (default: http://localhost:11434 for ollama)")
    args = parser.parse_args(argv)

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    try:
        config = game_config(args.size or "medium", args.civs, seed,
                             host=args.host, port=args.port, tick_rate=args.tick_rate)
    except ValueError as exc:
        parser.error(str(exc))
    # With nothing said about the game, the viewer opens on its main menu and the game is
    # chosen there; a game playing itself is shown behind it meanwhile.
    lobby = not args.headless and all(option is None for option in (args.seed, args.rule, args.size, args.civs))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    brain = make_brain(args.llm, args.model, args.llm_url)
    if isinstance(brain, LLMBrain) and hasattr(brain.client, "check"):
        problem = brain.client.check()
        if problem:
            logging.warning("%s. Civs will keep their previous stances until it answers; "
                            "use --llm rules to run without a model.", problem)

    sim = Simulation(config)
    if args.rule is not None:
        problem = sim.ruler.command("take_control", {"civ": args.rule})
        if problem:
            parser.error(f"--rule {args.rule}: {problem}")
    if args.headless:
        # Check-ins are answered before the next tick, so the run waits on the model.
        for _ in range(args.ticks):
            sim.step_with(brain)
        print(summary(sim))
        return
    try:
        asyncio.run(SimServer(sim, brain, config.host, config.port, config.tick_rate, args.paused, lobby).run())
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
