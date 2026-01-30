import requests
from bs4 import BeautifulSoup
import json
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

USE_FLARE = True
FLARE_SOLVER_URL = "http://localhost:8191/v1"


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
                "cookies": [],  # Add consent cookies here if needed
            }
            resp = requests.post(FLARE_SOLVER_URL, json=payload, timeout=100)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "ok":
                logging.info(f"Page fetched successfully ({len(data['solution']['response'])} chars)")
                return data["solution"]["response"]
            else:
                logging.error(f"FlareSolverr error: {data.get('message')}")
                return None
        except Exception as e:
            logging.error(f"FlareSolverr failed: {e}")
            return None
    else:
        try:
            r = requests.get(url, headers=headers, timeout=25)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logging.error(f"Direct request failed: {e}")
            return None


def parse_match_odds(html, match_url):
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    betting_section = soup.find("div", id="betting")
    if not betting_section:
        logging.warning("No #betting section found")
        return None

    # Get teams from header row
    header_row = betting_section.find("tr", class_="")
    if not header_row:
        logging.warning("No header row in betting table")
        return None

    team_cells = header_row.find_all("td", class_="team-cell")
    if len(team_cells) < 2:
        logging.warning("Could not find both team names")
        return None

    team1 = team_cells[0].get_text(strip=True)
    team2 = team_cells[1].get_text(strip=True)
    logging.debug(f"Teams extracted: {team1} vs {team2}")

    # Find all bookmaker rows
    provider_rows = betting_section.find_all("tr", class_="provider")
    logging.debug(f"Found {len(provider_rows)} provider rows")

    odds = {}

    for row in provider_rows:
        # Provider name from aria-label
        logo_link = row.find("a", class_="betting-logo-link")
        if not logo_link or "aria-label" not in logo_link.attrs:
            logging.debug("Skipping row: no valid provider link")
            continue

        provider_name = logo_link["aria-label"].replace("Go to ", "").strip()
        logging.debug(f"Processing provider: {provider_name}")

        # Odds cells
        odds_cells = row.find_all("td", class_="odds-cell")
        if len(odds_cells) < 2:
            logging.debug(f"Odds cells found: {len(odds_cells)} | HTML: {str(row.find_all('td', class_='odds-cell'))[:200]}")
            logging.debug(f"Skipping {provider_name}: not enough odds cells")
            continue

        logging.debug(f"Odds cells found: {len(odds_cells)} | HTML: {str(row.find_all('td', class_='odds-cell'))[:200]}")

        odd1_a = odds_cells[0].find("a")
        odd2_a = odds_cells[1].find("a")

        odd1 = odd1_a.get_text(strip=True) if odd1_a else "N/A"
        odd2 = odd2_a.get_text(strip=True) if odd2_a else "N/A"

        odds[provider_name] = {
            "team1": odd1,
            "team2": odd2
        }

        logging.info(f"{provider_name}: {team1} {odd1} – {team2} {odd2}")

    if not odds:
        logging.warning("No valid odds rows found")
        return None

    return {
        "team1": team1,
        "team2": team2,
        "odds": odds,
        "match_url": match_url
    }


def main():
    # Replace with your target match URL
    match_url = "https://www.hltv.org/matches/2389684/mibr-vs-9z-fire-conter-season-1"

    logging.info(f"Fetching: {match_url}")
    html = get_html(match_url)

    if not html:
        logging.error("Failed to get page content")
        return

    result = parse_match_odds(html, match_url)

    if result:
        logging.info("Extraction successful")
        with open("match_odds.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # Print nice summary
        print(f"\n{result['team1']} vs {result['team2']}")
        for prov, odds in result["odds"].items():
            print(f"  {prov:15} → {result['team1']}: {odds['team1']:>5}   {result['team2']}: {odds['team2']:>5}")
        print(f"\nSaved to match_odds.json")
    else:
        print("\nNo odds extracted. Check logs for details.")


if __name__ == "__main__":
    main()
