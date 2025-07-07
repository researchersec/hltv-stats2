import os
import json
import time
import logging
from bs4 import BeautifulSoup
import requests
import zoneinfo
import tzlocal

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

HLTV_COOKIE_TIMEZONE = "Europe/Copenhagen"
HLTV_ZONEINFO = zoneinfo.ZoneInfo(HLTV_COOKIE_TIMEZONE)
LOCAL_TIMEZONE_NAME = tzlocal.get_localzone_name()
LOCAL_ZONEINFO = zoneinfo.ZoneInfo(LOCAL_TIMEZONE_NAME)
FLARE_SOLVERR_URL = "http://localhost:8191/v1"

TEAM_MAP_FOR_RESULTS = []

def get_parsed_page(url):
    logging.info(f"Fetching page: {url}")
    headers = {
        "referer": "https://www.hltv.org/stats",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    cookies = {"hltvTimeZone": HLTV_COOKIE_TIMEZONE}
    post_body = {"cmd": "request.get", "url": url, "maxTimeout": 60000}

    try:
        response = requests.post(FLARE_SOLVERR_URL, headers=headers, json=post_body)
        response.raise_for_status()
        json_response = response.json()
        if json_response.get("status") == "ok":
            html = json_response["solution"]["response"]
            logging.info(f"Successfully fetched page: {url}")
            return BeautifulSoup(html, "lxml")
        else:
            logging.error(f"Failed to fetch page: {url}, status: {json_response.get('status')}")
    except requests.RequestException as e:
        logging.error(f"Error making HTTP request for {url}: {e}")
    return None

def parse_match_details(soup, url):
    match_data = {"url": url, "format": "", "stage": "", "veto": [], "maps": []}

    # Find the relevant section
    maps_section = soup.find("div", class_="col-6 col-7-small")
    if not maps_section:
        logging.warning(f"No maps section found for {url}")
        return match_data

    # Extract match format and stage
    format_div = maps_section.find("div", class_="standard-box veto-box")
    if format_div:
        format_text = format_div.find("div", class_="padding preformatted-text")
        if format_text:
            lines = format_text.text.strip().split("\n")
            match_data["format"] = lines[0].strip() if lines else ""
            match_data["stage"] = lines[1].strip().lstrip("* ") if len(lines) > 1 else ""

    # Extract veto process
    veto_div = maps_section.find("div", class_="padding")
    if veto_div:
        veto_steps = veto_div.find_all("div")
        match_data["veto"] = [step.text.strip() for step in veto_steps]

    # Extract map results
    map_holders = maps_section.find_all("div", class_="mapholder")
    for map_holder in map_holders:
        map_data = {}
        # Map name
        map_name_div = map_holder.find("div", class_="mapname")
        map_data["map"] = map_name_div.text.strip() if map_name_div else "Unknown"

        # Team results
        results = map_holder.find("div", class_="results")
        if results:
            # Team 1 (left)
            team1 = results.find("div", class_="results-left")
            team1_name = team1.find("div", class_="results-teamname").text.strip() if team1 else ""
            team1_score = team1.find("div", class_="results-team-score").text.strip() if team1 else ""
            team1_status = "won" if "won" in team1.get("class", []) else "lost"

            # Team 2 (right)
            team2 = results.find("span", class_="results-right")
            team2_name = team2.find("div", class_="results-teamname").text.strip() if team2 else ""
            team2_score = team2.find("div", class_="results-team-score").text.strip() if team2 else ""
            team2_status = "won" if "won" in team2.get("class", []) else "lost"

            # Half-time scores
            half_scores = results.find("div", class_="results-center-half-score")
            half_score_text = half_scores.text.strip() if half_scores else ""
            
            map_data["team1"] = {
                "name": team1_name,
                "score": team1_score,
                "status": team1_status
            }
            map_data["team2"] = {
                "name": team2_name,
                "score": team2_score,
                "status": team2_status
            }
            map_data["half_scores"] = half_score_text

        match_data["maps"].append(map_data)

    return match_data

def update_results_json(json_file_path):
    # Read the original JSON file
    try:
        with open(json_file_path, 'r') as file:
            results_data = json.load(file)
    except FileNotFoundError:
        logging.error(f"JSON file not found: {json_file_path}")
        return
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON file: {json_file_path}")
        return

    # Get unique URLs to avoid redundant scraping
    unique_urls = list(set(match['url'] for match in results_data))
    logging.info(f"Found {len(unique_urls)} unique URLs to scrape")

    # Dictionary to store scraped data for each URL
    scraped_data = {}

    # Scrape data for each unique URL
    for url in unique_urls:
        soup = get_parsed_page(url)
        if soup:
            match_data = parse_match_details(soup, url)
            scraped_data[url] = match_data
            logging.info(f"Scraped data for {url}: {match_data}")
        else:
            logging.warning(f"Failed to parse page for {url}")
            scraped_data[url] = {"url": url, "format": "", "stage": "", "veto": [], "maps": []}
        time.sleep(1)  # Delay to avoid rate limiting

    # Update each entry in results_data with scraped data
    for match in results_data:
        url = match['url']
        if url in scraped_data:
            match.update({
                "format": scraped_data[url]["format"],
                "stage": scraped_data[url]["stage"],
                "veto": scraped_data[url]["veto"],
                "maps": scraped_data[url]["maps"]
            })

    # Save updated data to a new JSON file
    output_file = "updated_results.json"
    with open(output_file, 'w') as f:
        json.dump(results_data, f, indent=2)
    logging.info(f"Saved updated results to {output_file}")

def main():
    json_file_path = "results.json"  # Path to your JSON file
    update_results_json(json_file_path)

if __name__ == "__main__":
    main()
