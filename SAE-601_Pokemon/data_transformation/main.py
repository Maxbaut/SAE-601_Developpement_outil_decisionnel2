import psycopg
import os
import json
import re
from datetime import datetime

# Paramètres de connexion PostgreSQL
DB_NAME = "PokemonDB"
DB_USER = "postgres"
DB_PASSWORD = "1234"
DB_HOST = "127.0.0.1"
DB_PORT = "5432"

def get_connection_string():
    """Retourne la chaîne de connexion à la base de données PostgreSQL."""
    return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def get_absolute_path(relative_path):
    """Convertit un chemin relatif en chemin absolu basé sur le répertoire courant du script."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), relative_path))

def execute_sql_script(relative_path):
    """Exécute un script SQL à partir d'un fichier."""
    full_path = get_absolute_path(relative_path)
    with psycopg.connect(get_connection_string()) as conn:
        with conn.cursor() as cur:
            with open(full_path, encoding="utf-8") as f:
                cur.execute(f.read())

def normalize_player_id(player_id):
    """Normalise l'identifiant du joueur."""
    return re.sub(r'[^a-z0-9]', '', player_id.lower())

def load_json_data(file_path):
    """Charge les données JSON à partir d'un fichier."""
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)

def insert_data_from_json(directory, sql_query, data_extractor):
    """Insère des données dans la base de données à partir de fichiers JSON."""
    data = []
    for file in os.listdir(directory):
        file_path = os.path.join(directory, file)
        tournament = load_json_data(file_path)
        data.extend(data_extractor(tournament))

    with psycopg.connect(get_connection_string()) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql_query, data)

def extract_tournament_data(tournament):
    """Extrait les données de tournoi."""
    return [(tournament['id'], tournament['name'], datetime.strptime(tournament['date'], '%Y-%m-%dT%H:%M:%S.000Z'),
             tournament['organizer'], tournament['format'], int(tournament['nb_players']))]

def extract_decklist_data(tournament):
    """Extrait les données de liste de decks."""
    tournament_id = tournament['id']
    decklist_data = []
    for player in tournament['players']:
        player_id = normalize_player_id(player['id'])
        deck_signature = f"{tournament_id}_{player_id}"
        for card in player['decklist']:
            decklist_data.append((
                tournament_id,
                player_id,
                card['type'],
                card['name'],
                card['url'],
                int(card['count']),
                deck_signature
            ))
    return decklist_data

def extract_match_data(tournament):
    """Extrait les données de matchs."""
    tournament_id = tournament['id']
    match_data = []
    for idx, match in enumerate(tournament.get('matches', [])):
        for result in match['match_results']:
            player_id = normalize_player_id(result['player_id'])
            score = result['score']
            match_data.append((tournament_id, idx, player_id, score))
    return match_data

def build_evolution_hierarchy(cards_data):
    """Construire une hiérarchie d'évolution à partir des données des cartes."""
    evolution_hierarchy = {}
    for card in cards_data:
        pokemon_name = card["name"].split(" (")[0]
        evolves_from = card.get("evolves_from", "N/A")
        if evolves_from != "N/A":
            if evolves_from not in evolution_hierarchy:
                evolution_hierarchy[evolves_from] = []
            evolution_hierarchy[evolves_from].append(pokemon_name)
    return evolution_hierarchy

def check_final_evolution(pokemon_name, evolution_hierarchy):
    """Vérifie si un Pokémon est une évolution finale."""
    return pokemon_name not in evolution_hierarchy

def get_final_evolution_pokemons(detailed_cards_data):
    """Identifie les Pokémon au stade final de leur évolution."""
    evolution_hierarchy = build_evolution_hierarchy(detailed_cards_data)
    final_evolution_pokemons = set()

    for card in detailed_cards_data:
        pokemon_name = card["name"].split(" (")[0]
        if check_final_evolution(pokemon_name, evolution_hierarchy):
            final_evolution_pokemons.add(pokemon_name)

    return final_evolution_pokemons

def calculate_winrate():
    """Calcule le winrate et met à jour la table des statistiques de deck."""
    with psycopg.connect(get_connection_string()) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM wrk_deck_stats")

            cur.execute("""
                SELECT
                    m.tournament_id || '_' || m.player_id AS deck_signature,
                    COUNT(*) AS games_played,
                    SUM(CASE WHEN m.score = 2 THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN m.score = 0 THEN 1 ELSE 0 END) AS losses,
                    ROUND(SUM(CASE WHEN m.score = 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS winrate
                FROM
                    wrk_matches m
                GROUP BY
                    deck_signature
            """)
            winrate_data = cur.fetchall()

            for row in winrate_data:
                cur.execute("""
                    INSERT INTO wrk_deck_stats (deck_signature, games_played, wins, losses, winrate)
                    VALUES (%s, %s, %s, %s, %s)
                """, row)

def insert_detailed_cards():
    """Insère des données détaillées sur les cartes dans la base de données."""
    pokemon_cards_path = get_absolute_path("../data_collection/pokemon_cards.json")
    with open(pokemon_cards_path, 'r', encoding='utf-8') as f:
        detailed_cards_data = json.load(f)

    final_evolution_pokemons = get_final_evolution_pokemons(detailed_cards_data)

    with psycopg.connect(get_connection_string()) as conn:
        with conn.cursor() as cur:
            for card in detailed_cards_data:
                pokemon_name = card["name"].split(" (")[0]
                is_final_evolution = pokemon_name in final_evolution_pokemons

                cur.execute("""
                    INSERT INTO public.detailed_cards
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    card["name"],
                    card["element_type"],
                    card["evolution_stage"],
                    card["hp"],
                    card["rarity"],
                    card["url"],
                    card["image_url"],
                    is_final_evolution
                ))

def get_all_deck_signatures():
    """Récupère tous les deck_signature uniques de la base de données."""
    with psycopg.connect(get_connection_string()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT deck_signature
                FROM wrk_decklists
            """)
            deck_signatures = [row[0] for row in cur.fetchall()]

    return deck_signatures

def get_cards_in_deck(deck_signature):
    """Récupère les cartes d'un deck donné."""
    with psycopg.connect(get_connection_string()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT card_name, card_count
                FROM wrk_decklists
                WHERE deck_signature = %s
            """, (deck_signature,))

            cards = cur.fetchall()

    return cards

def format_deck_cards(cards):
    """Formate les cartes du deck selon le format souhaité."""
    formatted_cards = [f"{card[0]}:{card[1]}" for card in cards]
    return ",".join(formatted_cards)

def clean_pokemon_name(pokemon_name):
    """Nettoie le nom du Pokémon en supprimant les parenthèses et les suffixes comme 'ex'."""
    cleaned_name = re.sub(r'\s*\(.*?\)', '', pokemon_name)
    cleaned_name = re.sub(r'\s*ex\s*$', '', cleaned_name, flags=re.IGNORECASE).strip()
    return cleaned_name

def get_final_evolution_pokemons_in_deck(deck_signature):
    """Récupère les noms des Pokémon à leur dernier stade d'évolution dans un deck donné."""
    with psycopg.connect(get_connection_string()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT d.card_name
                FROM wrk_decklists w
                JOIN detailed_cards d ON w.card_name = d.card_name
                WHERE w.deck_signature = %s AND d.is_final_evolution = TRUE
            """, (deck_signature,))

            final_evolution_pokemons = [row[0] for row in cur.fetchall()]

    return final_evolution_pokemons

def generate_deck_name(deck_signature):
    """Génère le nom du deck basé sur les Pokémon à leur dernier stade d'évolution."""
    final_evolution_pokemons = get_final_evolution_pokemons_in_deck(deck_signature)
    cleaned_pokemon_names = [clean_pokemon_name(name) for name in final_evolution_pokemons]
    deck_name = " - ".join(cleaned_pokemon_names)
    return deck_name

def store_deck_info(deck_signature, formatted_cards, deck_name):
    """Stocke les informations du deck dans la base de données."""
    with psycopg.connect(get_connection_string()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO public.deck_names (deck_signature, formatted_cards, deck_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (deck_signature) DO UPDATE
                SET formatted_cards = EXCLUDED.formatted_cards, deck_name = EXCLUDED.deck_name
            """, (deck_signature, formatted_cards, deck_name))

def main():
    print("Creating work tables...")
    execute_sql_script("00_create_wrk_tables.sql")

    output_directory = get_absolute_path("../data_collection/output")

    print("Inserting tournament data...")
    insert_data_from_json(output_directory, """
        INSERT INTO public.wrk_tournaments VALUES (%s, %s, %s, %s, %s, %s)
    """, extract_tournament_data)

    print("Inserting decklist data...")
    insert_data_from_json(output_directory, """
        INSERT INTO public.wrk_decklists (tournament_id, player_id, card_type, card_name, card_url, card_count, deck_signature)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, extract_decklist_data)

    print("Inserting match data...")
    insert_data_from_json(output_directory, """
        INSERT INTO public.wrk_matches VALUES (%s, %s, %s, %s)
    """, extract_match_data)

    print("Building card dimension...")
    execute_sql_script("01_dwh_cards.sql")

    print("Building deck statistics...")
    execute_sql_script("02_analysis_deck_stats.sql")

    print("Creating detailed cards table...")
    execute_sql_script("03_create_detailed_cards_table.sql")

    print("Creating deck names table...")
    execute_sql_script("04_create_deck_names_table.sql")

    print("Inserting detailed cards data...")
    insert_detailed_cards()

    

    # Récupérer tous les deck_signature et traiter chaque deck
    deck_signatures = get_all_deck_signatures()
    for deck_signature in deck_signatures:
        cards = get_cards_in_deck(deck_signature)
        formatted_cards = format_deck_cards(cards)
        deck_name = generate_deck_name(deck_signature)

        # Stocker les informations du deck dans la base de données
        store_deck_info(deck_signature, formatted_cards, deck_name)

    print("Data transformation completed successfully!")

if __name__ == "__main__":
    main()
