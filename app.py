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
st.markdown("Cruza automáticamente la ubicación de tus clientes con los polígonos de distribución (GeoJSON) y gestiona correcciones con mapa interactivo sincronizado.")

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

# Sidebar para navegación
st.sidebar.header("Panel de Control")
modo = st.sidebar.radio("Selecciona una opción:", ["Consulta y Asignación Automática", "Editor de Coordenadas y Bitácora"])

if modo == "Consulta y Asignación Automática":
    st.subheader("🔍 Búsqueda por ID de Cliente y Asignación de Distribuidor")
    
    # Selector basado en IdCliente
    cliente_opciones = df_clientes['IdCliente'].astype(str).unique()
    cliente_seleccionado = st.selectbox("Seleccione o busque el ID de Cliente:", cliente_opciones)
    
    cliente_data = df_clientes[df_clientes['IdCliente'].astype(str) == str(cliente_seleccionado)].iloc[0]
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### Datos del Cliente")
        st.write(f"**ID Cliente:** {cliente_data.get('IdCliente', 'N/A')}")
        st.write(f"**Razón Social:** {cliente_data.get('Razon_Social', 'N/A')}")
        st.write(f"**Dirección:** {cliente_data.get('Direccion', 'N/A')}")
        
        lat_actual = float(str(cliente_data.get('Latitud', 0)).replace(',', '.'))
        lon_actual = float(str(cliente_data.get('Longitud', 0)).replace(',', '.'))
        
        st.write(f"**Latitud original:** {lat_actual}")
        st.write(f"**Longitud original:** {lon_actual}")
        
        # Motor Point-in-Polygon
        punto = Point(lon_actual, lat_actual)
        zona_encontrada = None
        distribuidor_encontrado = None
        
        for feature in geojson_data['features']:
            geom = shape(feature['geometry'])
            if geom.contains(punto):
                props = feature['properties']
                zona_encontrada = props.get('CODIGO_ZONA_RTM') or props.get('id_zona')
                distribuidor_encontrado = props.get('PROVEEDOR_RTM') or props.get('distribuidor')
                break
                
        st.markdown("### Resultado de Asignación")
        if zona_encontrada:
            st.success(f"✅ **Zona Asignada:** {zona_encontrada}\n\n**Proveedor / Distribuidor:** {distribuidor_encontrado}")
        else:
            st.warning("⚠️ **Fuera de cobertura:** Las coordenadas actuales no intersectan con ningún polígono activo.")

    with col2:
        st.markdown("### Visualización Cartográfica")
        m = folium.Map(location=[lat_actual, lon_actual], zoom_start=14)
        
        folium.GeoJson(
            geojson_data,
            name="Zonas RTM",
            style_function=lambda x: {'fillColor': '#3388ff', 'color': '#3388ff', 'weight': 2, 'fillOpacity': 0.2}
        ).add_to(m)
        
        folium.Marker(
            [lat_actual, lon_actual],
            popup=f"ID: {cliente_seleccionado} - {cliente_data.get('Razon_Social', '')}",
            icon=folium.Icon(color="red", icon="user")
        ).add_to(m)
        
        st_folium(m, width=700, height=450)

elif modo == "Editor de Coordenadas y Bitácora":
    st.subheader("📝 Corrección Interactiva de Georreferenciación por ID")
    st.markdown("Busca al cliente por su ID, ajusta su ubicación escribiendo los valores o haciendo clic en el mapa.")
    
    cliente_opciones = df_clientes['IdCliente'].astype(str).unique()
    cliente_sel = st.selectbox("Seleccione el ID de Cliente a corregir:", cliente_opciones, key="edit_client")
    
    row_data = df_clientes[df_clientes['IdCliente'].astype(str) == str(cliente_sel)].iloc[0]
    
    # Inicializar estado de sesión para edición si cambia de cliente
    if 'current_client' not in st.session_state or st.session_state.current_client != cliente_sel:
        st.session_state.current_client = cliente_sel
        st.session_state.edit_lat = float(str(row_data.get('Latitud', 0)).replace(',', '.'))
        st.session_state.edit_lon = float(str(row_data.get('Longitud', 0)).replace(',', '.'))

    orig_lat = float(str(row_data.get('Latitud', 0)).replace(',', '.'))
    orig_lon = float(str(row_data.get('Longitud', 0)).replace(',', '.'))
    
    st.info(f"**Cliente:** {row_data.get('Razon_Social', 'N/A')} | **Dirección:** {row_data.get('Direccion', 'N/A')}")
    
    col_form, col_map = st.columns([1, 1.5])
    
    with col_form:
        with st.form("form_correccion"):
            st.markdown("#### Coordenadas Editables")
            # Campos numéricos sincronizados con el estado
            nueva_lat = st.number_input("Latitud", value=float(st.session_state.edit_lat), format="%.6f", key="input_lat")
            nueva_lon = st.number_input("Longitud", value=float(st.session_state.edit_lon), format="%.6f", key="input_lon")
            
            usuario = st.text_input("Usuario responsable:", "Operador_Logistico")
            
            submitted = st.form_submit_button("Guardar Corrección")
            
            if submitted:
                st.session_state.edit_lat = nueva_lat
                st.session_state.edit_lon = nueva_lon
                
                nuevo_registro = {
                    "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Cliente_ID": cliente_sel,
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
                
                st.success(f"¡Corrección guardada para el ID {cliente_sel}!")

    with col_map:
        st.markdown("#### Mapa Interactivo (Haz clic para mover el pin)")
        
        # Crear mapa centrado en las coordenadas actuales de edición
        m_edit = folium.Map(location=[st.session_state.edit_lat, st.session_state.edit_lon], zoom_start=15)
        
        folium.GeoJson(
            geojson_data,
            name="Zonas RTM",
            style_function=lambda x: {'fillColor': '#3388ff', 'color': '#3388ff', 'weight': 2, 'fillOpacity': 0.2}
        ).add_to(m_edit)
        
        folium.Marker(
            [st.session_state.edit_lat, st.session_state.edit_lon],
            popup=f"ID: {cliente_sel} (Modificable)",
            icon=folium.Icon(color="green", icon="map-marker")
        ).add_to(m_edit)
        
        map_data = st_folium(m_edit, width=500, height=400, key=f"map_{cliente_sel}")
        
        # Capturar clic en el mapa para actualizar coordenadas automáticamente
        if map_data and map_data.get("last_clicked"):
            clicked_lat = map_data["last_clicked"]["lat"]
            clicked_lon = map_data["last_clicked"]["lng"]
            
            if clicked_lat != st.session_state.edit_lat or clicked_lon != st.session_state.edit_lon:
                st.session_state.edit_lat = clicked_lat
                st.session_state.edit_lon = clicked_lon
                st.rerun()

    if 'correcciones' in st.session_state and len(st.session_state['correcciones']) > 0:
        st.markdown("---")
        st.markdown("### Historial de Correcciones en la Sesión Actual")
        df_corr = pd.DataFrame(st.session_state['correcciones'])
        st.dataframe(df_corr)
