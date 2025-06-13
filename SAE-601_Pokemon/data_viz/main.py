import streamlit as st
import pandas as pd
import psycopg2 as psycopg
import plotly.express as px
import plotly.graph_objects as go

# Connexion PostgreSQL
DB_NAME = "PokemonDB"
DB_USER = "postgres"
DB_PASSWORD = "1234"
DB_HOST = "127.0.0.1"
DB_PORT = "5432"

@st.cache_resource
def get_connection():
    return psycopg.connect(
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?client_encoding=utf8"
    )

# Chargement des données
def load_deck_stats():
    conn = get_connection()
    return pd.read_sql("SELECT * FROM wrk_deck_stats;", conn)

def load_first_pokemon():
    conn = get_connection()
    return pd.read_sql("SELECT * FROM wrk_deck_first_pokemon;", conn)

def load_decklists():
    conn = get_connection()
    return pd.read_sql("SELECT * FROM wrk_deck_versions;", conn)

# App Streamlit
st.set_page_config(page_title="Pokémon TCG Pocket - Metagame", layout="wide")
st.title("📊 Pokémon TCG Pocket - Analyse du Metagame")

tab1, tab2 = st.tabs(["🏆 Vue d'ensemble", "🔬 Étude d’un deck"])

# Chargement des datasets
df_stats = load_deck_stats()
df_first = load_first_pokemon()
df_decklists = load_decklists()

# Fusion avec la première carte Pokémon
df_merged = df_stats.merge(df_first, on="deck_signature", how="left")

# Gestion de la colonne principale
if "first_pokemon_card_name" in df_merged.columns:
    df_merged["main_card"] = df_merged["first_pokemon_card_name"]
elif "first_pokemon_card_name_y" in df_merged.columns:
    df_merged["main_card"] = df_merged["first_pokemon_card_name_y"]
elif "card_name" in df_merged.columns:
    df_merged["main_card"] = df_merged["card_name"]
else:
    st.error("⚠️ La colonne contenant la carte principale n'a pas été trouvée.")
    df_merged["main_card"] = "inconnue"

# Convertir les versions de deck en catégories ordonnées
deck_version_order = ["A1", "A1a", "A2", "A2a", "A2b", "A3", "A3a"]
df_merged["deck_version"] = pd.Categorical(df_merged["deck_version"], categories=deck_version_order, ordered=True)

# Tab 1 : Vue d'ensemble
with tab1:
    st.subheader("📋 Tableau des decks")
    df_filtered = df_merged[df_merged["games_played"] > 50]
    df_filtered = df_filtered.sort_values("deck_version")
    st.dataframe(df_filtered[["main_card", "games_played", "winrate", "deck_version"]])

    st.subheader("🎯 Nuage de points : Winrate par version")
    fig1 = px.scatter(
        df_filtered,
        x="deck_version",
        y="winrate",
        size="games_played",
        color="main_card",
        hover_name="main_card",
        title=" ",
        labels={
            "winrate": "Taux de victoire (%)",
            "deck_version": "Version",
            "main_card": "Carte principale",
            "games_played": "Nombre de parties"
        },
        size_max=80,
        height=600,
        width=1200,
        category_orders={"deck_version": deck_version_order}
    )
    fig1.update_layout(
        title_font_size=20,
        legend_title="Carte principale",
        legend=dict(itemsizing='constant', font=dict(size=12)),
        xaxis=dict(title_font=dict(size=16), tickfont=dict(size=14)),
        yaxis=dict(title_font=dict(size=16), tickfont=dict(size=14)),
        margin=dict(l=40, r=40, t=60, b=40)
    )
    st.plotly_chart(fig1, use_container_width=False)

    st.subheader("📈 Courbe : Nombre d'utilisations des decks par version")
    usage_data = df_merged.groupby(["main_card", "deck_version"]).agg({"games_played": "sum"}).reset_index()
    usage_data = usage_data.sort_values("deck_version")

    fig2 = go.Figure()
    for card in usage_data["main_card"].unique():
        subset = usage_data[usage_data["main_card"] == card]
        fig2.add_trace(go.Scatter(
            x=subset["deck_version"],
            y=subset["games_played"],
            mode='lines+markers',
            name=card
        ))

    fig2.update_layout(
        title="",
        xaxis_title="Version de deck",
        yaxis_title="Nombre de parties",
        height=600,
        width=1200,
        xaxis={'categoryorder':'array', 'categoryarray':deck_version_order}
    )
    st.plotly_chart(fig2, use_container_width=False)

# Tab 2 : Étude d’un deck
with tab2:
    st.subheader("🔍 Analyse détaillée d’un deck")

    selected_signature = st.selectbox("Choisis un deck :", df_merged["deck_signature"].unique())
    deck_info = df_merged[df_merged["deck_signature"] == selected_signature].iloc[0]

    st.markdown(f"### 🧬 Détails du deck `{selected_signature}`")
    st.markdown(f"- **Carte principale** : {deck_info['main_card']}")
    st.markdown(f"- **Total de parties jouées** : {deck_info['games_played']}")
    st.markdown(f"- **Winrate** : {deck_info['winrate']} %")
    st.markdown(f"- **Version** : {deck_info['deck_version']}")

