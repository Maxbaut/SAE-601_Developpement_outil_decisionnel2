DROP TABLE IF EXISTS public.wrk_tournaments;
DROP TABLE IF EXISTS public.wrk_decklists;
DROP TABLE IF EXISTS public.wrk_matches;
DROP TABLE IF EXISTS public.wrk_deck_stats;

CREATE TABLE public.wrk_tournaments (
  tournament_id varchar,
  tournament_name varchar,
  tournament_date timestamp,
  tournament_organizer varchar,
  tournament_format varchar,
  tournament_nb_players int
);

CREATE TABLE public.wrk_decklists (
  tournament_id varchar,
  player_id varchar,
  card_type varchar,
  card_name varchar,
  card_url varchar,
  card_count int,
  deck_signature varchar
);

CREATE TABLE public.wrk_matches (
  tournament_id varchar,
  match_id int,
  player_id varchar,
  score int
);

CREATE TABLE public.wrk_deck_stats (
  deck_signature varchar PRIMARY KEY,
  games_played int,
  wins int,
  losses int,
  winrate float
);


CREATE INDEX idx_decklists_tournament ON public.wrk_decklists(tournament_id);
CREATE INDEX idx_decklists_player ON public.wrk_decklists(player_id);
CREATE INDEX idx_matches_tournament ON public.wrk_matches(tournament_id);
CREATE INDEX idx_matches_player ON public.wrk_matches(player_id);
