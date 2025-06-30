
from datetime import datetime
import pandas as pd
import json
import xml.etree.ElementTree as ET
import os
import plotly.express as px
import streamlit as st
from io import StringIO
from pathlib import Path
from xml.dom import minidom

# App title
st.set_page_config(page_title="Flexibel Dashboard", layout="wide")
st.title("📊 Flexibel Data Dashboard")

# Create default download directory
DOWNLOAD_DIR = Path.home() / "Downloads"

# --- FILE LOADER ---
st.sidebar.header("📁 Data inladen")
upload_option = st.sidebar.radio("Kies gegevensbron:", ["Upload CSV", "Laad via URL"])

df = None
if upload_option == "Upload CSV":
    uploaded_file = st.sidebar.file_uploader("Upload een CSV-bestand", type="csv")
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
elif upload_option == "Laad via URL":
    url = st.sidebar.text_input("Voer een geldige CSV-URL in")
    if url:
        try:
            df = pd.read_csv(url)
        except Exception as e:
            st.sidebar.error(f"Fout bij laden van URL: {e}")

# --- MAIN DASHBOARD ---
if df is not None:
    st.success("✅ Data succesvol geladen!")
    st.subheader("📌 Voorbeelddata")
    st.dataframe(df.head())

    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    categorical_cols = df.select_dtypes(include='object').columns.tolist()

    # FILTER OPSLAAN / LADEN
    st.sidebar.header("💾 Filters opslaan / laden")
    filter_name = st.sidebar.text_input("Naam voor filterinstelling")
    filter_file = st.sidebar.file_uploader("Laad filterbestand", type="json")
    loaded_filters = {}

    if filter_file:
        try:
            loaded_filters = json.load(filter_file)
            missing_columns = [col for col in loaded_filters if col not in df.columns]
            if missing_columns:
                st.sidebar.warning(f"Filter bevat kolommen die niet bestaan in de data: {missing_columns}")
                loaded_filters = {}
            else:
                st.sidebar.success("Filter succesvol geladen en toegepast.")
        except Exception as e:
            st.sidebar.error(f"Fout bij laden van filter: {e}")
            loaded_filters = {}

    # FILTERS
    st.sidebar.header("🔍 Filters")
    filters = {}
    for col in df.columns:
        unique_vals = df[col].dropna().unique()
        if df[col].dtype == 'object' or len(unique_vals) < 30:
            default = loaded_filters.get(col, [])
            selection = st.sidebar.multiselect(f"{col}", unique_vals, default=default)
            if selection:
                filters[col] = selection
        else:
            min_val, max_val = float(df[col].min()), float(df[col].max())
            default_range = loaded_filters.get(col, [min_val, max_val])
            range_val = st.sidebar.slider(f"{col}", min_val, max_val, tuple(default_range))
            filters[col] = range_val

    if st.sidebar.button("Filterinstelling opslaan"):
        if filter_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filter_name}_{timestamp}.json"
            filepath = DOWNLOAD_DIR / filename
            with open(filepath, "w") as f:
                json.dump(filters, f)
            st.sidebar.success(f"Opgeslagen als: {filepath}")

    # Pas filters toe
    df_filtered = df.copy()
    for col, val in filters.items():
        if isinstance(val, list):
            df_filtered = df_filtered[df_filtered[col].isin(val)]
        else:
            df_filtered = df_filtered[df_filtered[col].between(val[0], val[1])]

    st.subheader("📊 Visualisatie")
    chart_type = st.selectbox("Kies grafiektype", ["Tabel", "Lijngrafiek", "Staafgrafiek", "Cirkeldiagram", "Scatterplot", "Heatmap"])
    x_axis = st.selectbox("X-as", df_filtered.columns)
    y_axis = st.selectbox("Y-as", df_filtered.columns)

    if chart_type == "Tabel":
        st.dataframe(df_filtered)
    elif chart_type == "Lijngrafiek":
        fig = px.line(df_filtered, x=x_axis, y=y_axis)
        st.plotly_chart(fig, use_container_width=True)
    elif chart_type == "Staafgrafiek":
        fig = px.bar(df_filtered, x=x_axis, y=y_axis)
        st.plotly_chart(fig, use_container_width=True)
    elif chart_type == "Cirkeldiagram":
        fig = px.pie(df_filtered, names=x_axis, values=y_axis)
        st.plotly_chart(fig, use_container_width=True)
    elif chart_type == "Scatterplot":
        fig = px.scatter(df_filtered, x=x_axis, y=y_axis)
        st.plotly_chart(fig, use_container_width=True)
    elif chart_type == "Heatmap":
        if x_axis in numeric_cols and y_axis in numeric_cols:
            fig = px.density_heatmap(df_filtered, x=x_axis, y=y_axis)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Voor een heatmap moeten zowel X als Y numeriek zijn.")

    # EXPORT
    st.subheader("📤 Exporteren van data")
    export_format = st.selectbox("Kies exportformaat", ["CSV", "JSON", "XML"])
    export_name = st.text_input("Bestandsnaam zonder extensie")

    if st.button("Exporteer"):
        if export_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{export_name}_{timestamp}.{export_format.lower()}"
            filepath = DOWNLOAD_DIR / filename

            if export_format == "CSV":
                csv_data = df_filtered.to_csv(index=False)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(csv_data)
            elif export_format == "JSON":
                json_data = df_filtered.to_json(orient="records")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(json_data)
            elif export_format == "XML":
                root = ET.Element("data")
                for _, row in df_filtered.iterrows():
                    item = ET.SubElement(root, "record")
                    for col in df_filtered.columns:
                        child = ET.SubElement(item, col)
                        child.text = str(row[col])
                xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(xml_str)

            st.success(f"✅ Bestand opgeslagen in: {filepath}")
else:
    st.info("📂 Upload een dataset of geef een URL op om te beginnen.")
