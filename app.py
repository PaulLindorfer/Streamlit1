import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from io import StringIO

# Funktion, um das Datum in Epoch Sekunden umzuwandeln
def date_to_epoch(date):
    dt = datetime.strptime(date, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)  # Millisekunden

# Funktion, um das Datum im benötigten Format zu generieren
def format_date_for_url(date):
    return date.strftime("%Y-%m-%dT%H%M%S")

# Streamlit Layout
st.title('API Abfrage mit Streamlit und Plotly')

# Schieberegler für Datumsauswahl (letzte 45 Tage)
today = datetime.today()
days = [today - timedelta(days=i) for i in range(45)]  # Jetzt 45 Tage
dates = [d.strftime("%Y-%m-%d") for d in days]

selected_date = st.selectbox("Wählen Sie einen der letzten 45 Tage", dates)

# Schieberegler für die Anzahl der Tage, die abgerufen werden sollen (max. 45 Tage)
num_days = st.slider("Wählen Sie die Anzahl der Tage", min_value=1, max_value=45, value=1)

# Umwandlung des ausgewählten Datums in Epoch Sekunden
epoch_time = date_to_epoch(selected_date)
end_epoch_time = epoch_time + num_days * 24 * 60 * 60 * 1000  # Berechne End-Zeitstempel

st.write(f"Epoch Zeit für {selected_date}: {epoch_time}")
st.write(f"End-Epoch Zeit nach {num_days} Tagen: {end_epoch_time}")

# API-Abfrage für Marktpreis mit Start- und End-Zeitstempel
url_marketprice = f"https://api.awattar.at/v1/marketdata?start={epoch_time}&end={end_epoch_time}"
response_marketprice = requests.get(url_marketprice)
data_marketprice = response_marketprice.json()

# Verarbeitung der Marktpreisdaten
df_marketprice = pd.DataFrame(data_marketprice['data'])

# Umwandlung der Start-Zeitstempel in ein lesbares Datumsformat
df_marketprice['start_datetime'] = pd.to_datetime(df_marketprice['start_timestamp'], unit='ms')

# Berechnung der Start- und Enddaten für den CSV-Download (flexibel je nach Auswahl)
start_date = datetime.strptime(selected_date, "%Y-%m-%d")
end_date = start_date + timedelta(days=num_days)  # Berechne das Enddatum basierend auf dem Schieberegler

# Formatieren der Daten für den Download-Link
start_date_str = format_date_for_url(start_date)
end_date_str = format_date_for_url(end_date)

# URL für den CSV-Download
download_url = f"https://transparency.apg.at/api/v1/AE/Download/German/PT15M/{start_date_str}/{end_date_str}?p_aeMode=Export&resolution=PT15M"

# CSV-Datei herunterladen und in Pandas DataFrame umwandeln
response_csv = requests.get(download_url)
csv_data = StringIO(response_csv.text)  # CSV-Text in einen StringIO-Buffer laden
df_csv = pd.read_csv(csv_data, sep=';')  # CSV in ein DataFrame laden

pd.set_option('future.no_silent_downcasting', True)
df_csv.columns = ["Zeit_von", "Zeit_bis", "AE_Erstveröffentlichung", "AE_Vorläufig", "AE_Final"]
df_csv["AE"] = df_csv[["AE_Final", "AE_Vorläufig", "AE_Erstveröffentlichung"]].bfill(axis=1).iloc[:, 0]
df_csv["AE"] = df_csv["AE"].infer_objects()


# Vorbereitung df_csv
df_csv["Zeit_von"] = pd.to_datetime(df_csv["Zeit_von"], format="%d.%m.%Y %H:%M:%S")
df_csv["AE"] = df_csv["AE"].str.replace(",", ".").astype(float)

# AE-Typ bestimmen
def ae_typ(row):
    if pd.notna(row["AE_Final"]):
        return "AE_Final"
    elif pd.notna(row["AE_Vorläufig"]):
        return "AE_Vorläufig"
    elif pd.notna(row["AE_Erstveröffentlichung"]):
        return "AE_Erstveröffentlichung"
    else:
        return None

df_csv["AE_Typ"] = df_csv.apply(ae_typ, axis=1)

# Gleitender Mittelwert über 4 Intervalle (1h)
df_csv["AE_MA_1h"] = df_csv["AE"].rolling(window=4, min_periods=1).mean()


# Vorbereitung df_marketprice
df_marketprice["start_datetime"] = pd.to_datetime(df_marketprice["start_datetime"])



# Farben für Typen (klar unterscheidbar)
ae_farbmap = {
    "AE_Final": "#2ca02c",              # Grün
    "AE_Vorläufig": "#ffbb78",          # Hellorange (nicht zu nah an Spotpreis)
    "AE_Erstveröffentlichung": "#1f77b4"  # Blau
}

# Plot initialisieren
fig = go.Figure()

# 1. Linie (AE unbearbeitet)
fig.add_trace(go.Scatter(
    x=df_csv["Zeit_von"],
    y=df_csv["AE"],
    mode="lines",
    name="AE",
    line=dict(color="#7f7f7f", width=1),  # Dünn, neutral grau
    hoverinfo="skip"
))

# 2. Marker je AE-Typ
for ae_typ_name, farbe in ae_farbmap.items():
    df_typ = df_csv[df_csv["AE_Typ"] == ae_typ_name]
    fig.add_trace(go.Scatter(
        x=df_typ["Zeit_von"],
        y=df_typ["AE"],
        mode='markers',
        name=ae_typ_name,
        marker=dict(color=farbe, size=6),
        customdata=df_typ["AE"].values
    ))

# 3. Gleitender Mittelwert
fig.add_trace(go.Scatter(
    x=df_csv["Zeit_von"],
    y=df_csv["AE_MA_1h"],
    mode='lines',
    name='AE (1h gleitend)',
    line=dict(color='#17becf', width=1, dash='dash'),  # Türkis, dünn, gestrichelt
    hovertemplate="%{x}<br>AE Ø1h: %{y:.2f} €/MWh"
))

# 4. Spotpreis (hervorgehoben in kräftigem Violett)
fig.add_trace(go.Scatter(
    x=df_marketprice["start_datetime"],
    y=df_marketprice["marketprice"],
    mode='lines+markers',
    name='Spotpreis (1h)',
    line=dict(color='#8e44ad', width=3),  # Kräftiges Violett
    marker=dict(size=6),
    hovertemplate="%{x}<br>Spotpreis: %{y:.2f} €/MWh"
))

# Streamlit Button zur dynamischen Y-Achsenbegrenzung
if st.button('Setze y-Achse auf [-150, 300]'):
    fig.update_layout(
        yaxis=dict(range=[-150, 300])
    )

# Streamlit Plotly Integration
st.plotly_chart(fig, use_container_width=True)
