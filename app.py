import streamlit as st
import pandas as pd
import json
from shapely.geometry import Point, shape
import folium
from streamlit_folium import st_folium

# Corrección aplicada: st.set_page_config en lugar de st.set_page_title
st.set_page_config(
    page_title="Gestión Comercial y Logística RTM",
    page_icon="🗺️",
    layout="wide"
)

st.title("🗺️ Herramienta RTM: Asignación Espacial y Corrección de Clientes")
st.markdown("Cruza automáticamente la ubicación de tus clientes con los polígonos de distribución (GeoJSON) y gestiona correcciones.")

@st.cache_data
def load_data():
    # Cargar CSV de clientes con manejo de errores de encoding
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
                
    # Cargar GeoJSON
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
    st.subheader("🔍 Búsqueda de Cliente y Asignación de Distribuidor")
    
    # Selector de cliente
    cliente_opciones = df_clientes['Razon_Social'].unique()
    cliente_seleccionado = st.selectbox("Seleccione o busque un Cliente:", cliente_opciones)
    
    cliente_data = df_clientes[df_clientes['Razon_Social'] == cliente_seleccionado].iloc[0]
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### Datos del Cliente")
        st.write(f"**ID Cliente:** {cliente_data.get('IdCliente', 'N/A')}")
        st.write(f"**Razón Social:** {cliente_data.get('Razon_Social', 'N/A')}")
        st.write(f"**Dirección:** {cliente_data.get('Direccion', 'N/A')}")
        
        lat_actual = float(str(cliente_data.get('Latitud', 0)).replace(',', '.'))
        lon_actual = float(str(cliente_data.get('Longitud', 0)).replace(',', '.'))
        
        st.write(f"**Latitud:** {lat_actual}")
        st.write(f"**Longitud:** {lon_actual}")
        
        # Motor Point-in-Polygon (Shapely requiere (longitud, latitud))
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
        
        # Agregar polígonos del GeoJSON
        folium.GeoJson(
            geojson_data,
            name="Zonas RTM",
            style_function=lambda x: {'fillColor': '#3388ff', 'color': '#3388ff', 'weight': 2, 'fillOpacity': 0.2}
        ).add_to(m)
        
        # Marcar la posición del cliente
        folium.Marker(
            [lat_actual, lon_actual],
            popup=f"{cliente_seleccionado}",
            icon=folium.Icon(color="red", icon="user")
        ).add_to(m)
        
        st_folium(m, width=700, height=450)

elif modo == "Editor de Coordenadas y Bitácora":
    st.subheader("📝 Corrección de Georreferenciación")
    st.markdown("Modifica las coordenadas del cliente y registra el cambio para su sincronización.")
    
    cliente_opciones = df_clientes['Razon_Social'].unique()
    cliente_sel = st.selectbox("Cliente a corregir:", cliente_opciones, key="edit_client")
    
    row_data = df_clientes[df_clientes['Razon_Social'] == cliente_sel].iloc[0]
    
    orig_lat = float(str(row_data.get('Latitud', 0)).replace(',', '.'))
    orig_lon = float(str(row_data.get('Longitud', 0)).replace(',', '.'))
    
    with st.form("form_correccion"):
        c1, c2 = st.columns(2)
        with c1:
            nueva_lat = st.number_input("Nueva Latitud", value=orig_lat, format="%.6f")
        with c2:
            nueva_lon = st.number_input("Nueva Longitud", value=orig_lon, format="%.6f")
            
        usuario = st.text_input("Usuario responsable:", "Operador_Logistico")
        
        submitted = st.form_submit_button("Guardar Corrección")
        
        if submitted:
            nuevo_registro = {
                "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Cliente_ID": row_data.get('IdCliente'),
                "Razon_Social": cliente_sel,
                "Lat_Original": orig_lat,
                "Lon_Original": orig_lon,
                "Lat_Corregida": nueva_lat,
                "Lon_Corregida": nueva_lon,
                "Usuario": usuario
            }
            
            if 'correcciones' not in st.session_state:
                st.session_state['correcciones'] = []
            st.session_state['correcciones'].append(nuevo_registro)
            
            st.success("¡Corrección registrada exitosamente en la sesión actual!")

    if 'correcciones' in st.session_state and len(st.session_state['correcciones']) > 0:
        st.markdown("### Historial de Correcciones en la Sesión Actual")
        df_corr = pd.DataFrame(st.session_state['correcciones'])
        st.dataframe(df_corr)
