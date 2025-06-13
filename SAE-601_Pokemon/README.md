Voici les étapes à suivre pour exécuter le projet d’analyse du métagame Pokémon TCG.


1) Installer les bibliothèques nécessaires avec la commande :

pip install beautifulsoup4 aiohttp aiofile requests psycopg2 streamlit pandas plotly


2) Instructions d'exécution

Exécuter dans l'ordre

Dans data_collection/ :

- python data_collection/main.py

- python data_collection/card.py

Transformation des données
Dans data_transformation/ :

- python data_transformation/main.py

Visualisation des données
Dans data_viz/ :

- streamlit run data_viz/main.py


Auteurs
Nom : Maxendre Bauthamy, Adel Mouaki-Dadi
