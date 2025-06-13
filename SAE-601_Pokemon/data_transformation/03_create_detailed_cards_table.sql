DROP TABLE IF EXISTS public.detailed_cards;

CREATE TABLE public.detailed_cards (
  card_name varchar,
  element_type varchar,
  evolution_stage varchar,
  hp varchar,
  rarity varchar,
  url varchar,
  image_url varchar,
  is_final_evolution boolean
);
