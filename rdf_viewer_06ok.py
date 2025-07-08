import streamlit as st

# Check for required libraries
try:
    from rdflib import Graph, URIRef
    import pandas as pd
    from pyvis.network import Network
except ModuleNotFoundError as e:
    missing = str(e).split()[-1].strip("'")
    st.error(f"Module '{missing}' niet gevonden. Voeg '{missing}' toe aan requirements.txt en herdeploy de app.")
    st.stop()

import tempfile
from streamlit_folium import st_folium
import os
from datetime import datetime

st.set_page_config(layout="wide")
st.title("🧩 RDF Viewer & Visualisatie")

# Prefix-definities
st.subheader("📐 Prefix-instellingen")
default_prefixes = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <https://schema.org/>"""
prefixes = st.text_area("SPARQL Prefixes", value=default_prefixes, height=100)

# Upload
uploaded_file = st.file_uploader("📂 Upload RDF (.nt) file", type=["nt"])

# Session state defaults
if 'sparql_df' not in st.session_state:
    st.session_state['sparql_df'] = pd.DataFrame(columns=["Subject","Predicate","Object"])
if 'viz_started' not in st.session_state:
    st.session_state['viz_started'] = False

if uploaded_file:
    # Parse RDF
    g = Graph()
    g.parse(uploaded_file, format="nt")
    df = pd.DataFrame([(str(s), str(p), str(o)) for s,p,o in g], columns=["Subject","Predicate","Object"])

    # Data-overzicht en statistieken (expander)
    with st.expander("📊 Data-overzicht en statistieken", expanded=False):
        total_triples = len(df)
        unique_subjects = df['Subject'].nunique()
        unique_predicates = df['Predicate'].nunique()
        unique_objects = df['Object'].nunique()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Totaal triples", total_triples)
        c2.metric("Unieke Subjects", unique_subjects)
        c3.metric("Unieke Predicates", unique_predicates)
        c4.metric("Unieke Objects", unique_objects)
        st.write("**Top 10 Predicates**")
        st.bar_chart(df['Predicate'].value_counts().head(10))
        st.write("**Top 10 Subjects**")
        st.bar_chart(df['Subject'].value_counts().head(10))
        df_num = df.copy()
        df_num['NumericValue'] = pd.to_numeric(df_num['Object'], errors='coerce')
        if df_num['NumericValue'].notna().any():
            st.write("**Verdeling numerieke literal-waarden**")
            num_counts = pd.cut(df_num['NumericValue'], bins=10).value_counts().sort_index()
            num_counts.index = num_counts.index.astype(str)
            st.bar_chart(num_counts)
        date_preds = [p for p in df['Predicate'].unique() if 'date' in p.lower() or 'time' in p.lower()]
        if date_preds:
            df_date = df[df['Predicate'].isin(date_preds)].copy()
            df_date['Date'] = pd.to_datetime(df_date['Object'], errors='coerce')
            df_date = df_date.dropna(subset=['Date'])
            if not df_date.empty:
                st.write("**Tijdreeks van datumpredicates**")
                st.line_chart(df_date['Date'].dt.date.value_counts().sort_index())

    # Klikbare triples
    def linkify(val):
        return f'<a href="{val}" target="_blank">{val}</a>' if val.startswith("http") else val
    st.subheader("📄 RDF Triples (klikbaar)")
    styled = df.rename(columns={'Subject':'Subject','Predicate':'Predicate','Object':'Object'})
    st.markdown(
        f"<div style='max-height:300px;overflow-y:auto;border:1px solid #ddd;padding:10px'>"
        + styled.style.format({'Subject':linkify,'Predicate':linkify,'Object':linkify}).to_html()
        + "</div>", unsafe_allow_html=True
    )

    # Geavanceerde filters
    with st.expander("⚙️ Geavanceerde filters", expanded=False):
        sub_f = st.text_input("Subject regex")
        pred_f = st.text_input("Predicate regex")
        obj_f = st.text_input("Object regex")
        filtered_adv = df.copy()
        if sub_f:
            filtered_adv = filtered_adv[filtered_adv['Subject'].str.contains(sub_f, regex=True)]
        if pred_f:
            filtered_adv = filtered_adv[filtered_adv['Predicate'].str.contains(pred_f, regex=True)]
        if obj_f:
            filtered_adv = filtered_adv[filtered_adv['Object'].str.contains(obj_f, regex=True)]

    # SPARQL Query Builder
    subjects = sorted({s for s,p,o in g}, key=lambda t: str(t))
    predicates = sorted({p for s,p,o in g}, key=lambda t: str(t))
    objects = sorted({o for s,p,o in g}, key=lambda t: str(t))
    subj_map = {str(s): s.n3() for s in subjects}
    pred_map = {str(p): p.n3() for p in predicates}
    obj_map = {str(o): o.n3() for o in objects}
    st.subheader("🧪 SPARQL Query Builder")
    c1, c2, c3 = st.columns(3)
    with c1: sel_s = st.selectbox("Subject", ["(any)"]+list(subj_map.keys()))
    with c2: sel_p = st.selectbox("Predicate", ["(any)"]+list(pred_map.keys()))
    with c3: sel_o = st.selectbox("Object", ["(any)"]+list(obj_map.keys()))
    limit = st.number_input("Limit results", min_value=1, max_value=1000, value=10)
    sparql = f"{prefixes}\nSELECT * WHERE {{ {subj_map.get(sel_s,'?s')} {pred_map.get(sel_p,'?p')} {obj_map.get(sel_o,'?o')} }} LIMIT {limit}"
    st.text_area("Gegenereerde SPARQL", value=sparql, height=120)
    col_run, col_clear = st.columns(2)
    if col_run.button("Run SPARQL"):
        try:
            rows = []
            for b in g.query(sparql).bindings:
                rows.append({
                    "Subject": b.get('s', b.get('?s')).n3() if b.get('s', b.get('?s')) else None,
                    "Predicate": b.get('p', b.get('?p')).n3() if b.get('p', b.get('?p')) else None,
                    "Object": b.get('o', b.get('?o')).n3() if b.get('o', b.get('?o')) else None
                })
            st.session_state['sparql_df'] = pd.DataFrame(rows)
        except Exception as e:
            st.error(f"SPARQL error: {e}")
    if col_clear.button("Wis SPARQL"):
        st.session_state['sparql_df'] = pd.DataFrame(columns=["Subject","Predicate","Object"])

    # Prepare time data
    time_preds = [p for p in df['Predicate'].unique() if 'date' in p.lower() or 'time' in p.lower()]
    df_time = pd.DataFrame()
    if time_preds:
        df_time = df[df['Predicate'].isin(time_preds)].copy()
        df_time['Date'] = pd.to_datetime(df_time['Object'], errors='coerce')
        df_time = df_time.dropna(subset=['Date'])

    # Visualisatie
    if not st.session_state['viz_started']:
        if st.button("Start visualisatie"):
            st.session_state['viz_started'] = True
    if st.session_state['viz_started']:
        # Tijd slider
        if not df_time.empty:
            min_date = df_time['Date'].min().date()
            max_date = df_time['Date'].max().date()
            start_date, end_date = st.slider(
                "Selecteer datumbereik",
                min_value=min_date,
                max_value=max_date,
                value=(min_date, max_date),
                format="YYYY-MM-DD"
            )
            date_map = {row['Subject']: row['Date'].date() for _, row in df_time.iterrows()}
        # Type filter
        type_uri = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
        sel_type = st.selectbox("Filter type", ["(all)"] + sorted(df[df['Predicate']==str(type_uri)]['Object'].unique()))
        df_type = df if sel_type=="(all)" else df[df['Object']==sel_type]
        vis_df = st.session_state['sparql_df'] if not st.session_state['sparql_df'].empty else pd.merge(df_type, filtered_adv, how='inner')
        if not df_time.empty:
            vis_df = vis_df[vis_df['Subject'].map(date_map).between(start_date, end_date)]
        # Color mappings
        node_types = {row['Subject']: row['Object'] for _, row in df[df['Predicate']==str(type_uri)].iterrows()}
        palette = ["red","blue","green","orange","purple","teal","brown","pink","gray","cyan"]
        type_colors = {t: palette[i%len(palette)] for i,t in enumerate(sorted(set(node_types.values())))}
        pred_counts = vis_df['Predicate'].value_counts()
        max_count = pred_counts.max() if not pred_counts.empty else 1
        pred_colors = {p: palette[i%len(palette)] for i,p in enumerate(sorted(pred_counts.index))}
        # Sidebar filter styling
        st.sidebar.markdown(
            """
            <style>
            [data-testid="stSidebar"] [data-baseweb="tag"] {
              white-space: normal !important;
            }
            [data-testid="stSidebar"] [data-baseweb="select"] > div {
              min-width: 250px !important;
            }
            [data-testid="stSidebar"] [data-baseweb="popover-content"] {
              min-width: 250px !important;
            }
            </style>
            """, unsafe_allow_html=True)
        show_types = st.sidebar.multiselect("Types tonen", list(type_colors.keys()), default=list(type_colors.keys()))
        show_preds = st.sidebar.multiselect("Predicates tonen", list(pred_colors.keys()), default=list(pred_colors.keys()))
#SBATCH
        vis_filtered = vis_df[
            vis_df['Predicate'].isin(show_preds) &
            vis_df['Subject'].isin([s for s,t in node_types.items() if t in show_types])
        ]
        # Label options
        node_label = st.selectbox("Kies node label:", ["URI","Local Name"])
        edge_label = st.selectbox("Kies edge label:", ["URI","Local Name"])
        # Build network
        net = Network(height="600px", directed=True)
        for _,r in vis_filtered.iterrows():
            subj = str(r['Subject'])
            obj = str(r['Object'])
            s_lbl = subj if node_label=="URI" else subj.split('/')[-1]
            o_lbl = obj if node_label=="URI" else obj.split('/')[-1]
            pred = str(r['Predicate'])
            e_lbl = pred if edge_label=="URI" else pred.split('/')[-1]
            weight = pred_counts.get(pred,1)
            width = 1+(weight-1)/(max_count-1)*4 if max_count>1 else 2
            net.add_node(subj, label=s_lbl, color=type_colors.get(node_types.get(subj),"gray"))
            net.add_node(obj, label=o_lbl, color=type_colors.get(node_types.get(obj),"gray"))
            net.add_edge(subj, obj, label=e_lbl, color=pred_colors.get(pred,"lightgray"), width=width)
        net.set_options('{"interaction":{"hover":true,"hoverConnectedEdges":true,"selectConnectedEdges":true}}')
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "graph.html")
        net.write_html(path)
        import streamlit.components.v1 as components
        components.html(open(path,"r",encoding="utf-8").read(), height=600)
        # Legenda
        st.subheader("Legenda")
        type_items = [
            f"<div style='display:flex;align-items:center;margin-right:15px;margin-bottom:5px'>"
            f"<span style='display:inline-block;width:15px;height:15px;background:{c};margin-right:5px'></span>"
            f"{t.split('/')[-1]}</div>" for t,c in type_colors.items()
        ]
        st.markdown(
            "<b>Node types:</b><div style='display:flex;flex-wrap:wrap;'>" +
            "".join(type_items) +
            "</div>", unsafe_allow_html=True
        )
        pred_items = [
            f"<div style='display:flex;align-items:center;margin-right:15px;margin-bottom:5px'>"
            f"<span style='display:inline-block;width:15px;height:15px;background:{c};margin-right:5px'></span>"
            f"{p.split('/')[-1]}</div>" for p,c in pred_colors.items()
        ]
        st.markdown(
            "<b>Edge predicates:</b><div style='display:flex;flex-wrap:wrap;'>" +
            "".join(pred_items) +
            "</div>", unsafe_allow_html=True
        )

        # Optie 6: Geospatiale kaart
        st.subheader("🌍 Geospatiale kaart")
        # Detecteer geo predicaten
        lat_preds = [p for p in df['Predicate'].unique() if 'lat' in p.lower()]
        lon_preds = [p for p in df['Predicate'].unique() if 'long' in p.lower() or 'lng' in p.lower()]
        # Detecteer foto predicaten
        img_preds = [p for p in df['Predicate'].unique() if any(x in p.lower() for x in ['image', 'foto', 'depict'])]
        if lat_preds and lon_preds:
            df_geo = df[df['Predicate'].isin(lat_preds + lon_preds)]
            geo_pivot = df_geo.pivot_table(index='Subject', columns='Predicate', values='Object', aggfunc='first')
            coords = []
            photo_map = {}
            for subj in geo_pivot.index:
                try:
                    lat = float(geo_pivot.loc[subj, lat_preds[0]])
                    lon = float(geo_pivot.loc[subj, lon_preds[0]])
                except Exception:
                    continue
                # Verzamel foto's
                fotos = []
                if img_preds:
                    fotos = df[(df['Subject']==subj) & (df['Predicate'].isin(img_preds))]['Object'].tolist()
                photo_map[subj] = fotos
                coords.append((subj, lat, lon))
            if coords:
                import folium
                # Centreer kaart
                avg_lat = sum(lat for _, lat, _ in coords) / len(coords)
                avg_lon = sum(lon for _, _, lon in coords) / len(coords)
                m = folium.Map(location=[avg_lat, avg_lon], zoom_start=2)
                # Marker kleuren op type
                for subj, lat, lon in coords:
                    fotos = photo_map.get(subj, [])
                    popup_html = f"<b>{subj}</b><br>"
                    if fotos:
                        popup_html += f"<i>{len(fotos)} foto(s)</i><br>"
                        for url in fotos:
                            popup_html += f'<a href="{url}" target="_blank"><img src="{url}" width="50"></a>'
                    else:
                        popup_html += "Geen foto beschikbaar"
                    # Marker popup
                    folium.Marker(
                        [lat, lon],
                        popup=folium.Popup(popup_html, max_width=300),
                        icon=folium.Icon(color='blue')
                    ).add_to(m)
                # Voeg legenda toe aan kaart
                legend_html = '''
                <div style="position: fixed; bottom: 50px; left: 50px; width: 150px; height: auto; background-color: white; opacity: 0.8; padding: 10px;">
                  <h4>Legenda</h4>
                '''
                for t, c in type_colors.items():
                    label = t.split('/')[-1]
                    legend_html += f'<i style="background:{c};width:10px;height:10px;display:inline-block;margin-right:5px;"></i>{label}<br>'
                legend_html += '</div>'
                m.get_root().html.add_child(folium.Element(legend_html))
                # Voeg layer control toe
                folium.LayerControl().add_to(m)
                # Render map over de volle breedte
                st_folium(m, width="100%", height=500, use_container_width=True)
            else:
                st.info("Geen geldige geo-coördinaten gevonden voor plotting.")
        else:
            st.info("Geen geo:lat en geo:long predicaten gevonden in de data.")
