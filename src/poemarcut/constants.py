"""Constants for PoEMarcut."""

POE2_EX_WORTHLESS_VAL = 500  # if poe2 div<=>ex is above this value, ex is worthless

S_IN_HOUR = 3600

BOLD = "\033[1m"  # ANSI escape bold
RESET = "\033[0m"  # ANSI escape reset

# mapping of merchant tab currency trade id to full name
MERCHANT_CURRENCIES: dict[str, str] = {
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
    "offer": "Offering to the Goddess",
}

# mapping of merchant tab currency trade id to unique minimum full-name prefix for dropdown selection
MERCHANT_CURRENCY_PREFIXES: dict[str, str] = {
    "chaos": "chao",
    "divine": "d",
    "alch": "alc",
    "exalted": "e",
    "alt": "alt",
    "mirror": "m",
    "chrome": "chr",
    "blessed": "bl",
    "fusing": "f",
    "jewellers": "j",
    "regal": "rega",
    "vaal": "v",
    "chance": "chan",
    "annul": "an",
    "aug": "au",
    "regret": "regr",
    "scour": "sco",
    "transmute": "t",
    "wisdom": "wi",
    "portal": "p",
    "scrap": "scr",
    "whetstone": "wh",
    "gcp": "g",
    "bauble": "ba",
    "offer": "o",
}
