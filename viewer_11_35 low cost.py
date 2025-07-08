import os
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import re
from openai import OpenAI
from dotenv import load_dotenv

st.set_page_config(layout="wide")

# Laad API key uit .env bestand
load_dotenv("sleu.env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialiseer de gebruikersvraag in session_state
if "user_question" not in st.session_state:
    st.session_state["user_question"] = ""

def main():
    st.sidebar.header('Instellingen')

    st.markdown("""
        <style>
        .responsive-table {
            width: 100% !important;
            table-layout: auto !important;
        }
        .responsive-table th, .responsive-table td {
            word-wrap: break-word;
            white-space: normal !important;
        }
        </style>
    """, unsafe_allow_html=True)

    uploaded_file = st.sidebar.file_uploader(
        'Selecteer of upload de metadata CSV',
        type=['csv'],
        help='Upload hier het CSV-bestand met de gegenereerde metadata'
    )
    if not uploaded_file:
        st.sidebar.info('Upload een CSV-bestand om te beginnen.')
        return

    try:
        df = pd.read_csv(uploaded_file)
    except Exception as e:
        st.sidebar.error(f"Kan CSV niet laden: {e}")
        return

    keyword = st.sidebar.text_input('Zoek trefwoord', '', help='Filter op trefwoord in metadata')
    match_type = st.sidebar.radio('Match type', options=['Exact', 'Deeltekst'], index=1)
    kw = keyword.strip()
    kw_lower = kw.lower()

    user_question = st.sidebar.text_area(
        'Stel een vraag over de metadata',
        value="",
        key="user_question_input"
    )
    
    ext_map = df[df['metadata_field'] == 'file_extension']\
        .set_index('file_key')['metadata_value'].to_dict()

    unique_types = sorted(set(ext_map.values()))
    selected_types = st.sidebar.multiselect(
        'Selecteer bestandstypes om te tonen',
        ['Alles'] + unique_types,
        default=['Alles']
    )
    allowed_keys = list(ext_map.keys()) if 'Alles' in selected_types else [k for k, v in ext_map.items() if v in selected_types]
    df = df[df['file_key'].isin(allowed_keys)].copy()

    all_fields = sorted(df['metadata_field'].unique())
    selected_fields = st.sidebar.multiselect(
        'Selecteer metadata types om te tonen',
        all_fields,
        default=all_fields
    )
    filtered = df[df['metadata_field'].isin(selected_fields)].copy()

    ext_rows = pd.DataFrame([
        {'file_key': k, 'metadata_field': 'file_extension', 'metadata_value': ext_map[k]}
        for k in allowed_keys
    ])
    filtered = pd.concat([filtered, ext_rows], ignore_index=True)
    filtered = filtered.drop_duplicates(subset=['file_key', 'metadata_field'], keep='first')

    if kw:
        if match_type == 'Exact':
            mask = (
                (filtered['metadata_field'].str.lower() == kw_lower) |
                (filtered['metadata_value'].str.lower() == kw_lower)
            )
        else:
            mask = (
                filtered['metadata_field'].str.contains(kw, case=False, na=False) |
                filtered['metadata_value'].str.contains(kw, case=False, na=False)
            )
        filtered = filtered[mask]

    date_fields = [f for f in selected_fields if 'timestamp' in f or f.endswith('_created') or f.endswith('_modified')]
    date_masks = []
    for field in date_fields:
        dt_values = pd.to_datetime(filtered['metadata_value'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
        if dt_values.notna().any():
            field_mask = filtered['metadata_field'] == field
            series = dt_values[field_mask]
            if series.empty:
                continue
            min_dt, max_dt = series.min().date(), series.max().date()
            start, end = st.sidebar.date_input(f'Datum-range voor {field}', [min_dt, max_dt])
            mask_other = ~field_mask
            mask_in_range = dt_values.dt.date.between(start, end)
            date_masks.append(mask_other | mask_in_range)
    if date_masks:
        combined = date_masks[0]
        for m in date_masks[1:]:
            combined &= m
        filtered = filtered[combined]

    mdto_list = []
    for fk, group in filtered.groupby('file_key'):
        md = {row['metadata_field']: row['metadata_value'] for _, row in group.iterrows()}
        mdto_list.append({'file_key': fk, 'metadata': md})
    mdto_json = json.dumps({'MDTO': mdto_list}, ensure_ascii=False, indent=2)
    st.sidebar.download_button(
        'Export naar MDTO',
        data=mdto_json,
        file_name='metadata.mdto.json',
        mime='application/json'
    )

    st.markdown("""
        <style>
        h1, h4 {
            pointer-events: none;
        }
        </style>
        <h1>Metadata Overzicht per Document</h1>
    """, unsafe_allow_html=True)

    if user_question.strip():
        filtered_subset = filtered[filtered['metadata_field'].isin(['ai_summary', 'image_description'])]
        data_for_llm = filtered_subset.groupby('file_key').apply(
            lambda group: {row['metadata_field']: row['metadata_value'] for _, row in group.iterrows()}
        ).to_dict()

        prompt = f"""
Beantwoord kort en feitelijk op basis van onderstaande metadata (max 50 woorden).
Metadata:
{json.dumps(data_for_llm, indent=2)}

Vraag: {user_question}
Antwoord:
"""

        with st.spinner("Zoeken naar antwoord..."):
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=150
                )
                answer = response.choices[0].message.content
                st.markdown(f"""
                    <div style='margin-top: 2em; margin-bottom: 2em; padding: 1em; border: 1px solid #ccc; border-radius: 8px;'>
                        <h4 style='pointer-events: none;'>Vraag:</h4>
                        <p style='font-style: italic;'>{user_question}</p>
                        <h4 style='pointer-events: none;'>Antwoord:</h4>
                        <p>{answer}</p>
                    </div>
                """, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Er ging iets mis bij het ophalen van het antwoord: {e}")

    for file_key, group in filtered.groupby('file_key'):
        with st.expander(file_key, expanded=False):
            table = group[['metadata_field', 'metadata_value']].reset_index(drop=True)
            styled = table.style
            if kw and match_type == 'Deeltekst':
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
                def highlight_substring(v):
                    return pattern.sub(lambda m: f"<span style='background-color: yellow'>{m.group(0)}</span>", str(v))
                styled = styled.format({
                    'metadata_field': highlight_substring,
                    'metadata_value': highlight_substring
                })
            styled = styled.set_table_attributes('class="responsive-table"')
            styled = styled.set_table_styles([
                {'selector': 'th.col0', 'props': [('max-width', '200px'), ('white-space', 'normal')]},
                {'selector': 'td.col0', 'props': [('max-width', '200px'), ('white-space', 'normal')]}
            ])
            html = styled.to_html(escape=False)
            st.markdown(f'<div style="overflow-x:auto;">{html}</div>', unsafe_allow_html=True)

if __name__ == '__main__':
    main()
