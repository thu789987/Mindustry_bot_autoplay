"""Dict-based Vietnamese command -> structured build command.

Deliberately not an LLM: for a fixed, small vocabulary of building names a
lookup table is faster, free, and 100% deterministic. Swap in an LM Studio
call later only if commands need to support more flexible phrasing (see
NEXT_STEPS.md).
"""

# phrase (lowercase) -> building name in simulator.buildings.CATALOG
BUILDING_PHRASES = {
    "nhà máy silicon": "silicon-smelter",
    "máy nén silicon": "silicon-smelter",
    "silicon": "silicon-smelter",
    "nhà máy graphite": "graphite-press",
    "máy ép than": "graphite-press",
    "graphite": "graphite-press",
    "máy khoan": "mechanical-drill",
    "drill": "mechanical-drill",
}

# ore keyword (lowercase) -> item name in simulator.buildings.ITEMS,
# only relevant when the target building is a drill
ORE_PHRASES = {
    "than": "coal",
    "đồng": "copper",
    "cát": "sand",
}


def parse_command(text: str) -> dict:
    normalized = text.lower().strip()

    building = None
    for phrase in sorted(BUILDING_PHRASES, key=len, reverse=True):
        if phrase in normalized:
            building = BUILDING_PHRASES[phrase]
            break

    if building is None:
        return {"action": "unknown", "raw": text}

    command = {"action": "build", "building": building}

    if building == "mechanical-drill":
        for phrase in sorted(ORE_PHRASES, key=len, reverse=True):
            if phrase in normalized:
                command["ore_target"] = ORE_PHRASES[phrase]
                break

    return command
