"""Settings. Override any value with an environment variable or a .env file."""
import os
from pathlib import Path

_env = Path(__file__).with_name(".env")
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")          # free: https://the-odds-api.com (500 credits/month)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # optional: AI swarm panel
SWARM_MODEL = os.getenv("SWARM_MODEL", "claude-sonnet-5-5")

LEAGUES = os.getenv("LEAGUES", ",".join([
    "soccer_epl", "soccer_spain_la_liga", "soccer_italy_serie_a",
    "soccer_germany_bundesliga", "soccer_france_ligue_one", "soccer_efl_champ",
    "soccer_netherlands_eredivisie", "soccer_portugal_primeira_liga",
    "soccer_uefa_champs_league", "soccer_uefa_europa_league",
])).split(",")

# Up to 10 bookmakers = 1 credit per market per league. Betfair Exchange is the price we bet at,
# Pinnacle is the sharp reference, the rest build the consensus.
BOOKMAKERS = os.getenv("BOOKMAKERS", "betfair_ex_uk,pinnacle,matchbook,williamhill,paddypower,"
                       "skybet,unibet_uk,ladbrokes_uk,coral,betfair_sb_uk")

MIN_ODDS = float(os.getenv("MIN_ODDS", "1.40"))
MAX_ODDS = float(os.getenv("MAX_ODDS", "2.20"))
MIN_PROB = float(os.getenv("MIN_PROB", "0.60"))
MAX_PICKS = int(os.getenv("MAX_PICKS", "15"))
HOURS_AHEAD = int(os.getenv("HOURS_AHEAD", "72"))
BETFAIR_COMMISSION = float(os.getenv("BETFAIR_COMMISSION", "0.05"))
CACHE_MINUTES = int(os.getenv("CACHE_MINUTES", "30"))   # protects free API credits
BANKROLL = float(os.getenv("BANKROLL", "100"))
PORT = int(os.getenv("PORT", "8050"))
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).with_name("picks.db")))
