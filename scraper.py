import requests
from bs4 import BeautifulSoup
import json
import logging
import re

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("analytics_scraper_debug.log", encoding="utf-8")
    ]
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
        logging.info("Using FlareSolverr to fetch page...")
        try:
            payload = {
                "cmd": "request.get",
                "url": url,
                "maxTimeout": 65000,
                "cookies": [],  # ← Add real Cookiebot/CookieConsent here if you have them
            }
            resp = requests.post(FLARE_SOLVER_URL, json=payload, timeout=100)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "ok":
                logging.info("FlareSolverr success - page length: %d chars", len(data["solution"]["response"]))
                return data["solution"]["response"]
            else:
                logging.error("FlareSolverr returned error: %s", data.get("message"))
                return None
        except Exception as e:
            logging.error("FlareSolverr request failed: %s", str(e))
            return None
    else:
        logging.warning("Direct request (no FlareSolverr) - likely blocked by Cloudflare")
        try:
            r = requests.get(url, headers=headers, timeout=25)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logging.error("Direct request failed: %s", str(e))
            return None


def parse_matches(html):
    if not html:
        logging.error("No HTML content received")
        return []

    soup = BeautifulSoup(html, "lxml")
    matches = []
    skipped = []

    match_blocks = soup.find_all("div", class_="bc-analytics-insights-middle")
    logging.info(f"Found {len(match_blocks)} elements with class 'bc-analytics-insights-middle'")

    for idx, block in enumerate(match_blocks, 1):
        logging.debug(f"─── Processing match block #{idx} ───")

        # Log a snippet of the block HTML for debugging
        block_html = str(block)
        snippet = block_html[:300] + " ... " + block_html[-200:] if len(block_html) > 500 else block_html
        logging.debug(f"Block HTML snippet:\n{snippet}\n")

        # Teams
        team_rows = block.find_all("div", class_="bc-analytics-insights-team-row")
        if len(team_rows) < 2:
            logging.warning(f"Block #{idx}: Missing team rows (found {len(team_rows)})")
            skipped.append({"index": idx, "reason": "missing team rows"})
            continue

        team1_div = team_rows[0].find("div", class_="bc-analytics-insights-team-name")
        team2_div = team_rows[1].find("div", class_="bc-analytics-insights-team-name")

        if not team1_div or not team2_div:
            logging.warning(f"Block #{idx}: Missing team name divs")
            skipped.append({"index": idx, "reason": "missing team name divs"})
            continue

        team1 = team1_div.get_text(strip=True)
        team2 = team2_div.get_text(strip=True)
        logging.debug(f"Block #{idx}: Teams → {team1} vs {team2}")

        # Odds
        odds_divs = block.find_all("div", class_="bc-analytics-best-o")
        if len(odds_divs) < 2:
            logging.warning(f"Block #{idx}: Missing best odds divs (found {len(odds_divs)})")
            skipped.append({"index": idx, "reason": "missing best odds divs"})
            continue

        odd1_raw = odds_divs[0].get_text(strip=True)
        odd2_raw = odds_divs[1].get_text(strip=True)
        logging.debug(f"Block #{idx}: Raw odds → team1: '{odd1_raw}'   team2: '{odd2_raw}'")

        odd1 = odd1_raw if odd1_raw and odd1_raw != '-' else "N/A"
        odd2 = odd2_raw if odd2_raw and odd2_raw != '-' else "N/A"

        odds = {
            "best": {
                "team1": odd1,
                "team2": odd2
            }
        }

        # Link extraction
        form_link = block.find("a", class_="bc-analytics-form-link")
        full_url = None
        analytics_url = None

        if form_link and form_link.has_attr("href"):
            href = form_link["href"]
            full_url = f"https://www.hltv.org{href}" if href.startswith("/") else href
            logging.debug(f"Block #{idx}: Found form link → {href}")

            match_obj = re.search(r"/matches/(\d+)/([^/?#]+)", href)
            if match_obj:
                match_id = match_obj.group(1)
                slug = match_obj.group(2).rstrip('/')
                analytics_url = f"https://www.hltv.org/betting/analytics/{match_id}/{slug}"
                logging.debug(f"Block #{idx}: Built analytics URL → {analytics_url}")
            else:
                logging.debug(f"Block #{idx}: Could not extract match ID/slug from href")
        else:
            logging.debug(f"Block #{idx}: No bc-analytics-form-link found")

        # Decision: save or skip
        if odd1 != "N/A" or odd2 != "N/A":
            entry = {
                "team1": team1,
                "team2": team2,
                "odds": odds,
                "match_url": full_url,
                "analytics_url": analytics_url,
            }
            matches.append(entry)
            logging.info(f"Block #{idx}: ADDED → {team1} vs {team2}  (odds: {odd1} / {odd2})")
        else:
            logging.warning(f"Block #{idx}: SKIPPED → both odds are N/A or '-'")
            skipped.append({
                "index": idx,
                "teams": f"{team1} vs {team2}",
                "raw_odds": [odd1_raw, odd2_raw],
                "reason": "odds are '-' or empty"
            })

    logging.info(f"Summary: {len(matches)} matches added  |  {len(skipped)} blocks skipped")
    if skipped:
        logging.info(f"Skipped blocks reasons: {len(set(s['reason'] for s in skipped))}")

    # Save skipped blocks for inspection
    with open("skipped_blocks_debug.json", "w", encoding="utf-8") as f:
        json.dump(skipped, f, ensure_ascii=False, indent=2)
    logging.info("Saved skipped blocks details to 'skipped_blocks_debug.json'")

    return matches


def main():
    url = "https://www.hltv.org/betting/analytics"

    logging.info(f"Starting scrape of {url}")
    html = get_html(url)

    if not html:
        logging.critical("No HTML content received - aborting")
        return

    logging.info(f"HTML received ({len(html)} characters)")
    results = parse_matches(html)

    logging.info(f"Final result: {len(results)} matches extracted")

    with open("hltv_analytics_odds.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Print summary of extracted matches
    if results:
        print("\nExtracted matches:")
        for m in results:
            o = m["odds"]["best"]
            print(f"{m['team1']} vs {m['team2']}")
            print(f"  best odds → team1: {o['team1']}   team2: {o['team2']}")
            print(f"  analytics: {m.get('analytics_url', '—')}")
            print("─" * 70)
    else:
        print("\nNo matches extracted. Check analytics_scraper_debug.log and skipped_blocks_debug.json")


if __name__ == "__main__":
    main()
