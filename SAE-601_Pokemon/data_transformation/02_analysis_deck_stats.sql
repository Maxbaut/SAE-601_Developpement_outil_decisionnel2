-- Étape 1 : Signature des decks
DROP TABLE IF EXISTS wrk_player_decks;
CREATE TABLE wrk_player_decks AS
SELECT
  tournament_id,
  player_id,
  STRING_AGG(CONCAT(card_name, ':', card_count), ',' ORDER BY card_name) AS deck_signature
FROM wrk_decklists
GROUP BY tournament_id, player_id;

-- Étape 2 : Associer chaque match à une deck_signature
DROP TABLE IF EXISTS wrk_match_decks;
CREATE TABLE wrk_match_decks AS
SELECT
  m.tournament_id,
  m.match_id,
  m.player_id,
  m.score,
  d.deck_signature
FROM wrk_matches m
JOIN wrk_player_decks d ON m.tournament_id = d.tournament_id AND m.player_id = d.player_id;

-- Étape 3 : Calculer winrate par deck_signature
DROP TABLE IF EXISTS wrk_deck_winrates;
CREATE TABLE wrk_deck_winrates AS
SELECT
  deck_signature,
  COUNT(*) AS games_played,
  SUM(CASE WHEN score = 2 THEN 1 ELSE 0 END) AS wins,
  SUM(CASE WHEN score = 0 THEN 1 ELSE 0 END) AS losses,
  ROUND(SUM(CASE WHEN score = 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS winrate
FROM wrk_match_decks
GROUP BY deck_signature;

-- Étape 4 : Extraire la version la plus élevée commençant par A
DROP TABLE IF EXISTS wrk_deck_versions;
CREATE TABLE wrk_deck_versions AS
SELECT
  sub.deck_signature,
  MAX(sub.version_clean) AS version
FROM (
  SELECT
    d.deck_signature,
    REGEXP_REPLACE(SPLIT_PART(card_name, '(', 2), '[^A-Za-z0-9].*', '') AS version_clean
  FROM wrk_player_decks d
  JOIN wrk_decklists l ON d.tournament_id = l.tournament_id AND d.player_id = l.player_id
  WHERE card_name LIKE '%(A%'
) AS sub
WHERE sub.version_clean ~ '^A'
GROUP BY sub.deck_signature;

-- Étape 5 : Première carte Pokémon dans chaque deck
DROP TABLE IF EXISTS wrk_deck_first_pokemon;
CREATE TABLE wrk_deck_first_pokemon AS
SELECT DISTINCT ON (d.deck_signature)
  d.deck_signature,
  l.card_name AS first_pokemon_card_name
FROM wrk_player_decks d
JOIN wrk_decklists l ON d.tournament_id = l.tournament_id AND d.player_id = l.player_id
WHERE l.card_type = 'Pokémon' AND l.card_name LIKE '%(A%'
ORDER BY d.deck_signature, l.card_name;

-- Étape 6 : Résumé global avec PRIMARY KEY
DROP TABLE IF EXISTS wrk_deck_stats;
CREATE TABLE wrk_deck_stats AS
SELECT
  w.deck_signature,
  w.games_played,
  w.wins,
  w.losses,
  w.winrate,
  v.version AS deck_version,
  f.first_pokemon_card_name
FROM wrk_deck_winrates w
LEFT JOIN wrk_deck_versions v ON w.deck_signature = v.deck_signature
LEFT JOIN wrk_deck_first_pokemon f ON w.deck_signature = f.deck_signature;

-- Ajouter la contrainte PRIMARY KEY après la création
ALTER TABLE wrk_deck_stats ADD CONSTRAINT pk_deck_stats PRIMARY KEY (deck_signature);