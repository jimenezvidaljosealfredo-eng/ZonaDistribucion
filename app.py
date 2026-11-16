import streamlit as st
import pandas as pd
import json
from shapely.geometry import Point, shape
import folium
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Gestión Comercial y Logística RTM",
    page_icon="🗺️",
    layout="wide"
)

st.title("🗺️ Herramienta RTM: Asignación Espacial y Corrección de Clientes")
st.markdown("Consulta y edición geoespacial con soporte para clientes existentes y nuevos registros diarios.")

@st.cache_data
def load_data():
    df_clientes = None
    for enc in ['latin-1', 'utf-8', 'cp1252']:
        try:
            df_clientes = pd.read_csv('BD PuebaLP.csv', sep=';', encoding=enc)
            break
        except Exception:
            try:
                df_clientes = pd.read_csv('BD PuebaLP.csv', sep=',', encoding=enc)
                break
            except Exception:
                continue
                
    with open('MapaDistibucion LPZPrueba.geojson', 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
        
    return df_clientes, geojson_data

try:
    df_clientes, geojson_data = load_data()
except Exception as e:
    st.error(f"Error cargando los archivos de datos locales: {e}")
    st.stop()

# Asegurar IdCliente como string
df_clientes['IdCliente'] = df_clientes['IdCliente'].astype(str)

# Sidebar para navegación
st.sidebar.header("Panel de Control")
modo = st.sidebar.radio("Selecciona una opción:", ["Consulta y Asignación Rápida", "Editor y Creación de Clientes"])

# ==========================================
# PESTAÑA 1: CONSULTA Y ASIGNACIÓN RÁPIDA
# ==========================================
if modo == "Consulta y Asignación Rápida":
    st.subheader("🔍 Consulta Dinámica por ID de Cliente")
    
    lista_ids = [""] + sorted(df_clientes['IdCliente'].unique().tolist())
    id_buscado = st.selectbox("Seleccione o busque el ID de Cliente:", lista_ids, key="sel_consulta_id")

    # Valores por defecto (Centro de La Paz)
    lat_val = -16.528041
    lon_val = -68.104807
    cliente_encontrado = None

    if id_buscado and id_buscado != "":
        resultado = df_clientes[df_clientes['IdCliente'] == str(id_buscado).strip()]
        if not resultado.empty:
            cliente_encontrado = resultado.iloc[0]
            lat_val = float(str(cliente_encontrado.get('Latitud', lat_val)).replace(',', '.'))
            lon_val = float(str(cliente_encontrado.get('Longitud', lon_val)).replace(',', '.'))

    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### 📋 Datos del Cliente")
        razon_social_txt = "N/A"
        direccion_txt = "N/A"
        
        if cliente_encontrado is not None:
            razon_social_txt = cliente_encontrado.get('Razon_Social', 'N/A')
            direccion_txt = cliente_encontrado.get('Direccion', 'N/A')
            st.success(f"Encontrado: **{razon_social_txt}**")
        else:
            st.info("Seleccione un ID de cliente válido para cargar sus datos.")

        st.write(f"**Razón Social:** {razon_social_txt}")
        st.write(f"**Dirección:** {direccion_txt}")
        
        # Campos sincronizados para visualizar/ajustar
        lat_actual = st.number_input("Latitud", value=lat_val, format="%.6f", key="q_lat")
        lon_actual = st.number_input("Longitud", value=lon_val, format="%.6f", key="q_lon")
        
        # --- MOTOR POINT-IN-POLYGON ---
        punto = Point(lon_actual, lat_actual)
        zona_encontrada = None
        id_zona_dis = None
        distribuidor_encontrado = None
        
        for feature in geojson_data['features']:
            geom = shape(feature['geometry'])
            if geom.contains(punto):
                props = feature['properties']
                zona_encontrada = props.get('CODIGO_ZONA_RTM') or props.get('id_zona')
                id_zona_dis = props.get('ORIG_IdZonaDist') or props.get('idZonaDis') or zona_encontrada
                distribuidor_encontrado = props.get('PROVEEDOR_RTM') or props.get('distribuidor')
                break
                
        st.markdown("### 🎯 Cuadro de Asignación Territorial")
        if id_zona_dis or zona_encontrada:
            st.info(f"""
            📌 **Id zona Dis / Zona:** `{id_zona_dis or zona_encontrada}`  
            🏢 **Distribuidor / Proveedor:** `{distribuidor_encontrado or 'Asignado por Zona'}`
            """)
        else:
            st.error("⚠️ **Fuera de cobertura:** Las coordenadas actuales no intersectan con ningún polígono activo.")

    with col2:
        st.markdown("### 🗺️ Visualización Cartográfica")
        m = folium.Map(location=[lat_actual, lon_actual], zoom_start=15)
        
        folium.GeoJson(
            geojson_data,
            name="Zonas RTM",
            style_function=lambda x: {'fillColor': '#3388ff', 'color': '#3388ff', 'weight': 2, 'fillOpacity': 0.2}
        ).add_to(m)
        
        folium.Marker(
            [lat_actual, lon_actual],
            popup=f"ID: {id_buscado} - {razon_social_txt}",
            icon=folium.Icon(color="red", icon="user")
        ).add_to(m)
        
        st_folium(m, width=700, height=450, key=f"map_cons_{id_buscado}_{lat_actual}_{lon_actual}")

# ==========================================
# PESTAÑA 2: EDITOR Y CREACIÓN DE CLIENTES
# ==========================================
elif modo == "Editor y Creación de Clientes":
    st.subheader("📝 Gestión de Corrección y Creación Diario")
    
    tipo_accion = st.radio("Seleccione el flujo de trabajo:", ["Modificar Cliente Existente", "Registrar Nuevo Cliente"], horizontal=True)
    
    row_data = None
    id_objetivo = ""
    
    if tipo_accion == "Modificar Cliente Existente":
        lista_ids_edit = [""] + sorted(df_clientes['IdCliente'].unique().tolist())
        id_objetivo = st.selectbox("Seleccione el ID de Cliente existente a modificar:", lista_ids_edit, key="sel_edit_id")
        
        if id_objetivo and id_objetivo != "":
            res_edit = df_clientes[df_clientes['IdCliente'] == str(id_objetivo).strip()]
            if not res_edit.empty:
                row_data = res_edit.iloc[0]
                
        if row_data is not None:
            default_lat = float(str(row_data.get('Latitud', -16.528041)).replace(',', '.'))
            default_lon = float(str(row_data.get('Longitud', -68.104807)).replace(',', '.'))
            razon_social_val = row_data.get('Razon_Social', 'N/A')
            direccion_val = row_data.get('Direccion', 'N/A')
        else:
            default_lat, default_lon = -16.528041, -68.104807
            razon_social_val, direccion_val = "", ""
            
    else:  # Registrar Nuevo Cliente
        st.markdown("#### Ingresar Datos del Nuevo Cliente")
        id_objetivo = st.text_input("Nuevo Código de Cliente (IdCliente):", placeholder="Ej: 999888")
        razon_social_val = st.text_input("Razón Social / Nombre Comercial:", placeholder="Ej: TIENDA NUEVA")
        direccion_val = st.text_input("Dirección física:", placeholder="Ej: Av. Principal Nro 123")
        default_lat = st.number_input("Latitud Inicial", value=-16.528041, format="%.6f")
        default_lon = st.number_input("Longitud Inicial", value=-68.104807, format="%.6f")
        
        if id_objetivo:
            row_data = {"IdCliente": id_objetivo, "Razon_Social": razon_social_val, "Direccion": direccion_val}

    if id_objetivo and id_objetivo != "":
        # Inicializar estado para edición/creación fluida
        if 'edit_lat' not in st.session_state or st.session_state.get('curr_target') != id_objetivo:
            st.session_state.edit_lat = default_lat
            st.session_state.edit_lon = default_lon
            st.session_state.curr_target = id_objetivo

        st.info(f"**Operando sobre ID:** {id_objetivo} | **Cliente:** {razon_social_val}")

        col_form, col_map = st.columns([1, 1.5])
        
        with col_form:
            with st.form("form_correccion_creacion"):
                st.markdown("#### Coordenadas Activas")
                nueva_lat = st.number_input("Latitud", value=float(st.session_state.edit_lat), format="%.6f", key="input_lat")
                nueva_lon = st.number_input("Longitud", value=float(st.session_state.edit_lon), format="%.6f", key="input_lon")
                usuario = st.text_input("Usuario responsable:", "Operador_Logistico")
                
                # Evaluación espacial previa al guardar
                punto_edit = Point(nueva_lon, nueva_lat)
                zona_temp, distribuidor_temp = "Fuera de cobertura", "Ninguno"
                for feature in geojson_data['features']:
                    geom = shape(feature['geometry'])
                    if geom.contains(punto_edit):
                        props = feature['properties']
                        zona_temp = props.get('ORIG_IdZonaDist') or props.get('idZonaDis') or props.get('CODIGO_ZONA_RTM')
                        distribuidor_temp = props.get('PROVEEDOR_RTM') or props.get('distribuidor')
                        break
                
                st.markdown(f"**Zona Detectada:** `{zona_temp}`")
                st.markdown(f"**Distribuidor:** `{distribuidor_temp}`")
                
                submitted = st.form_submit_button("Guardar Registro / Corrección")
                
                if submitted:
                    st.session_state.edit_lat = nueva_lat
                    st.session_state.edit_lon = nueva_lon
                    
                    nuevo_registro = {
                        "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Tipo_Operacion": tipo_accion,
                        "Cliente_ID": id_objetivo,
                        "Razon_Social": razon_social_val,
                        "Direccion": direccion_val,
                        "Lat_Asignada": nueva_lat,
                        "Lon_Asignada": nueva_lon,
                        "Zona_Asignada": zona_temp,
                        "Distribuidor": distribuidor_temp,
                        "Usuario": usuario
                    }
                    
                    if 'correcciones' not in st.session_state:
                        st.session_state['correcciones'] = []
                    st.session_state['correcciones'].append(nuevo_registro)
                    st.success(f"¡Registro guardado exitosamente para el ID {id_objetivo}!")

        with col_map:
            st.markdown("#### Mapa Interactivo (Haz clic para reubicar el pin)")
            m_edit = folium.Map(location=[st.session_state.edit_lat, st.session_state.edit_lon], zoom_start=15)
            
            folium.GeoJson(
                geojson_data,
                name="Zonas RTM",
                style_function=lambda x: {'fillColor': '#3388ff', 'color': '#3388ff', 'weight': 2, 'fillOpacity': 0.2}
            ).add_to(m_edit)
            
            folium.Marker(
                [st.session_state.edit_lat, st.session_state.edit_lon],
                popup=f"ID: {id_objetivo} ({tipo_accion})",
                icon=folium.Icon(color="green", icon="map-marker")
            ).add_to(m_edit)
            
            map_data = st_folium(m_edit, width=500, height=400, key=f"map_edit_{id_objetivo}")
            
            if map_data and map_data.get("last_clicked"):
                clicked_lat = map_data["last_clicked"]["lat"]
                clicked_lon = map_data["last_clicked"]["lng"]
                if clicked_lat != st.session_state.edit_lat or clicked_lon != st.session_state.edit_lon:
                    st.session_state.edit_lat = clicked_lat
                    st.session_state.edit_lon = clicked_lon
                    st.rerun()

        if 'correcciones' in st.session_state and len(st.session_state['correcciones']) > 0:
            st.markdown("---")
            st.markdown("### Historial de Bitácora (Sesión Actual)")
            df_corr = pd.DataFrame(st.session_state['correcciones'])
            st.dataframe(df_corr)
    else:
        st.warning("Seleccione un cliente existente o ingrese un nuevo código de cliente para comenzar.")
