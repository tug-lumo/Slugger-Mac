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
R_VP_VEHICLE  = "VP (INT. Vehicle)"
R_VP_AIRCRAFT = "VP (INT. Aircraft)"
R_LUMOSTAGE   = "Lumostage"
R_ON_LOCATION = "On Location"
R_EITHER      = "Option: Either"
R_SET_BUILD   = "Set Build"
R_VFX         = "VFX"
R_OMITTED     = "OMITTED"

ALL_OPTIONS = [
    R_VP_VEHICLE,
    R_VP_AIRCRAFT,
    R_LUMOSTAGE,
    R_ON_LOCATION,
    R_EITHER,
    R_SET_BUILD,
    R_VFX,
    R_OMITTED,
]

# ── Keyword banks ─────────────────────────────────────────────────────────────

# INT. moving-vehicle scenes
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

# Moving vessels / transit (INT. or EXT.)
_INT_AIRCRAFT = {
    "AIRPLANE", "PLANE", "JET", "AIRCRAFT", "COCKPIT",
    "HELICOPTER", "CHOPPER", "PRIVATE JET", "CARGO PLANE",
    "MILITARY PLANE", "FIGHTER JET",
    "TRAIN", "SUBWAY", "METRO", "RAIL CAR", "DINING CAR", "SLEEPER CAR",
    "BOAT", "SPEEDBOAT", "YACHT", "FERRY", "CRUISE SHIP", "SHIP",
    "SUBMARINE", "GONDOLA", "CABLE CAR",
}

# ── "DOESN'T EXIST" — impossible or fantastical ───────────────────────────────
_DOESNT_EXIST = {
    # Space / sci-fi
    "SPACE", "OUTER SPACE", "SPACESHIP", "SPACECRAFT", "SPACE STATION",
    "ALIEN PLANET", "ALIEN SHIP", "ALIEN WORLD", "MOTHERSHIP",
    "WORMHOLE", "BLACK HOLE", "NEBULA",
    # Digital / virtual
    "DIGITAL WORLD", "CYBERSPACE", "VIRTUAL REALITY", "VR WORLD",
    "INSIDE COMPUTER", "THE MATRIX",
    # Pure fantasy
    "FANTASY KINGDOM", "ENCHANTED FOREST", "MAGICAL REALM", "DRAGON",
    "CASTLE GREAT HALL", "DUNGEON", "THRONE ROOM",
    # Period — no longer exists as-is
    "MEDIEVAL", "ANCIENT ROME", "ANCIENT EGYPT", "ROMAN FORUM",
    "VICTORIAN LONDON", "WILD WEST", "OLD WEST", "FRONTIER TOWN",
    "CIVIL WAR BATTLEFIELD", "WWI TRENCH", "WWII BUNKER",
    "PROHIBITION ERA",
}

# ── "DANGEROUS" — unsafe to shoot practically ────────────────────────────────
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

# ── "DIFFICULT/DISTANT" — far from Lower Mainland BC ────────────────────────
# Production base is Vancouver/Lower Mainland. These are geographically distant.
_DISTANT_CITIES = {
    # USA
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
    # Canada (outside BC)
    "TORONTO", "MONTREAL", "CALGARY", "EDMONTON", "OTTAWA", "WINNIPEG",
    # International
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

# Landscapes/environments that don't exist in or near Lower Mainland BC
_DISTANT_LANDSCAPES = {
    "DESERT", "SAHARA", "MOJAVE", "SONORAN", "ARABIAN DESERT",
    "SAVANNA", "SAFARI", "AFRICAN PLAIN", "SERENGETI",
    "TROPICAL BEACH", "CARIBBEAN BEACH", "TROPICAL ISLAND",
    "JUNGLE", "TROPICAL RAINFOREST", "AMAZON",
    "STEPPE", "GRASSLAND", "PRAIRIE",  # BC has some but not classic prairie
    "BADLANDS", "CANYON", "GRAND CANYON", "MESA",
    "SWAMP", "BAYOU", "EVERGLADES",
}

# ── EXT. scenes that need real environment — crowds, scale, authentic setting
# These are On Location even if the city is distant (go there or use a stand-in).
# Contrast with intimate/contained EXT. scenes that work well on an LED stage.
# NOTE: HIGHWAY / FREEWAY intentionally excluded — driving environments are VP-friendly.
_ENVIRONMENTAL_EXT = {
    # Streets and pedestrian environments (need authentic movement/scale)
    "STREET", "AVENUE", "BOULEVARD", "ROAD",
    "CROSSWALK", "CROSSING", "PEDESTRIAN CROSSING",
    "BUSY STREET", "CROWDED STREET", "CITY STREET",
    "TIMES SQUARE", "GRAND CENTRAL TERMINAL", "PENN STATION",
    # Crowds and events
    "FESTIVAL", "PARADE", "STREET PARADE", "CARNIVAL",
    "PROTEST", "RALLY", "DEMONSTRATION", "RIOT",
    "MARKET", "STREET MARKET", "BAZAAR", "FARMERS MARKET",
    # Large public spaces
    "PLAZA", "TOWN SQUARE", "PUBLIC SQUARE", "PIAZZA",
    "BOARDWALK", "BEACHFRONT BOARDWALK",
    "STADIUM", "SPORTS STADIUM", "ARENA",
    "AIRPORT TERMINAL", "TRAIN STATION", "BUS TERMINAL",
    # Natural wide environments
    "BEACH",  # wide beach — intimate beach can be LED
    "WATERFRONT", "HARBOUR", "PORT",
}

# ── "DOESN'T EXIST" subtype — strong Lumostage even if not fully fantastical ─
_LUMOSTAGE_STRONG = {
    # Extreme / impossible natural EXT.
    "VOLCANO", "GLACIER", "ARCTIC TUNDRA", "ANTARCTIC",
    "MOUNTAIN PEAK", "MOUNTAINTOP", "SUMMIT",
    "CANYON RIM", "CRATER",
    "UNDERWATER", "OCEAN FLOOR", "DEEP SEA", "SEABED",
    # Controlled tech/institutional INT.
    "OPERATING ROOM", "SURGERY ROOM", "OR ",
    "MORGUE", "AUTOPSY ROOM",
    "SERVER ROOM", "DATA CENTER", "CONTROL ROOM", "MISSION CONTROL",
    "BUNKER", "BOMB SHELTER", "VAULT", "SAFE ROOM",
    "SPACESHIP BRIDGE", "COMMAND BRIDGE",
    "NEWSROOM", "BROADCAST STUDIO", "SOUNDSTAGE",
}

# ── Local / easily practical EXT. locations ───────────────────────────────────
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
    """True if any keyword from the set appears as a whole word in text."""
    for kw in keyword_set:
        if re.search(r"\b" + re.escape(kw) + r"\b", text):
            return True
    return False


# ── Rules persistence ─────────────────────────────────────────────────────────

def load_rules() -> dict:
    if _RULES_FILE.exists():
        try:
            with open(_RULES_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"learned": {}, "version": 1}


def save_rules(rules: dict) -> None:
    _RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2)


def _norm(location: str) -> str:
    return location.upper().strip()


# ── Core recommendation ───────────────────────────────────────────────────────

def recommend_vp(
    int_ext: str,
    location: str,
    time_of_day: str,
    rules: dict | None = None,
) -> tuple[str, str]:
    """
    Return (recommendation_label, confidence_string).

    confidence values:
        "learned"            — from stored user edits (exact match)
        "learned (similar)"  — from stored user edits (root-location match)
        "high"               — strong keyword signal
        "medium"             — moderate keyword signal
        "low"                — default / fallback
    """
    if rules is None:
        rules = {}

    loc_up = location.upper()
    ie_up  = int_ext.upper()
    is_int = "INT" in ie_up
    is_ext = "EXT" in ie_up

    # ── 1. Learned rules (highest priority) ──────────────────────────────────
    norm = _norm(location)
    learned: dict = rules.get("learned", {})
    if norm in learned:
        return learned[norm]["recommendation"], "learned"

    root = loc_up.split(" - ")[0].strip()
    for learned_loc, data in learned.items():
        if root == learned_loc.split(" - ")[0].strip() and len(root) >= 3:
            return data["recommendation"], "learned (similar)"

    # ── 2. Road vehicles — VP regardless of city (it's a moving-vehicle rig) ──
    if is_int and _kw_match(_INT_VEHICLE, loc_up):
        return R_VP_VEHICLE, "high"

    # ── 3. Distant / Difficult locations (checked BEFORE transit vessels) ─────
    # In a distant city an INT. subway or train is best built on the LED stage;
    # checking here prevents SUBWAY triggering VP (Aircraft) for a NY scene.
    is_distant = _kw_match(_DISTANT_CITIES, loc_up) or _kw_match(_DISTANT_LANDSCAPES, loc_up)

    if is_distant:
        if is_int:
            # Interior of a distant location → build it on the LED stage
            return R_LUMOSTAGE, "high"
        else:
            # Environmental EXT. (crowds, scale, authentic atmosphere) → On Location
            if _kw_match(_ENVIRONMENTAL_EXT, loc_up):
                return R_ON_LOCATION, "medium"
            # Contained / intimate EXT. → Lumostage with a backdrop
            return R_LUMOSTAGE, "medium"

    # ── 4. Local transit / moving vessels ─────────────────────────────────────
    if _kw_match(_INT_AIRCRAFT, loc_up):
        return R_VP_AIRCRAFT, "high"

    # ── 5. "Doesn't Exist" — fantastical / period / impossible ────────────────
    # Lumostage is a large-exterior locations solution, not just small stages.
    # EXT. alien worlds, space vistas, etc. can absolutely be shot on Lumostage.
    # VFX (full-CG / compositing-only) is a manual call the human makes in context.
    if _kw_match(_DOESNT_EXIST, loc_up):
        return R_LUMOSTAGE, "high"

    # ── 6. "Dangerous" — unsafe to shoot practically ──────────────────────────
    if _kw_match(_DANGEROUS, loc_up):
        return R_LUMOSTAGE, "high"

    # ── 7. Strong Lumostage signals (extreme or highly controlled) ────────────
    if _kw_match(_LUMOSTAGE_STRONG, loc_up):
        return R_LUMOSTAGE, "medium"

    # ── 8. Clearly practical local EXT. ───────────────────────────────────────
    if is_ext:
        if _kw_match(_PRACTICAL_EXT, loc_up) or _kw_match(_ENVIRONMENTAL_EXT, loc_up):
            return R_ON_LOCATION, "medium"
        return R_ON_LOCATION, "low"

    # ── 9. Generic INT. — context-dependent ───────────────────────────────────
    return R_EITHER, "low"


# ── Learning from user edits ──────────────────────────────────────────────────

def learn_from_edits(rows: list[dict], rules: dict | None = None) -> dict:
    """
    Update learned rules from a list of edited breakdown rows.
    Each row must have: 'Location', 'INT/EXT', 'Approach'

    Majority-vote: a new recommendation wins once its count exceeds the stored one.
    """
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
