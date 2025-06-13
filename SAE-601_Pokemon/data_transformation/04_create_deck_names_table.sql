DROP TABLE IF EXISTS public.deck_names;

CREATE TABLE public.deck_names (
  deck_signature varchar PRIMARY KEY,
  formatted_cards text,
  deck_name varchar
);
