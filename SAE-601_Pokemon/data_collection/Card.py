import requests
from bs4 import BeautifulSoup
import json
import time
import re

base_url = "https://pocket.limitlesstcg.com"
cards_index_url = f"{base_url}/cards"
headers = {'User-Agent': 'Mozilla/5.0'}

def get_all_set_links():
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
        liens_sets.add(base_url + href)

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
        liens_cartes.add(base_url + href)

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

    rarity = "N/A"
    rarete_labels = [
        "Common", "Uncommon", "Rare", "Holo Rare", "Ultra Rare",
        "Secret Rare", "Rainbow Rare", "Promo"
    ]
    full_text = soup.get_text(separator=" ")
    for label in rarete_labels:
        if re.search(rf"\b{re.escape(label)}\b", full_text):
            rarity = label
            break

    # Extract "Evolves from" information
    evolves_from = "N/A"
    evolves_from_tag = soup.find(string=re.compile("Evolves from"))
    if evolves_from_tag:
        evolves_from = evolves_from_tag.find_next("a").text.strip()

    return {
        "name": full_name,
        "element_type": element_type,
        "evolution_stage": evolution_stage,
        "hp": hp,
        "rarity": rarity,
        "evolves_from": evolves_from,
        "url": card_url,
        "image_url": image_url
    }

def main():
    print("1) Récupération des liens de sets…")
    set_links = get_all_set_links()
    if not set_links:
        print("    Aucun set trouvé. Vérifie que https://pocket.limitlesstcg.com/cards est accessible.")
        return

    print(f"   {len(set_links)} sets trouvés :")
    for url_set in set_links:
        print("    •", url_set)
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
        print("⚠️ Aucun lien de carte trouvé. Peut-être que les sélecteurs ont changé.")
        return

    print(f"\n2) Au total, {len(all_card_links)} cartes récupérées.\n")

    cards_data = []
    for i, card_url in enumerate(all_card_links, start=1):
        print(f"[{i}/{len(all_card_links)}] Scraping {card_url}")
        info = scrape_card_info(card_url)
        if info:
            cards_data.append(info)
        time.sleep(0.3)

    with open("pokemon_cards.json", "w", encoding="utf-8") as f:
        json.dump(cards_data, f, indent=2, ensure_ascii=False)

    print("\n✅ Scraping terminé. Fichier généré : pokemon_cards.json")

if __name__ == "__main__":
    main()
