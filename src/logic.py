from typing import Iterable, Generator
import time
import requests
from itertools import chain

try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda *args, **kwargs: args[0]

BASE_URL = "api.the-odds-api.com/v4"
PROTOCOL = "https://"


class APIException(RuntimeError):
    def __str__(self):
        return f"('{self.args[0]}', '{self.args[1].json()['message']}')"


class AuthenticationException(APIException):
    pass


class RateLimitException(APIException):
    pass


def handle_faulty_response(response: requests.Response):
    if response.status_code == 401:
        raise AuthenticationException("Failed to authenticate with the API. Is the API key valid?", response)
    elif response.status_code == 429:
        raise RateLimitException("Encountered API rate limit.", response)
    else:
        raise APIException("Unknown issue arose while trying to access the API.", response)


def get_sports(key: str) -> set[str]:
    url = f"{BASE_URL}/sports/"
    escaped_url = PROTOCOL + requests.utils.quote(url)
    querystring = {"apiKey": key}

    response = requests.get(escaped_url, params=querystring)
    if not response:
        handle_faulty_response(response)

    return {item["key"] for item in response.json()}


def get_upcoming_events_data(key: str, sport: str, region: str = "eu", odds_format: str = "decimal"):
    url = f"{BASE_URL}/sports/{sport}/odds/"
    escaped_url = PROTOCOL + requests.utils.quote(url)
    querystring = {
        "apiKey": key,
        "regions": region,
        "oddsFormat": odds_format,
    }

    response = requests.get(escaped_url, params=querystring)
    if not response:
        handle_faulty_response(response)

    # Ensure that 'upcoming' events are filtered
    upcoming_events = [event for event in response.json() if "commence_time" in event and int(event["commence_time"]) > time.time()]

    return upcoming_events


def process_upcoming_events_data(events: Iterable) -> Generator[dict, None, None]:
    for event in events:
        # Check if the event has a 'status' field and if it indicates the match is upcoming
        status = event.get("status", "").lower()
        if "commence_time" in event and (status == "upcoming" or status == "pre-match"):
            start_time = int(event["commence_time"])

            best_odd_per_outcome = {}
            for bookmaker in event["bookmakers"]:
                bookie_name = bookmaker["title"]
                for outcome in bookmaker["markets"][0]["outcomes"]:
                    outcome_name = outcome["name"]
                    odd = outcome["price"]
                    if outcome_name not in best_odd_per_outcome.keys() or odd > best_odd_per_outcome[outcome_name][1]:
                        best_odd_per_outcome[outcome_name] = (bookie_name, odd)

            total_implied_odds = sum(1/i[1] for i in best_odd_per_outcome.values())
            match_name = f"{event['home_team']} v. {event['away_team']}"
            time_to_start = (start_time - time.time())/3600
            league = event["sport_key"]
            yield {
                "match_name": match_name,
                "match_start_time": start_time,
                "hours_to_start": time_to_start,
                "league": league,
                "best_outcome_odds": best_odd_per_outcome,
                "total_implied_odds": total_implied_odds,
            }




def get_upcoming_arbitrage_opportunities(key: str, region: str, cutoff: float):
    sports = get_sports(key)
    for sport in sports:
        upcoming_events_data = get_upcoming_events_data(key, sport, region=region)
        if "message" not in upcoming_events_data:
            results = process_upcoming_events_data(upcoming_events_data)
            arbitrage_opportunities = filter(lambda x: 0 < x["total_implied_odds"] < 1-cutoff, results)
            yield from arbitrage_opportunities


def main():
    # Provide your API key and region
    YOUR_API_KEY = "your_api_key"
    region = "your_region"

    cutoff = 0.05  # Adjust the cutoff as needed

    upcoming_arbitrage_opportunities = get_upcoming_arbitrage_opportunities(YOUR_API_KEY, region, cutoff)

    for opportunity in upcoming_arbitrage_opportunities:
        print(opportunity)


if __name__ == '__main__':
    main()
