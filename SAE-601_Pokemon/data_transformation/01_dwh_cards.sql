DROP TABLE IF EXISTS public.dwh_cards;

CREATE TABLE public.dwh_cards AS
SELECT DISTINCT card_type, card_name, card_url
FROM public.wrk_decklists;
