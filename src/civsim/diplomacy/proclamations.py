"""What a civ proclaims when it declares war: one line in its own voice, from the real reason
for the war (the strategist's motive, see strategy/utility.py) and the history between the two.

{target} is the civ attacked, {about} what the motive names (a region, a rich node, a resource,
an ally) and {us} the declarer. The line is picked from a few phrasings by the game's seeded
random stream, so a replay says the same.
"""

LINES = {
    "lost_lands": ["{target} shall be punished for taking our lands! {about} will be ours again.",
                   "{about} was ours, and {target} will give it back in blood.",
                   "We have not forgotten {about}. Today we take it back from {target}!"],
    "home": ["{target} sits in the hall of our fathers. We are coming home!",
             "Our old home groans under {target}'s rule. No longer!"],
    "resources": ["{about} is ours by right, and we will have it!",
                  "{target} hoards {about} while our forges stand cold. We will take it!",
                  "The riches of {about} belong to {us}. Let {target} try to keep them!"],
    "refused": ["{target} would not sell us {about}. Then we will take it!",
                "Our envoys begged {target} for {about} and were turned away. They will regret it."],
    "land_hunger": ["Our people have no room left. {target}'s fields will feed them!",
                    "{us} has outgrown its borders, and {target} stands in the way."],
    "gate": ["{target} holds {about}, a dagger at our throat. We will break it!",
             "Whoever holds {about} holds our door. It will not be {target}."],
    "grudge": ["{target} has wronged us for the last time!",
               "We remember every insult {target} has done us. Today they answer for them all."],
    "faithless": ["{target} broke faith with us. Let them answer for it!",
                  "Once we trusted {target}. Never again: to war!"],
    "betrayal": ["The alliance with {target} is ended. Its weakness is our opportunity.",
                 "Friendship with {target} has served its turn. Now we strike!"],
    "prize": ["{about} will fly our banner, and {target} cannot stop us!",
              "{target} holds {about}. It belongs to {us}."],
    "victory": ["One more push, and the land is ours! {target} is the last wall.",
                "With {about} the realm will be ours. {target} will not stand in the way."],
    "rival": ["There can be only one first among the realms, and it is not {target}!",
              "{target} grows too proud. We will bring it low before it brings us low."],
    "runaway": ["{target} would rule us all. Stand with us, or kneel to {target}!",
                "If no one stops {target}, no one will be left. We march!"],
    "ally": ["{about} does not fight alone. {target}, you face us both!",
             "An attack on {about} is an attack on {us}. To arms against {target}!"],
    "water": ["Our wells are dry and {target}'s run full. We will drink!",
              "{target} has water and will not share it. Then we take it!"],
    "sick": ["{target} is laid low by plague. The time to strike is now!"],
    "exposed": ["{target}'s armies are far away. Its gates stand open to us!",
                "{target} has just been beaten. We will finish what was started."],
    "busy": ["{target} is already at war. Let it fight on two fronts!"],
    "bully": ["{target} is small, and we are not. It will bow to {us}.",
              "{target} should have known its place. We will teach it."],
    "restless": ["Too long have our swords rested. {target} will feel them!",
                 "The long peace has made us soft. {target} will remind us what we are."],
    "weaker": ["{target} is weak, and the weak do not keep what they hold.",
               "{target} cannot stand against us. Forward!"],
}
DEFAULT = ["{us} declares war on {target}!"]
# Motives that say little on their own: a history between the two speaks louder.
PLAIN = {"weaker", "busy", "exposed", "bully", "restless", None}


def proclaim(declarer: str, target: str, motive: str | None, about: str | None, rng) -> str:
    """The line {declarer} proclaims as it declares war on {target}."""
    lines = LINES.get(motive or "", DEFAULT)
    if about is None:
        lines = [line for line in lines if "{about}" not in line] or DEFAULT
    return rng.choice(lines).format(target=target, about=about or "", us=declarer)
