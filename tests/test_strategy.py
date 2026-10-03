import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from civsim.config import SimConfig
from civsim.diplomacy import Stance
from civsim.diplomacy.rules import MAX_RATE
from civsim.llm import LLMError, make_client
from civsim.llm.ollama import OllamaClient
from civsim.simulation import Simulation
from civsim.strategy import CHECKIN_INTERVAL, LLMBrain, RuleBrain, parse_stances, stance_context
from civsim.strategy import prompt
from civsim.strategy.checkin import CheckinRequest


class ScriptedClient:
    """Stands in for a language model: returns whatever reply it was given."""

    name = "scripted"

    def __init__(self, reply):
        self.reply = reply
        self.calls: list[tuple[str, str, dict]] = []

    def complete_json(self, system, user, schema):
        self.calls.append((system, user, schema))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply(user) if callable(self.reply) else self.reply


@pytest.fixture
def sim() -> Simulation:
    return Simulation(SimConfig(seed=3))


def entry(civ, stance, **fields):
    base = {"civ": civ, "stance": stance, "give": "none", "give_per_tick": 0, "want": "none",
            "want_per_tick": 0, "troop_commitment": 0}
    return {**base, **fields}


# -- validating replies ------------------------------------------------------

def test_well_formed_reply_becomes_intents(sim):
    civ = sim.civs[0]
    context = stance_context(sim, civ)
    a, b, c = (n["name"] for n in context["neighbors"])
    reply = {"reason": "  Trade with one,\nfight another.  ", "stances": [
        entry(a, "trade", give="wood", give_per_tick=0.8, want="ore", want_per_tick=0.4),
        entry(b.upper(), "aggression", troop_commitment=0.75),
        entry(c, "ally", give="food", give_per_tick=1, want="stone", want_per_tick=1),
    ]}
    intents, reason = parse_stances(reply, context, tick=7)
    ids = [n["id"] for n in context["neighbors"]]
    assert reason == "Trade with one, fight another."
    assert intents[ids[0]].stance is Stance.TRADE
    assert (intents[ids[0]].give, intents[ids[0]].give_rate, intents[ids[0]].want) == ("wood", 0.8, "ore")
    assert intents[ids[1]].stance is Stance.AGGRESSION and intents[ids[1]].commitment == 0.75
    assert intents[ids[2]].stance is Stance.ALLY and intents[ids[2]].give == "food"
    assert all(intent.tick == 7 for intent in intents.values())


@pytest.mark.parametrize("reply", [None, "war", [], {}, {"stances": "all of them"}, {"stances": [1, None, "x"]},
                                   {"stances": [{"civ": "Atlantis", "stance": "trade"}]},
                                   {"stances": [{"stance": "aggression"}]}])
def test_garbage_replies_change_nothing(sim, reply):
    intents, reason = parse_stances(reply, stance_context(sim, sim.civs[0]), tick=1)
    assert intents == {} and reason == ""


def test_out_of_range_values_are_clamped_and_gaps_filled(sim):
    civ = sim.civs[0]
    civ.resources.update(food=100, wood=240, stone=100, ore=0, gold=100)
    civ.capacity.update(wood=10, stone=10, ore=0)
    context = stance_context(sim, civ)
    a, b, c = (n["name"] for n in context["neighbors"])
    ids = [n["id"] for n in context["neighbors"]]
    reply = {"reason": 42, "stances": [
        entry(a, "trade", give="wood", give_per_tick=999, want="uranium", want_per_tick="lots"),
        entry(b, "WAR", troop_commitment=17),
        entry(c, "trade"),  # no offer at all
        entry(a, "aggression"),  # second entry for the same civ is ignored
    ]}
    intents, reason = parse_stances(reply, context, tick=1)
    assert reason == ""
    assert intents[ids[0]].stance is Stance.TRADE
    assert intents[ids[0]].give_rate == MAX_RATE and intents[ids[0]].want is None
    assert intents[ids[1]].stance is Stance.AGGRESSION and intents[ids[1]].commitment == 1.0
    # The empty trade falls back to "my fullest stockpile for what I lack".
    assert intents[ids[2]].give == "wood" and intents[ids[2]].want == "ore"
    assert "bogus" not in {i.stance.value for i in intents.values()}


def test_unknown_stance_means_ignore(sim):
    context = stance_context(sim, sim.civs[0])
    name, civ_id = context["neighbors"][0]["name"], context["neighbors"][0]["id"]
    intents, _ = parse_stances({"stances": [entry(name, "befriend")]}, context, tick=1)
    assert intents[civ_id].stance is Stance.IGNORE


# -- check-in scheduling -----------------------------------------------------

def test_each_civ_checks_in_once_per_interval_and_never_piles_up(sim):
    seen: dict[int, list[int]] = {civ.id: [] for civ in sim.civs}
    held = []
    for _ in range(3 * CHECKIN_INTERVAL):
        sim.step()
        for request in sim.take_requests():
            assert request.kind == "stance"
            seen[request.civ_id].append(request.tick)
            held.append(request)
    assert all(len(ticks) == 1 for ticks in seen.values()), "unanswered check-ins are not repeated"
    assert len({ticks[0] for ticks in seen.values()}) == len(sim.civs), "check-ins are staggered"
    assert all(civ.thinking for civ in sim.civs)

    for request in held:
        sim.submit(request, None)
    for _ in range(CHECKIN_INTERVAL):
        sim.step()
    assert len(sim.take_requests()) == len(sim.civs), "answering frees the civ for its next check-in"


def test_no_answer_keeps_previous_stances(sim):
    civ = sim.civs[0]
    context = stance_context(sim, civ)
    target = context["neighbors"][0]
    request = CheckinRequest(civ.id, sim.tick, "stance", context)
    sim.submit(request, {"reason": "x", "stances": [entry(target["name"], "aggression", troop_commitment=0.5)]})
    sim.step()
    assert sim.diplomacy.intent(civ.id, target["id"]).stance is Stance.AGGRESSION
    assert civ.last_reason == "x"

    sim.submit(request, None)
    sim.submit(request, {"stances": "nonsense"})
    sim.step()
    assert sim.diplomacy.intent(civ.id, target["id"]).stance is Stance.AGGRESSION


# -- brains ------------------------------------------------------------------

def test_llm_brain_sends_the_situation_and_returns_the_models_reply(sim):
    civ = sim.civs[0]
    request = CheckinRequest(civ.id, sim.tick, "stance", stance_context(sim, civ))
    client = ScriptedClient({"reason": "ok", "stances": []})
    assert LLMBrain(client).decide(request) == {"reason": "ok", "stances": []}

    system, user, schema = client.calls[0]
    assert civ.name in system and civ.personality.name not in ("",)
    for neighbor in request.context["neighbors"]:
        assert neighbor["name"] in system and neighbor["name"] in user
    assert '"weights"' not in user and '"id"' not in user, "internal fields are not shown to the model"
    assert schema == prompt.STANCE_SCHEMA
    assert json.loads(user[user.index("{"): user.rindex("}") + 1])["you"]["name"] == civ.name


def test_llm_brain_swallows_model_failures(sim):
    civ = sim.civs[0]
    request = CheckinRequest(civ.id, sim.tick, "stance", stance_context(sim, civ))
    assert LLMBrain(ScriptedClient(LLMError("down"))).decide(request) is None


def test_llm_driven_run_forms_a_deal_and_fights_a_war():
    """A scripted 'model' that always trades with everyone except one civ, which it attacks."""
    sim = Simulation(SimConfig(seed=3))
    villain = sim.civs[0].name

    def reply(user: str) -> dict:
        context = json.loads(user[user.index("{"): user.rindex("}") + 1])
        me = context["you"]["name"]
        if "neighbors" not in context:  # an invention check-in
            return {"name": f"{me} Steelmaking", "description": "", "materials": ["wood"],
                    "effects": [{"type": "military", "resource": "none", "amount": 0.2}]}
        stances = []
        for n in context["neighbors"]:
            if me == villain and n == context["neighbors"][0]:
                stances.append(entry(n["name"], "aggression", troop_commitment=1.0))
            else:
                give, want = ("food", "wood") if me < n["name"] else ("wood", "food")  # so offers complement
                stances.append(entry(n["name"], "trade", give=give, give_per_tick=0.5, want=want, want_per_tick=0.5))
        return {"reason": f"{me} decides.", "stances": stances}

    brain = LLMBrain(ScriptedClient(reply))
    kinds: dict[str, int] = {}
    for _ in range(1500):
        for event in sim.step_with(brain):
            kinds[event["kind"]] = kinds.get(event["kind"], 0) + 1
    assert kinds.get("trade", 0) > 0
    assert kinds.get("war", 0) > 0, "the aggressor's border reached its target and war was declared"
    assert sim.civs[0].last_reason == f"{villain} decides."
    owned = [tile for civ in sim.civs for tile in civ.territory]
    assert len(owned) == len(set(owned))


def test_rule_brain_runs_are_deterministic_and_active():
    def run() -> tuple[list[dict], list[int]]:
        sim = Simulation(SimConfig(seed=5))
        brain = RuleBrain()
        for _ in range(800):
            sim.step_with(brain)
        return sim.diplomacy.history, [len(civ.territory) for civ in sim.civs]

    first, second = run(), run()
    assert first == second
    assert any("trades" in entry["text"] for entry in first[0])


# -- Ollama client -----------------------------------------------------------

@pytest.fixture
def fake_ollama():
    """A local HTTP server that answers like Ollama's /api/chat and /api/tags."""
    state = {"content": '{"reason": "hi", "stances": []}', "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state["requests"].append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self._send({"message": {"role": "assistant", "content": state["content"]}})

        def do_GET(self):
            self._send({"models": [{"name": "llama3.1:8b"}]})

        def _send(self, payload):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()
    server.server_close()


def test_ollama_client_round_trip(fake_ollama):
    client = make_client("ollama", base_url=fake_ollama["url"])
    assert isinstance(client, OllamaClient) and client.model == "llama3.1:8b"
    assert client.check() is None
    assert client.complete_json("sys", "usr", {"type": "object"}) == {"reason": "hi", "stances": []}
    sent = fake_ollama["requests"][0]
    assert sent["model"] == "llama3.1:8b" and sent["format"] == {"type": "object"} and sent["stream"] is False
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]


@pytest.mark.parametrize("content", ["not json at all", "[1, 2, 3]", ""])
def test_ollama_client_rejects_non_object_replies(fake_ollama, content):
    fake_ollama["content"] = content
    with pytest.raises(LLMError):
        OllamaClient(base_url=fake_ollama["url"]).complete_json("s", "u", {})


def test_ollama_client_reports_unreachable_server_and_missing_model(fake_ollama):
    dead = OllamaClient(base_url="http://127.0.0.1:9", timeout=2)
    assert "cannot reach" in dead.check()
    with pytest.raises(LLMError):
        dead.complete_json("s", "u", {})
    assert "ollama pull" in OllamaClient(model="nope:1b", base_url=fake_ollama["url"]).check()


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        make_client("telepathy")
