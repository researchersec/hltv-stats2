import os
import json
import time
import datetime
import logging
from bs4 import BeautifulSoup
from python_utils import converters
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

def scrape_urls_from_json(json_file_path):
    # Read the JSON file
    try:
        with open(json_file_path, 'r') as file:
            data = json.load(file)
    except FileNotFoundError:
        logging.error(f"JSON file not found: {json_file_path}")
        return
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON file: {json_file_path}")
        return

    # Extract unique URLs (since some URLs may be duplicated)
    urls = list(set(match['url'] for match in data))
    logging.info(f"Found {len(urls)} unique URLs to scrape")

    # Process each URL
    for url in urls:
        soup = get_parsed_page(url)
        if soup:
            # Add your scraping logic here
            # Example: Extract the page title
            title = soup.title.text if soup.title else "No title found"
            logging.info(f"Scraped title from {url}: {title}")

            # Example: Extract specific elements (modify as needed)
            # e.g., soup.find_all('div', class_='some-class')
            # Process the BeautifulSoup object to extract desired data

            # Optional: Save or process the scraped data
            # with open(f"output_{url.split('/')[-1]}.txt", 'w') as f:
            #     f.write(str(soup))

        # Add a delay to avoid overwhelming the server
        time.sleep(1)  # Adjust delay as needed

def main():
    json_file_path = "results.json"  # Path to your JSON file
    scrape_urls_from_json(json_file_path)

if __name__ == "__main__":
    main()
