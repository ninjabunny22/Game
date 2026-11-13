"""Plays variants of the strategist against the standard one, to find better numbers by play
rather than by guesswork.

    .venv/bin/python -m civsim.league --tweak PARITY=1.05 PREP_MIN=15      # is this variant better?
    .venv/bin/python -m civsim.league --evolve 6                           # try six mutations, keep what wins
    .venv/bin/python -m civsim.league --aim fun --evolve 10                # tune for good games instead

Two aims. **strength** (the default): in each game half the civs play the variant, and it
is kept if its civs outscore the others. **fun**: every civ plays the variant, and it is kept
if the games are better to watch (see `entertainment`): they run long enough without
dragging, there are wars, alliances and rallies, the lead changes hands, the prizes are
fought over and taken, someone comes close to winning, and the winner is not always in the
same place.

In each game half the civs (a different half each game) decide by the changed numbers and the
rest by the standard ones, on the chosen maps. A variant is judged by how its civs score
against the others in the same games, and by what it does to the games themselves: how many
wars there are, when the first comes and how long the game runs. Winning by making games dull
is not an improvement, so a variant that cuts wars sharply is refused however well it does.

Never more than six games to a comparison: more adds minutes, not information.
"""

import argparse
import json
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import fields

from .config import game_config
from .simulation import Simulation
from .strategy.utility import DEFAULT, Params, UtilityBrain

MAX_GAMES = 6
GAMES = (("small", 0), ("small", 1), ("medium", 0), ("medium", 1), ("large", 0), ("large", 1))
BETTER = 1.05  # a variant's civs must outscore the others by this much to be kept ...
DULLER = 0.7  # ... without cutting the number of wars below this share of what the standard gives
STEP = 0.15  # how far a mutation moves a number, as a share of its value
INTEGERS = {f.name for f in fields(Params) if f.type in (int, "int")}


class LeagueBrain:
    """Answers each civ's check-ins with the strategist assigned to it."""

    name = "league"

    def __init__(self, brains: dict[int, UtilityBrain]):
        self.brains = brains

    def decide(self, request):
        return self.brains[request.civ_id].decide(request)


def play(size: str, seed: int, tweaks: dict, game: int, ticks: int | None = None) -> dict:
    """One game in which every other civ (which ones depends on `game`) plays the variant."""
    config = game_config(size, seed=seed)
    sim = Simulation(config)
    variant, standard = UtilityBrain(**tweaks), UtilityBrain()
    challengers = {civ.id for civ in sim.civs if (civ.id + game) % 2 == 0}
    brain = LeagueBrain({civ.id: variant if civ.id in challengers else standard for civ in sim.civs})
    wars, first = 0, None
    for _ in range(ticks or config.end_tick):
        for event in sim.step_with(brain):
            if "declares war" in event.get("text", ""):
                wars += 1
                first = first or sim.tick
        if sim.victory:
            break
    scores = {civ.id: sim.score(civ) if civ.alive else 0 for civ in sim.civs}
    mean = lambda ids: sum(scores[i] for i in ids) / max(1, len(ids))  # noqa: E731
    others = set(scores) - challengers
    return {"size": size, "seed": seed, "variant": mean(challengers), "standard": mean(others),
            "won": bool(sim.victory) and sim.victory["civ"] in challengers,
            "wars": wars, "first_war": first, "ended": sim.tick}


FUN_BETTER = 1.03  # a variant's games must be this much better to watch to be kept


def watch(size: str, seed: int, tweaks: dict) -> dict:
    """One whole game with every civ playing the variant: what happened in it."""
    config = game_config(size, seed=seed)
    sim = Simulation(config)
    brain = UtilityBrain(**tweaks)
    world = sim.world
    prizes = [r for r in world.regions if "prize" in r.tags or r.strength > 1]
    counts = {"wars": 0, "alliances": 0, "rallies": 0}
    leaders, best = [], 0
    while not sim.victory and sim.tick < config.end_tick:
        for event in sim.step_with(brain):
            text = event.get("text", "")
            counts["wars"] += "declares war" in text
            counts["alliances"] += "form an alliance" in text
            counts["rallies"] += "calls a rally" in text
        if sim.tick % 100 == 0:
            lead = max(sim.civs, key=lambda c: (sim.points_held(c), c.id))
            if not leaders or leaders[-1] != lead.id:
                leaders.append(lead.id)
            best = max(best, sim.points_held(lead))
    need = sim.domination_target()[0]
    home = {}
    for civ in sim.civs:
        home[civ.id] = next((s for s, (h, _) in world.starts.items() if h == world.region_of[civ.capital.tile]), civ.id) \
            if civ.settlements else civ.id
    winner = sim.victory["civ"] if sim.victory else max(sim.civs, key=lambda c: (sim.score(c), -c.id)).id
    return {"size": size, "seed": seed, "map": world.map_id, "ended": sim.tick, "last_day": config.end_tick,
            **counts, "lead_changes": max(0, len(leaders) - 1),
            "prizes_taken": sum(1 for r in prizes if r.owner is not None) / max(1, len(prizes)),
            "closest": best / max(1, need), "winner_slot": f"{world.map_id}:{home.get(winner)}"}


def entertainment(game: dict) -> float:
    """How good a game was to watch, 0 to 1: the mean of six things, each 1 when it is as it
    should be."""
    share = game["ended"] / game["last_day"]
    length = 1.0 if 0.6 <= share <= 1.0 else max(0.0, share / 0.6) if share < 0.6 else 1.0
    per_k = 1000 / max(1, game["ended"])
    parts = [
        length,
        min(1.0, game["wars"] * per_k / 1.5),  # a war every seven hundred days or so
        min(1.0, (game["alliances"] + game["rallies"]) * per_k / 1.5),
        min(1.0, game["lead_changes"] / 3),
        min(1.0, game["prizes_taken"] / 0.7),
        min(1.0, game["closest"] / 0.8),  # somebody came near winning outright
    ]
    return sum(parts) / len(parts)


def compare_fun(tweaks: dict, games: int = MAX_GAMES) -> dict:
    """Every civ plays the variant: how good the games are to watch, game by game and as a
    whole (with a share for the winners not always coming from the same place)."""
    chosen = GAMES[:min(games, MAX_GAMES)]
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(watch, [g[0] for g in chosen], [g[1] for g in chosen], [tweaks] * len(chosen)))
    fun = sum(entertainment(r) for r in results) / len(results)
    variety = len({r["winner_slot"] for r in results}) / len(results)
    return {"tweaks": tweaks, "games": len(results), "fun": round(0.85 * fun + 0.15 * variety, 3),
            "wars": round(sum(r["wars"] for r in results) / len(results), 1),
            "length": round(sum(r["ended"] / r["last_day"] for r in results) / len(results), 2),
            "rallies": round(sum(r["rallies"] for r in results) / len(results), 1),
            "prizes": round(sum(r["prizes_taken"] for r in results) / len(results), 2)}


def compare(tweaks: dict, games: int = MAX_GAMES, ticks: int | None = None) -> dict:
    """Play the variant against the standard strategist and sum up how it did."""
    chosen = GAMES[:min(games, MAX_GAMES)]
    n = len(chosen)
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(play, [g[0] for g in chosen], [g[1] for g in chosen], [tweaks] * n, range(n),
                                [ticks] * n))
    variant, standard = sum(r["variant"] for r in results), sum(r["standard"] for r in results)
    firsts = [r["first_war"] for r in results if r["first_war"]]
    return {"tweaks": tweaks, "games": n, "advantage": round(variant / max(1.0, standard), 3),
            "wins": sum(r["won"] for r in results), "wars": round(sum(r["wars"] for r in results) / n, 1),
            "first_war": round(sum(firsts) / len(firsts)) if firsts else None,
            "length": round(sum(r["ended"] for r in results) / n)}


def mutate(base: dict, rng: random.Random, count: int = 3) -> dict:
    """`base` with a few of the strategist's numbers moved a little, up or down."""
    tweaks = dict(base)
    for name in rng.sample(sorted(f.name for f in fields(Params)), count):
        value = tweaks.get(name, getattr(DEFAULT, name)) * (1 + rng.choice((-STEP, STEP)))
        tweaks[name] = max(1, round(value)) if name in INTEGERS else round(value, 4)
    return tweaks


def evolve(rounds: int, seed: int = 0, games: int = MAX_GAMES, ticks: int | None = None, log=print,
           aim: str = "strength") -> dict:
    """Hill-climb: mutate the best set so far, keep the mutation if it does clearly better (by
    `aim`; with strength, only if the games also stay lively). Returns the changes kept."""
    rng = random.Random(seed)
    best: dict = {}
    if aim == "fun":
        standing = compare_fun({}, games)
        log(f"standard: fun {standing['fun']}, {standing['wars']} wars a game, {standing['rallies']} rallies, "
            f"{standing['length']:.0%} of the last day, prizes {standing['prizes']:.0%} taken")
        for round_no in range(1, rounds + 1):
            trial = mutate(best, rng)
            result = compare_fun(trial, games)
            changed = {k: v for k, v in trial.items() if best.get(k) != v}
            keep = result["fun"] >= FUN_BETTER * standing["fun"]
            log(f"round {round_no}: {changed} -> fun {result['fun']} ({result['wars']} wars, {result['rallies']} "
                f"rallies, {result['length']:.0%} long): {'kept' if keep else 'dropped'}")
            if keep:
                best, standing = trial, result
        return best
    baseline = compare({}, games, ticks)  # what games are like with nothing changed
    log(f"standard: {baseline['wars']} wars a game, first at day {baseline['first_war']}, {baseline['length']} days long")
    for round_no in range(1, rounds + 1):
        trial = mutate(best, rng)
        result = compare(trial, games, ticks)
        changed = {k: v for k, v in trial.items() if best.get(k) != v}
        keep = result["advantage"] >= BETTER and result["wars"] >= DULLER * baseline["wars"]
        log(f"round {round_no}: {changed} -> advantage {result['advantage']}, {result['wins']} wins, "
            f"{result['wars']} wars a game: {'kept' if keep else 'dropped'}")
        if keep:
            best = trial
    return best


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="civsim.league", description=__doc__.split("\n\n")[0])
    parser.add_argument("--tweak", nargs="*", default=[], metavar="NAME=VALUE",
                        help="numbers to change, by the names in strategy/utility.py Params")
    parser.add_argument("--evolve", type=int, default=0, metavar="ROUNDS", help="mutate and keep what wins")
    parser.add_argument("--games", type=int, default=MAX_GAMES, help=f"games per comparison (at most {MAX_GAMES})")
    parser.add_argument("--seed", type=int, default=0, help="which mutations --evolve tries")
    parser.add_argument("--aim", choices=("strength", "fun"), default="strength",
                        help="keep what wins (strength) or what makes better games to watch (fun)")
    args = parser.parse_args(argv)
    known = {f.name: f for f in fields(Params)}
    tweaks = {}
    for item in args.tweak:
        name, _, value = item.partition("=")
        if name not in known:
            parser.error(f"unknown number {name!r}; they are: {', '.join(sorted(known))}")
        tweaks[name] = int(float(value)) if name in INTEGERS else float(value)
    if args.evolve:
        best = evolve(args.evolve, args.seed, args.games, aim=args.aim)
        print("kept:", json.dumps(best, indent=2) if best else "nothing: the standard numbers stand")
    elif args.aim == "fun":
        print(json.dumps(compare_fun(tweaks, args.games), indent=2))
    else:
        print(json.dumps(compare(tweaks, args.games), indent=2))


if __name__ == "__main__":
    main()
