import json
import streamlit as st
import pandas as pd
import folium
from shapely.geometry import Point, shape
from streamlit_folium import st_folium


# ============================================================
# 1. CONFIGURACIÓN GENERAL
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


# ============================================================
# 2. CARGA DE INFORMACIÓN
# ============================================================

@st.cache_data
def load_data():
    """Carga el CSV probando las codificaciones y separadores originales."""
    df_clientes = None
    errores = []

    for encoding in ["latin-1", "utf-8", "cp1252"]:
        try:
            df_clientes = pd.read_csv(
                ARCHIVO_CLIENTES,
                sep=";",
                encoding=encoding,
            )
            break
        except Exception as error_punto_y_coma:
            errores.append(str(error_punto_y_coma))

            try:
                df_clientes = pd.read_csv(
                    ARCHIVO_CLIENTES,
                    sep=",",
                    encoding=encoding,
                )
                break
            except Exception as error_coma:
                errores.append(str(error_coma))

    if df_clientes is None:
        raise ValueError(
            "No fue posible leer el CSV. " + " | ".join(errores)
        )

    with open(ARCHIVO_GEOJSON, "r", encoding="utf-8") as archivo:
        geojson_data = json.load(archivo)

    return df_clientes, geojson_data


try:
    df_clientes, geojson_data = load_data()
except Exception as error:
    st.error(f"Error cargando los archivos locales: {error}")
    st.stop()

if "IdCliente" not in df_clientes.columns:
    st.error("El archivo CSV no contiene la columna 'IdCliente'.")
    st.stop()

df_clientes["IdCliente"] = df_clientes["IdCliente"].astype(str)


# ============================================================
# 3. FUNCIONES AUXILIARES Y GESTIÓN DEL ESTADO
# ============================================================

def convertir_coordenada(valor, defecto):
    """Convierte coordenadas con coma o punto decimal a float."""
    try:
        return round(float(str(valor).replace(",", ".")), 6)
    except (TypeError, ValueError):
        return defecto


def obtener_datos_cliente(id_cliente):
    """Devuelve la primera fila que coincide con el ID indicado."""
    if not id_cliente:
        return None

    resultado = df_clientes[
        df_clientes["IdCliente"] == str(id_cliente).strip()
    ]

    return None if resultado.empty else resultado.iloc[0]


def actualizar_coordenadas(prefijo, latitud, longitud):
    """
    Actualiza el estado central y las keys de los number_input.

    Esta función debe ejecutarse antes de instanciar los widgets
    numéricos en el ciclo de renderizado actual.
    """
    latitud = round(float(latitud), 6)
    longitud = round(float(longitud), 6)

    st.session_state[f"{prefijo}_lat"] = latitud
    st.session_state[f"{prefijo}_lon"] = longitud

    st.session_state[f"input_{prefijo}_lat"] = latitud
    st.session_state[f"input_{prefijo}_lon"] = longitud


def callback_latitud(prefijo):
    """Callback: copia la latitud editada al estado central."""
    st.session_state[f"{prefijo}_lat"] = round(
        float(st.session_state[f"input_{prefijo}_lat"]), 6
    )


def callback_longitud(prefijo):
    """Callback: copia la longitud editada al estado central."""
    st.session_state[f"{prefijo}_lon"] = round(
        float(st.session_state[f"input_{prefijo}_lon"]), 6
    )


def procesar_clic_mapa(map_data, prefijo):
    """
    Procesa un clic nuevo del mapa y sincroniza las coordenadas.

    st_folium puede devolver el último last_clicked en ejecuciones
    posteriores. Por eso se registra el par lat/lon antes de pedir
    un rerun. El mismo evento no vuelve a procesarse.

    Se usa un clic directo sobre el mapa; el marcador no es draggable.
    """
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

    # Registrar el evento antes del rerun evita el ciclo infinito.
    st.session_state[control_key] = click_token

    coordenadas_actuales = (
        round(float(st.session_state[f"{prefijo}_lat"]), 6),
        round(float(st.session_state[f"{prefijo}_lon"]), 6),
    )

    # No solicitar rerun si el clic coincide con las coordenadas actuales.
    if click_token == coordenadas_actuales:
        return

    actualizar_coordenadas(prefijo, click_lat, click_lon)

    # Un único rerun controlado para volver a dibujar el marcador
    # en la nueva posición. El evento ya quedó marcado como procesado.
    st.rerun()


def obtener_asignacion(latitud, longitud):
    """
    Motor Point-in-Polygon.
    Mantiene las propiedades y alternativas de nombres originales.
    """
    punto = Point(float(longitud), float(latitud))

    for feature in geojson_data["features"]:
        geometria = shape(feature["geometry"])

        if geometria.contains(punto):
            propiedades = feature["properties"]

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


def crear_mapa(latitud, longitud, zoom=15):
    """
    Crea el mapa con OpenStreetMap como cartografía base.

    OSM se mantiene como opción recomendada: no requiere API Key
    ni expone la aplicación a las condiciones de uso de teselas
    no oficiales de Google. El servidor público de OSM sí tiene
    política de uso y no ofrece SLA para aplicaciones productivas.
    """
    mapa = folium.Map(
        location=[latitud, longitud],
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    folium.GeoJson(
        geojson_data,
        name="Zonas RTM",
        style_function=lambda feature: {
            "fillColor": "#3388ff",
            "color": "#3388ff",
            "weight": 2,
            "fillOpacity": 0.20,
        },
        highlight_function=lambda feature: {
            "weight": 4,
            "color": "#ff7800",
            "fillOpacity": 0.35,
        },
    ).add_to(mapa)

    folium.LayerControl(collapsed=True).add_to(mapa)

    return mapa


def guardar_registro_bitacora(registro_dict):
    """
    Fase 1: guarda el registro en la bitácora de la sesión.

    Fase 2 (integración futura con Google Sheets):
    - Configurar secrets.toml con las credenciales necesarias.
    - Instalar/configurar el conector elegido.
    - Leer la hoja 'Correcciones' y anexar el registro.
    - Mantener esta función como único punto de escritura externa.

    Ejemplo orientativo con streamlit_gsheets:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        df_actual = conn.read(worksheet="Correcciones")
        df_nuevo = pd.concat(
            [df_actual, pd.DataFrame([registro_dict])],
            ignore_index=True
        )
        conn.update(worksheet="Correcciones", data=df_nuevo)

    La conexión externa NO se ejecuta en esta fase.
    """
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
    "prev_edit_target": None,
    "cons_last_processed_click": None,
    "edit_last_processed_click": None,
    "correcciones": [],
}

for clave, valor in VALORES_INICIALES.items():
    if clave not in st.session_state:
        st.session_state[clave] = valor


# ============================================================
# 5. NAVEGACIÓN
# ============================================================

st.sidebar.header("Panel de Control")

modo = st.sidebar.radio(
    "Selecciona una opción:",
    [
        "Consulta y Asignación Rápida",
        "Editor y Creación de Clientes",
    ],
)


# ============================================================
# 6. PESTAÑA 1: CONSULTA Y ASIGNACIÓN RÁPIDA
# ============================================================

if modo == "Consulta y Asignación Rápida":

    st.subheader("🔍 Consulta Dinámica por ID de Cliente")

    lista_ids = [""] + sorted(df_clientes["IdCliente"].unique().tolist())

    id_buscado = st.selectbox(
        "Seleccione o busque el ID de Cliente:",
        lista_ids,
        key="sel_consulta_id",
    )

    # Al cambiar de cliente, cargar sus coordenadas originales.
    if id_buscado != st.session_state["prev_cons_id"]:
        st.session_state["prev_cons_id"] = id_buscado

        cliente = obtener_datos_cliente(id_buscado)

        if cliente is not None:
            latitud = convertir_coordenada(
                cliente.get("Latitud"), LAT_DEFAULT
            )
            longitud = convertir_coordenada(
                cliente.get("Longitud"), LON_DEFAULT
            )
        else:
            latitud, longitud = LAT_DEFAULT, LON_DEFAULT

        actualizar_coordenadas("cons", latitud, longitud)

        # Se limpia el token porque cambió el objetivo de consulta.
        st.session_state["cons_last_processed_click"] = None

    cliente_encontrado = obtener_datos_cliente(id_buscado)

    razon_social_txt = "N/A"
    direccion_txt = "N/A"

    if cliente_encontrado is not None:
        razon_social_txt = cliente_encontrado.get("Razon_Social", "N/A")
        direccion_txt = cliente_encontrado.get("Direccion", "N/A")

    col1, col2 = st.columns([1, 2])

    # El mapa se renderiza y procesa antes de crear los number_input.
    # Así, si hubo un clic, las keys de los widgets ya estarán actualizadas.
    with col2:
        st.markdown("### 🗺️ Visualización Cartográfica")

        mapa_consulta = crear_mapa(
            st.session_state["cons_lat"],
            st.session_state["cons_lon"],
            zoom=15,
        )

        folium.Marker(
            [
                st.session_state["cons_lat"],
                st.session_state["cons_lon"],
            ],
            popup=f"ID: {id_buscado} - {razon_social_txt}",
            icon=folium.Icon(color="red", icon="user"),
        ).add_to(mapa_consulta)

        # La key cambia por cliente: evita reutilizar un last_clicked
        # antiguo al seleccionar otro ID.
        id_mapa_consulta = str(id_buscado or "sin_cliente")
        map_cons_data = st_folium(
            mapa_consulta,
            width=700,
            height=450,
            key=f"map_consulta_{id_mapa_consulta}",
            returned_objects=["last_clicked"],
        )

        procesar_clic_mapa(map_cons_data, "cons")

    with col1:
        st.markdown("### 📋 Datos del Cliente")

        if cliente_encontrado is not None:
            st.success(f"Encontrado: **{razon_social_txt}**")
        else:
            st.info("Seleccione un ID de cliente válido.")

        st.write(f"**Razón Social:** {razon_social_txt}")
        st.write(f"**Dirección:** {direccion_txt}")

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

    tipo_accion = st.radio(
        "Seleccione el flujo de trabajo:",
        [
            "Modificar Cliente Existente",
            "Registrar Nuevo Cliente",
        ],
        horizontal=True,
    )

    row_data = None
    id_objetivo = ""
    razon_social_val = ""
    direccion_val = ""

    # --------------------------------------------------------
    # MODIFICAR CLIENTE EXISTENTE
    # --------------------------------------------------------

    if tipo_accion == "Modificar Cliente Existente":

        lista_ids_edit = [""] + sorted(
            df_clientes["IdCliente"].unique().tolist()
        )

        id_objetivo = st.selectbox(
            "Seleccione el ID de Cliente existente a modificar:",
            lista_ids_edit,
            key="sel_edit_id",
        )

        if id_objetivo:
            row_data = obtener_datos_cliente(id_objetivo)

        if row_data is not None:
            default_lat = convertir_coordenada(
                row_data.get("Latitud"), LAT_DEFAULT
            )
            default_lon = convertir_coordenada(
                row_data.get("Longitud"), LON_DEFAULT
            )
            razon_social_val = row_data.get("Razon_Social", "N/A")
            direccion_val = row_data.get("Direccion", "N/A")
        else:
            default_lat, default_lon = LAT_DEFAULT, LON_DEFAULT

    # --------------------------------------------------------
    # REGISTRAR NUEVO CLIENTE
    # --------------------------------------------------------

    else:

        st.markdown("#### Ingresar Datos del Nuevo Cliente")

        id_objetivo = st.text_input(
            "Nuevo Código de Cliente (IdCliente):",
            placeholder="Ej: 999888",
            key="new_client_id",
        )

        razon_social_val = st.text_input(
            "Razón Social / Nombre Comercial:",
            placeholder="Ej: TIENDA NUEVA",
            key="new_client_name",
        )

        direccion_val = st.text_input(
            "Dirección física:",
            placeholder="Ej: Av. Principal Nro 123",
            key="new_client_dir",
        )

        default_lat = LAT_DEFAULT
        default_lon = LON_DEFAULT

        if id_objetivo:
            row_data = {
                "IdCliente": id_objetivo,
                "Razon_Social": razon_social_val,
                "Direccion": direccion_val,
            }

    # --------------------------------------------------------
    # DETECTAR CAMBIO DE CLIENTE / OBJETIVO
    # --------------------------------------------------------

    if id_objetivo:

        target_token = (
            tipo_accion,
            str(id_objetivo).strip(),
        )

        if target_token != st.session_state["prev_edit_target"]:
            st.session_state["prev_edit_target"] = target_token

            actualizar_coordenadas(
                "edit",
                default_lat,
                default_lon,
            )

            st.session_state["edit_last_processed_click"] = None

    # --------------------------------------------------------
    # FORMULARIO Y MAPA
    # --------------------------------------------------------

    if id_objetivo:

        st.info(
            f"**Operando sobre ID:** {id_objetivo} "
            f"| **Cliente:** {razon_social_val or 'Nuevo'}"
        )

        col_form, col_map = st.columns([1, 1.5])

        # Primero mapa, luego formulario: permite sincronizar las
        # coordenadas antes de crear los widgets numéricos.
        with col_map:

            st.markdown(
                "#### 🗺️ Mapa Interactivo "
                "(Haz clic para reubicar el pin)"
            )

            mapa_editor = crear_mapa(
                st.session_state["edit_lat"],
                st.session_state["edit_lon"],
                zoom=15,
            )

            folium.Marker(
                [
                    st.session_state["edit_lat"],
                    st.session_state["edit_lon"],
                ],
                popup=f"ID: {id_objetivo} ({tipo_accion})",
                icon=folium.Icon(color="green", icon="map-marker"),
            ).add_to(mapa_editor)

            # Key dinámica: un objetivo nuevo no hereda el clic anterior.
            tipo_key = (
                "existente"
                if tipo_accion == "Modificar Cliente Existente"
                else "nuevo"
            )
            id_key = str(id_objetivo).strip()

            map_edit_data = st_folium(
                mapa_editor,
                width=600,
                height=450,
                key=f"map_editor_{tipo_key}_{id_key}",
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

            # Recalcular asignación con las coordenadas vigentes.
            zona_temp, id_zona_dis_temp, distribuidor_temp = (
                obtener_asignacion(
                    st.session_state["edit_lat"],
                    st.session_state["edit_lon"],
                )
            )

            zona_temp = zona_temp or "Fuera de cobertura"
            id_zona_dis_temp = id_zona_dis_temp or "Fuera de cobertura"
            distribuidor_temp = distribuidor_temp or "Ninguno"

            st.markdown("---")
            st.markdown(f"**Zona Detectada:** `{zona_temp}`")
            st.markdown(f"**Id Zona Dis:** `{id_zona_dis_temp}`")
            st.markdown(f"**Distribuidor:** `{distribuidor_temp}`")

            if st.button(
                "Guardar Registro / Corrección",
                type="primary",
            ):

                nuevo_registro = {
                    "Timestamp": pd.Timestamp.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
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

                st.success(
                    f"¡Registro guardado exitosamente para el ID "
                    f"{id_objetivo}!"
                )

        # ----------------------------------------------------
        # HISTORIAL DE BITÁCORA
        # ----------------------------------------------------

        if st.session_state["correcciones"]:

            st.markdown("---")
            st.markdown("### 📑 Historial de Bitácora (Sesión Actual)")

            df_corr = pd.DataFrame(
                st.session_state["correcciones"]
            )

            st.dataframe(
                df_corr,
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                f"Total de registros en esta sesión: {len(df_corr)}"
            )

    else:

        st.warning(
            "Seleccione un cliente existente o ingrese un nuevo "
            "código de cliente para comenzar."
        )
