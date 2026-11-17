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

    # Nombres sin guion bajo inicial para que itertuples() los reconozca
    for col in ["Latitud", "Longitud"]:
        if col in df_clientes.columns:
            df_clientes[f"{col}_num"] = pd.to_numeric(
                df_clientes[col].astype(str).str.replace(",", ".", regex=False),
                errors="coerce",
            ).round(6)
        else:
            df_clientes[f"{col}_num"] = None

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
    if not ocultar_poligonos_no_pertenecientes or not filtros_activos["hay_filtro"]:
        return geojson_data

    zonas_dis_validas = set(df_filtrado[COL_ZONA_DIS].unique()) if COL_ZONA_DIS in df_filtrado.columns else set()
    zonas_com_validas = set(df_filtrado[COL_ZONA_COM].unique()) if COL_ZONA_COM in df_filtrado.columns else set()

    features_filtradas = []
    for feature in geojson_data.get("features", []):
        props = feature.get("properties", {})

        z_dis_geo = str(props.get("ORIG_IdZonaDist") or props.get("idZonaDis") or "").strip().removesuffix(".0")
        z_com_geo = str(props.get("CODIGO_ZONA_RTM") or props.get("id_zona") or "").strip().removesuffix(".0")

        coincide_dis = bool(z_dis_geo and z_dis_geo in zonas_dis_validas)
        coincide_com = bool(z_com_geo and z_com_geo in zonas_com_validas)

        if coincide_dis or coincide_com:
            features_filtradas.append(feature)

    if not features_filtradas:
        return geojson_data

    return {"type": "FeatureCollection", "features": features_filtradas}


def crear_mapa(latitud, longitud, zoom=15, geojson_a_mostrar=None):
    mapa = folium.Map(
        location=[latitud, longitud],
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True,
        prefer_canvas=True,
    )

    datos_geo = geojson_a_mostrar if geojson_a_mostrar is not None else geojson_data

    campos = [
        "_orig_proveedores",
        "_orig_visita_vendedor",
        "_orig_dv_distribuidor",
        "_orig_id_zona_dist",
    ]
    alias = [
        "Orig Proveedores:",
        "DV Vendedor:",
        "DV Distribuidor:",
        "IdZona Dist:",
    ]

    if datos_geo.get("features"):
        folium.GeoJson(
            datos_geo,
            name="Zonas RTM",
            style_function=lambda feature: {
                "fillColor": "#3388ff",
                "color": "#3388ff",
                "weight": 2,
                "fillOpacity": 0.18,
            },
            highlight_function=lambda feature: {
                "weight": 3,
                "color": "#ff7800",
                "fillOpacity": 0.38,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=campos,
                aliases=alias,
                sticky=True,
                labels=True,
            ),
            bubblingMouseEvents=False,
        ).add_to(mapa)

    return mapa


def agregar_clientes_optimizado(mapa, df_filtrado, modo_vista="Puntos filtrados (máx. 500)"):
    df_validos = df_filtrado.dropna(subset=["Latitud_num", "Longitud_num"])
    df_validos = df_validos[
        (df_validos["Latitud_num"].between(-90, 90))
        & (df_validos["Longitud_num"].between(-180, 180))
    ]

    if df_validos.empty or modo_vista == "Ocultar cartera de clientes":
        return mapa

    if modo_vista == "Agrupar en Clústeres (Rápido)":
        coordenadas = df_validos[["Latitud_num", "Longitud_num"]].values.tolist()
        FastMarkerCluster(coordenadas, name="Clúster Clientes").add_to(mapa)
        return mapa

    capa_clientes = folium.FeatureGroup(name="Clientes Filtrados", show=True)
    df_muestra = df_validos.head(500)

    # Iteración segura por registros (evita conflictos de nombres en itertuples)
    columnas_necesarias = ["IdCliente", "Razon_Social", "Direccion", COL_ZONA_DIS, "Latitud_num", "Longitud_num"]
    cols_presentes = [c for c in columnas_necesarias if c in df_muestra.columns]

    for row in df_muestra[cols_presentes].to_dict(orient="records"):
        c_id = html.escape(str(row.get("IdCliente", "")))
        razon = html.escape(str(row.get("Razon_Social", "S/N")))
        direc = html.escape(str(row.get("Direccion", "S/N")))
        z_dis = html.escape(str(row.get(COL_ZONA_DIS, "S/N")))

        folium.CircleMarker(
            location=[row["Latitud_num"], row["Longitud_num"]],
            radius=4,
            color="#455a64",
            weight=1,
            fill=True,
            fill_color="#607d8b",
            fill_opacity=0.80,
            bubblingMouseEvents=False,
            tooltip=f"{c_id} - {razon}",
            popup=folium.Popup(
                f"<b>ID:</b> {c_id}<br><b>Cliente:</b> {razon}<br>"
                f"<b>Dir:</b> {direc}<br><b>idZonaDis:</b> {z_dis}",
                max_width=260,
            ),
        ).add_to(capa_clientes)

    capa_clientes.add_to(mapa)
    return mapa


def guardar_registro_bitacora(registro_dict):
    if "correcciones" not in st.session_state:
        st.session_state["correcciones"] = []
    st.session_state["correcciones"].append(registro_dict.copy())


# ============================================================
# 4. INICIALIZACIÓN DEL ESTADO DE SESIÓN
# ============================================================

VALORES_INICIALES = {
    "cons_lat": LAT_DEFAULT,
    "cons_lon": LON_DEFAULT,
    "edit_lat": LAT_DEFAULT,
    "edit_lon": LON_DEFAULT,
    "input_cons_lat": LAT_DEFAULT,
    "input_cons_lon": LON_DEFAULT,
    "input_edit_lat": LAT_DEFAULT,
    "input_edit_lon": LON_DEFAULT,
    "prev_cons_id": "",
    "prev_cons_filter_token": None,
    "prev_edit_target": None,
    "cons_last_processed_click": None,
    "edit_last_processed_click": None,
    "correcciones": [],
}

for clave, valor in VALORES_INICIALES.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor


# ============================================================
# 5. NAVEGACIÓN Y OPCIONES DE VISUALIZACIÓN EN SIDEBAR
# ============================================================

st.sidebar.header("Panel de Control")

modo = st.sidebar.radio(
    "Selecciona una opción:",
    [
        "Consulta y Asignación Rápida",
        "Editor y Creación de Clientes",
    ],
)

st.sidebar.markdown("---")
st.sidebar.subheader("⚡ Rendimiento y Capas")
modo_puntos = st.sidebar.selectbox(
    "Visualización de clientes en mapa:",
    [
        "Puntos filtrados (máx. 500)",
        "Agrupar en Clústeres (Rápido)",
        "Ocultar cartera de clientes",
    ],
    index=0,
)

ocultar_poligonos = st.sidebar.checkbox(
    "Ocultar polígonos fuera del filtro",
    value=True,
    help="Cuando filtras por Grupo RTM, idZonaList o idZonaDis, oculta del mapa los polígonos que no pertenecen a esa selección.",
)


# ============================================================
# 6. PESTAÑA 1: CONSULTA Y ASIGNACIÓN RÁPIDA
# ============================================================

if modo == "Consulta y Asignación Rápida":

    st.subheader("🔍 Consulta Dinámica por ID de Cliente")

    df_clientes_filtrados, filtros_activos = renderizar_filtros_clientes("cons")

    lista_ids = [""] + sorted(df_clientes_filtrados["IdCliente"].unique().tolist())

    id_buscado = st.selectbox(
        "Seleccione o busque el ID de Cliente (solo muestra los pertenecientes al filtro):",
        lista_ids,
        key="sel_consulta_id",
    )

    token_filtro_actual = (filtros_activos["rtm"], filtros_activos["com"], filtros_activos["dis"])
    if token_filtro_actual != st.session_state["prev_cons_filter_token"]:
        st.session_state["prev_cons_filter_token"] = token_filtro_actual
        if not id_buscado and filtros_activos["hay_filtro"]:
            df_coords = df_clientes_filtrados.dropna(subset=["Latitud_num", "Longitud_num"])
            if not df_coords.empty:
                actualizar_coordenadas(
                    "cons",
                    df_coords["Latitud_num"].mean(),
                    df_coords["Longitud_num"].mean(),
                )

    if id_buscado != st.session_state["prev_cons_id"]:
        st.session_state["prev_cons_id"] = id_buscado
        cliente = obtener_datos_cliente(id_buscado)

        if cliente is not None:
            latitud = cliente.get("Latitud_num")
            longitud = cliente.get("Longitud_num")
            latitud = LAT_DEFAULT if pd.isna(latitud) else float(latitud)
            longitud = LON_DEFAULT if pd.isna(longitud) else float(longitud)
        else:
            latitud, longitud = st.session_state["cons_lat"], st.session_state["cons_lon"]

        actualizar_coordenadas("cons", latitud, longitud)
        st.session_state["cons_last_processed_click"] = None

    cliente_encontrado = obtener_datos_cliente(id_buscado)

    razon_social_txt = "N/A"
    direccion_txt = "N/A"

    if cliente_encontrado is not None:
        razon_social_txt = cliente_encontrado.get("Razon_Social", "N/A")
        direccion_txt = cliente_encontrado.get("Direccion", "N/A")

    col1, col2 = st.columns([1, 2])

    with col2:
        st.markdown("### 🗺️ Visualización Cartográfica")

        geojson_filtrado = filtrar_geojson_por_seleccion(
            df_clientes_filtrados,
            filtros_activos,
            ocultar_poligonos_no_pertenecientes=ocultar_poligonos,
        )

        mapa_consulta = crear_mapa(
            st.session_state["cons_lat"],
            st.session_state["cons_lon"],
            zoom=15,
            geojson_a_mostrar=geojson_filtrado,
        )

        agregar_clientes_optimizado(
            mapa_consulta,
            df_clientes_filtrados,
            modo_vista=modo_puntos,
        )

        folium.CircleMarker(
            location=[
                st.session_state["cons_lat"],
                st.session_state["cons_lon"],
            ],
            radius=8,
            color="#ffffff",
            weight=2,
            fill=True,
            fill_color="#1976d2",
            fill_opacity=0.95,
            bubblingMouseEvents=False,
            tooltip="Coordenada activa",
            popup=folium.Popup(
                f"<b>ID:</b> {id_buscado or 'Sin seleccionar'}<br>{razon_social_txt}",
                max_width=280,
            ),
        ).add_to(mapa_consulta)

        folium.LayerControl(collapsed=True).add_to(mapa_consulta)

        id_mapa_consulta = f"{id_buscado or 'sin_id'}_{token_filtro_actual}"
        map_cons_data = st_folium(
            mapa_consulta,
            use_container_width=True,
            height=500,
            key=f"map_consulta_{id_mapa_consulta}",
            returned_objects=["last_clicked"],
        )

        procesar_clic_mapa(map_cons_data, "cons")

    with col1:
        st.markdown("### 📋 Datos del Cliente")

        if cliente_encontrado is not None:
            st.success(f"Encontrado: **{razon_social_txt}**")
            st.write(f"**Razón Social:** {razon_social_txt}")
            st.write(f"**Dirección:** {direccion_txt}")
            st.write(f"**Grupo RTM:** {cliente_encontrado.get(COL_GRUPO_RTM, 'N/A')}")
            st.write(f"**Zona Comercial (`idZonaList`):** {cliente_encontrado.get(COL_ZONA_COM, 'N/A')}")
            st.write(f"**Zona Distribución (`idZonaDis`):** {cliente_encontrado.get(COL_ZONA_DIS, 'N/A')}")
            if "Tipo_Negocio" in df_clientes.columns:
                st.write(f"**Tipo Negocio:** {cliente_encontrado.get('Tipo_Negocio', 'N/A')}")
            if "FrecuenciaRTM" in df_clientes.columns:
                st.write(f"**Frecuencia RTM:** {cliente_encontrado.get('FrecuenciaRTM', 'N/A')}")
        else:
            st.info("Seleccione un ID de cliente válido.")

        st.number_input(
            "Latitud",
            format="%.6f",
            key="input_cons_lat",
            on_change=callback_latitud,
            args=("cons",),
        )

        st.number_input(
            "Longitud",
            format="%.6f",
            key="input_cons_lon",
            on_change=callback_longitud,
            args=("cons",),
        )

        zona, id_zona_dis, distribuidor = obtener_asignacion(
            st.session_state["cons_lat"],
            st.session_state["cons_lon"],
        )

        st.markdown("### 🎯 Cuadro de Asignación Territorial")

        if id_zona_dis or zona:
            st.info(
                f"📌 **Id zona Dis / Zona:** `{id_zona_dis or zona}`\n\n"
                f"🏢 **Distribuidor / Proveedor:** "
                f"`{distribuidor or 'Asignado por Zona'}`"
            )
        else:
            st.error(
                "⚠️ **Fuera de cobertura:** Las coordenadas actuales "
                "no intersectan con ningún polígono activo."
            )


# ============================================================
# 7. PESTAÑA 2: EDITOR Y CREACIÓN DE CLIENTES
# ============================================================

elif modo == "Editor y Creación de Clientes":

    st.subheader("📝 Gestión de Corrección y Creación Diaria")

    tipo_accion = "Modificar Cliente Existente"

    df_edit_filtrados, filtros_edit_activos = renderizar_filtros_clientes("edit")

    lista_ids_edit = [""] + sorted(
        df_edit_filtrados["IdCliente"].unique().tolist()
    )

    id_objetivo = st.selectbox(
        "Seleccione el ID de Cliente existente a modificar (filtrado):",
        lista_ids_edit,
        key="sel_edit_id",
    )

    row_data = obtener_datos_cliente(id_objetivo) if id_objetivo else None

    if row_data is not None:
        lat_val = row_data.get("Latitud_num")
        lon_val = row_data.get("Longitud_num")
        default_lat = LAT_DEFAULT if pd.isna(lat_val) else float(lat_val)
        default_lon = LON_DEFAULT if pd.isna(lon_val) else float(lon_val)
        razon_social_val = row_data.get("Razon_Social", "N/A")
        direccion_val = row_data.get("Direccion", "N/A")
    else:
        default_lat, default_lon = LAT_DEFAULT, LON_DEFAULT
        razon_social_val, direccion_val = "", ""

    if id_objetivo:
        target_token = (tipo_accion, str(id_objetivo).strip())

        if target_token != st.session_state["prev_edit_target"]:
            st.session_state["prev_edit_target"] = target_token
            actualizar_coordenadas("edit", default_lat, default_lon)
            st.session_state["edit_last_processed_click"] = None

        st.info(
            f"**Operando sobre ID:** {id_objetivo} "
            f"| **Cliente:** {razon_social_val or 'Nuevo'} "
            f"| **idZonaDis actual:** {row_data.get(COL_ZONA_DIS, 'N/A')}"
        )

        col_form, col_map = st.columns([1, 1.5])

        with col_map:
            st.markdown("#### 🗺️ Mapa Interactivo (Haz clic para reubicar el pin)")

            geojson_edit_filtrado = filtrar_geojson_por_seleccion(
                df_edit_filtrados,
                filtros_edit_activos,
                ocultar_poligonos_no_pertenecientes=ocultar_poligonos,
            )

            mapa_editor = crear_mapa(
                st.session_state["edit_lat"],
                st.session_state["edit_lon"],
                zoom=15,
                geojson_a_mostrar=geojson_edit_filtrado,
            )

            folium.Marker(
                [
                    st.session_state["edit_lat"],
                    st.session_state["edit_lon"],
                ],
                popup=f"ID: {id_objetivo} ({tipo_accion})",
                icon=folium.Icon(color="green", icon="map-marker"),
            ).add_to(mapa_editor)

            folium.LayerControl(collapsed=True).add_to(mapa_editor)

            id_key = str(id_objetivo).strip()
            map_edit_data = st_folium(
                mapa_editor,
                use_container_width=True,
                height=480,
                key=f"map_editor_existente_{id_key}",
                returned_objects=["last_clicked"],
            )

            procesar_clic_mapa(map_edit_data, "edit")

        with col_form:
            st.markdown("#### 📍 Coordenadas Activas")

            st.number_input(
                "Latitud",
                format="%.6f",
                key="input_edit_lat",
                on_change=callback_latitud,
                args=("edit",),
            )

            st.number_input(
                "Longitud",
                format="%.6f",
                key="input_edit_lon",
                on_change=callback_longitud,
                args=("edit",),
            )

            usuario = st.text_input(
                "Usuario responsable:",
                "Operador_Logistico",
                key="input_usuario",
            )

            zona_temp, id_zona_dis_temp, distribuidor_temp = obtener_asignacion(
                st.session_state["edit_lat"],
                st.session_state["edit_lon"],
            )

            zona_temp = zona_temp or "Fuera de cobertura"
            id_zona_dis_temp = id_zona_dis_temp or "Fuera de cobertura"
            distribuidor_temp = distribuidor_temp or "Ninguno"

            st.markdown("---")
            st.markdown(f"**Zona Detectada:** `{zona_temp}`")
            st.markdown(f"**Id Zona Dis:** `{id_zona_dis_temp}`")
            st.markdown(f"**Distribuidor:** `{distribuidor_temp}`")

            if st.button("Guardar Registro / Corrección", type="primary"):
                nuevo_registro = {
                    "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Tipo_Operacion": tipo_accion,
                    "Cliente_ID": id_objetivo,
                    "Razon_Social": razon_social_val,
                    "Direccion": direccion_val,
                    "Lat_Asignada": st.session_state["edit_lat"],
                    "Lon_Asignada": st.session_state["edit_lon"],
                    "Id_Zona_Dis": id_zona_dis_temp,
                    "Distribuidor": distribuidor_temp,
                    "Usuario": usuario,
                }
                guardar_registro_bitacora(nuevo_registro)
                st.success(f"¡Registro guardado exitosamente para el ID {id_objetivo}!")

        if st.session_state["correcciones"]:
            st.markdown("---")
            st.markdown("### 📑 Historial de Bitácora (Sesión Actual)")
            df_corr = pd.DataFrame(st.session_state["correcciones"])
            st.dataframe(df_corr, use_container_width=True, hide_index=True)
            st.caption(f"Total de registros en esta sesión: {len(df_corr)}")
    else:
        st.warning("Seleccione un cliente existente para comenzar la corrección.")
