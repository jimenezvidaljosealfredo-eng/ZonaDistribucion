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
st.markdown("Consulta rápida por **ID de Cliente** (sin listas desplegables) con análisis espacial instantáneo.")

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

# Asegurar que IdCliente sea string para búsquedas limpias
df_clientes['IdCliente'] = df_clientes['IdCliente'].astype(str)

# Sidebar para navegación
st.sidebar.header("Panel de Control")
modo = st.sidebar.radio("Selecciona una modo:", ["Consulta y Asignación Rápida", "Editor de Coordenadas y Bitácora"])

if modo == "Consulta y Asignación Rápida":
    st.subheader("🔍 Búsqueda Directa por ID de Cliente")
    
    # ENFOQUE SIN LISTA DESPLEGABLE: Caja de texto libre para ingresar el ID
    col_search, col_info = st.columns([1, 2])
    with col_search:
        id_buscado = st.text_input("Ingrese el ID de Cliente:", value="", placeholder="Ej: 100014")

    # Valores por defecto (centro de La Paz si no se encuentra o está vacío)
    lat_val = -16.528041
    lon_val = -68.104807
    cliente_encontrado = None

    if id_buscado:
        resultado = df_clientes[df_clientes['IdCliente'] == id_buscado.strip()]
        if not resultado.empty:
            cliente_encontrado = resultado.iloc[0]
            lat_val = float(str(cliente_encontrado.get('Latitud', lat_val)).replace(',', '.'))
            lon_val = float(str(cliente_encontrado.get('Longitud', lon_val)).replace(',', '.'))
            with col_info:
                st.success(f"Cliente encontrado: **{cliente_encontrado.get('Razon_Social', 'N/A')}**")
        else:
            with col_info:
                st.warning("⚠️ ID de Cliente no encontrado en la base de datos. Se usan coordenadas neutrales o puede buscarlas libremente.")

    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### 📋 Datos del Registro")
        if cliente_encontrado is not None:
            st.write(f"**Razón Social:** {cliente_encontrado.get('Razon_Social', 'N/A')}")
            st.write(f"**Dirección:** {cliente_encontrado.get('Direccion', 'N/A')}")
        
        # Coordenadas editables manualmente para prueba rápida
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
                
        # --- CUADRO DINÁMICO DE ZONA Y DISTRIBUIDOR ---
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
        m = folium.Map(location=[lat_actual, lon_actual], zoom_start=14)
        
        folium.GeoJson(
            geojson_data,
            name="Zonas RTM",
            style_function=lambda x: {'fillColor': '#3388ff', 'color': '#3388ff', 'weight': 2, 'fillOpacity': 0.2}
        ).add_to(m)
        
        folium.Marker(
            [lat_actual, lon_actual],
            popup=f"Ubicación Consultada",
            icon=folium.Icon(color="red", icon="user")
        ).add_to(m)
        
        # Renderizado optimizado del mapa
        st_folium(m, width=700, height=450, key="map_consulta")

elif modo == "Editor de Coordenadas y Bitácora":
    st.subheader("📝 Corrección Interactiva de Georreferenciación por ID")
    st.markdown("Escriba el ID del cliente o mueva el marcador en el mapa para actualizar las coordenadas con menor retraso.")
    
    col_e1, col_e2 = st.columns([1, 2])
    with col_e1:
        id_edit = st.text_input("Ingrese ID de Cliente a corregir:", value="", placeholder="Ej: 100018")
    
    row_data = None
    if id_edit:
        res_edit = df_clientes[df_clientes['IdCliente'] == id_edit.strip()]
        if not res_edit.empty:
            row_data = res_edit.iloc[0]

    if row_data is not None:
        orig_lat = float(str(row_data.get('Latitud', -16.528041)).replace(',', '.'))
        orig_lon = float(str(row_data.get('Longitud', -68.104807)).replace(',', '.'))
        
        # Control de estado para evitar bucles de retraso en el mapa
        if 'edit_lat' not in st.session_state or st.session_state.get('last_id') != id_edit:
            st.session_state.edit_lat = orig_lat
            st.session_state.edit_lon = orig_lon
            st.session_state.last_id = id_edit

        st.info(f"**Cliente:** {row_data.get('Razon_Social', 'N/A')} | **Dirección:** {row_data.get('Direccion', 'N/A')}")
        
        col_form, col_map = st.columns([1, 1.5])
        
        with col_form:
            with st.form("form_correccion"):
                st.markdown("#### Coordenadas Editables")
                nueva_lat = st.number_input("Latitud", value=float(st.session_state.edit_lat), format="%.6f", key="input_lat")
                nueva_lon = st.number_input("Longitud", value=float(st.session_state.edit_lon), format="%.6f", key="input_lon")
                usuario = st.text_input("Usuario responsable:", "Operador_Logistico")
                
                submitted = st.form_submit_button("Guardar Corrección")
                
                if submitted:
                    st.session_state.edit_lat = nueva_lat
                    st.session_state.edit_lon = nueva_lon
                    
                    nuevo_registro = {
                        "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Cliente_ID": id_edit,
                        "Razon_Social": row_data.get('Razon_Social'),
                        "Lat_Original": orig_lat,
                        "Lon_Original": orig_lon,
                        "Lat_Corregida": nueva_lat,
                        "Lon_Corregida": nueva_lon,
                        "Usuario": usuario
                    }
                    
                    if 'correcciones' not in st.session_state:
                        st.session_state['correcciones'] = []
                    st.session_state['correcciones'].append(nuevo_registro)
                    st.success(f"¡Corrección guardada para el ID {id_edit}!")

        with col_map:
            st.markdown("#### Mapa Interactivo de Ajuste")
            m_edit = folium.Map(location=[st.session_state.edit_lat, st.session_state.edit_lon], zoom_start=15)
            
            folium.GeoJson(
                geojson_data,
                name="Zonas RTM",
                style_function=lambda x: {'fillColor': '#3388ff', 'color': '#3388ff', 'weight': 2, 'fillOpacity': 0.2}
            ).add_to(m_edit)
            
            folium.Marker(
                [st.session_state.edit_lat, st.session_state.edit_lon],
                popup=f"ID: {id_edit}",
                icon=folium.Icon(color="green", icon="map-marker")
            ).add_to(m_edit)
            
            map_data = st_folium(m_edit, width=500, height=400, key=f"map_edit_{id_edit}")
            
            # Captura optimizada de clic en el mapa
            if map_data and map_data.get("last_clicked"):
                clicked_lat = map_data["last_clicked"]["lat"]
                clicked_lon = map_data["last_clicked"]["lng"]
                if clicked_lat != st.session_state.edit_lat or clicked_lon != st.session_state.edit_lon:
                    st.session_state.edit_lat = clicked_lat
                    st.session_state.edit_lon = clicked_lon
                    st.rerun()

        if 'correcciones' in st.session_state and len(st.session_state['correcciones']) > 0:
            st.markdown("---")
            st.markdown("### Historial de Correcciones en la Sesión")
            df_corr = pd.DataFrame(st.session_state['correcciones'])
            st.dataframe(df_corr)
    else:
        if id_edit:
            st.warning("Ingrese un ID válido existente en el archivo CSV para comenzar la edición.")
