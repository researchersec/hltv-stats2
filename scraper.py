import requests
from bs4 import BeautifulSoup
import json
import logging
import re

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

FLARE_SOLVER_URL = "http://localhost:8191/v1"
USE_FLARE = True


def get_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://www.hltv.org/",
        "Accept-Language": "en-US,en;q=0.9",
    }

    if USE_FLARE:
        try:
            payload = {
                "cmd": "request.get",
                "url": url,
                "maxTimeout": 65000,
            }
            resp = requests.post(FLARE_SOLVER_URL, json=payload, timeout=100)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "ok":
                return data["solution"]["response"]
            else:
                logging.error("FlareSolverr error: %s", data.get("message"))
                return None
        except Exception as e:
            logging.error("FlareSolverr failed: %s", e)
            return None
    else:
        try:
            r = requests.get(url, headers=headers, timeout=25)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logging.error("Direct request failed: %s", e)
            return None


def parse_matches(html):
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    matches = []

    # Match blocks are div.bc-analytics-insights-middle
    match_blocks = soup.find_all("div", class_="bc-analytics-insights-middle")
    logging.info(f"Found {len(match_blocks)} potential match blocks")

    for block in match_blocks:
        # Extract teams from cell1
        team_rows = block.find_all("div", class_="bc-analytics-insights-team-row")
        if len(team_rows) < 2:
            logging.warning("Missing teams in block")
            continue
        team1 = team_rows[0].find("div", class_="bc-analytics-insights-team-name").get_text(strip=True)
        team2 = team_rows[1].find("div", class_="bc-analytics-insights-team-name").get_text(strip=True)

        # Extract odds from cell2 (best odds)
        odds_divs = block.find_all("div", class_="bc-analytics-best-o")
        if len(odds_divs) < 2:
            logging.warning("Missing odds in block")
            continue
        odd1 = odds_divs[0].get_text(strip=True)
        odd2 = odds_divs[1].get_text(strip=True)

        # Construct odds dict (best provider)
        odds = {
            "best": {
                "team1": odd1 if odd1 != '-' else "N/A",
                "team2": odd2 if odd2 != '-' else "N/A"
            }
        }

        # Extract match ID and slug from form links in cell3
        form_link = block.find("a", class_="bc-analytics-form-link")
        full_url = None
        analytics_url = None
        if form_link and 'href' in form_link.attrs:
            href = form_link["href"]
            match = re.search(r"/matches/(\d+)/(.+)", href)
            if match:
                match_id = match.group(1)
                slug = match.group(2)
                full_url = f"https://www.hltv.org{match_link['href']}"
                analytics_url = f"https://www.hltv.org/betting/analytics/{match_id}/{slug}"

        # Save entry if odds are present
        if odds["best"]["team1"] != "N/A" or odds["best"]["team2"] != "N/A":
            entry = {
                "team1": team1,
                "team2": team2,
                "odds": odds,
                "match_url": full_url,
                "analytics_url": analytics_url,
            }
            matches.append(entry)
            logging.debug(f"Extracted match: {team1} vs {team2} with odds {odds}")

    return matches


def main():
    url = "https://www.hltv.org/betting/analytics"

    logging.info("Fetching HLTV betting analytics page...")
    html = get_html(url)

    if not html:
        logging.error("Failed to retrieve page")
        return

    logging.info("Parsing matches...")
    results = parse_matches(html)

    logging.info(f"Extracted {len(results)} matches with odds")

    with open("hltv_analytics_odds.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Print preview
    for match in results:
        print(f"{match['team1']} vs {match['team2']}")
        for prov, sides in match["odds"].items():
            t1 = sides.get("team1", "—")
            t2 = sides.get("team2", "—")
            print(f"  {prov:18}  team1: {t1:>5}   team2: {t2:>5}")
        print(f"  → {match.get('analytics_url')}")
        print("─" * 70)


if __name__ == "__main__":
    main()
