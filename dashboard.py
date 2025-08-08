import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
from scipy.stats import ttest_ind
from datetime import datetime
import requests, os, glob, tempfile, base64, calendar


st.set_page_config(
    page_title="Dashboard Bertoldi Boats",
    layout="wide"
)

# === PALETTE & STILI ===
primary_blue = "#073763"
gold = "#c7a96b"
accent = "#c50051"
background = "#FAFAFA"
palette_bertoldi = [primary_blue, gold, accent, "#E4C59E"]

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap');
    html, body, [class*="css"] {{
        font-family: 'Montserrat', sans-serif !important;
        background-color: {background};
        color: {primary_blue};
    }}
    h1, h2, h3, h4 {{
        font-family: 'Montserrat', sans-serif !important;
        text-transform: uppercase;
        color: {primary_blue};
        font-weight: 700;
        letter-spacing: 0.02em;
    }}
    .stTabs [role="tab"] {{
        font-family: 'Montserrat', sans-serif !important;
        color: {primary_blue};
        font-weight: 600;
    }}
    .stTabs [role="tab"][aria-selected="true"] {{
        background-color: {gold}22;
        color: {primary_blue} !important;
    }}
    .stButton>button, .stDownloadButton>button {{
        background-color: {primary_blue};
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.5em 1.5em;
        font-weight: 600;
    }}
    .stButton>button:hover, .stDownloadButton>button:hover {{
        background-color: {gold};
        color: {primary_blue};
    }}
    .stSidebar, .stSidebarContent {{
        background-color: white;
        color: {primary_blue};
    }}
    .stMetric-value {{
        color: {gold};
        font-size: 2.1em;
        font-weight: 700;
    }}
    .stMetric-label {{
        color: {primary_blue};
        text-transform: uppercase;
        letter-spacing: 0.03em;
        font-weight: 600;
    }}
    .logo-img {{
        display: block;
        margin-left: auto;
        margin-right: auto;
        margin-top: 0.5em;
        margin-bottom: 0.5em;
        width: 85%;
        max-width: 240px;
    }}
    </style>
""", unsafe_allow_html=True)

def logo_base64(path):
    with open(path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode("utf-8")

with st.sidebar:
    st.markdown(
        f'<img src="data:image/png;base64,{logo_base64("Logo.png")}" class="logo-img">',
        unsafe_allow_html=True
    )
    st.header("Dashboard Bertoldi Boats")

    # ========== LOGICA DI PAGINA ==========



def breadcrumb(area=None, barca=None):
    gold = "#C9B037"
    bc = "Home"
    if area and area != "Tutte":
        bc += f" > {area}"
    if barca and barca != "Tutte":
        bc += f" > {barca}"
    st.markdown(
        f"<span style='color:{gold};font-size:1.15em;font-weight:600'>{bc}</span>",
        unsafe_allow_html=True
    )



# ========== CARICAMENTO DATI KPI (Taxi) ==========

@st.cache_data
def carica_dati():
    files = sorted(glob.glob("crmboats_taxi*.xlsx"))
    dfs = []
    for file in files:
        xls = pd.ExcelFile(file)
        for nome_foglio in xls.sheet_names:
            nome_clean = str(nome_foglio).strip().lower().replace("<", "").replace(">", "")
            if any(x in nome_clean for x in ["totale", "totali", "sintesi", "legenda"]):
                continue
            tmp = pd.read_excel(xls, sheet_name=nome_foglio, skiprows=2, usecols="B:I")
            if tmp.shape[0] > 0:
                tmp = tmp.iloc[:-1]  # Escludi ultima riga (totale mensile)
            col_data = tmp.columns[0]
            tmp = tmp.rename(columns={col_data: "Data"})
            tmp["MeseFoglio"] = nome_foglio
            tmp["AnnoFile"] = os.path.basename(file)
            dfs.append(tmp)
    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce", dayfirst=True).ffill()

    col_tratte = df.columns[1]
    col_durata = df.columns[2]
    col_clienti = df.columns[3]
    col_barca = df.columns[4]
    col_dip = df.columns[5]
    col_incasso = df.columns[6]
    col_gasolio = df.columns[7]

    df["TipoRiga"] = df[col_dip].apply(lambda x: "Totale" if pd.notnull(x) and str(x).strip() != "" else "Dettaglio")
    df["Incasso"] = pd.to_numeric(df[col_incasso].replace({r"[€]": ""}, regex=True).str.replace(",", "."), errors="coerce")
    df["Gasolio"] = pd.to_numeric(df[col_gasolio].replace({r"[€]": ""}, regex=True).str.replace(",", "."), errors="coerce")
    df["Clienti"] = pd.to_numeric(df[col_clienti], errors="coerce")
    df["Durata"] = df[col_durata]
    df["Dipendente"] = df[col_dip]

    # --- Normalizzazione barche: abbreviazioni SOLO su Dettaglio ---
    ABBREV_TO_FULL = {
        "Bel": "Beluga", "Lib": "Libera", "Ghi": "Ghibli", "Mag": "Magia", "Kia": "Kiar di Luna",
        "Bec": "Become", "Ete": "Eternity", "Col": "Columbus", "Can": "Candido", "Vir": "Virgilio", "Riv": "Riva"
    }
    FULL_NAMES = set([
        "Beluga", "Libera", "Ghibli", "Magia", "Kiar di Luna", "Become",
        "Eternity", "L’Aurora", "L'Aurora", "Columbus", "Candido", "Virgilio", "Riva"
    ])

    def normalizza_barca_condizionale(nome, tipo_riga):
        if pd.isnull(nome):
            return None
        s = str(nome).strip().replace("’", "'").replace("‘", "'")
        s_lower = s.lower()
        if s_lower in ("l'aurora", "l’aurora"):
            return "L’Aurora"
        if tipo_riga == "Dettaglio":
            for abbr, full in ABBREV_TO_FULL.items():
                if s_lower == abbr.lower():
                    return full
            for full in FULL_NAMES:
                if s_lower == full.lower():
                    return "L’Aurora" if "aurora" in s_lower else full
            return None
        else:  # Totale
            for full in FULL_NAMES:
                if s_lower == full.lower():
                    return "L’Aurora" if "aurora" in s_lower else full
            return None

    df["Barca_Normalizzata"] = df.apply(
        lambda r: normalizza_barca_condizionale(r[col_barca], r["TipoRiga"]),
        axis=1
    )

    # Assegna area
    AREE_BARCHE = {
        "Sirmione": ["Beluga", "Libera", "Ghibli", "Magia", "Kiar di Luna", "Become"],
        "Desenzano": ["Eternity", "L’Aurora"],
        "BSD": ["Columbus"],
        "Exclusive": ["Candido", "Virgilio"],
        "Riva": ["Riva"]
    }
    def assegna_area(nome_barca):
        if pd.isnull(nome_barca):
            return None
        for area, elenco in AREE_BARCHE.items():
            if nome_barca in elenco:
                return area
        return None

    df["Area"] = df["Barca_Normalizzata"].apply(assegna_area)
    df = df.dropna(subset=["Barca_Normalizzata", "Area"])

    # Colonne derivate
    df["Anno"] = df["Data"].dt.year
    oggi = pd.Timestamp(datetime.now().date())
    df = df[df["Data"] <= oggi]
    df["TipoGiorno"] = df["Data"].dt.weekday.apply(lambda x: "Alti" if x >= 5 else "Bassi")
    df["TipoCliente"] = df.apply(
        lambda row: "Privati" if row["TipoRiga"] == "Dettaglio" and pd.notnull(row["Clienti"]) and row["Clienti"] <= 5
        else ("Gruppo" if row["TipoRiga"] == "Dettaglio" and pd.notnull(row["Clienti"]) and row["Clienti"] > 5 else None),
        axis=1
    )

    return df

# Gestione del pulsante per ricaricare i dati
ricarica = st.sidebar.button("🔄 Ricarica dati")
if ricarica:
    st.cache_data.clear()
    st.success("Dati ricaricati! Puoi aggiornare la pagina.")

# Carica dati sempre PRIMA di ogni utilizzo!
df = carica_dati()

def aggiorna_meteo(df, start_date, end_date):
    import requests
    lat, lon = 45.492, 10.608  # Sirmione
    anni = list(range(start_date.year, end_date.year + 1))
    meteo_dfs = []
    for anno in anni:
        inizio = max(start_date, pd.Timestamp(f"{anno}-01-01"))
        fine = min(end_date, pd.Timestamp(f"{anno}-12-31"))
        url = (
            f"https://archive-api.open-meteo.com/v1/archive?"
            f"latitude={lat}&longitude={lon}"
            f"&start_date={inizio.strftime('%Y-%m-%d')}&end_date={fine.strftime('%Y-%m-%d')}"
            f"&daily=precipitation_sum,weathercode,windspeed_10m_max"
            f"&timezone=Europe%2FBerlin"
        )
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            resp_json = r.json()
            if "daily" in resp_json and resp_json["daily"]:
                data = resp_json["daily"]
                meteo_df = pd.DataFrame(data)
                meteo_df["Data"] = pd.to_datetime(meteo_df["time"])
                meteo_df["Maltempo"] = (meteo_df["precipitation_sum"] > 3) | (meteo_df["windspeed_10m_max"] > 40)
                meteo_dfs.append(meteo_df)
        except Exception as e:
            st.warning(f"Errore caricamento meteo per il {anno}: {e}")

    if not meteo_dfs:
        st.warning("Nessun dato meteo disponibile.")
        if "Maltempo" not in df.columns:
            df["Maltempo"] = np.nan
        return df

    meteo_df_tot = pd.concat(meteo_dfs, ignore_index=True)
    # Merge: normalizza data per evitare problemi di orario
    df["DataNorm"] = pd.to_datetime(df["Data"]).dt.normalize()
    meteo_df_tot["DataNorm"] = meteo_df_tot["Data"].dt.normalize()
    df = pd.merge(
        df, 
        meteo_df_tot[["DataNorm", "precipitation_sum", "windspeed_10m_max", "Maltempo"]],
        left_on="DataNorm", right_on="DataNorm", how="left"
    )
    df.drop(columns=["DataNorm"], inplace=True)
    st.success(f"Dati meteo scaricati per {len(meteo_df_tot)} giorni (in blocchi annuali).")
    return df

start_date = df["Data"].min()
end_date = df["Data"].max()
df = aggiorna_meteo(df, start_date, end_date)
if "Maltempo" not in df.columns:
    df["Maltempo"] = np.nan

# ========== CARICAMENTO SPESE ==========

def carica_spese(path="Bertoldi Boats.csv"):
    try:
        df_spese = pd.read_csv(path)
    except Exception as e:
        st.error(f"Errore nella lettura del file spese: {e}")
        return pd.DataFrame()

    colonne_originali = df_spese.columns.str.strip().str.upper()
    mapping = {}
    if "DATA" in colonne_originali:
        mapping[df_spese.columns[colonne_originali.get_loc("DATA")]] = "Data"
    if "COSTO" in colonne_originali:
        mapping[df_spese.columns[colonne_originali.get_loc("COSTO")]] = "Costo"
    if "TIPO SPESA" in colonne_originali:
        mapping[df_spese.columns[colonne_originali.get_loc("TIPO SPESA")]] = "Tipo_Spesa"
    if "FORNITORE" in colonne_originali:
        mapping[df_spese.columns[colonne_originali.get_loc("FORNITORE")]] = "Fornitore"
    if "CATEGORIA" in colonne_originali:
        mapping[df_spese.columns[colonne_originali.get_loc("CATEGORIA")]] = "Categoria"
    if "DESTINAZIONE" in colonne_originali:
        mapping[df_spese.columns[colonne_originali.get_loc("DESTINAZIONE")]] = "Destinazione"
    if "METODO PAGAMENTO" in colonne_originali:
        mapping[df_spese.columns[colonne_originali.get_loc("METODO PAGAMENTO")]] = "Metodo_Pagamento"
    df_spese = df_spese.rename(columns=mapping)

    if "Data" in df_spese.columns:
        df_spese["Data"] = pd.to_datetime(df_spese["Data"], dayfirst=True, errors="coerce")
    if "Costo" in df_spese.columns:
        df_spese["Costo"] = (
            df_spese["Costo"]
            .astype(str)
            .str.replace("€", "")
            .str.replace(".", "")
            .str.replace(",", ".")
            .str.strip()
        )
        df_spese["Costo"] = pd.to_numeric(df_spese["Costo"], errors="coerce")
    return df_spese

df_spese = carica_spese("Bertoldi Boats.csv")

# ========== CLASSIFICAZIONE SPESE ==========
def classifica_spese(df):
    df.columns = [c.strip().capitalize() for c in df.columns]

    def macro_categoria(row):
        cat = str(row.get("Categoria", "")).lower() if pd.notnull(row.get("Categoria", "")) else ""
        tipo = str(row.get("Tipo_spesa", "")).lower() if pd.notnull(row.get("Tipo_spesa", "")) else ""
        if "acquisto nuovo" in cat:
            return "Acquisto nuovo"
        elif "provvigioni" in cat:
            return "Provvigioni"
        elif "gasolio" in cat:
            return "Gasolio"
        elif "stipendi" in cat or "f24" in cat:
            return "Stipendi"
        elif tipo == "fissi" and not any(x in cat for x in ["acquisto nuovo", "gasolio", "provvigioni", "tasse"]):
            return "Spese fisse"
        elif tipo == "variabili" and "acquisto nuovo" not in cat and "provvigioni" not in cat:
            return "Spese variabili"
        else:
            return "Altro"
    df["MACRO_CATEGORIA"] = df.apply(macro_categoria, axis=1)
    return df

if not df_spese.empty:
    df_spese = classifica_spese(df_spese)

# ========== FILTRI E SIDEBAR ==========
anni = sorted(df["Anno"].dropna().unique())
mesi = [calendar.month_name[m] for m in range(1, 13)]
sett_max = int(df["Data"].dt.isocalendar().week.max())
settimane = list(range(1, sett_max + 1))
aree = ["Tutte"] + sorted(df["Area"].dropna().unique().tolist())
aree_barche = {
    "Sirmione": ["Beluga", "Libera", "Ghibli", "Magia", "Kiar di Luna", "Become"],
    "Desenzano": ["Eternity", "L’Aurora"],
    "BSD": ["Columbus"],
    "Exclusive": ["Candido", "Virgilio"],
    "Riva": ["Riva"]
}

st.sidebar.title("⚙️ Filtri avanzati")
modalita = st.sidebar.radio("Modalità", ["Analisi", "Confronto"])
periodo_tipo = st.sidebar.selectbox("Tipo di periodo", ["Annuale", "Mensile", "Settimanale"])

if modalita == "Analisi":
    if periodo_tipo == "Annuale":
        anno_1 = st.sidebar.selectbox("Anno", anni, key="analisi_anno")
        periodo_selezionato = {"modalita": "analisi", "tipo": "annuale", "anno": anno_1}
    elif periodo_tipo == "Mensile":
        anno_1 = st.sidebar.selectbox("Anno", anni, key="analisi_mese_anno")
        mese_1 = st.sidebar.selectbox("Mese", mesi, key="analisi_mese")
        periodo_selezionato = {"modalita": "analisi", "tipo": "mensile", "anno": anno_1, "mese": mesi.index(mese_1) + 1}
    elif periodo_tipo == "Settimanale":
        anno_1 = st.sidebar.selectbox("Anno", anni, key="analisi_sett_anno")
        sett_1 = st.sidebar.selectbox("Settimana", settimane, key="analisi_sett")
        periodo_selezionato = {"modalita": "analisi", "tipo": "settimanale", "anno": anno_1, "settimana": sett_1}
else:
    if periodo_tipo == "Annuale":
        anno_1 = st.sidebar.selectbox("Anno 1", anni, key="confronto_anno1")
        anno_2 = st.sidebar.selectbox("Anno 2", [a for a in anni if a != anno_1], key="confronto_anno2")
        periodo_selezionato = {"modalita": "confronto", "tipo": "annuale", "anno1": anno_1, "anno2": anno_2}
    elif periodo_tipo == "Mensile":
        anno_1 = st.sidebar.selectbox("Anno 1", anni, key="confronto_mese_anno1")
        mese_1 = st.sidebar.selectbox("Mese 1", mesi, key="confronto_mese1")
        anno_2 = st.sidebar.selectbox("Anno 2", anni, key="confronto_mese_anno2")
        mese_2 = st.sidebar.selectbox("Mese 2", mesi, key="confronto_mese2")
        periodo_selezionato = {
            "modalita": "confronto", "tipo": "mensile",
            "anno1": anno_1, "mese1": mesi.index(mese_1) + 1,
            "anno2": anno_2, "mese2": mesi.index(mese_2) + 1
        }
    elif periodo_tipo == "Settimanale":
        anno_1 = st.sidebar.selectbox("Anno 1", anni, key="confronto_sett_anno1")
        sett_1 = st.sidebar.selectbox("Settimana 1", settimane, key="confronto_sett1")
        anno_2 = st.sidebar.selectbox("Anno 2", anni, key="confronto_sett_anno2")
        sett_2 = st.sidebar.selectbox("Settimana 2", settimane, key="confronto_sett2")
        periodo_selezionato = {
            "modalita": "confronto", "tipo": "settimanale",
            "anno1": anno_1, "settimana1": sett_1,
            "anno2": anno_2, "settimana2": sett_2
        }

st.sidebar.markdown("---")
giorno_sel = st.sidebar.selectbox("Tipo di giornata", ["Tutti", "Alti", "Bassi", "Confronto Alti/Bassi"])
tipo_cliente_sel = st.sidebar.selectbox("Tipo Cliente", ["Tutti", "Privati", "Gruppo", "Confronto Privati/Gruppo"])
area_sel = st.sidebar.selectbox("Area", aree, index=0)
if area_sel and area_sel != "Tutte":
    barche_disp = ["Tutte"] + aree_barche.get(area_sel, [])
else:
    barche_disp = ["Tutte"] + sorted(df["Barca_Normalizzata"].dropna().unique().tolist())
barca_sel = st.sidebar.selectbox("Barca", barche_disp, index=0)
st.sidebar.info("💡 **Consiglio:** I filtri si riflettono su tutti i grafici e le tabelle.")

# ========== FUNZIONE FILTRO ==========
def filtra_dataframe(df, periodo_sel, giorno_sel, tipo_cliente_sel, area_sel, barca_sel=None):
    df_filtrato = df.copy()
    # --- FILTRO PERIODO ---
    if periodo_sel["modalita"] == "analisi":
        if periodo_sel["tipo"] == "annuale":
            df_filtrato = df_filtrato[df_filtrato["Anno"] == periodo_sel["anno"]]
        elif periodo_sel["tipo"] == "mensile":
            df_filtrato = df_filtrato[
                (df_filtrato["Anno"] == periodo_sel["anno"]) &
                (df_filtrato["Data"].dt.month == periodo_sel["mese"])
            ]
        elif periodo_sel["tipo"] == "settimanale":
            settimana = periodo_sel["settimana"]
            anno = periodo_sel["anno"]
            df_filtrato = df_filtrato[
                (df_filtrato["Anno"] == anno) &
                (df_filtrato["Data"].dt.isocalendar().week == settimana)
            ]
    elif periodo_sel["modalita"] == "confronto":
        if periodo_sel["tipo"] == "annuale":
            anni = [periodo_sel["anno1"], periodo_sel["anno2"]]
            df_filtrato = df_filtrato[df_filtrato["Anno"].isin(anni)]
        elif periodo_sel["tipo"] == "mensile":
            mask_1 = (df_filtrato["Anno"] == periodo_sel["anno1"]) & (df_filtrato["Data"].dt.month == periodo_sel["mese1"])
            mask_2 = (df_filtrato["Anno"] == periodo_sel["anno2"]) & (df_filtrato["Data"].dt.month == periodo_sel["mese2"])
            df_filtrato = df_filtrato[mask_1 | mask_2]
        elif periodo_sel["tipo"] == "settimanale":
            mask_1 = (df_filtrato["Anno"] == periodo_sel["anno1"]) & (df_filtrato["Data"].dt.isocalendar().week == periodo_sel["settimana1"])
            mask_2 = (df_filtrato["Anno"] == periodo_sel["anno2"]) & (df_filtrato["Data"].dt.isocalendar().week == periodo_sel["settimana2"])
            df_filtrato = df_filtrato[mask_1 | mask_2]
    # --- FILTRO GIORNO ---
    if giorno_sel == "Alti":
        df_filtrato = df_filtrato[df_filtrato["TipoGiorno"] == "Alti"]
    elif giorno_sel == "Bassi":
        df_filtrato = df_filtrato[df_filtrato["TipoGiorno"] == "Bassi"]
    elif giorno_sel == "Confronto Alti/Bassi":
        df_filtrato = df_filtrato[df_filtrato["TipoGiorno"].isin(["Alti", "Bassi"])]
    # --- FILTRO TIPO CLIENTE ---
    if tipo_cliente_sel == "Privati":
        df_filtrato = df_filtrato[df_filtrato["TipoCliente"] == "Privati"]
    elif tipo_cliente_sel == "Gruppo":
        df_filtrato = df_filtrato[df_filtrato["TipoCliente"] == "Gruppo"]
    elif tipo_cliente_sel == "Confronto Privati/Gruppo":
        df_filtrato = df_filtrato[df_filtrato["TipoCliente"].isin(["Privati", "Gruppo"])]
    # --- FILTRO AREA ---
    if area_sel and area_sel != "Tutte":
        df_filtrato = df_filtrato[df_filtrato["Area"] == area_sel]
    # --- FILTRO BARCA ---
    if barca_sel and barca_sel != "Tutte":
        df_filtrato = df_filtrato[df_filtrato["Barca_Normalizzata"] == barca_sel]
    return df_filtrato

# Esempio uso: 
df_kpi = filtra_dataframe(df, periodo_selezionato, giorno_sel, tipo_cliente_sel, area_sel, barca_sel)


# ========== FUNZIONI TAB PRINCIPALI ==========



def tab_kpi(df_filtrato, periodo_selezionato, giorno_sel, tipo_cliente_sel, area=None, barca=None):
    if df_filtrato.empty:
        st.warning("Nessun dato disponibile per il filtro selezionato.")
        return

    label_area = f" – Area: {area}" if area and area != "Tutte" else ""
    label_barca = f" – Barca: {barca}" if barca and barca != "Tutte" else ""
    st.subheader(f"📊 KPI chiave{label_area}{label_barca}")

    # Usa solo righe Totale per i KPI globali giornalieri
    df_tot = df_filtrato[df_filtrato["TipoRiga"] == "Totale"].copy()

    incasso_tot = df_tot["Incasso"].sum()
    num_tour = df_tot.shape[0]
    media_clienti = df_tot["Clienti"].mean()
    efficienza = (
        df_tot["Incasso"].sum() /
        df_tot["Gasolio"].replace(0, np.nan).sum()
        if df_tot["Gasolio"].sum() > 0 else np.nan
    )
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Incasso totale", f"{incasso_tot:,.0f} €")
    kpi2.metric("Num. tour", f"{num_tour:,}")
    kpi3.metric("Media clienti/tour", f"{media_clienti:.1f}")
    kpi4.metric("Efficienza (€ per litro)", f"{efficienza:.1f}" if not np.isnan(efficienza) else "n.d.")
    

df_kpi = filtra_dataframe(df, periodo_selezionato, giorno_sel, tipo_cliente_sel, area_sel, barca_sel)




def tab_performance(df_filtrato, periodo_selezionato, giorno_sel, tipo_cliente_sel, area=None, barca=None):
    if df_filtrato.empty:
        st.warning("Nessun dato disponibile per il filtro selezionato.")
        return

    # Lavoro su una copia
    dfw = df_filtrato.copy()

    # --- Crea 'Periodo' PRIMA di fare i subset (solo se modalità confronto) ---
    period_label_used = False
    if periodo_selezionato.get("modalita") == "confronto":
        period_label_used = True
        if periodo_selezionato["tipo"] == "annuale":
            dfw["Periodo"] = dfw["Anno"].astype(str)

        elif periodo_selezionato["tipo"] == "mensile":
            anno1, mese1 = periodo_selezionato["anno1"], periodo_selezionato["mese1"]
            anno2, mese2 = periodo_selezionato["anno2"], periodo_selezionato["mese2"]
            dfw["Periodo"] = "Altro"
            mask1 = (dfw["Anno"] == anno1) & (dfw["Data"].dt.month == mese1)
            mask2 = (dfw["Anno"] == anno2) & (dfw["Data"].dt.month == mese2)
            dfw.loc[mask1, "Periodo"] = f"{calendar.month_name[mese1]} {anno1}"
            dfw.loc[mask2, "Periodo"] = f"{calendar.month_name[mese2]} {anno2}"

        elif periodo_selezionato["tipo"] == "settimanale":
            anno1, sett1 = periodo_selezionato["anno1"], periodo_selezionato["settimana1"]
            anno2, sett2 = periodo_selezionato["anno2"], periodo_selezionato["settimana2"]
            weeks = dfw["Data"].dt.isocalendar().week
            dfw["Periodo"] = "Altro"
            dfw.loc[(dfw["Anno"] == anno1) & (weeks == sett1), "Periodo"] = f"Settimana {sett1} {anno1}"
            dfw.loc[(dfw["Anno"] == anno2) & (weeks == sett2), "Periodo"] = f"Settimana {sett2} {anno2}"

    # --- Ora i subset Totale/Dettaglio (dopo la creazione di 'Periodo') ---
    df_dettaglio = dfw[dfw["TipoRiga"] == "Dettaglio"].copy()
    df_tot = dfw[dfw["TipoRiga"] == "Totale"].copy()

    # --- Scelta split ---
    area_unique = dfw["Area"].nunique() if "Area" in dfw.columns else 0
    barche_unique = dfw["Barca_Normalizzata"].nunique() if "Barca_Normalizzata" in dfw.columns else 0

    if area and area != "Tutte":
        focus_descr = f"**Area selezionata:** {area}"
        if barche_unique > 1:
            split_col = "Barca_Normalizzata"
            titolo = f"Incasso per Barca in {area}"
            caption = f"Confronto tra le barche operative nell’area {area}."
        else:
            split_col = "Durata"
            titolo = f"Incasso per Tipologia di Tour ({barca or ''})"
            caption = f"Analisi delle tipologie di tour svolte dalla barca {barca or 'selezionata'}."
    else:
        focus_descr = "**Nessuna area selezionata:** confronto tra aree"
        if area_unique > 1:
            split_col = "Area"
            titolo = "Incasso per Area"
            caption = "Confronto tra tutte le aree operative."
        elif barche_unique > 1:
            split_col = "Barca_Normalizzata"
            titolo = "Incasso per Barca"
            caption = "Confronto tra le barche di tutte le aree."
        else:
            split_col = "Durata"
            titolo = "Incasso per Tipologia Tour"
            caption = "Analisi delle diverse tipologie di tour nella flotta."

    palette = palette_bertoldi

    # --- Costruzione colonne di groupby ---
    gb_cols = [split_col]
    color_col = None

    # Confronto Alti/Bassi → aggiungo TipoGiorno (e color se non già impostato)
    if giorno_sel == "Confronto Alti/Bassi":
        gb_cols.append("TipoGiorno")
        color_col = "TipoGiorno"

    # Confronto periodi → aggiungo Periodo (e color a Periodo se non già impostato da TipoGiorno)
    if period_label_used:
        gb_cols.append("Periodo")
        if color_col is None:
            color_col = "Periodo"

    # --- Confronto Privati/Gruppo sui Dettagli ---
    if tipo_cliente_sel == "Confronto Privati/Gruppo" and "TipoCliente" in df_dettaglio.columns:
        gb_cols_clienti = gb_cols + ["TipoCliente"]
        color_for_fig = "TipoCliente"  # colore sul tipo cliente
        gdf = df_dettaglio.groupby(gb_cols_clienti, dropna=False)["Incasso"].agg(["sum", "mean"]).reset_index()
        fig = px.bar(
            gdf, x=split_col, y="sum", color=color_for_fig,
            barmode="group", text_auto=True, color_discrete_sequence=palette,
            labels={"sum": "Incasso Totale", split_col: split_col, "TipoCliente": "Cliente", "Periodo": "Periodo", "TipoGiorno": "TipoGiorno"}
        )
    else:
        gdf = df_dettaglio.groupby(gb_cols, dropna=False)["Incasso"].agg(["sum", "mean"]).reset_index()
        fig = px.bar(
            gdf, x=split_col, y="sum", color=color_col,
            barmode="group", text_auto=True, color_discrete_sequence=palette,
            labels={"sum": "Incasso Totale", split_col: split_col, "Periodo": "Periodo", "TipoGiorno": "TipoGiorno"}
        )

    st.subheader(titolo)
    st.caption(focus_descr + "  \n" + caption)
    st.plotly_chart(fig, use_container_width=True)

    # --- Tabella di sintesi + Top 3 ---
    st.markdown("**Sintesi:**")
    st.dataframe(gdf.style.format({"sum": "{:,.0f} €", "mean": "{:,.0f} €"}))
    top3 = gdf.sort_values("sum", ascending=False).head(3)
    st.markdown(f"**🏆 Top 3 per {split_col}:**")
    st.dataframe(top3.style.format({"sum": "{:,.0f} €", "mean": "{:,.0f} €"}))

    # --- Delta confronto tra periodi (solo se il colore è Periodo e ci sono esattamente 2 periodi) ---
    if period_label_used and color_col == "Periodo":
        try:
            pivot = gdf.pivot(index=split_col, columns="Periodo", values="sum")
            if pivot.shape[1] == 2:
                col1, col2 = pivot.columns
                pivot["Delta €"] = pivot[col2] - pivot[col1]
                pivot["Delta %"] = np.where(pivot[col1] > 0, 100 * (pivot[col2] - pivot[col1]) / pivot[col1], np.nan)
                st.markdown("**Delta confronto tra periodi:**")
                st.dataframe(pivot.style.format({"Delta €": "{:,.0f} €", "Delta %": "{:+.1f}%"}))
        except KeyError:
            pass

    # --- Nota statistica ---
    st.info("""
**Nota statistica – ANOVA**  
Il test ANOVA verifica se le differenze di incasso medio tra gruppi (area/barca/tour) sono statisticamente significative.
- Se il valore p < 0.05 → differenze reali tra gruppi.
- Se il valore p > 0.05 → differenze attribuibili al caso.

Le tabelle e i grafici sono focalizzati **solo sull’area selezionata** (se presente).
""")

def tab_popolarita(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area=None, barca=None):
    if df_kpi.empty:
        st.warning("Nessun dato disponibile per il filtro selezionato.")
        return

    # ====== PREP E 'Periodo' ======
    dfw = df_kpi.copy()
    compare_periods = (periodo_selezionato.get("modalita") == "confronto")

    if compare_periods:
        if periodo_selezionato["tipo"] == "annuale":
            dfw["Periodo"] = dfw["Anno"].astype(str)

        elif periodo_selezionato["tipo"] == "mensile":
            anno1, mese1 = periodo_selezionato["anno1"], periodo_selezionato["mese1"]
            anno2, mese2 = periodo_selezionato["anno2"], periodo_selezionato["mese2"]
            dfw["Periodo"] = "Altro"
            m1 = (dfw["Anno"] == anno1) & (dfw["Data"].dt.month == mese1)
            m2 = (dfw["Anno"] == anno2) & (dfw["Data"].dt.month == mese2)
            dfw.loc[m1, "Periodo"] = f"{calendar.month_name[mese1]} {anno1}"
            dfw.loc[m2, "Periodo"] = f"{calendar.month_name[mese2]} {anno2}"

        elif periodo_selezionato["tipo"] == "settimanale":
            anno1, sett1 = periodo_selezionato["anno1"], periodo_selezionato["settimana1"]
            anno2, sett2 = periodo_selezionato["anno2"], periodo_selezionato["settimana2"]
            iso_week = dfw["Data"].dt.isocalendar().week
            dfw["Periodo"] = "Altro"
            dfw.loc[(dfw["Anno"] == anno1) & (iso_week == sett1), "Periodo"] = f"Settimana {sett1} {anno1}"
            dfw.loc[(dfw["Anno"] == anno2) & (iso_week == sett2), "Periodo"] = f"Settimana {sett2} {anno2}"

    # ====== SCELTA righe (Dettaglio/Totale) in base ai clienti ======
    if tipo_cliente_sel in ["Privati", "Gruppo", "Confronto Privati/Gruppo"]:
        dfw = dfw[dfw["TipoRiga"] == "Dettaglio"]
        if tipo_cliente_sel == "Privati":
            dfw = dfw[dfw["TipoCliente"] == "Privati"]
        elif tipo_cliente_sel == "Gruppo":
            dfw = dfw[dfw["TipoCliente"] == "Gruppo"]
        # Per "Confronto Privati/Gruppo" tengo entrambe le classi
    else:
        dfw = dfw[dfw["TipoRiga"] == "Totale"]

    # ====== TITOLO/CONTESTO ======
    context_msg = ""
    if area and area != "Tutte":
        context_msg += f" – Area: {area}"
    if barca and barca != "Tutte":
        context_msg += f" – Barca: {barca}"
    st.subheader(f"Top 5 Tour più richiesti{context_msg}")

    palette = palette_bertoldi

    # Helper: top-N per gruppo
    def top_n_per_group(df_in, by_cols, sort_col, n=5):
        return (df_in.sort_values(sort_col, ascending=False)
                    .groupby(by_cols, group_keys=False)
                    .head(n)
                    .reset_index(drop=True))

    # ====== SEZIONE GRAFICO PRINCIPALE (come prima) ======
    # Provo a mantenere la tua logica a rami, ma senza ripetere troppo.
    def plot_top5_base(df_src, gb_cols, group_for_top, color_col=None, facet_col=None, caption_msg=""):
        gdf = df_src.groupby(gb_cols, dropna=False).size().reset_index(name="Conteggio")
        if group_for_top:  # es. ["Periodo", "TipoCliente"] per top per ogni gruppo
            top = top_n_per_group(gdf, group_for_top, "Conteggio", n=5)
        else:
            top = gdf.nlargest(5, "Conteggio")

        if facet_col:
            fig = px.bar(
                top, x="Durata", y="Conteggio",
                color=color_col, barmode="group", text_auto=True,
                facet_col=facet_col, facet_col_wrap=2,
                color_discrete_sequence=palette
            )
        else:
            fig = px.bar(
                top, x="Durata", y="Conteggio",
                color=color_col, barmode="group", text_auto=True,
                color_discrete_sequence=palette
            )
        st.plotly_chart(fig, use_container_width=True)
        if caption_msg:
            st.caption(caption_msg)

    # Rami principali
    if tipo_cliente_sel == "Confronto Privati/Gruppo" and "TipoCliente" in dfw.columns:
        if area and area != "Tutte" and (barca in [None, "Tutte"]) and dfw["Barca_Normalizzata"].nunique() > 1:
            gb_cols = ["Durata", "TipoCliente", "Barca_Normalizzata"]
            if compare_periods: gb_cols.append("Periodo")
            group_for_top = ["TipoCliente", "Barca_Normalizzata"] + (["Periodo"] if compare_periods else [])
            plot_top5_base(
                dfw, gb_cols, group_for_top,
                color_col="Barca_Normalizzata",
                facet_col=("Periodo" if compare_periods else "TipoCliente"),
                caption_msg="Top 5 tour per barca e tipologia cliente" + (" con confronto periodi." if compare_periods else ".")
            )
        else:
            gb_cols = ["Durata", "TipoCliente"]
            if compare_periods: gb_cols.append("Periodo")
            group_for_top = (["Periodo", "TipoCliente"] if compare_periods else ["TipoCliente"])
            plot_top5_base(
                dfw, gb_cols, group_for_top,
                color_col="TipoCliente",
                facet_col=("Periodo" if compare_periods else None),
                caption_msg="Top 5 tour per tipologia cliente" + (" per ciascun periodo." if compare_periods else ".")
            )

    elif area and area != "Tutte" and (barca in [None, "Tutte"]) and dfw["Barca_Normalizzata"].nunique() > 1:
        gb_cols = ["Durata", "Barca_Normalizzata"]
        if compare_periods: gb_cols.append("Periodo")
        group_for_top = (["Barca_Normalizzata", "Periodo"] if compare_periods else ["Barca_Normalizzata"])
        plot_top5_base(
            dfw, gb_cols, group_for_top,
            color_col="Barca_Normalizzata",
            facet_col=("Periodo" if compare_periods else None),
            caption_msg="Top 5 tour per ogni barca dell’area selezionata" + (" con confronto tra periodi." if compare_periods else ".")
        )

    elif giorno_sel == "Confronto Alti/Bassi" and "TipoGiorno" in dfw.columns:
        gb_cols = ["Durata", "TipoGiorno"]
        if compare_periods: gb_cols.append("Periodo")
        group_for_top = (["Periodo", "TipoGiorno"] if compare_periods else ["TipoGiorno"])
        plot_top5_base(
            dfw, gb_cols, group_for_top,
            color_col="TipoGiorno",
            facet_col=("Periodo" if compare_periods else None),
            caption_msg="Confronto top 5 tour tra giorni Alti/Bassi" + (" per ciascun periodo." if compare_periods else ".")
        )

    else:
        gb_cols = ["Durata"]
        if compare_periods: gb_cols.append("Periodo")
        group_for_top = (["Periodo"] if compare_periods else None)
        plot_top5_base(
            dfw, gb_cols, group_for_top,
            color_col=("Periodo" if compare_periods else None),
            facet_col=None,
            caption_msg="Top 5 tour più richiesti nel periodo/segmento selezionato" + (" con confronto tra periodi." if compare_periods else ".")
        )

    # ====== 1) I 5 PEGGIORI TOUR (meno richiesti) ======
    st.markdown("### ⬇️ I 5 tour meno richiesti")
    base_counts = (dfw.groupby("Durata", dropna=False)
                      .size()
                      .reset_index(name="Conteggio"))
    # Considero solo tour con almeno 1 occorrenza (per non riempire di zeri)
    worst5 = base_counts[base_counts["Conteggio"] > 0].nsmallest(5, "Conteggio")
    if worst5.empty:
        st.info("Nessun tour con conteggio > 0 nel contesto selezionato.")
    else:
        st.dataframe(worst5.rename(columns={"Conteggio": "Occorrenze"}), use_container_width=True)

    # ====== 2) & 3) Maggior incremento/decremento (normalizzato su #barche) ======
    st.markdown("### 🔁 Variazioni tra periodi (normalizzate per # barche)")
    if not compare_periods:
        st.info("Per vedere incrementi/decrementi attiva la modalità **Confronto** nella sidebar.")
        return

    # Considero solo i due periodi target (escludo 'Altro' se presente)
    periodi_validi = [p for p in dfw["Periodo"].dropna().unique().tolist() if p != "Altro"]
    if len(periodi_validi) != 2:
        st.info("Servono esattamente due periodi da confrontare.")
        return
    p1, p2 = periodi_validi[0], periodi_validi[1]

    # Conteggi per (Durata, Periodo)
    cnt = (dfw[dfw["Periodo"].isin([p1, p2])]
              .groupby(["Durata", "Periodo"], dropna=False)
              .size()
              .reset_index(name="Conteggio"))

    # # barche attive per periodo (nunique)
    boats = (dfw[dfw["Periodo"].isin([p1, p2])]
                .groupby("Periodo")["Barca_Normalizzata"]
                .nunique()
                .rename("Boats")
                .reset_index())

    # Join per normalizzare
    cnt_norm = cnt.merge(boats, on="Periodo", how="left")
    cnt_norm["NormConteggio"] = cnt_norm.apply(
        lambda r: (r["Conteggio"] / r["Boats"]) if (pd.notnull(r["Boats"]) and r["Boats"] > 0) else np.nan,
        axis=1
    )

    # Pivot per avere colonne p1/p2
    piv = (cnt_norm.pivot(index="Durata", columns="Periodo", values="NormConteggio")
                    .reset_index())
    # Rinomina colonne per sicurezza (se i nomi periodo hanno spazi)
    piv.columns.name = None

    if p1 in piv.columns and p2 in piv.columns:
        piv["Delta_norm"] = piv[p2].fillna(0) - piv[p1].fillna(0)
        piv["Delta_%"] = np.where(piv[p1].fillna(0) > 0, 100 * piv["Delta_norm"] / piv[p1].fillna(0), np.nan)

        # Top 5 incrementi
        top_inc = piv.sort_values("Delta_norm", ascending=False).head(5)[["Durata", p1, p2, "Delta_norm", "Delta_%"]]
        # Top 5 decrementi
        top_dec = piv.sort_values("Delta_norm", ascending=True).head(5)[["Durata", p1, p2, "Delta_norm", "Delta_%"]]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**⬆️ Top 5 incremento (normalizzato)**")
            st.dataframe(
                top_inc.rename(columns={
                    p1: f"Norm {p1}",
                    p2: f"Norm {p2}",
                    "Delta_norm": "Δ norm",
                    "Delta_%": "Δ %"
                }).style.format({
                    f"Norm {p1}": "{:.2f}",
                    f"Norm {p2}": "{:.2f}",
                    "Δ norm": "{:+.2f}",
                    "Δ %": "{:+.1f}%"
                }),
                use_container_width=True
            )
        with col2:
            st.markdown("**⬇️ Top 5 decremento (normalizzato)**")
            st.dataframe(
                top_dec.rename(columns={
                    p1: f"Norm {p1}",
                    p2: f"Norm {p2}",
                    "Delta_norm": "Δ norm",
                    "Delta_%": "Δ %"
                }).style.format({
                    f"Norm {p1}": "{:.2f}",
                    f"Norm {p2}": "{:.2f}",
                    "Δ norm": "{:+.2f}",
                    "Δ %": "{:+.1f}%"
                }),
                use_container_width=True
            )
    else:
        st.info("Non è stato possibile calcolare il delta normalizzato: colonne dei periodi mancanti.")

    # Nota
    st.info("""
**Nota**  
- Le variazioni sono calcolate su conteggi di tour normalizzati per il **numero di barche attive** nel periodo.
- I “peggiori tour” sono quelli con **minori occorrenze** nel contesto filtrato corrente.
""")

def tab_stagionalita(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area=None, barca=None):
    import calendar

    if df_kpi.empty:
        st.warning("Nessun dato disponibile per il filtro selezionato.")
        return
    
    oggi = pd.Timestamp(datetime.now().date())
    df_kpi = df_kpi[df_kpi["Data"] <= oggi].copy()

    # --- FILTRO AGGIUNTIVO: GIORNO E CLIENTE (con distinzione TipoRiga) ---
    grouping_label = None  # Nessun grouping extra di default

    # Filtro giorno
    if giorno_sel == "Alti":
        df_kpi = df_kpi[df_kpi["TipoGiorno"] == "Alti"]
    elif giorno_sel == "Bassi":
        df_kpi = df_kpi[df_kpi["TipoGiorno"] == "Bassi"]
    elif giorno_sel == "Confronto Alti/Bassi":
        df_kpi = df_kpi[df_kpi["TipoGiorno"].isin(["Alti", "Bassi"])]
        grouping_label = "TipoGiorno"

    # Filtro cliente con distinzione TipoRiga
    if tipo_cliente_sel == "Privati":
        df_kpi = df_kpi[(df_kpi["TipoCliente"] == "Privati") & (df_kpi["TipoRiga"] == "Dettaglio")]
    elif tipo_cliente_sel == "Gruppo":
        df_kpi = df_kpi[(df_kpi["TipoCliente"] == "Gruppo") & (df_kpi["TipoRiga"] == "Dettaglio")]
    elif tipo_cliente_sel == "Confronto Privati/Gruppo":
        df_kpi = df_kpi[(df_kpi["TipoCliente"].isin(["Privati", "Gruppo"])) & (df_kpi["TipoRiga"] == "Dettaglio")]
        grouping_label = "TipoCliente"
    else:
        # Tutti i dati, usiamo solo Totale per evitare sovrapposizioni
        df_kpi = df_kpi[df_kpi["TipoRiga"] == "Totale"]

    st.subheader("📈 Trend temporali & Confronto storico")

    # --- Impostazioni base ---
    anni_disp = sorted(df_kpi["Data"].dt.year.dropna().unique())
    if len(anni_disp) == 0:
        st.warning("Nessun dato disponibile per il periodo selezionato.")
        return
    anno_1 = anni_disp[0]
    anno_2 = anni_disp[-1] if len(anni_disp) > 1 else anni_disp[0]
    mesi = [calendar.month_name[m] for m in range(1,13)]

    df_trend = df_kpi.copy()
    df_trend["Anno"] = df_trend["Data"].dt.year
    df_trend["Mese"] = df_trend["Data"].dt.month
    df_trend["Settimana"] = df_trend["Data"].dt.isocalendar().week
    df_trend["X"] = pd.Categorical(df_trend["Mese"].apply(lambda m: calendar.month_name[m]), categories=mesi, ordered=True)

    # --- Raggruppamento dati ---
    group_fields = ["Anno", "X"]
    if grouping_label:
        group_fields.append(grouping_label)

    g = df_trend.groupby(group_fields, observed=True)["Incasso"].sum().reset_index()

    # --- Serie tabellare pivotata ---
    if grouping_label:
        df_cmp = g.pivot_table(index="X", columns=[grouping_label, "Anno"], values="Incasso").fillna(0)
    else:
        g1 = g[g["Anno"] == anno_1].groupby("X")["Incasso"].sum()
        g2 = g[g["Anno"] == anno_2].groupby("X")["Incasso"].sum()
        g1 = g1.reindex(mesi)
        g2 = g2.reindex(mesi)
        df_cmp = pd.DataFrame({
            f"Incasso {anno_1}": g1,
            f"Incasso {anno_2}": g2
        }).fillna(0)

    st.dataframe(df_cmp)

    # --- Grafico trend ---
    if grouping_label:
        fig_cmp = px.line(
            g, x="X", y="Incasso", color=grouping_label, line_dash="Anno", markers=True,
            title=f"Trend incasso mensile: confronto {grouping_label.lower()} ({anno_1} vs {anno_2})",
            color_discrete_sequence=palette_bertoldi
        )
    else:
        fig_cmp = px.line(
            g, x="X", y="Incasso", color="Anno", markers=True,
            title=f"Confronto incasso per Mese ({anno_1} vs {anno_2})",
            color_discrete_sequence=palette_bertoldi
        )
    st.plotly_chart(fig_cmp, use_container_width=True)

    # --- Boxplot ---
    if grouping_label:
        fig_box = px.box(
            df_trend, x="X", y="Incasso", color=grouping_label, points="all",
            category_orders={"X": mesi},
            color_discrete_sequence=palette_bertoldi
        )
    else:
        fig_box = px.box(
            df_trend, x="X", y="Incasso", points="all",
            category_orders={"X": mesi},
            color_discrete_sequence=palette_bertoldi
        )
    fig_box.update_layout(title="Distribuzione incasso per mese", xaxis_title="Mese")
    st.plotly_chart(fig_box, use_container_width=True)

    # --- Media storica ---
    if grouping_label:
        media_storica = g.groupby(["X", grouping_label])["Incasso"].mean().reset_index(name="Media storica")
        for label in media_storica[grouping_label].unique():
            ms = media_storica[media_storica[grouping_label] == label]
            fig_cmp.add_scatter(x=ms["X"], y=ms["Media storica"], mode="lines+markers", name=f"Media storica {label}", line=dict(dash='dash'))
    else:
        media_storica = g.groupby("X")["Incasso"].mean().reindex(mesi).reset_index(name="Media storica")
        fig_cmp.add_scatter(x=media_storica["X"], y=media_storica["Media storica"], mode="lines+markers",
                            name="Media storica", line=dict(color="#00396B", dash='dash'))

    st.info("""
**Nota statistica**  
Questa tab ti permette di confrontare rapidamente **stagionalità** e trend tra diversi anni, clienti, tipologie di giornata, e di visualizzare anche la distribuzione degli incassi (boxplot).  
La **media storica** viene sempre visualizzata come linea tratteggiata.
""")

def tab_maltempo(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area=None, barca=None):

    st.subheader("☔ Impatto Maltempo su Incassi")
    if "Maltempo" not in df_kpi.columns or df_kpi["Maltempo"].isna().all():
        st.warning("Nessun dato meteo disponibile per il periodo selezionato.")
        return

    # --- FILTRO RIGHE IN BASE AL TIPO CLIENTE ---
    # Solo righe Dettaglio se filtro Privati/Gruppo/Confronto
    if tipo_cliente_sel in ["Privati", "Gruppo", "Confronto Privati/Gruppo"]:
        df_kpi = df_kpi[df_kpi["TipoRiga"] == "Dettaglio"]
    else:
        df_kpi = df_kpi[df_kpi["TipoRiga"] == "Totale"]

    df_tot = df_kpi[df_kpi["Maltempo"].notna()]

    # --- LOGICA GRUPPI PER ANALISI ---
    if tipo_cliente_sel == "Confronto Privati/Gruppo":
        grouping = "TipoCliente"
        grouping_label = "Privati / Gruppo"
    elif giorno_sel == "Confronto Alti/Bassi":
        grouping = "TipoGiorno"
        grouping_label = "Giorni Alti / Bassi"
    elif area and area != "Tutte":
        grouping = "Barca_Normalizzata"
        grouping_label = f"Barca ({area})"
    elif area is None or area == "Tutte":
        grouping = "Area"
        grouping_label = "Area"
    else:
        grouping = None
        grouping_label = None

    # --- BOXPLOT ---
    st.markdown(f"**Boxplot incasso giornaliero per Maltempo / {grouping_label}:**")
    if grouping and grouping in df_tot.columns:
        fig_box = px.box(df_tot, x="Maltempo", y="Incasso", color="Maltempo", points="all", 
                         facet_col=grouping, color_discrete_sequence=palette_bertoldi,
                         category_orders={"Maltempo": [False, True]})
    else:
        fig_box = px.box(df_tot, x="Maltempo", y="Incasso", color="Maltempo", points="all", 
                         color_discrete_sequence=palette_bertoldi,
                         category_orders={"Maltempo": [False, True]})
    st.plotly_chart(fig_box, use_container_width=True)

    # --- TABELLA SINTESI ---
    st.markdown("**Tabella di sintesi impatto maltempo:**")
    cols = [grouping, "Maltempo"] if grouping else ["Maltempo"]
    sintesi = df_tot.groupby(cols).agg(
        Incasso_medio=("Incasso", "mean"),
        Incasso_totale=("Incasso", "sum"),
        Tour=("Incasso", "count")
    ).reset_index()

    if grouping:
        try:
            sintesi = sintesi.pivot(index=grouping, columns="Maltempo", values=["Incasso_medio", "Incasso_totale", "Tour"])
            sintesi.columns = [f"{m}_{'Maltempo' if b else 'Buono'}" for m, b in sintesi.columns]
            sintesi = sintesi.fillna(0)
            sintesi["Delta % Incasso medio"] = np.where(
                sintesi.get("Incasso_medio_Buono", 0) > 0,
                100*(sintesi.get("Incasso_medio_Maltempo", 0) - sintesi.get("Incasso_medio_Buono", 0))/sintesi.get("Incasso_medio_Buono", 1),
                np.nan
            )
        except Exception as e:
            st.warning(f"Errore nel calcolo della tabella di sintesi: {e}")
            st.dataframe(sintesi.style.format("{:,.0f}"))
        else:
            st.dataframe(sintesi.style.format("{:,.0f}"))
    else:
        sintesi["Delta % Incasso medio"] = np.nan
        st.dataframe(sintesi.style.format("{:,.0f}"))

    # --- BARPLOT DELTA % ---
    if grouping and "Delta % Incasso medio" in sintesi.columns:
        delta_df = sintesi.reset_index()
        fig_delta = px.bar(
            delta_df, x=grouping, y="Delta % Incasso medio", color=grouping,
            title="Delta percentuale incasso medio: Maltempo vs Buono",
            color_discrete_sequence=palette_bertoldi, text_auto=".1f"
        )
        fig_delta.update_layout(yaxis_title="Delta %")
        st.plotly_chart(fig_delta, use_container_width=True)

    # --- ISTOGRAMMA FREQUENZA MALTEMPO ---
    freq_maltempo = df_tot.groupby(df_tot["Data"].dt.to_period("M"))["Maltempo"].mean().reset_index()
    freq_maltempo["Data"] = freq_maltempo["Data"].astype(str)
    fig_meteo = px.bar(
        freq_maltempo, x="Data", y="Maltempo",
        title="Frequenza giorni di maltempo (quota mensile)", color_discrete_sequence=palette_bertoldi
    )
    fig_meteo.update_yaxes(title="Quota giorni maltempo")
    st.plotly_chart(fig_meteo, use_container_width=True)

    # --- SCATTER PLOT INCASSI VS MALTEMPO ---
    st.markdown("**Distribuzione incassi giornalieri rispetto al meteo:**")
    fig_scatter = px.scatter(
        df_tot, x="Maltempo", y="Incasso", color=grouping if grouping in df_tot.columns else None,
        title="Incasso giornaliero: bel tempo vs maltempo", color_discrete_sequence=palette_bertoldi
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    # --- BARCHE SENSIBILI AL MALTEMPO ---
    if grouping == "Barca_Normalizzata":
        df_sens = df_tot.groupby(["Barca_Normalizzata", "Maltempo"])["Incasso"].mean().unstack()
        df_sens["Delta %"] = np.where(
            df_sens.get(False, 0) > 0,
            100*(df_sens.get(True, 0) - df_sens.get(False, 0))/df_sens.get(False, 1),
            np.nan
        )
        sens_ord = df_sens.sort_values("Delta %")
        st.markdown("**Barche più sensibili al maltempo (delta % incasso):**")
        fig_sens = px.bar(
            sens_ord.reset_index(), x="Barca_Normalizzata", y="Delta %",
            color="Delta %", color_continuous_scale="rdbu", text="Delta %"
        )
        st.plotly_chart(fig_sens, use_container_width=True)

    # --- TEST STATISTICO ---
    st.markdown("**Test statistico:**")
    if grouping and grouping in df_tot.columns:
        gruppi = df_tot[grouping].unique()
        for g in gruppi:
            buono = df_tot[(df_tot[grouping]==g) & (df_tot["Maltempo"]==False)]["Incasso"].dropna()
            brutto = df_tot[(df_tot[grouping]==g) & (df_tot["Maltempo"]==True)]["Incasso"].dropna()
            if len(buono)>1 and len(brutto)>1:
                t_stat, p_val = ttest_ind(buono, brutto, equal_var=False)
                st.markdown(
                    f"- <b>{g}</b>: t = {t_stat:.2f}, p = {p_val:.4f} &rarr; "
                    f"{'<span style=\"color:green\">differenza significativa</span>' if p_val<0.05 else '<span style=\"color:red\">nessuna differenza significativa</span>'}",
                    unsafe_allow_html=True
                )
    else:
        buono = df_tot[df_tot["Maltempo"]==False]["Incasso"].dropna()
        brutto = df_tot[df_tot["Maltempo"]==True]["Incasso"].dropna()
        if len(buono)>1 and len(brutto)>1:
            t_stat, p_val = ttest_ind(buono, brutto, equal_var=False)
            st.markdown(
                f"- <b>Tutti i dati</b>: t = {t_stat:.2f}, p = {p_val:.4f} &rarr; "
                f"{'<span style=\"color:green\">differenza significativa</span>' if p_val<0.05 else '<span style=\"color:red\">nessuna differenza significativa</span>'}",
                unsafe_allow_html=True
            )

    # --- SUGGERIMENTI OPERATIVI ---
    st.markdown("""
    <div style='background:#FAF5E3;padding:1em;border-radius:1em;margin-top:1em'>
    <b>💡 Raccomandazioni:</b>
    <ul>
        <li>In presenza di forte impatto negativo, valuta promozioni o offerte mirate nei giorni di maltempo.</li>
        <li>I tour di gruppo spesso risentono meno del maltempo: potenzia la comunicazione di questa offerta.</li>
        <li>Considera tour "weatherproof" (al coperto, coperti, sconti per maltempo).</li>
        <li>Analizza la stagionalità: ci sono mesi/settimane più sensibili al meteo?</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)



def tab_forecast(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area=None, barca=None):

    st.subheader("📈 Forecast Incassi & Clienti – Anno in corso, trend ponderato e breakdown")

    oggi = pd.Timestamp(datetime.now().date())
    anno_corrente = oggi.year

    # --- Copia base e aggiungi colonne ---
    df_base = df_kpi.copy()
    df_base["Mese"] = df_base["Data"].dt.month
    df_base["Anno"] = df_base["Data"].dt.year

    # --- Filtra area/barca se richiesto ---
    if area and area != "Tutte":
        df_base = df_base[df_base["Area"] == area]
    if barca and barca != "Tutte":
        df_base = df_base[df_base["Barca_Normalizzata"] == barca]
    if giorno_sel == "Alti":
        df_base = df_base[df_base["TipoGiorno"] == "Alti"]
    elif giorno_sel == "Bassi":
        df_base = df_base[df_base["TipoGiorno"] == "Bassi"]
    elif giorno_sel == "Confronto Alti/Bassi":
        df_base = df_base[df_base["TipoGiorno"].isin(["Alti", "Bassi"])]

    # --- Areelist per breakdown, mesi, stagione ---
    aree = df_base["Area"].dropna().unique().tolist() if area in [None, "Tutte"] else [area]
    mesi_bassa = [1, 2, 11, 12]
    mesi_alta = [m for m in range(1, 13) if m not in mesi_bassa]

    # --- Dati storici e anno corrente ---
    df_storici = df_base[df_base["Anno"] < anno_corrente]
    df_anno_corr = df_base[df_base["Anno"] == anno_corrente]

    mesi = [calendar.month_name[m] for m in range(1, 13)]
    forecast_rows = []
    area_rows = []

    # --- Fattore andamento rispetto a storico SOLO sulle righe Dettaglio ---
    mesi_fino_oggi = list(range(1, oggi.month))
    incasso_att = df_anno_corr[
        (df_anno_corr["Mese"].isin(mesi_fino_oggi)) &
        (df_anno_corr["TipoRiga"] == "Dettaglio")
    ]["Incasso"].sum()
    clienti_att = df_anno_corr[
        (df_anno_corr["Mese"].isin(mesi_fino_oggi)) &
        (df_anno_corr["TipoRiga"] == "Dettaglio")
    ]["Clienti"].sum()
    incasso_storico = df_storici[
        (df_storici["Mese"].isin(mesi_fino_oggi)) &
        (df_storici["TipoRiga"] == "Dettaglio")
    ].groupby("Anno")["Incasso"].sum().mean()
    clienti_storico = df_storici[
        (df_storici["Mese"].isin(mesi_fino_oggi)) &
        (df_storici["TipoRiga"] == "Dettaglio")
    ].groupby("Anno")["Clienti"].sum().mean()
    fattore_incasso = incasso_att / incasso_storico if incasso_storico > 0 else 1
    fattore_clienti = clienti_att / clienti_storico if clienti_storico > 0 else 1

    # --- STEP 1: calcola barche attive mese/area ---
    n_barche_attive_area = {}
    for a in aree:
        n_barche_attive_area[a] = {}
        # BASSA stagione (media storica)
        for mese in mesi_bassa:
            n_storico = df_storici[(df_storici["Area"] == a) & (df_storici["Mese"] == mese)].groupby("Anno")["Barca_Normalizzata"].nunique().mean()
            n_barche_attive_area[a][mese] = int(round(n_storico)) if pd.notnull(n_storico) else 0
        # ALTA stagione (max fino a oggi, storici e anno corrente)
        max_barche_alta = 0
        for mese in mesi_alta:
            n_corr = df_anno_corr[(df_anno_corr["Area"] == a) & (df_anno_corr["Mese"] == mese) & (df_anno_corr["Data"] <= oggi)]["Barca_Normalizzata"].nunique()
            n_storico = df_storici[(df_storici["Area"] == a) & (df_storici["Mese"] == mese)].groupby("Anno")["Barca_Normalizzata"].nunique().mean()
            max_barche_alta = max(max_barche_alta, int(n_corr), int(round(n_storico)) if pd.notnull(n_storico) else 0)
            n_barche_attive_area[a][mese] = max_barche_alta
        for mese in range(min(mesi_alta), 11):  # marzo-ottobre
            n_barche_attive_area[a][mese] = max_barche_alta

    # --- STEP 2: previsione mese per mese ---
    for mese in range(1, 13):
        mese_nome = calendar.month_name[mese]
        n_barche_totali = sum([n_barche_attive_area[a][mese] for a in aree])

        # --- DATI REALI, PREVISIONALI O MISTI ---
        if mese < oggi.month:
            # Dato reale: sempre dalle righe Totale
            incasso = df_base[(df_base["Anno"] == anno_corrente) & (df_base["Mese"] == mese) & (df_base["TipoRiga"] == "Totale")]["Incasso"].sum()
            clienti = df_base[(df_base["Anno"] == anno_corrente) & (df_base["Mese"] == mese) & (df_base["TipoRiga"] == "Totale")]["Clienti"].sum()
            tipo = "DATO REALE"
            # Breakdown Privati/Gruppo SOLO Dettaglio!
            priv = df_base[(df_base["Anno"] == anno_corrente) & (df_base["Mese"] == mese) & (df_base["TipoRiga"] == "Dettaglio") & (df_base["TipoCliente"] == "Privati")]
            gruppo = df_base[(df_base["Anno"] == anno_corrente) & (df_base["Mese"] == mese) & (df_base["TipoRiga"] == "Dettaglio") & (df_base["TipoCliente"] == "Gruppo")]
            incasso_priv = priv["Incasso"].sum()
            clienti_priv = priv["Clienti"].sum()
            incasso_gruppo = gruppo["Incasso"].sum()
            clienti_gruppo = gruppo["Clienti"].sum()
        elif mese == oggi.month:
            # Parte reale + previsione giorni mancanti
            giorni_del_mese = pd.Period(f"{anno_corrente}-{mese:02d}").days_in_month
            giorni_passati = oggi.day
            giorni_mancanti = giorni_del_mese - giorni_passati

            # Reale
            df_giorni_passati = df_anno_corr[(df_anno_corr["Mese"] == mese) & (df_anno_corr["Data"].dt.day <= oggi.day)]
            incasso_reale = df_giorni_passati[df_giorni_passati["TipoRiga"] == "Totale"]["Incasso"].sum()
            clienti_reale = df_giorni_passati[df_giorni_passati["TipoRiga"] == "Totale"]["Clienti"].sum()

            priv_reale = df_giorni_passati[(df_giorni_passati["TipoRiga"] == "Dettaglio") & (df_giorni_passati["TipoCliente"] == "Privati")]
            gruppo_reale = df_giorni_passati[(df_giorni_passati["TipoRiga"] == "Dettaglio") & (df_giorni_passati["TipoCliente"] == "Gruppo")]
            incasso_priv_reale = priv_reale["Incasso"].sum()
            clienti_priv_reale = priv_reale["Clienti"].sum()
            incasso_gruppo_reale = gruppo_reale["Incasso"].sum()
            clienti_gruppo_reale = gruppo_reale["Clienti"].sum()

            # Previsione
            storici_mese = df_storici[(df_storici["Mese"] == mese) & (df_storici["TipoRiga"] == "Dettaglio")]
            media_incasso_anno = storici_mese.groupby("Anno")["Incasso"].sum().mean() if n_barche_totali > 0 else 0
            media_clienti_anno = storici_mese.groupby("Anno")["Clienti"].sum().mean() if n_barche_totali > 0 else 0
            media_incasso_giornaliero = media_incasso_anno / giorni_del_mese if giorni_del_mese else 0
            media_clienti_giornaliero = media_clienti_anno / giorni_del_mese if giorni_del_mese else 0

            incasso_previsto = media_incasso_giornaliero * giorni_mancanti * fattore_incasso * n_barche_totali / max(n_barche_totali, 1)
            clienti_previsti = media_clienti_giornaliero * giorni_mancanti * fattore_clienti * n_barche_totali / max(n_barche_totali, 1)

            # Proporzioni storiche breakdown
            tot_storico = storici_mese["Incasso"].sum()
            if tot_storico > 0:
                incasso_priv_storico = storici_mese[storici_mese["TipoCliente"] == "Privati"]["Incasso"].sum()
                incasso_gruppo_storico = storici_mese[storici_mese["TipoCliente"] == "Gruppo"]["Incasso"].sum()
                p_priv = incasso_priv_storico / tot_storico
                p_gruppo = incasso_gruppo_storico / tot_storico
            else:
                p_priv = 0.5
                p_gruppo = 0.5

            incasso_priv_prev = incasso_previsto * p_priv
            incasso_gruppo_prev = incasso_previsto * p_gruppo
            clienti_priv_prev = clienti_previsti * p_priv
            clienti_gruppo_prev = clienti_previsti * p_gruppo

            # Somma parte reale + previsionale
            incasso = incasso_reale + incasso_previsto
            clienti = clienti_reale + clienti_previsti
            incasso_priv = incasso_priv_reale + incasso_priv_prev
            incasso_gruppo = incasso_gruppo_reale + incasso_gruppo_prev
            clienti_priv = clienti_priv_reale + clienti_priv_prev
            clienti_gruppo = clienti_gruppo_reale + clienti_gruppo_prev

            tipo = "PARTE REALE + PREVISIONE"


        else:
            # Solo previsione futura
            storici_mese = df_storici[(df_storici["Mese"] == mese) & (df_storici["TipoRiga"] == "Dettaglio")]
            media_incasso_anno = storici_mese.groupby("Anno")["Incasso"].sum().mean() if n_barche_totali > 0 else 0
            media_clienti_anno = storici_mese.groupby("Anno")["Clienti"].sum().mean() if n_barche_totali > 0 else 0

            incasso = media_incasso_anno * fattore_incasso * n_barche_totali / max(n_barche_totali, 1)
            clienti = media_clienti_anno * fattore_clienti * n_barche_totali / max(n_barche_totali, 1)
            tipo = "PREVISIONE"

            tot_storico = storici_mese["Incasso"].sum()
            if tot_storico > 0:
                incasso_priv_storico = storici_mese[storici_mese["TipoCliente"] == "Privati"]["Incasso"].sum()
                incasso_gruppo_storico = storici_mese[storici_mese["TipoCliente"] == "Gruppo"]["Incasso"].sum()
                p_priv = incasso_priv_storico / tot_storico
                p_gruppo = incasso_gruppo_storico / tot_storico
            else:
                p_priv = 0.5
                p_gruppo = 0.5
            incasso_priv = incasso * p_priv
            incasso_gruppo = incasso * p_gruppo
            clienti_priv = clienti * p_priv
            clienti_gruppo = clienti * p_gruppo

        forecast_rows.append({
            "Mese": mese_nome,
            "Barche attive stimate": n_barche_totali,
            "Incasso previsto": incasso,
            "Clienti previsti": clienti,
            "Incasso privati": incasso_priv,
            "Clienti privati": clienti_priv,
            "Incasso gruppo": incasso_gruppo,
            "Clienti gruppo": clienti_gruppo,
            "Tipo dato": tipo
        })

        # Dettaglio area (opzionale: breakdown area)
        for a in aree:
            area_rows.append({
                "Mese": mese_nome,
                "Area": a,
                "Barche attive stimate": n_barche_attive_area[a][mese],
            })

    forecast_df = pd.DataFrame(forecast_rows)
    area_df = pd.DataFrame(area_rows)

    # === MAIN TABLE ===
    st.dataframe(
        forecast_df.set_index("Mese")[[
            "Barche attive stimate", "Incasso previsto", "Clienti previsti",
            "Incasso privati", "Clienti privati", "Incasso gruppo", "Clienti gruppo", "Tipo dato"
        ]].style.format({
            "Incasso previsto": "{:,.0f} €", "Clienti previsti": "{:,.0f}",
            "Incasso privati": "{:,.0f} €", "Clienti privati": "{:,.0f}",
            "Incasso gruppo": "{:,.0f} €", "Clienti gruppo": "{:,.0f}",
            "Barche attive stimate": "{:,.0f}"
        })
    )

    # === GRAFICI ===
    st.markdown("#### Incasso Previsto: Totale, Privati e Gruppo")
    fig = px.bar(
        forecast_df, x="Mese", y=["Incasso privati", "Incasso gruppo"], barmode="stack",
        color_discrete_sequence=palette_bertoldi, text_auto=True,
        labels={"value": "Incasso previsto (€)", "variable": "Segmento"}
    )
    fig.add_scatter(x=forecast_df["Mese"], y=forecast_df["Incasso previsto"], mode="lines+markers", name="Totale stimato", marker_color=accent)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Clienti Previsti: Totale, Privati e Gruppo")
    fig2 = px.bar(
        forecast_df, x="Mese", y=["Clienti privati", "Clienti gruppo"], barmode="stack",
        color_discrete_sequence=palette_bertoldi, text_auto=True,
        labels={"value": "Clienti previsti", "variable": "Segmento"}
    )
    fig2.add_scatter(x=forecast_df["Mese"], y=forecast_df["Clienti previsti"], mode="lines+markers", name="Totale stimato", marker_color=accent)
    st.plotly_chart(fig2, use_container_width=True)

    # === DETTAGLIO AREA (SOLO IN VISTA TOTALE) ===
    if area in [None, "Tutte"] and len(aree) > 1:
        st.markdown("#### Barche attive stimate per area (tutti i mesi)")
        area_pivot = area_df.pivot(index="Mese", columns="Area", values="Barche attive stimate").fillna(0).astype(int)
        st.dataframe(area_pivot)

    st.caption("""
**Logica forecast**  
- Nei mesi di alta stagione (marzo-ottobre) viene mantenuto come base il massimo numero di barche raggiunto nei mesi di alta stagione già trascorsi, per ogni area.
- Nei mesi di bassa stagione si usa la media storica.
- Se un’area è chiusa (zero barche attive), la previsione è zero.
- Il forecast pesa la proporzione delle aree, il numero di barche e la stagionalità.
- I breakdown per privati e gruppi sono stimati in base alle proporzioni storiche e dati reali correnti.
""")


def tab_simulatore(df_kpi):

    st.subheader("🔮 Simulatore What-If (storico con trend automatico)")
    stagione_map = {
        "Bassa (gen, feb, mar, nov, dic)":   [1, 2, 3, 11, 12],
        "Alta (apr, mag, set, ott)":         [4, 5, 9, 10],
        "Altissima (giu, lug, ago)":         [6, 7, 8],
        "8 mesi (mar-ott)":                  [3, 4, 5, 6, 7, 8, 9, 10],
        "12 mesi (anno intero)":             list(range(1,13)),
    }
    stagione_label = st.selectbox("Periodo di stagione", list(stagione_map.keys()), index=2)
    mesi_scelti = stagione_map[stagione_label]

    aree_disponibili = ["Tutte"] + sorted(df_kpi["Area"].dropna().unique())
    area_sel = st.selectbox("Area da simulare", aree_disponibili, index=0)
    df_det = df_kpi[df_kpi["TipoRiga"] == "Dettaglio"].copy()

    max_barche_global = 15
    # --- Trova barche massime storiche e giorni attivi ---
    max_barche_area = {}
    giorni_barca_attivi = {}
    for area in sorted(df_kpi["Area"].dropna().unique()):
        df_area_mesi = df_det[(df_det["Area"] == area) & (df_det["Data"].dt.month.isin(mesi_scelti))]
        if df_area_mesi.empty:
            max_barche_area[area] = 0
            giorni_barca_attivi[area] = 0
            continue
        by_day = df_area_mesi.groupby(df_area_mesi["Data"].dt.date)["Barca_Normalizzata"].nunique()
        max_barche_area[area] = int(by_day.max())
        giorni_barca_attivi[area] = int(df_area_mesi.groupby(["Data", "Barca_Normalizzata"]).ngroups)

    # --- Input barche operative per ogni area ---
    barche_per_area = {}
    if area_sel == "Tutte":
        for area in sorted(df_kpi["Area"].dropna().unique()):
            barche_per_area[area] = st.number_input(
                f"{area}: barche operative", min_value=1, max_value=max_barche_global, value=1, step=1
            )
    else:
        area = area_sel
        barche_per_area[area] = st.slider(
            f"{area}: barche operative", min_value=1, max_value=max_barche_global, value=1, step=1
        )

    incasso_medio = {}
    clienti_medio = {}
    giorni_attivi_per_barca = {}

    anno_corrente = pd.Timestamp.today().year
    trend_incasso = {}
    trend_clienti = {}

    for area in barche_per_area:
        df_area_mesi = df_det[(df_det["Area"] == area) & (df_det["Data"].dt.month.isin(mesi_scelti))]
        if df_area_mesi.empty or max_barche_area[area] == 0:
            incasso_medio[area] = 0
            clienti_medio[area] = 0
            giorni_attivi_per_barca[area] = 0
            trend_incasso[area] = 1
            trend_clienti[area] = 1
            continue

        giorno_barca = df_area_mesi.groupby([df_area_mesi["Data"].dt.date, "Barca_Normalizzata"])
        incassi = giorno_barca["Incasso"].sum().values
        clienti = giorno_barca["Clienti"].sum().values
        n_giorni_barca = len(incassi)
        incasso_medio[area] = np.mean(incassi) if n_giorni_barca > 0 else 0
        clienti_medio[area] = np.mean(clienti) if n_giorni_barca > 0 else 0
        giorni_attivi_per_barca[area] = n_giorni_barca / max(1, max_barche_area[area])

        # --- Trend storico ---
        df_area_mesi["Anno"] = pd.DatetimeIndex(df_area_mesi["Data"]).year
        inc_per_anno = df_area_mesi.groupby("Anno")["Incasso"].mean().sort_index()
        cli_per_anno = df_area_mesi.groupby("Anno")["Clienti"].mean().sort_index()
        if len(inc_per_anno) > 1:
            trend_incasso[area] = (inc_per_anno.iloc[-1] / inc_per_anno.iloc[0]) ** (1/(len(inc_per_anno)-1))
        else:
            trend_incasso[area] = 1
        if len(cli_per_anno) > 1:
            trend_clienti[area] = (cli_per_anno.iloc[-1] / cli_per_anno.iloc[0]) ** (1/(len(cli_per_anno)-1))
        else:
            trend_clienti[area] = 1

    totale_incasso = 0
    totale_clienti = 0
    for area in barche_per_area:
        n_barche = barche_per_area[area]
        if giorni_attivi_per_barca[area] == 0: continue
        # --- Applica il trend annuo dalla media storica all’anno corrente
        n_anni = anno_corrente - (min(df_det["Data"].dt.year) if not df_det.empty else anno_corrente)
        incasso_area = incasso_medio[area] * giorni_attivi_per_barca[area] * n_barche * (trend_incasso[area] ** n_anni)
        clienti_area = clienti_medio[area] * giorni_attivi_per_barca[area] * n_barche * (trend_clienti[area] ** n_anni)
        totale_incasso += incasso_area
        totale_clienti += clienti_area

    st.metric("Incasso stimato totale (trend attualizzato)", f"{totale_incasso:,.0f} €")
    st.metric("Clienti stimati totali (trend attualizzato)", f"{totale_clienti:,.0f}")

    st.caption("""
**Nota:**  
- La simulazione tiene conto della crescita/recessione storica (trend).
- "Riva" compare solo se nei dati ci sono sue tratte reali nei mesi scelti.
- Il calcolo è lineare rispetto al numero di barche inserite (più barche, più risultato).
""")

def tab_suggerimenti(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area=None, barca=None):
    st.header("💡 Suggerimenti & Alert Automatici")
    alert_list = []

    df_tot = df_kpi[df_kpi["TipoRiga"] == "Totale"].copy()
    df_tot["Mese"] = df_tot["Data"].dt.to_period("M").astype(str)
    mesi_nome = df_tot["Data"].dt.month.apply(lambda m: calendar.month_name[m])
    df_tot["MeseNome"] = mesi_nome

    # 1. EFFICIENZA - Soglia dinamica
    eff_mensile = (
        df_tot.groupby(["Barca_Normalizzata", "Mese"])
        .agg({"Incasso": "sum", "Gasolio": "sum"})
        .reset_index()
    )
    eff_mensile["Efficienza"] = eff_mensile["Incasso"] / eff_mensile["Gasolio"].replace(0, np.nan)
    eff_media_barca = eff_mensile.groupby("Barca_Normalizzata")["Efficienza"].mean().dropna()
    soglia_efficienza = eff_media_barca.mean() * 0.8 if len(eff_media_barca) > 0 else 80
    for b, e in eff_media_barca.items():
        if e < soglia_efficienza:
            alert_list.append(f"⚠️ <b>Barca {b}</b> con efficienza media mensile bassa: {e:.1f} €/litro (sotto soglia dinamica {soglia_efficienza:.1f} €/litro)")

    # 2. TOP performer
    top = df_tot.groupby("Barca_Normalizzata")["Incasso"].sum().sort_values(ascending=False)
    if len(top) > 0:
        alert_list.append(f"🏅 <b>Top performer:</b> {top.index[0]} ({top.iloc[0]:,.0f}€)")

    # 3. TREND: confronto incasso ultimo mese vs mese precedente
    if len(df_tot["Mese"].unique()) >= 2:
        mesi_ordine = sorted(df_tot["Mese"].unique())
        mese_attuale = mesi_ordine[-1]
        mese_precedente = mesi_ordine[-2]
        incasso_att = df_tot[df_tot["Mese"] == mese_attuale].groupby("Barca_Normalizzata")["Incasso"].sum()
        incasso_prev = df_tot[df_tot["Mese"] == mese_precedente].groupby("Barca_Normalizzata")["Incasso"].sum()
        for b in incasso_att.index:
            if b in incasso_prev and incasso_att[b] < incasso_prev[b] * 0.8:
                alert_list.append(f"📉 <b>Trend in calo:</b> {b} ha avuto un incasso inferiore del 20% rispetto al mese precedente.")

    # 4. CONCENTRAZIONE: se >60% incasso viene da un solo tour
    if "Durata" in df_kpi.columns:
        tour_top = df_kpi.groupby("Durata")["Incasso"].sum().sort_values(ascending=False)
        incasso_totale = df_kpi["Incasso"].sum()
        if len(tour_top) > 0 and incasso_totale > 0 and tour_top.iloc[0] / incasso_totale > 0.6:
            alert_list.append(f"💡 <b>Attenzione:</b> Il tour <b>{tour_top.index[0]}</b> rappresenta oltre il 60% dell’incasso totale (scarsa diversificazione).")

    # 5. ANOMALIA STAGIONALE: incasso mese corrente inferiore media anni precedenti
    if len(df_tot["Anno"].unique()) >= 2:
        for mese in df_tot["MeseNome"].unique():
            anni = df_tot["Anno"].unique()
            for anno in anni:
                incasso_corr = df_tot[(df_tot["MeseNome"] == mese) & (df_tot["Anno"] == anno)]["Incasso"].sum()
                incassi_passati = df_tot[(df_tot["MeseNome"] == mese) & (df_tot["Anno"] != anno)] \
                                    .groupby("Anno")["Incasso"].sum().values
                if len(incassi_passati) >= 1:
                    media_passati = np.mean(incassi_passati)
                    if media_passati > 0 and incasso_corr < media_passati * 0.7:
                        alert_list.append(f"📉 <b>{mese} {anno} sotto media:</b> incasso inferiore del 30% rispetto alla media dello stesso mese negli anni precedenti.")

    # 6. SFRUTTAMENTO DELLA FLOTTA: barche usate meno della media
    utilizzo_barche = df_tot.groupby("Barca_Normalizzata")["Data"].nunique()
    giorni_totali = df_tot["Data"].nunique()
    media_utilizzo = utilizzo_barche.mean()
    for b, giorni in utilizzo_barche.items():
        if giorni < 0.7 * media_utilizzo:
            alert_list.append(f"⏳ <b>Barca {b}</b> sottoutilizzata: attiva solo {giorni} giorni rispetto a una media di {media_utilizzo:.0f} giorni.")

    # 7. SENSIBILITÀ MALTEMPO: barche che “perdono di più” dei colleghi nei giorni di maltempo
    if "Maltempo" in df_tot.columns and df_tot["Maltempo"].notna().any():
        medie_meteo = df_tot.groupby(["Barca_Normalizzata", "Maltempo"])["Incasso"].mean().unstack()
        if False in medie_meteo.columns and True in medie_meteo.columns:
            medie_meteo["Delta"] = (medie_meteo[True] - medie_meteo[False]) / medie_meteo[False] * 100
            media_flottante = medie_meteo["Delta"].mean()
            for b, delta in medie_meteo["Delta"].items():
                if delta < media_flottante - 15:
                    alert_list.append(f"🌧️ <b>{b}</b> subisce un calo di incasso col maltempo superiore alla media flotta ({delta:.0f}% vs {media_flottante:.0f}%).")

    # 8. BASSA PRENOTAZIONE GIORNI ALTI
    incasso_alti = df_tot[df_tot["TipoGiorno"]=="Alti"]["Incasso"].sum()
    incasso_bassi = df_tot[df_tot["TipoGiorno"]=="Bassi"]["Incasso"].sum()
    if incasso_alti < incasso_bassi * 0.8:
        alert_list.append(f"⚠️ <b>Bassa prenotazione nei giorni ad alta domanda:</b> Incasso giorni alti < 80% rispetto ai giorni bassi.")

    # ALERT OUTPUT
    if alert_list:
        for alert in alert_list:
            st.markdown(alert, unsafe_allow_html=True)
    else:
        st.success("Nessun alert! Tutti i valori sono sopra le soglie.")

    st.caption("""
**Nota:**  
Gli alert automatici segnalano barche poco efficienti, best performer, trend di incasso in calo, scarsa diversificazione commerciale,
anomalie stagionali, sfruttamento sotto media, alta sensibilità al maltempo e bassa prenotazione nei giorni ad alta domanda.
""")

def tab_analisi_spese(df_spese, anno_sel=None, mese_sel=None, area_sel=None):
    st.subheader("💸 Analisi Spese Aziendali")

    # Controlli robusti
    if df_spese is None or df_spese.empty:
        st.warning("Nessuna spesa caricata!")
        return
    if "Data" not in df_spese.columns or "Costo" not in df_spese.columns:
        st.error("Colonne fondamentali mancanti nelle spese!")
        return

    # Filtro per anno/mese
    if anno_sel:
        df_spese = df_spese[df_spese["Data"].dt.year == int(anno_sel)]
    if mese_sel:
        df_spese = df_spese[df_spese["Data"].dt.month == int(mese_sel)]
    if area_sel and area_sel != "Tutte":
        df_spese = df_spese[df_spese["Destinazione"] == area_sel]


    # Spese totali per macro-categoria
    if "Tipo_Spesa" in df_spese.columns:
        spese_fisse = df_spese[df_spese["Tipo_Spesa"].str.lower() == "fissi"]["Costo"].sum()
        spese_var = df_spese[df_spese["Tipo_Spesa"].str.lower() == "variabili"]["Costo"].sum()
        st.metric("Spese fisse", f"{spese_fisse:,.0f} €")
        st.metric("Spese variabili", f"{spese_var:,.0f} €")

    # Spese per categoria (top 10)
    if "Categoria" in df_spese.columns:
        st.markdown("**Spese per Categoria (Top 10)**")
        spese_cat = df_spese.groupby("Categoria")["Costo"].sum().sort_values(ascending=False).head(10)
        st.dataframe(spese_cat.to_frame("Totale").style.format({"Totale": "{:,.0f} €"}))

    # Spese per fornitore (top 10)
    if "Fornitore" in df_spese.columns:
        st.markdown("**Spese per Fornitore (Top 10)**")
        spese_forn = df_spese.groupby("Fornitore")["Costo"].sum().sort_values(ascending=False).head(10)
        st.dataframe(spese_forn.to_frame("Totale").style.format({"Totale": "{:,.0f} €"}))

    # Spese per destinazione (es: barca o azienda)
    if "Destinazione" in df_spese.columns:
        st.markdown("**Spese per Destinazione (Top 10)**")
        spese_dest = df_spese.groupby("Destinazione")["Costo"].sum().sort_values(ascending=False).head(10)
        st.dataframe(spese_dest.to_frame("Totale").style.format({"Totale": "{:,.0f} €"}))

    # Grafico di trend mensile
    if "Data" in df_spese.columns:
        df_spese["AnnoMese"] = df_spese["Data"].dt.to_period("M")
        trend_mensile = df_spese.groupby("AnnoMese")["Costo"].sum()
        st.line_chart(trend_mensile)

    # Tabella completa filtrata (opzionale)
    st.markdown("**Tabella Spese Filtrata**")
    st.dataframe(df_spese.head(50))

def tab_pdf(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area=None, barca=None):
    from fpdf import FPDF
    import matplotlib.pyplot as plt
    st.header("📄 Report PDF – Esporta analisi")
    if st.button("Crea e scarica report PDF"):
        tmpdir = tempfile.mkdtemp()
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Report Analitico Tour Boat Taxi", ln=True, align="C")
        pdf.set_font("Arial", "", 12)
        df_tot = df_kpi[df_kpi["TipoRiga"] == "Totale"]
        start_date = df_tot["Data"].min()
        end_date = df_tot["Data"].max()
        pdf.cell(0, 10, f"Periodo analisi: {start_date.strftime('%d/%m/%Y')} – {end_date.strftime('%d/%m/%Y')}", ln=True)
        pdf.ln(5)
        pdf.cell(0, 8, f"Incasso totale: {df_tot['Incasso'].sum():,.0f} €", ln=True)
        pdf.cell(0, 8, f"Numero clienti: {df_tot['Clienti'].sum():,.0f}", ln=True)
        pdf.cell(0, 8, f"Tour effettuati: {len(df_tot)}", ln=True)
        try:
            pdf.cell(0, 8, f"Efficienza €/litro: {(df_tot['Incasso'].sum()/df_tot['Gasolio'].sum()):.2f}", ln=True)
        except:
            pdf.cell(0, 8, f"Efficienza €/litro: —", ln=True)
        pdf.ln(5)
        fig, ax = plt.subplots(figsize=(5,3))
        df_box = df_tot.copy()
        if not df_box.empty:
            df_box.boxplot(column="Incasso", by="TipoCliente", ax=ax)
            plt.title("Boxplot Incasso per Cliente")
            plt.suptitle("")
            fig.tight_layout()
            img_path = os.path.join(tmpdir, "boxplot.png")
            fig.savefig(img_path)
            pdf.image(img_path, w=100)
            plt.close(fig)
        df_box["Mese"] = df_box["Data"].dt.to_period("M").astype(str)
        if not df_box.empty:
            fig2, ax2 = plt.subplots(figsize=(5,3))
            df_box.groupby("Mese")["Incasso"].sum().plot(ax=ax2)
            ax2.set_title("Trend incasso mensile")
            fig2.tight_layout()
            img_path2 = os.path.join(tmpdir, "trend.png")
            fig2.savefig(img_path2)
            pdf.image(img_path2, w=100)
            plt.close(fig2)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(0, 10, "Statistiche principali:", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 8, "Vedi dashboard per ulteriori approfondimenti.", ln=True)
        pdf_file = os.path.join(tmpdir, "report_analitico.pdf")
        pdf.output(pdf_file)
        with open(pdf_file, "rb") as f:
            st.download_button("Scarica PDF", f, file_name="report_analitico.pdf", mime="application/pdf")
        import shutil
        shutil.rmtree(tmpdir)
        

def tab_tutti_i_tab(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area, barca, df=None):
    """
    Visualizza tutte le tab principali, incluso il forecast.
    Args:
        df_kpi: DataFrame filtrato per i KPI (filtraggio principale)
        periodo_selezionato, giorno_sel, tipo_cliente_sel, area, barca: filtri correnti
        df: DataFrame globale non filtrato (necessario solo per Forecast)
    """
    tab_kpi(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area, barca)
    tabs = st.tabs([
        "Performance", "Popolarità Tour", "Trend & Confronto Storico", "Maltempo",
        "Forecast", "Simulatore", "Suggerimenti", "Analisi Spese", "PDF Report"
    ])

    with tabs[0]:
        tab_performance(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area, barca)
    with tabs[1]:
        tab_popolarita(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area, barca)
    with tabs[2]:
        tab_stagionalita(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area, barca)
    with tabs[3]:
        tab_maltempo(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area, barca)
    with tabs[4]:
        # --- Forecast: parte sempre dal df globale ---
        df_forecast = df.copy() if df is not None else df_kpi.copy()
        if area and area != "Tutte":
            df_forecast = df_forecast[df_forecast["Area"] == area]
        if barca and barca != "Tutte":
            df_forecast = df_forecast[df_forecast["Barca_Normalizzata"] == barca]
        if giorno_sel == "Alti":
            df_forecast = df_forecast[df_forecast["TipoGiorno"] == "Alti"]
        elif giorno_sel == "Bassi":
            df_forecast = df_forecast[df_forecast["TipoGiorno"] == "Bassi"]
        elif giorno_sel == "Confronto Alti/Bassi":
            df_forecast = df_forecast[df_forecast["TipoGiorno"].isin(["Alti", "Bassi"])]
        # TipoCliente: solo sulle righe Dettaglio, quindi filtra dopo
        if tipo_cliente_sel == "Privati":
            df_forecast = df_forecast[df_forecast["TipoCliente"] == "Privati"]
        elif tipo_cliente_sel == "Gruppo":
            df_forecast = df_forecast[df_forecast["TipoCliente"] == "Gruppo"]
        elif tipo_cliente_sel == "Confronto Privati/Gruppo":
            df_forecast = df_forecast[df_forecast["TipoCliente"].isin(["Privati", "Gruppo"])]
        tab_forecast(df_forecast, periodo_selezionato, giorno_sel, tipo_cliente_sel, area, barca)
    with tabs[5]:
        tab_simulatore(df_kpi)
    with tabs[6]:
        tab_suggerimenti(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area, barca)
    with tabs[7]:
        tab_analisi_spese(df_spese, anno_sel=2025, mese_sel=None, area_sel="Azienda")
    with tabs[8]:
        tab_pdf(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area, barca)

tab_tutti_i_tab(df_kpi, periodo_selezionato, giorno_sel, tipo_cliente_sel, area_sel, barca_sel, df=df)
