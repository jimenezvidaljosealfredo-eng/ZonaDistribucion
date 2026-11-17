import html
import json
import streamlit as st
import pandas as pd
import folium
from folium.plugins import FastMarkerCluster
from shapely.geometry import Point, shape
from streamlit_folium import st_folium


# ============================================================
# 1. CONFIGURACIÓN GENERAL Y COLUMNAS EXACTAS DEL CSV
# ============================================================

st.set_page_config(
    page_title="Gestión Comercial y Logística RTM",
    page_icon="🗺️",
    layout="wide",
)

st.title("🗺️ Herramienta RTM: Asignación Espacial y Corrección de Clientes")
st.markdown(
    "Consulta y edición geoespacial para la gestión comercial y logística."
)

LAT_DEFAULT = -16.528041
LON_DEFAULT = -68.104807

ARCHIVO_CLIENTES = "BD PuebaLP.csv"
ARCHIVO_GEOJSON = "MapaDistibucion LPZPrueba.geojson"

# Nombres exactos según la estructura de tu CSV
COL_GRUPO_RTM = "Grupo RTM"
COL_ZONA_COM = "idZonaList"
COL_ZONA_DIS = "idZonaDis"


# ============================================================
# 2. CARGA Y PRE-PROCESAMIENTO OPTIMIZADO EN CACHÉ
# ============================================================

@st.cache_data
def load_data():
    """Carga el CSV limpiando tipos de datos y pre-procesa el GeoJSON."""
    df_clientes = None
    errores = []

    for encoding in ["latin-1", "utf-8", "cp1252"]:
        for sep in [";", ","]:
            try:
                df_temp = pd.read_csv(
                    ARCHIVO_CLIENTES,
                    sep=sep,
                    encoding=encoding,
                    low_memory=False,
                )
                if len(df_temp.columns) > 1:
                    df_clientes = df_temp
                    break
            except Exception as e:
                errores.append(str(e))
        if df_clientes is not None:
            break

    if df_clientes is None:
        raise ValueError("No fue posible leer el CSV. " + " | ".join(errores))

    # Limpiar posibles espacios en los encabezados del CSV
    df_clientes.columns = df_clientes.columns.str.strip()

    if "IdCliente" not in df_clientes.columns:
        raise ValueError("El archivo CSV no contiene la columna 'IdCliente'.")

    # Normalizar ID y columnas de filtro (quita '.0' si Pandas las leyó como float)
    columnas_texto = ["IdCliente", COL_GRUPO_RTM, COL_ZONA_COM, COL_ZONA_DIS]
    for col in columnas_texto:
        if col in df_clientes.columns:
            df_clientes[col] = (
                df_clientes[col]
                .fillna("Sin asignar")
                .astype(str)
                .str.strip()
                .str.replace(r"\
