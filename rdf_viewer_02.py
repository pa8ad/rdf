import streamlit as st

# Check for required libraries
try:
    from rdflib import Graph, URIRef
    import pandas as pd
    from pyvis.network import Network
except ModuleNotFoundError as e:
    missing = str(e).split(" ")[-1].strip("'")
    st.error(f"Module '{missing}' niet gevonden. Voeg '{missing}' toe aan requirements.txt en herdeploy de app.")
    st.stop()

import pandas as pd
from rdflib import Graph, URIRef
from pyvis.network import Network
import tempfile
import os
from rdflib import Graph, URIRef
import pandas as pd
from pyvis.network import Network
import tempfile
import os

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

# Session state voor SPARQL-resultaten
if 'sparql_df' not in st.session_state:
    st.session_state['sparql_df'] = pd.DataFrame(columns=["Subject","Predicate","Object"])

if uploaded_file:
    # Parse RDF
    g = Graph()
    g.parse(uploaded_file, format="nt")

    # Unieke termen voor builder
    subjects = sorted({s for s,p,o in g}, key=lambda t: str(t))
    predicates = sorted({p for s,p,o in g}, key=lambda t: str(t))
    objects = sorted({o for s,p,o in g}, key=lambda t: str(t))

    subj_map = {str(s): s.n3() for s in subjects}
    pred_map = {str(p): p.n3() for p in predicates}
    obj_map = {str(o): o.n3() for o in objects}

    # Basis DataFrame
    df = pd.DataFrame([(str(s),str(p),str(o)) for s,p,o in g], columns=["Subject","Predicate","Object"])

    # Klikbare links
    def linkify(val):
        return f'<a href="{val}" target="_blank">{val}</a>' if val.startswith("http") else val

    st.subheader("📄 RDF Triples (klikbaar)")
    with st.container():
        st.markdown(
            "<div style='max-height:300px;overflow-y:auto;border:1px solid #ccc;padding:10px'>"+
            df.to_html(escape=False, formatters={"Subject":linkify,"Predicate":linkify,"Object":linkify})+
            "</div>",
            unsafe_allow_html=True
        )

    # Geavanceerde filters
    with st.expander("⚙️ Geavanceerde filters"):
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
    st.subheader("🧪 SPARQL Query Builder")
    s_choices = ["(any)"] + list(subj_map.keys())
    p_choices = ["(any)"] + list(pred_map.keys())
    o_choices = ["(any)"] + list(obj_map.keys())

    col1, col2, col3 = st.columns(3)
    with col1:
        sel_s = st.selectbox("Subject", s_choices)
    with col2:
        sel_p = st.selectbox("Predicate", p_choices)
    with col3:
        sel_o = st.selectbox("Object", o_choices)

    limit = st.number_input("Limit results", min_value=1, max_value=1000, value=10)

    s_term = subj_map[sel_s] if sel_s != "(any)" else "?s"
    p_term = pred_map[sel_p] if sel_p != "(any)" else "?p"
    o_term = obj_map[sel_o] if sel_o != "(any)" else "?o"

    sparql = f"{prefixes}\nSELECT * WHERE {{ {s_term} {p_term} {o_term} }} LIMIT {limit}"
    st.text_area("Gegenereerde SPARQL", value=sparql, height=120, key="sparql_area")

    # Buttons voor run en clear
    col_run, col_clear = st.columns(2)
    with col_run:
        run_clicked = st.button("Run SPARQL")
    with col_clear:
        clear_clicked = st.button("Wis SPARQL")

    if run_clicked:
        try:
            res = g.query(sparql)
            rows = []
            for b in res.bindings:
                row = {
                    "Subject": b.get('s', b.get('?s')).n3() if b.get('s', b.get('?s')) else None,
                    "Predicate": b.get('p', b.get('?p')).n3() if b.get('p', b.get('?p')) else None,
                    "Object": b.get('o', b.get('?o')).n3() if b.get('o', b.get('?o')) else None
                }
                rows.append(row)
            df_sparql = pd.DataFrame(rows)
            st.session_state['sparql_df'] = df_sparql
            if not df_sparql.empty:
                st.success(f"{len(df_sparql)} results")
            else:
                st.warning("Geen resultaten gevonden.")
        except Exception as e:
            st.error(f"SPARQL error: {e}")

    if clear_clicked:
        st.session_state['sparql_df'] = pd.DataFrame(columns=["Subject","Predicate","Object"])

    # Filter op rdf:type
    type_uri = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    type_vals = df[df['Predicate'] == str(type_uri)]['Object'].unique().tolist()
    sel_type = st.selectbox("Filter type", ["(all)"] + sorted(type_vals))
    if sel_type != "(all)":
        subs = df[df['Object'] == sel_type]['Subject']
        df_type = df[df['Subject'].isin(subs)]
    else:
        df_type = df

    # Bepaal vis_df
    if not st.session_state['sparql_df'].empty:
        vis_df = st.session_state['sparql_df']
    else:
        vis_df = pd.merge(df_type, filtered_adv, how='inner')

    # Visualisatie
    st.subheader("🌐 Visualisatie")
    net = Network(height="600px", width="100%", directed=True)
    for _, r in vis_df.iterrows():
        subj_id = str(r['Subject'])
        obj_id = str(r['Object'])
        pred_label = str(r['Predicate']).split('/')[-1]
        net.add_node(subj_id, label=subj_id)
        net.add_node(obj_id, label=obj_id)
        net.add_edge(subj_id, obj_id, label=pred_label)
    tmp_dir = tempfile.mkdtemp()
    path = os.path.join(tmp_dir, "graph.html")
    net.write_html(path)
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
    st.components.v1.html(html, height=650, scrolling=True)

    # Export onderaan
    st.subheader("⬇️ Export")
    export_df = vis_df
    st.download_button("Download CSV", export_df.to_csv(index=False), "rdf.csv", "text/csv")
    st.download_button("Download JSON", export_df.to_json(orient='records'), "rdf.json", "application/json")
