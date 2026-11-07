# Football Picks - Betfair

Dashboard with 10-15 football picks (live + next 72h), odds 1.40-2.20, ranked by win chance, money picks highlighted.

## Run
```bash
cp .env.example .env        # add ODDS_API_KEY (free: the-odds-api.com)
python3 app.py              # http://localhost:8050
python3 app.py --once       # picks in terminal
python3 app.py --demo       # fake data, no key
python3 backtest.py         # real historical hit rate / ROI
```
No dependencies beyond Python 3.10+.

## How picks are made
| Source | Free | Role |
|---|---|---|
| The Odds API | 500 credits/mo | Betfair Exchange prices, Pinnacle + 8 UK books, in-play odds, live scores, results |
| Pinnacle (de-vigged) | via above | Sharp probability (50% weight) |
| Bookmaker consensus | via above | 25-30% weight |
| ClubElo `/Fixtures` | no key | Independent model, pre-match only (15-25%) |
| AI swarm (optional) | Anthropic key | MiroFish-style panel of 5 agents with web search for team news; max +/-2.5pp |

- **EV** = win chance x Betfair odds after 5% commission - 1.
- **MONEY PICK**: EV >= +2%, win chance >= 65%, models agree. These are the only ones that make money long-term.
- **Stake**: quarter-Kelly, capped at 3% bankroll; 0 when no edge.
- Every pre-match pick is saved to `picks.db` and settled automatically. The "real record" tile shows actual hit rate and ROI.

## Credits
10 leagues x 2 markets = ~20 credits per refresh. Results cache for 30 min. Reduce `LEAGUES` in `.env` to save credits.

## Notes
- **85% win rate at 1.40+ odds is not achievable.** At 1.40, the market already says ~70%. Expect a 65-72% hit rate on this list. Profit comes only from the EV-positive picks.
- MiroFish itself (github.com/666ghj/MiroFish) is a self-hosted simulation engine. It takes minutes per run and needs an LLM key plus Zep, so it's too slow for a refreshing dashboard. `swarm.py` uses the same multi-agent idea in a single call.
