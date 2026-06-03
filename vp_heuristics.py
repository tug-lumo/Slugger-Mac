"""
VP (Virtual Production) recommendation engine.

Two layers:
  1. Rule-based heuristics using the "3 D's" framework:
       - Doesn't Exist  → Lumostage / VFX
       - Dangerous       → Lumostage / VFX
       - Difficult/Distant (far from Lower Mainland BC) → Lumostage if INT. or
         contained EXT.; On Location if the scene needs real environment/crowds
  2. Learned rules — built up from user-edited breakdowns over time.

Learned rules are stored in data/vp_rules.json and persist across sessions.
"""

import json
import re
import sys
from pathlib import Path


def _rules_file() -> Path:
    if getattr(sys, 'frozen', False):
        user_data = Path.home() / "Library" / "Application Support" / "Slugger" / "data"
        user_data.mkdir(parents=True, exist_ok=True)
        user_rules = user_data / "vp_rules.json"
        if not user_rules.exists():
            bundled = Path(sys._MEIPASS) / "data" / "vp_rules.json"
            if bundled.exists():
                import shutil
                shutil.copy(bundled, user_rules)
        return user_rules
    return Path(__file__).parent / "data" / "vp_rules.json"


_RULES_FILE = _rules_file()

# ── Recommendation labels ────────────────────────────────────────────────────
R_VPROD         = "VPROD"
R_INT_CAR       = "INT. CAR"
R_INT_PLANE     = "INT. PLANE"
R_HYBRID_VIRTUAL = "HYBRID VIRTUAL"
R_SUBWAY_TRAIN  = "INT. SUBWAY TRAIN"
R_PLATFORM      = "INT. PLATFORM"
R_ROOFTOP       = "EXT. ROOFTOP"
R_DESERT        = "EXT. DESERT"
R_EITHER        = "EITHER"
R_LOCATION      = "LOCATION"
R_STUDIO        = "STUDIO"
R_VFX           = "VFX"
R_OMITTED       = "OMITTED"

# Legacy aliases (kept for any code that still references the old names)
R_LUMOSTAGE   = R_VPROD
R_VP_VEHICLE  = R_INT_CAR
R_VP_AIRCRAFT = R_INT_PLANE
R_SET_BUILD   = R_HYBRID_VIRTUAL
R_ON_LOCATION = R_LOCATION

ALL_OPTIONS = [
    R_VPROD,
    R_INT_CAR,
    R_INT_PLANE,
    R_HYBRID_VIRTUAL,
    R_SUBWAY_TRAIN,
    R_PLATFORM,
    R_ROOFTOP,
    R_DESERT,
    R_EITHER,
    R_LOCATION,
    R_STUDIO,
    R_VFX,
    R_OMITTED,
]

# ── Keyword banks ─────────────────────────────────────────────────────────────

_INT_VEHICLE = {
    "CAR", "VEHICLE", "TRUCK", "VAN", "BUS", "LIMO", "LIMOUSINE",
    "TAXI", "CAB", "RIDESHARE", "UBER", "JEEP", "SUV", "SEDAN",
    "PICKUP", "AMBULANCE", "POLICE CAR", "SQUAD CAR", "PATROL CAR",
    "FIRE TRUCK", "MOTORCYCLE", "MOTORBIKE", "MOPED", "GOLF CART",
    "MOVING CAR", "MOVING TRUCK", "BACK SEAT", "FRONT SEAT",
    "DRIVER SEAT", "PASSENGER SEAT", "CONVERTIBLE", "STATION WAGON",
    "HEARSE", "TRACTOR", "FORKLIFT", "SNOW PLOW", "ICE CREAM TRUCK",
    "SCHOOL BUS", "PARTY BUS", "RV", "CAMPER", "MOTORHOME",
    "GETAWAY CAR", "RACE CAR", "STUNT CAR",
}

# Subway / rail interiors → INT. SUBWAY TRAIN
_SUBWAY_KW = {
    "SUBWAY", "SUBWAY CAR", "SUBWAY TRAIN", "SUBWAY INTERIOR",
    "METRO", "METRO CAR", "UNDERGROUND TRAIN",
    "TRAIN CAR", "RAIL CAR", "DINING CAR", "SLEEPER CAR",
}

# Transit platforms → INT. PLATFORM
_PLATFORM_KW = {
    "PLATFORM", "SUBWAY PLATFORM", "TRAIN PLATFORM",
    "METRO PLATFORM", "TRANSIT PLATFORM", "BUS PLATFORM",
}

# Aircraft / vessels → INT. PLANE
_INT_AIRCRAFT = {
    "AIRPLANE", "PLANE", "JET", "AIRCRAFT", "COCKPIT",
    "HELICOPTER", "CHOPPER", "PRIVATE JET", "CARGO PLANE",
    "MILITARY PLANE", "FIGHTER JET",
    "BOAT", "SPEEDBOAT", "YACHT", "FERRY", "CRUISE SHIP", "SHIP",
    "SUBMARINE", "GONDOLA", "CABLE CAR",
}

# EXT. Rooftop → EXT. ROOFTOP
_ROOFTOP_KW = {
    "ROOFTOP", "ROOF TOP", "ROOF TERRACE", "ROOFTOP TERRACE",
    "PENTHOUSE TERRACE", "BUILDING ROOFTOP",
}

# EXT. Desert → EXT. DESERT (checked before distant-landscape pass)
_DESERT_KW = {
    "DESERT", "SAHARA", "MOJAVE", "SONORAN", "ARABIAN DESERT",
    "BADLANDS", "CANYON", "GRAND CANYON", "MESA", "SCRUBLAND",
}

# ── "DOESN'T EXIST" ───────────────────────────────────────────────────────────
_DOESNT_EXIST = {
    "SPACE", "OUTER SPACE", "SPACESHIP", "SPACECRAFT", "SPACE STATION",
    "ALIEN PLANET", "ALIEN SHIP", "ALIEN WORLD", "MOTHERSHIP",
    "WORMHOLE", "BLACK HOLE", "NEBULA",
    "DIGITAL WORLD", "CYBERSPACE", "VIRTUAL REALITY", "VR WORLD",
    "INSIDE COMPUTER", "THE MATRIX",
    "FANTASY KINGDOM", "ENCHANTED FOREST", "MAGICAL REALM", "DRAGON",
    "CASTLE GREAT HALL", "DUNGEON", "THRONE ROOM",
    "MEDIEVAL", "ANCIENT ROME", "ANCIENT EGYPT", "ROMAN FORUM",
    "VICTORIAN LONDON", "WILD WEST", "OLD WEST", "FRONTIER TOWN",
    "CIVIL WAR BATTLEFIELD", "WWI TRENCH", "WWII BUNKER",
    "PROHIBITION ERA",
}

# ── "DANGEROUS" ───────────────────────────────────────────────────────────────
_DANGEROUS = {
    "CLIFF EDGE", "CLIFF TOP", "CLIFF FACE",
    "ROOFTOP EDGE", "HIGH RISE EXTERIOR", "BUILDING LEDGE",
    "ACTIVE VOLCANO", "LAVA FIELD",
    "AVALANCHE", "MUDSLIDE", "ROCKSLIDE",
    "TORNADO", "HURRICANE", "BLIZZARD", "SANDSTORM",
    "BURNING BUILDING", "BUILDING ON FIRE",
    "COMBAT ZONE", "WAR ZONE", "ACTIVE BATTLEFIELD",
    "MINEFIELD",
    "DEEP WATER EXTERIOR", "OCEAN STORM",
    "EXPLOSION SITE", "CHEMICAL PLANT EXPLOSION",
}

# ── "DIFFICULT/DISTANT" ───────────────────────────────────────────────────────
_DISTANT_CITIES = {
    "NEW YORK", "NYC", "MANHATTAN", "BROOKLYN", "THE BRONX", "QUEENS",
    "TIMES SQUARE", "WALL STREET", "CENTRAL PARK", "PENN STATION",
    "GRAND CENTRAL", "BROOKLYN BRIDGE",
    "LOS ANGELES", "L.A.", "HOLLYWOOD", "BEVERLY HILLS", "DOWNTOWN LA",
    "CHICAGO", "WINDY CITY",
    "MIAMI", "MIAMI BEACH", "SOUTH BEACH",
    "WASHINGTON D.C.", "D.C.", "THE CAPITOL", "THE WHITE HOUSE",
    "SAN FRANCISCO", "GOLDEN GATE",
    "HOUSTON", "DALLAS", "BOSTON", "ATLANTA", "DETROIT",
    "LAS VEGAS", "THE STRIP", "NEW ORLEANS", "PHOENIX", "DENVER",
    "TORONTO", "MONTREAL", "CALGARY", "EDMONTON", "OTTAWA", "WINNIPEG",
    "LONDON", "PARIS", "BERLIN", "ROME", "MADRID", "AMSTERDAM",
    "MOSCOW", "PRAGUE", "VIENNA", "BUDAPEST", "WARSAW",
    "TOKYO", "OSAKA", "KYOTO", "HONG KONG", "BEIJING", "SHANGHAI",
    "SEOUL", "SINGAPORE", "BANGKOK", "HO CHI MINH",
    "SYDNEY", "MELBOURNE",
    "DUBAI", "ABU DHABI", "RIYADH",
    "MUMBAI", "DELHI", "ISTANBUL",
    "MEXICO CITY", "HAVANA", "SAO PAULO", "BUENOS AIRES",
    "CAIRO", "CAPE TOWN", "NAIROBI",
    "ATHENS", "BARCELONA",
}

_DISTANT_LANDSCAPES = {
    "SAVANNA", "SAFARI", "AFRICAN PLAIN", "SERENGETI",
    "TROPICAL BEACH", "CARIBBEAN BEACH", "TROPICAL ISLAND",
    "JUNGLE", "TROPICAL RAINFOREST", "AMAZON",
    "STEPPE", "GRASSLAND", "PRAIRIE",
    "SWAMP", "BAYOU", "EVERGLADES",
}

_ENVIRONMENTAL_EXT = {
    "STREET", "AVENUE", "BOULEVARD", "ROAD",
    "CROSSWALK", "CROSSING", "PEDESTRIAN CROSSING",
    "BUSY STREET", "CROWDED STREET", "CITY STREET",
    "TIMES SQUARE", "GRAND CENTRAL TERMINAL", "PENN STATION",
    "FESTIVAL", "PARADE", "STREET PARADE", "CARNIVAL",
    "PROTEST", "RALLY", "DEMONSTRATION", "RIOT",
    "MARKET", "STREET MARKET", "BAZAAR", "FARMERS MARKET",
    "PLAZA", "TOWN SQUARE", "PUBLIC SQUARE", "PIAZZA",
    "BOARDWALK", "BEACHFRONT BOARDWALK",
    "STADIUM", "SPORTS STADIUM", "ARENA",
    "AIRPORT TERMINAL", "TRAIN STATION", "BUS TERMINAL",
    "BEACH",
    "WATERFRONT", "HARBOUR", "PORT",
}

_LUMOSTAGE_STRONG = {
    "VOLCANO", "GLACIER", "ARCTIC TUNDRA", "ANTARCTIC",
    "MOUNTAIN PEAK", "MOUNTAINTOP", "SUMMIT",
    "CANYON RIM", "CRATER",
    "UNDERWATER", "OCEAN FLOOR", "DEEP SEA", "SEABED",
    "OPERATING ROOM", "SURGERY ROOM", "OR ",
    "MORGUE", "AUTOPSY ROOM",
    "SERVER ROOM", "DATA CENTER", "CONTROL ROOM", "MISSION CONTROL",
    "BUNKER", "BOMB SHELTER", "VAULT", "SAFE ROOM",
    "SPACESHIP BRIDGE", "COMMAND BRIDGE",
    "NEWSROOM", "BROADCAST STUDIO", "SOUNDSTAGE",
}

_PRACTICAL_EXT = {
    "PARKING LOT", "PARKING GARAGE", "SIDEWALK", "ALLEY", "ALLEYWAY",
    "STREET CORNER", "INTERSECTION",
    "PARK", "PLAYGROUND", "BASKETBALL COURT", "TENNIS COURT",
    "FOOTBALL FIELD", "BASEBALL DIAMOND", "SOCCER FIELD",
    "BACKYARD", "FRONT YARD", "FRONT PORCH", "BACK PORCH",
    "DRIVEWAY", "CARPORT",
    "SCHOOL ENTRANCE", "BUILDING ENTRANCE",
    "CONVENIENCE STORE", "GAS STATION", "STRIP MALL",
    "CEMETERY", "GRAVEYARD",
    "AIRPORT TARMAC", "AIRPORT RUNWAY",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _kw_match(keyword_set: set[str], text: str) -> bool:
    for kw in keyword_set:
        if re.search(r"\b" + re.escape(kw) + r"\b", text):
            return True
    return False


# ── Rules persistence ─────────────────────────────────────────────────────────

def load_rules() -> dict:
    if _RULES_FILE.exists():
        try:
            with open(_RULES_FILE, encoding="utf-8") as f:
                rules = json.load(f)
            return migrate_rules(rules)
        except (json.JSONDecodeError, OSError):
            pass
    return {"learned": {}, "version": 1}


def save_rules(rules: dict) -> None:
    _RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2)


def migrate_rules(rules: dict) -> dict:
    """Rewrite any legacy recommendation names in learned rules to current names."""
    from approach_config import LEGACY_NAMES
    changed = False
    for entry in rules.get("learned", {}).values():
        old = entry.get("recommendation", "")
        new = LEGACY_NAMES.get(old, old)
        if new != old:
            entry["recommendation"] = new
            changed = True
        for old_k in list(entry.get("pending", {}).keys()):
            new_k = LEGACY_NAMES.get(old_k, old_k)
            if new_k != old_k:
                entry["pending"][new_k] = entry["pending"].pop(old_k)
                changed = True
    if changed:
        save_rules(rules)
    return rules


def _norm(location: str) -> str:
    return location.upper().strip()


# ── Core recommendation ───────────────────────────────────────────────────────

def recommend_vp(
    int_ext: str,
    location: str,
    time_of_day: str,
    rules: dict | None = None,
) -> tuple[str, str]:
    if rules is None:
        rules = {}

    loc_up = location.upper()
    ie_up  = int_ext.upper()
    is_int = "INT" in ie_up
    is_ext = "EXT" in ie_up

    # 1. Learned rules
    norm = _norm(location)
    learned: dict = rules.get("learned", {})
    if norm in learned:
        return learned[norm]["recommendation"], "learned"

    root = loc_up.split(" - ")[0].strip()
    for learned_loc, data in learned.items():
        if root == learned_loc.split(" - ")[0].strip() and len(root) >= 3:
            return data["recommendation"], "learned (similar)"

    # 2. Road vehicles
    if is_int and _kw_match(_INT_VEHICLE, loc_up):
        return R_INT_CAR, "high"

    # 3. EXT. Desert (checked before distant pass so it gets specific label)
    if is_ext and _kw_match(_DESERT_KW, loc_up):
        return R_DESERT, "high"

    # 4. EXT. Rooftop
    if is_ext and _kw_match(_ROOFTOP_KW, loc_up):
        return R_ROOFTOP, "high"

    # 5. Distant / Difficult
    is_distant = _kw_match(_DISTANT_CITIES, loc_up) or _kw_match(_DISTANT_LANDSCAPES, loc_up)
    if is_distant:
        if is_int:
            return R_VPROD, "high"
        else:
            if _kw_match(_ENVIRONMENTAL_EXT, loc_up):
                return R_LOCATION, "medium"
            return R_VPROD, "medium"

    # 6. INT. Subway / rail
    if is_int and _kw_match(_SUBWAY_KW, loc_up):
        return R_SUBWAY_TRAIN, "high"

    # 7. INT. Platform
    if is_int and _kw_match(_PLATFORM_KW, loc_up):
        return R_PLATFORM, "high"

    # 8. Aircraft / vessels
    if _kw_match(_INT_AIRCRAFT, loc_up):
        return R_INT_PLANE, "high"

    # 9. Doesn't Exist
    if _kw_match(_DOESNT_EXIST, loc_up):
        return R_VPROD, "high"

    # 10. Dangerous
    if _kw_match(_DANGEROUS, loc_up):
        return R_VPROD, "high"

    # 11. Strong Lumostage signals
    if _kw_match(_LUMOSTAGE_STRONG, loc_up):
        return R_VPROD, "medium"

    # 12. Practical local EXT.
    if is_ext:
        if _kw_match(_PRACTICAL_EXT, loc_up) or _kw_match(_ENVIRONMENTAL_EXT, loc_up):
            return R_LOCATION, "medium"
        return R_LOCATION, "low"

    # 13. Generic INT.
    return R_EITHER, "low"


# ── Learning from user edits ──────────────────────────────────────────────────

def learn_from_edits(rows: list[dict], rules: dict | None = None) -> dict:
    if rules is None:
        rules = load_rules()

    learned = rules.setdefault("learned", {})

    for row in rows:
        loc = _norm(row.get("Location", ""))
        rec = row.get("Approach", "").strip()
        if not loc or not rec:
            continue

        if loc not in learned:
            learned[loc] = {"recommendation": rec, "count": 1, "pending": {}}
        else:
            entry = learned[loc]
            if entry["recommendation"] == rec:
                entry["count"] = entry.get("count", 1) + 1
            else:
                pending = entry.setdefault("pending", {})
                pending[rec] = pending.get(rec, 0) + 1
                if pending[rec] > entry.get("count", 1):
                    entry["recommendation"] = rec
                    entry["count"] = pending[rec]
                    pending.pop(rec, None)

    save_rules(rules)
    return rules


def rule_stats(rules: dict) -> dict:
    learned = rules.get("learned", {})
    by_rec: dict[str, int] = {}
    for entry in learned.values():
        rec = entry.get("recommendation", "Unknown")
        by_rec[rec] = by_rec.get(rec, 0) + 1
    return {"total": len(learned), "by_recommendation": by_rec}
