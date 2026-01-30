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
                "cookies": [],  # ← you can add consent cookies here later
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

    # Try to find match containers
    match_containers = soup.find_all("div", class_="b-match-container")
    if not match_containers:
        logging.warning("No 'b-match-container' found – trying fallback selectors")
        match_containers = soup.find_all(["div"], class_=re.compile(r"match|upcoming"))

    for container in match_containers:
        table = container.find("table", class_="bookmakerMatch")
        if not table:
            continue

        # Extract teams
        team_divs = table.find_all("div", class_="team-name")
        if len(team_divs) >= 2:
            team1 = team_divs[0].get_text(strip=True)
            team2 = team_divs[1].get_text(strip=True)
        else:
            team_spans = table.find_all(["span", "div"], class_=re.compile(r"team|text-ellipsis"))
            if len(team_spans) >= 2:
                team1 = team_spans[0].get_text(strip=True)
                team2 = team_spans[1].get_text(strip=True)
            else:
                logging.warning("Could not find team names")
                continue

        # Match link
        link_tag = table.find("a", class_="a-reset")
        match_href = link_tag["href"] if link_tag else None
        full_url = f"https://www.hltv.org{match_href}" if match_href and match_href.startswith("/") else match_href

        # === Collect odds ===
        odds = {}  # { "marathon": {"team1": "1.54", "team2": "2.31"}, ... }

        provider_cells = table.find_all("td", class_=lambda v: v and any("odds-provider" in c for c in v.split()))

        logging.debug(f"Found {len(provider_cells)} provider cells for {team1} vs {team2}")

        cell_index = 0
        for cell in provider_cells:
            classes = cell.get("class", [])
            provider_cls = next((c for c in classes if "odds-provider" in c), None)
            if not provider_cls:
                continue

            provider = re.sub(r"^(b-list-)?odds-provider-", "", provider_cls).lower().strip()

            # Try to determine side (team1 / team2)
            side = None
            row = cell.find_parent("tr")
            if row:
                # Look for team indicators in the row
                team1_indicators = row.find_all(["td", "th"], class_=re.compile(r"team1|left|first"))
                if cell in team1_indicators or cell_index % 2 == 0:
                    side = "team1"
                else:
                    side = "team2"
            # Fallback: alternate based on order (most tables are team1 then team2)
            if not side:
                side = "team1" if cell_index % 2 == 0 else "team2"

            # Extract odd value
            value = None
            candidates = [
                cell.find("a", class_="odds"),
                cell.find("a", class_="bestOdds"),
                cell.find("span"),
                cell
            ]
            for cand in candidates:
                if cand:
                    txt = cand.get_text(strip=True)
                    if txt and re.match(r"^\d+\.?\d{1,2}$", txt):
                        value = txt
                        break

            if value:
                if provider not in odds:
                    odds[provider] = {}
                odds[provider][side] = value
                logging.debug(f"  → {provider} {side:<6} = {value}")

            cell_index += 1

        # Fallback if provider cells didn't work well
        if not odds or all(len(v) < 2 for v in odds.values()):
            odds_links = table.find_all("a", class_="odds")
            logging.debug(f"Fallback: found {len(odds_links)} <a class='odds'> elements")
            for i, link in enumerate(odds_links):
                txt = link.get_text(strip=True)
                if txt and re.match(r"^\d+\.?\d{1,2}$", txt):
                    side = "team1" if i % 2 == 0 else "team2"
                    provider_fallback = f"odds_link_{i//2}"
                    if provider_fallback not in odds:
                        odds[provider_fallback] = {}
                    odds[provider_fallback][side] = txt

        # Save only if we have at least one provider with odds
        if odds:
            entry = {
                "team1": team1,
                "team2": team2,
                "odds": odds,
                "match_url": full_url,
                "analytics_url": full_url,
            }
            matches.append(entry)

    return matches


def main():
    url = "https://www.hltv.org/betting/money"

    logging.info("Fetching HLTV betting odds page...")
    html = get_html(url)

    if not html:
        logging.error("Failed to retrieve page")
        return

    logging.info("Parsing matches...")
    results = parse_matches(html)

    logging.info(f"Extracted {len(results)} matches with odds")

    with open("hltv_odds.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Print preview
    for match in results:
        print(f"{match['team1']} vs {match['team2']}")
        for prov, sides in match["odds"].items():
            t1 = sides.get("team1", "—")
            t2 = sides.get("team2", "—")
            print(f"  {prov:18}  team1: {t1:>5}   team2: {t2:>5}")
        print(f"  → {match.get('match_url')}")
        print("─" * 70)


if __name__ == "__main__":
    main()
