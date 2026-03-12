"""Constants for PoEMarcut."""

POE2_EX_WORTHLESS_VAL = 500  # if poe2 div<=>ex is above this value, ex is worthless

S_IN_HOUR = 3600

BOLD = "\033[1m"  # ANSI escape bold
RESET = "\033[0m"  # ANSI escape reset

# mapping of PoE1 merchant tab currency trade id to full name
POE1_MERCHANT_CURRENCIES: dict[str, str] = {
    "chaos": "Chaos Orb",
    "divine": "Divine Orb",
    "alch": "Orb of Alchemy",
    "exalted": "Exalted Orb",
    "alt": "Orb of Alteration",
    "mirror": "Mirror of Kalandra",
    "chrome": "Chromatic Orb",
    "blessed": "Blessed Orb",
    "fusing": "Orb of Fusing",
    "jewellers": "Jeweller's Orb",
    "regal": "Regal Orb",
    "vaal": "Vaal Orb",
    "chance": "Orb of Chance",
    "annul": "Orb of Annulment",
    "aug": "Orb of Augmentation",
    "regret": "Orb of Regret",
    "scour": "Orb of Scouring",
    "transmute": "Orb of Transmutation",
    "wisdom": "Scroll of Wisdom",
    "portal": "Portal Scroll",
    "scrap": "Armourer's Scrap",
    "whetstone": "Blacksmith's Whetstone",
    "gcp": "Gemcutter's Prism",
    "bauble": "Glassblower's Bauble",
    # "offer": "Offering to the Goddess",  # noqa: ERA001 -- not in the poe.ninja currency response, would need to implement a separate call
}

# mapping of PoE1 merchant tab currency trade id to unique minimum full-name prefix for dropdown selection
# Note: Longer strings will not work for typing selection. For ~>3, need to use index-based (not yet implemented)
POE1_MERCHANT_CURRENCY_PREFIXES: dict[str, str] = {
    "chaos": "cha",
    "divine": "d",
    "alch": "orbofalc",
    "exalted": "e",
    "alt": "orbofalt",
    "mirror": "m",
    "chrome": "chr",
    "blessed": "ble",
    "fusing": "orboff",
    "jewellers": "j",
    "regal": "r",
    "vaal": "v",
    "chance": "orbofc",
    "annul": "orbofan",
    "aug": "orbofau",
    "regret": "orbofr",
    "scour": "orbofs",
    "transmute": "orboft",
    "wisdom": "s",
    "portal": "p",
    "scrap": "a",
    "whetstone": "bla",
    "gcp": "ge",
    "bauble": "gl",
}

# mapping of PoE2 merchant tab currency trade id to full name
POE2_MERCHANT_CURRENCIES: dict[str, str] = {
    "exalted": "Exalted Orb",
    "greater-exalted-orb": "Greater Exalted Orb",
    "perfect-exalted-orb": "Perfect Exalted Orb",
    "divine": "Divine Orb",
    "chaos": "Chaos Orb",
    "greater-chaos-orb": "Greater Chaos Orb",
    "perfect-chaos-orb": "Perfect Chaos Orb",
    "alch": "Orb of Alchemy",
    "annul": "Orb of Annulment",
    "regal": "Regal Orb",
    "greater-regal-orb": "Greater Regal Orb",
    "perfect-regal-orb": "Perfect Regal Orb",
    "transmute": "Orb of Transmutation",
    "greater-orb-of-transmutation": "Greater Orb of Transmutation",
    "perfect-orb-of-transmutation": "Perfect Orb of Transmutation",
    "aug": "Orb of Augmentation",
    "greater-orb-of-augmentation": "Greater Orb of Augmentation",
    "perfect-orb-of-augmentation": "Perfect Orb of Augmentation",
    "chance": "Orb of Chance",
    "vaal": "Vaal Orb",
    "artificers": "Artificer's Orb",
    "fracturing-orb": "Fracturing Orb",
    "mirror": "Mirror of Kalandra",
    "wisdom": "Scroll of Wisdom",
}

# mapping of PoE2 merchant tab currency trade id to unique minimum full-name prefix for dropdown selection
POE2_MERCHANT_CURRENCY_PREFIXES: dict[str, str] = {
    "exalted": "e",
    "greater-exalted-orb": "greatere",
    "perfect-exalted-orb": "perfecte",
    "divine": "d",
    "chaos": "c",
    "greater-chaos-orb": "greaterc",
    "perfect-chaos-orb": "perfectc",
    "alch": "orbofal",
    "annul": "orbofan",
    "regal": "r",
    "greater-regal-orb": "greaterr",
    "perfect-regal-orb": "perfectr",
    "transmute": "orboft",
    "greater-orb-of-transmutation": "greaterorboft",
    "perfect-orb-of-transmutation": "perfectorboft",
    "aug": "orbofau",
    "greater-orb-of-augmentation": "greaterorbofa",
    "perfect-orb-of-augmentation": "perfectorbofa",
    "chance": "orbofc",
    "vaal": "v",
    "artificers": "a",
    "fracturing-orb": "f",
    "mirror": "m",
    "wisdom": "s",
}
