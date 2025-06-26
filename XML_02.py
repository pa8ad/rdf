import os
import json
import fnmatch
import streamlit as st
import streamlit.components.v1 as components
from xml.etree import ElementTree as ET
from pathlib import Path
from datetime import datetime

# Page configuration
st.set_page_config(page_title="Ingest Optimizer", layout='wide')
st.title("Ingest Optimizer")

# Global reset button
if st.button("Reset alles", key='global_reset'):
    for k in list(st.session_state.keys()):
        del st.session_state[k]

# Layout columns
col1, col2 = st.columns([3, 1])

with col1:
    # --- Upload XML/JSON (éénmalig) ---
    if 'file_content' not in st.session_state:
        upload_placeholder = st.empty()
        uploaded = upload_placeholder.file_uploader(
            "Upload XML of JSON bestand", type=["xml", "json"], key='uploader'
        )
        if not uploaded:
            st.stop()
        st.session_state['file_content'] = uploaded.read()
        st.session_state['file_name'] = uploaded.name
        upload_placeholder.empty()

    # Use stored file
    content = st.session_state['file_content']
    uploaded_name = st.session_state['file_name']
    suffix = Path(uploaded_name).suffix.lower()
    orig_size = len(content)

    # Parse and collect tags/keys
    if suffix == '.xml':
        try:
            tree = ET.ElementTree(ET.fromstring(content))
            root = tree.getroot()
        except ET.ParseError:
            st.error("Ongeldige of lege XML.")
            st.stop()
        data_format = 'xml'
        def collect_tags(e, p=""):
            tags = {}
            for c in e:
                full = f"{p}/{c.tag}" if p else c.tag
                tags.setdefault(full, []).append(c)
                tags.update(collect_tags(c, full))
            return tags
        tags = sorted(collect_tags(root).keys())
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            st.error("Ongeldige of lege JSON.")
            st.stop()
        data_format = 'json'
        def collect_keys(o, p=""):
            ks = {}
            if isinstance(o, dict):
                for k, v in o.items():
                    full = f"{p}/{k}" if p else k
                    ks.setdefault(full, []).append(v)
                    ks.update(collect_keys(v, full))
            elif isinstance(o, list):
                for item in o:
                    ks.update(collect_keys(item, p))
            return ks
        tags = sorted(collect_keys(data).keys())

    # --- Load filter JSON (éénmalig) ---
    filter_placeholder = st.empty()
    if 'filter_cfg' not in st.session_state:
        uploaded_filter = filter_placeholder.file_uploader(
            "Laad filterbestand (.filter.json)", type=["json"], key='filter_uploader'
        )
        if uploaded_filter:
            try:
                cfg = json.load(uploaded_filter)
                st.session_state['filter_cfg'] = cfg
                st.session_state['wildcard_input'] = ",".join(cfg.get('wildcards', []))
                st.session_state['include'] = cfg.get('include', tags)
                filter_placeholder.empty()
                st.success("Filterbestand geladen.")
            except Exception as e:
                st.error(f"Ongeldig filterbestand: {e}")
    else:
        cfg = st.session_state['filter_cfg']
        st.info(f"Filter ingeladen: {len(cfg.get('include', []))} tags, {len(cfg.get('wildcards', []))} wildcards")
        if st.button("Reset filter", key='reset_filter'):
            for key in ['filter_cfg', 'include', 'wildcard_input']:
                st.session_state.pop(key, None)

    # Wildcard exclusion input
    wildcard_input = st.text_input(
        "Wildcard-patronen om uit te sluiten", key='wildcard_input',
        help="Gebruik comma-separated fnmatch-patronen"
    )
    patterns = [p.strip() for p in wildcard_input.split(',') if p.strip()] if wildcard_input else []
    wild_excl = sorted({m for pat in patterns for m in fnmatch.filter(tags, pat)})
    if wild_excl:
        st.write(f"Wildcard uitgesloten: {len(wild_excl)} tags")

    # Tag selection multiselect
    options = [t for t in tags if t not in wild_excl]
    default_sel = st.session_state.get('include', options)
    default = [t for t in default_sel if t in options]
    include = st.multiselect(
        "Selecteer tags/keys om op te nemen", options, default, key='include'
    )
    exclude = [t for t in tags if t not in include or t in wild_excl]

with col2:
    st.header("Omvang")
    @st.cache_data
    def calc_size(excl):
        if data_format == 'xml':
            from copy import deepcopy
            nr = deepcopy(root)
            def pr(e, p=[]):
                for c in list(e):
                    f = '/'.join(p + [c.tag])
                    if f in excl:
                        e.remove(c)
                    else:
                        pr(c, p + [c.tag])
            pr(nr)
            return len(ET.tostring(nr, encoding='utf-8'))
        else:
            from copy import deepcopy
            nd = deepcopy(data)
            def pr(o, p=""):
                if isinstance(o, dict):
                    for k in list(o.keys()):
                        full = f"{p}/{k}" if p else k
                        if full in excl:
                            del o[k]
                        else:
                            pr(o[k], full)
                elif isinstance(o, list):
                    for i in o: pr(i, p)
            pr(nd)
            return len(json.dumps(nd).encode())

    new_size = calc_size(exclude)
    st.write(f"Origineel: {orig_size:,} bytes")
    st.write(f"Gefilterd: {new_size:,} bytes")
    st.write(f"Besparing: {orig_size-new_size:,} bytes")

    # Save filter als download
    fn = st.text_input("Naam filter (opslaan als)", key='save_name')
    if fn:
        dataf = json.dumps({'include': include, 'wildcards': patterns}, indent=2)
        st.download_button("Opslaan filter", data=dataf, file_name=f"{fn}.filter.json", mime='application/json')

    # Eén knop: download geoptimaliseerd bestand
    from copy import deepcopy
    stem = Path(uploaded_name).stem
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if data_format == 'xml':
        output_root = deepcopy(root)
        def prune(e, p=[]):
            for c in list(e):
                f = '/'.join(p + [c.tag])
                if f in exclude:
                    e.remove(c)
                else:
                    prune(c, p + [c.tag])
        prune(output_root)
        output_bytes = ET.tostring(output_root, encoding='utf-8', xml_declaration=True)
        ext = '.xml'
    else:
        output_data = deepcopy(data)
        def prune_any(o, p=""):
            if isinstance(o, dict):
                for k in list(o.keys()):
                    full = f"{p}/{k}" if p else k
                    if full in exclude:
                        del o[k]
                    else:
                        prune_any(o[k], full)
            elif isinstance(o, list):
                for i in o: prune_any(i, p)
        prune_any(output_data)
        output_bytes = json.dumps(output_data, indent=2).encode('utf-8')
        ext = '.json'
    optimized_name = f"{stem}_optimized_{ts}{ext}"
    st.download_button(
        label="Download geoptimaliseerd bestand",
        data=output_bytes,
        file_name=optimized_name,
        mime='application/octet-stream',
        key='download_optimized'
    )

# Footer stats
st.markdown("---")
st.write(f"Totaal tags/keys: {len(tags)}")
st.write(f"Totaal elementen: {len(root.findall('.//*'))}" if data_format=='xml' else f"Totaal entries: {cnt(data)}")

# Checkbox om hiërarchie te tonen
show_hierarchy = st.checkbox("Toon hiërarchie van bestand")
if show_hierarchy:
    # Toon binnen een inklapbaar paneel met vaste hoogte
    with st.expander("Bekijk hiërarchie", expanded=False):
        if data_format == 'xml':
            # Converteer XML naar geneste dict
            def xml_to_dict(elem):
                children = list(elem)
                if not children:
                    return elem.text or ""
                result = {}
                for child in children:
                    child_dict = xml_to_dict(child)
                    if child.tag in result:
                        if not isinstance(result[child.tag], list):
                            result[child.tag] = [result[child.tag]]
                        result[child.tag].append(child_dict)
                    else:
                        result[child.tag] = child_dict
                return result
            tree_data = {root.tag: xml_to_dict(root)}
        else:
            tree_data = data
        # Render als code in scrollbare HTML-container
        json_str = json.dumps(tree_data, indent=2)
        html = f"""
<div style='max-height:400px; overflow:auto; white-space: pre; font-family: monospace;'>
{json_str}
</div>
"""
        components.html(html, height=450)
