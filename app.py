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

    df_clientes.columns = df_clientes.columns.str.strip()

    if "IdCliente" not in df_clientes.columns:
        raise ValueError("El archivo CSV no contiene la columna 'IdCliente'.")

    # Limpieza segura sin barras invertidas ni regex (evita SyntaxError al copiar)
    columnas_texto = ["IdCliente", COL_GRUPO_RTM, COL_ZONA_COM, COL_ZONA_DIS]
    for col in columnas_texto:
        if col in df_clientes.columns:
            df_clientes[col] = (
                df_clientes[col]
                .fillna("Sin asignar")
                .astype(str)
                .str.strip()
                .str.removesuffix(".0")
            )

    # Vectorización de coordenadas una sola vez
    for col in ["Latitud", "Longitud"]:
        if col in df_clientes.columns:
            df_clientes[f"_{col}_num"] = pd.to_numeric(
                df_clientes[col].astype(str).str.replace(",", ".", regex=False),
                errors="coerce",
            ).round(6)
        else:
            df_clientes[f"_{col}_num"] = None

    with open(ARCHIVO_GEOJSON, "r", encoding="utf-8") as archivo:
        geojson_data = json.load(archivo)

    campos_etiqueta = [
        ("_orig_proveedores", "ORIG_PROVEEDORES"),
        ("_orig_visita_vendedor", "ORIG_VISITA_VENDEDOR"),
        ("_orig_dv_distribuidor", "ORIG_DV_DISTRIBUIDOR"),
        ("_orig_id_zona_dist", "ORIG_IdZonaDist"),
    ]

    for feature in geojson_data.get("features", []):
        propiedades = feature.setdefault("properties", {})
        for campo_auxiliar, campo_original in campos_etiqueta:
            valor = propiedades.get(campo_original)
            propiedades[campo_auxiliar] = (
                str(valor).strip() if valor not in (None, "") else "Sin dato"
            )

    return df_clientes, geojson_data


@st.cache_resource
def build_spatial_shapes(_geojson_data):
    """Pre-compila las geometrías de Shapely en memoria."""
    geometrias_preparadas = []
    for feature in _geojson_data.get("features", []):
        if feature.get("geometry"):
            geom = shape(feature["geometry"])
            props = feature.get("properties", {})
            geometrias_preparadas.append((geom, props))
    return geometrias_preparadas


try:
    df_clientes, geojson_data = load_data()
    geometrias_rtm = build_spatial_shapes(geojson_data)
except Exception as error:
    st.error(f"Error cargando los archivos locales: {error}")
    st.stop()


# ============================================================
# 3. FUNCIONES AUXILIARES Y FILTRADO DINÁMICO
# ============================================================

def obtener_datos_cliente(id_cliente):
    if not id_cliente:
        return None
    resultado = df_clientes[df_clientes["IdCliente"] == str(id_cliente).strip()]
    return None if resultado.empty else resultado.iloc[0]


def actualizar_coordenadas(prefijo, latitud, longitud):
    latitud = round(float(latitud), 6)
    longitud = round(float(longitud), 6)

    st.session_state[f"{prefijo}_lat"] = latitud
    st.session_state[f"{prefijo}_lon"] = longitud
    st.session_state[f"input_{prefijo}_lat"] = latitud
    st.session_state[f"input_{prefijo}_lon"] = longitud


def callback_latitud(prefijo):
    st.session_state[f"{prefijo}_lat"] = round(
        float(st.session_state[f"input_{prefijo}_lat"]), 6
    )


def callback_longitud(prefijo):
    st.session_state[f"{prefijo}_lon"] = round(
        float(st.session_state[f"input_{prefijo}_lon"]), 6
    )


def procesar_clic_mapa(map_data, prefijo):
    if not map_data:
        return

    click = map_data.get("last_clicked")
    if not click:
        return

    click_lat = round(float(click["lat"]), 6)
    click_lon = round(float(click["lng"]), 6)
    click_token = (click_lat, click_lon)

    control_key = f"{prefijo}_last_processed_click"
    if st.session_state.get(control_key) == click_token:
        return

    st.session_state[control_key] = click_token

    coordenadas_actuales = (
        round(float(st.session_state[f"{prefijo}_lat"]), 6),
        round(float(st.session_state[f"{prefijo}_lon"]), 6),
    )

    if click_token == coordenadas_actuales:
        return

    actualizar_coordenadas(prefijo, click_lat, click_lon)
    st.rerun()


def obtener_asignacion(latitud, longitud):
    punto = Point(float(longitud), float(latitud))

    for geometria, propiedades in geometrias_rtm:
        if geometria.contains(punto):
            zona = (
                propiedades.get("CODIGO_ZONA_RTM")
                or propiedades.get("id_zona")
            )
            id_zona_dis = (
                propiedades.get("ORIG_IdZonaDist")
                or propiedades.get("idZonaDis")
                or zona
            )
            distribuidor = (
                propiedades.get("PROVEEDOR_RTM")
                or propiedades.get("distribuidor")
            )
            return zona, id_zona_dis, distribuidor

    return None, None, None


def renderizar_filtros_clientes(prefijo_ui):
    k_rtm = f"{prefijo_ui}_filtro_rtm"
    k_com = f"{prefijo_ui}_filtro_com"
    k_dis = f"{prefijo_ui}_filtro_dis"

    for k in [k_rtm, k_com, k_dis]:
        if k not in st.session_state:
            st.session_state[k] = "Todos"

    def filtrar_df(df, rtm_val, com_val, dis_val):
        m = pd.Series(True, index=df.index)
        if rtm_val != "Todos" and COL_GRUPO_RTM in df.columns:
            m &= df[COL_GRUPO_RTM] == rtm_val
        if com_val != "Todos" and COL_ZONA_COM in df.columns:
            m &= df[COL_ZONA_COM] == com_val
        if dis_val != "Todos" and COL_ZONA_DIS in df.columns:
            m &= df[COL_ZONA_DIS] == dis_val
        return df[m]

    val_rtm = st.session_state[k_rtm]
    val_com = st.session_state[k_com]
    val_dis = st.session_state[k_dis]

    if COL_GRUPO_RTM in df_clientes.columns:
        validos_rtm = set(filtrar_df(df_clientes, "Todos", val_com, val_dis)[COL_GRUPO_RTM].unique())
        if val_rtm != "Todos" and val_rtm not in validos_rtm:
            st.session_state[k_rtm] = "Todos"
            val_rtm = "Todos"

    if COL_ZONA_COM in df_clientes.columns:
        validos_com = set(filtrar_df(df_clientes, val_rtm, "Todos", val_dis)[COL_ZONA_COM].unique())
        if val_com != "Todos" and val_com not in validos_com:
            st.session_state[k_com] = "Todos"
            val_com = "Todos"

    if COL_ZONA_DIS in df_clientes.columns:
        validos_dis = set(filtrar_df(df_clientes, val_rtm, val_com, "Todos")[COL_ZONA_DIS].unique())
        if val_dis != "Todos" and val_dis not in validos_dis:
            st.session_state[k_dis] = "Todos"
            val_dis = "Todos"

    with st.expander("🌪️ Filtros Dinámicos (Ocultan valores que no pertenecen)", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns([1.2, 1.2, 1.2, 0.6])

        with f_col1:
            if COL_GRUPO_RTM in df_clientes.columns:
                df_op_rtm = filtrar_df(df_clientes, "Todos", st.session_state[k_com], st.session_state[k_dis])
                opciones_rtm = ["Todos"] + sorted(df_op_rtm[COL_GRUPO_RTM].unique().tolist())
                st.selectbox("Grupo RTM:", opciones_rtm, key=k_rtm)
            else:
                st.caption(f"⚠️ `{COL_GRUPO_RTM}` no encontrada.")

        with f_col2:
            if COL_ZONA_COM in df_clientes.columns:
                df_op_com = filtrar_df(df_clientes, st.session_state[k_rtm], "Todos", st.session_state[k_dis])
                opciones_com = ["Todos"] + sorted(df_op_com[COL_ZONA_COM].unique().tolist())
                st.selectbox("Zona Comercial (idZonaList):", opciones_com, key=k_com)
            else:
                st.caption(f"⚠️ `{COL_ZONA_COM}` no encontrada.")

        with f_col3:
            if COL_ZONA_DIS in df_clientes.columns:
                df_op_dis = filtrar_df(df_clientes, st.session_state[k_rtm], st.session_state[k_com], "Todos")
                opciones_dis = ["Todos"] + sorted(df_op_dis[COL_ZONA_DIS].unique().tolist())
                st.selectbox("Zona Distribución (idZonaDis):", opciones_dis, key=k_dis)
            else:
                st.caption(f"⚠️ `{COL_ZONA_DIS}` no encontrada.")

        with f_col4:
            st.write("")
            st.write("")
            if st.button("🔄 Limpiar", key=f"{prefijo_ui}_btn_limpiar", use_container_width=True):
                st.session_state[k_rtm] = "Todos"
                st.session_state[k_com] = "Todos"
                st.session_state[k_dis] = "Todos"
                st.rerun()

        df_final = filtrar_df(
            df_clientes,
            st.session_state[k_rtm],
            st.session_state[k_com],
            st.session_state[k_dis],
        )

        filtros_activos = {
            "rtm": st.session_state[k_rtm],
            "com": st.session_state[k_com],
            "dis": st.session_state[k_dis],
            "hay_filtro": any(
                v != "Todos"
                for v in [st.session_state[k_rtm], st.session_state[k_com], st.session_state[k_dis]]
            ),
        }

        st.caption(
            f"📊 Mostrando **{len(df_final):,}** clientes pertenecientes a la selección "
            f"(de {len(df_clientes):,} totales)."
        )

    return df_final, filtros_activos


def filtrar_geojson_por_seleccion(df_filtrado, filtros_activos, ocultar_poligonos_no_pertenecientes=True):
    if not ocultar_poligonos_no_pertenecientes or not filtros_activos
