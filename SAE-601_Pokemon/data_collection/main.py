from bs4 import BeautifulSoup, Tag
from dataclasses import dataclass, asdict
import aiohttp
import aiofile
import asyncio
import os
import json
import re
import requests
import time

base_url = "https://play.limitlesstcg.com"
cards_base_url = "https://pocket.limitlesstcg.com"
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.106 Safari/537.36'}

# Define base directory for data collection
base_data_dir = "data_collection"
output_dir = os.path.join(base_data_dir, "output")
cards_output_file = os.path.join(base_data_dir, "pokemon_cards.json")

# Ensure directories exist
os.makedirs(output_dir, exist_ok=True)

# Dataclasses used for json generation
@dataclass
class DeckListItem:
    type: str
    url: str
    name: str
    count: int

@dataclass
class Player:
    id: str
    name: str
    placing: str
    country: str
    decklist: list[DeckListItem]

@dataclass
class MatchResult:
    player_id: str
    score: int

@dataclass
class Match:
    match_results: list[MatchResult]

@dataclass
class Tournament:
    id: str
    name: str
    date: str
    organizer: str
    format: str
    nb_players: str
    players: list[Player]
    matches: list[Match]

# Extract the tr tags from a table, omitting the first header
def extract_trs(soup: BeautifulSoup, table_class: str):
    trs = soup.find(class_=table_class).find_all("tr")
    trs.pop(0)  # Remove header
    return trs

# URLs helpers
def construct_standings_url(tournament_id: str):
    return f"/tournament/{tournament_id}/standings?players"

def construct_pairings_url(tournament_id: str):
    return f"/tournament/{tournament_id}/pairings"

def construct_decklist_url(tournament_id: str, player_id: str):
    return f"/tournament/{tournament_id}/player/{player_id}/decklist"

# Extract the previous pairing pages URLs
def extract_previous_pairings_urls(pairings: BeautifulSoup):
    pairing_urls = pairings.find(class_="mini-nav")

    if pairing_urls is None:
        return []

    pairing_urls = pairing_urls.find_all("a")
    pairing_urls.pop(-1)  # Pop the last item in array because it's the current page
    pairing_urls = [a.attrs["href"] for a in pairing_urls]

    return pairing_urls

# Check if the pairing page is a bracket (single elimination)
def is_bracket_pairing(pairings: BeautifulSoup):
    return pairings.find("div", class_="live-bracket") is not None

# Check if the pairing page is a table (swiss rounds)
regex_tournament_id = re.compile(r'[a-zA-Z0-9_\-]*')

def is_table_pairing(pairings: BeautifulSoup):
    pairings = pairings.find("div", class_="pairings")
    if pairings is not None:
        table = pairings.find("table", {'data-tournament': regex_tournament_id})
        if table is not None:
            return True
    return False

# Return a list of matches from a bracket style pairing page
def extract_matches_from_bracket_pairings(pairings: BeautifulSoup):
    matches = []
    matches_div = pairings.find("div", class_="live-bracket").find_all("div", class_="bracket-match")
    for match in matches_div:
        if match.find("a", class_="bye") is not None:
            continue

        players_div = match.find_all("div", class_="live-bracket-player")
        match_results = []
        for index in range(len(players_div)):
            player = players_div[index]
            match_results.append(MatchResult(
                player.attrs["data-id"],
                int(player.find("div", class_="score").attrs["data-score"])
            ))

        matches.append(Match(match_results))

    return matches

# Return a list of matches from a table style pairing page
def extract_matches_from_table_pairings(pairings: BeautifulSoup):
    matches = []
    matches_tr = pairings.find_all("tr", {'data-completed': '1'})

    for match in matches_tr:
        p1 = match.find("td", class_="p1")
        p2 = match.find("td", class_="p2")

        if p1 is not None and p2 is not None:
            matches.append(Match([
                MatchResult(p1.attrs["data-id"], int(p1.attrs["data-count"])),
                MatchResult(p2.attrs["data-id"], int(p2.attrs["data-count"]))
            ]))

    return matches

# Return a list of DeckListItems from a player decklist page
regex_card_url = re.compile(r'pocket\.limitlesstcg\.com/cards/.*')

def extract_decklist(decklist: BeautifulSoup) -> list[DeckListItem]:
    decklist_div = decklist.find("div", class_="decklist")
    cards = []
    if decklist_div is not None:
        cards_a = decklist_div.find_all("a", {'href': regex_card_url})
        for card in cards_a:
            cards.append(DeckListItem(
                card.parent.parent.find("div", class_="heading").text.split(" ")[0],
                card.attrs["href"],
                card.text[2:],
                int(card.text[0])
            ))

    return cards

# Extract a BeautifulSoup object from a URL
async def async_soup_from_url(session: aiohttp.ClientSession, sem: asyncio.Semaphore, url: str, use_cache: bool = True):
    if url is None:
        return None

    cache_filename = "cache" + url
    cache_filename = ''.join(x for x in cache_filename if (x == "/" or x.isalnum()))
    cache_filename = f"{cache_filename}.html"

    html = ""

    if use_cache and os.path.isfile(cache_filename):
        async with sem:
            async with aiofile.async_open(cache_filename, "r") as file:
                html = await file.read()
    else:
        async with session.get(url) as resp:
            html = await resp.text()

        # Ensure the directory exists before writing the file
        directory = os.path.dirname(cache_filename)
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        async with sem:
            async with aiofile.async_open(cache_filename, "w") as file:
                await file.write(html)

    return BeautifulSoup(html, 'html.parser')

async def extract_players(session: aiohttp.ClientSession, sem: asyncio.Semaphore, standings_page: BeautifulSoup, tournament_id: str) -> list[Player]:
    players = []
    player_trs = extract_trs(standings_page, "striped")
    player_ids = [player_tr.find("a", {'href': regex_player_id}).attrs["href"].split('/')[4] for player_tr in player_trs]
    has_decklist = [player_tr.find("a", {'href': regex_decklist_url}) is not None for player_tr in player_trs]
    player_names = [player_tr.attrs['data-name'] for player_tr in player_trs]
    player_placings = [player_tr.attrs.get("data-placing", -1) for player_tr in player_trs]
    player_countries = [player_tr.attrs.get("data-country", None) for player_tr in player_trs]

    decklist_urls = []
    for i in range(len(player_ids)):
        decklist_urls.append(construct_decklist_url(tournament_id, player_ids[i]) if has_decklist[i] else None)

    player_decklists = await asyncio.gather(*[async_soup_from_url(session, sem, url, True) for url in decklist_urls])

    players = []
    for i in range(len(player_ids)):
        if player_decklists[i] is None:
            continue

        players.append(Player(
            player_ids[i],
            player_names[i],
            player_placings[i],
            player_countries[i],
            extract_decklist(player_decklists[i])
        ))

    return players

async def extract_matches(session: aiohttp.ClientSession, sem: asyncio.Semaphore, tournament_id: str) -> list[Match]:
    matches = []
    last_pairings = await async_soup_from_url(session, sem, construct_pairings_url(tournament_id))
    previous_pairings_urls = extract_previous_pairings_urls(last_pairings)
    pairings = await asyncio.gather(*[async_soup_from_url(session, sem, url) for url in previous_pairings_urls])
    pairings.append(last_pairings)

    for pairing in pairings:
        if is_bracket_pairing(pairing):
            matches = matches + extract_matches_from_bracket_pairings(pairing)
        elif is_table_pairing(pairing):
            matches = matches + extract_matches_from_table_pairings(pairing)
        else:
            raise Exception("Unrecognized pairing type")

    return matches

regex_player_id = re.compile(r'/tournament/[a-zA-Z0-9_\-]*/player/[a-zA-Z0-9_]*')
regex_decklist_url = re.compile(r'/tournament/[a-zA-Z0-9_\-]*/player/[a-zA-Z0-9_]*/decklist')

async def handle_tournament_standings_page(session: aiohttp.ClientSession, sem: asyncio.Semaphore, standings_page: BeautifulSoup, tournament_id: str, tournament_name: str, tournament_date: str, tournament_organizer: str, tournament_format: str, tournament_nb_players: int):
    output_file = os.path.join(output_dir, f"{tournament_id}.json")
    print(f"Extracting tournament {tournament_id}", end="... ")

    if os.path.isfile(output_file):
        print("Skipping because tournament is already in output")
        return

    players = await extract_players(session, sem, standings_page, tournament_id)
    if len(players) == 0:
        print("Skipping because no decklist was detected")
        return

    nb_decklists = 0
    for player in players:
        if len(player.decklist) > 0:
            nb_decklists += 1

    matches = await extract_matches(session, sem, tournament_id)

    tournament = Tournament(
        tournament_id,
        tournament_name,
        tournament_date,
        tournament_organizer,
        tournament_format,
        tournament_nb_players,
        players,
        matches
    )

    print(f"{len(players)} players, {nb_decklists} decklists, {len(matches)} matches")

    with open(output_file, "w") as f:
        json.dump(asdict(tournament), f, indent=2)

first_tournament_page = "/tournaments/completed?game=POCKET&format=STANDARD&platform=all&type=online&time=all"
regex_standings_url = re.compile(r'/tournament/[a-zA-Z0-9_\-]*/standings')

async def handle_tournament_list_page(session: aiohttp.ClientSession, sem: asyncio.Semaphore, url: str):
    soup = await async_soup_from_url(session, sem, url, False)
    current_page = int(soup.find("ul", class_="pagination").attrs["data-current"])
    max_page = int(soup.find("ul", class_="pagination").attrs["data-max"])
    print(f"Extracting completed tournaments page {current_page}")

    tournament_trs = extract_trs(soup, "completed-tournaments")
    tournament_ids = [tournament_tr.find("a", {'href': regex_standings_url}).attrs["href"].split('/')[2] for tournament_tr in tournament_trs]
    tournament_names = [tournament_tr.attrs['data-name'] for tournament_tr in tournament_trs]
    tournament_dates = [tournament_tr.attrs['data-date'] for tournament_tr in tournament_trs]
    tournament_organizers = [tournament_tr.attrs['data-organizer'] for tournament_tr in tournament_trs]
    tournament_formats = [tournament_tr.attrs['data-format'] for tournament_tr in tournament_trs]
    tournament_nb_players = [tournament_tr.attrs['data-players'] for tournament_tr in tournament_trs]

    standings_urls = [construct_standings_url(tournament_id) for tournament_id in tournament_ids]
    standings = await asyncio.gather(*[async_soup_from_url(session, sem, url) for url in standings_urls])

    for i in range(len(tournament_ids)):
        await handle_tournament_standings_page(session, sem, standings[i], tournament_ids[i], tournament_names[i], tournament_dates[i], tournament_organizers[i], tournament_formats[i], tournament_nb_players[i])

    if current_page < max_page:
        await handle_tournament_list_page(session, sem, f"{first_tournament_page}&page={current_page+1}")

def get_all_set_links():
    cards_index_url = f"{cards_base_url}/cards"
    try:
        r = requests.get(cards_index_url, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print("Impossible d'atteindre la page des sets :", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    liens_sets = set()

    for a in soup.find_all("a", href=re.compile(r"^/cards/[A-Za-z0-9]+$")):
        href = a["href"]
        liens_sets.add(cards_base_url + href)

    return sorted(liens_sets)

def get_all_card_links_from_set(set_url):
    try:
        r = requests.get(set_url, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"  → Impossible de charger le set {set_url} :", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    liens_cartes = set()

    pattern_card = re.compile(r"^/cards/[A-Za-z0-9]+/[0-9]+$")
    for a in soup.find_all("a", href=pattern_card):
        href = a["href"]
        liens_cartes.add(cards_base_url + href)

    return sorted(liens_cartes)

def scrape_card_info(card_url):
    try:
        r = requests.get(card_url, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"    → Échec du chargement de la carte {card_url} : {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    img_tag = soup.select_one("div.card-image img")
    image_url = img_tag["src"].strip() if img_tag and img_tag.has_attr("src") else None

    span_name = soup.select_one("span.card-text-name a")
    name_simple = span_name.text.strip() if span_name else "N/A"

    parts = card_url.rstrip("/").split("/")
    set_part = parts[-2]
    num_part = parts[-1]
    set_id = f"{set_part}-{num_part}"
    full_name = f"{name_simple} ({set_id})"

    title_p = soup.find("p", class_="card-text-title")
    element_type = "N/A"
    hp = "N/A"
    if title_p:
        segments = [seg.strip() for seg in title_p.text.split(" - ")]
        if len(segments) >= 2:
            element_type = segments[1]
        if len(segments) >= 3:
            hp_match = re.search(r"(\d+)\s*HP", segments[2])
            hp = hp_match.group(1) if hp_match else segments[2]

    evo_p = soup.find("p", class_="card-text-type")
    evolution_stage = "N/A"
    if evo_p:
        parts_ev = [part.strip() for part in evo_p.text.split("-")]
        if len(parts_ev) >= 2:
            evolution_stage = parts_ev[1]

    # Extraire les informations d'évolution
    evolves_from = None
    evolves_from_p = soup.find("p", class_="card-text-evolves-from")
    if evolves_from_p:
        evolves_from = evolves_from_p.text.split(":")[1].strip()

    rarity = "N/A"
    rarete_labels = ["Common", "Uncommon", "Rare", "Holo Rare", "Ultra Rare", "Secret Rare", "Rainbow Rare", "Promo"]
    full_text = soup.get_text(separator=" ")
    for label in rarete_labels:
        if re.search(rf"\b{re.escape(label)}\b", full_text):
            rarity = label
            break

    # Déterminer si le Pokémon est à son dernier stade d'évolution
    is_final_evolution = evolves_from is None

    return {
        "name": full_name,
        "element_type": element_type,
        "evolution_stage": evolution_stage,
        "hp": hp,
        "rarity": rarity,
        "url": card_url,
        "image_url": image_url,
        "evolves_from": evolves_from,
        "is_final_evolution": is_final_evolution
    }


async def main():
    connector = aiohttp.TCPConnector(limit=20)
    sem = asyncio.Semaphore(50)

    async with aiohttp.ClientSession(base_url=base_url, connector=connector) as session:
        await handle_tournament_list_page(session, sem, first_tournament_page)

    set_links = get_all_set_links()
    if not set_links:
        print("Aucun set trouvé. Vérifie que https://pocket.limitlesstcg.com/cards est accessible.")
        return

    print(f"{len(set_links)} sets trouvés :")
    for url_set in set_links:
        print("•", url_set)
    print()

    all_card_links = []
    for idx, set_url in enumerate(set_links, start=1):
        print(f"[{idx}/{len(set_links)}] Exploration du set {set_url}…")
        cartes_du_set = get_all_card_links_from_set(set_url)
        print(f"    {len(cartes_du_set)} cartes dans ce set.")
        all_card_links.extend(cartes_du_set)
        time.sleep(0.5)

    all_card_links = sorted(set(all_card_links))

    if not all_card_links:
        print("Aucun lien de carte trouvé. Peut-être que les sélecteurs ont changé.")
        return

    print(f"\nAu total, {len(all_card_links)} cartes récupérées.\n")

    cards_data = []
    for i, card_url in enumerate(all_card_links, start=1):
        print(f"[{i}/{len(all_card_links)}] Scraping {card_url}")
        info = scrape_card_info(card_url)
        if info:
            cards_data.append(info)
        time.sleep(0.3)

    with open(cards_output_file, "w", encoding="utf-8") as f:
        json.dump(cards_data, f, indent=2, ensure_ascii=False)

    print("\n Scraping terminé. Fichier généré : pokemon_cards.json")

if __name__ == "__main__":
    asyncio.run(main())