"""Constants for PoEMarcut."""

POE1_CURRENCY_API_URL = "https://poe.ninja/poe1/api/economy/exchange/current/overview"
POE2_CURRENCY_API_URL = "https://poe.ninja/poe2/api/economy/exchange/current/overview"
POE2_EX_WORTHLESS_VAL = 500  # if poe2 div<=>ex is above this value, ex is worthless

S_IN_HOUR = 3600

BOLD = "\033[1m"  # ANSI escape bold
RESET = "\033[0m"  # ANSI escape reset
