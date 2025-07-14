import os
import json
import fnmatch
import streamlit as st
from xml.etree import ElementTree as ET
from pathlib import Path
from datetime import datetime
from copy import deepcopy

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
    # --- Upload XML/JSON ---
    if 'file_content' not in st.session_state:
        uploaded = st.file_uploader("Upload XML of JSON bestand", type=["xml", "json"], key='uploader')
        if not uploaded:
            st.stop()
        st.session_state['file_content'] = uploaded.read()
        st.session_state['file_name'] = uploaded.name

    content = st.session_state['file_content']
    uploaded_name = st.session_state['file_name']
    suffix = Path(uploaded_name).suffix.lower()
    orig_size = len(content)

    # Parse
    if suffix == '.xml':
        try:
            tree = ET.ElementTree(ET.fromstring(content))
            root = tree.getroot()
        except ET.ParseError:
            st.error("Ongeldige of lege XML.")
            st.stop()
        data_format = 'xml'
        def collect_tags(elem, path=""):
            tags = {}
            for child in elem:
                full = f"{path}/{child.tag}" if path else child.tag
                tags.setdefault(full, []).append(child)
                tags.update(collect_tags(child, full))
            return tags
        tags_map = {root.tag: [root]}
        tags_map.update(collect_tags(root))
    else:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            st.error("Ongeldige of lege JSON.")
            st.stop()
        data_format = 'json'
        def collect_keys(obj, path=""):
            keys = {}
            if isinstance(obj, dict):
                for k, v in obj.items():
                    full = f"{path}/{k}" if path else k
                    keys.setdefault(full, []).append(v)
                    keys.update(collect_keys(v, full))
            elif isinstance(obj, list):
                for item in obj:
                    keys.update(collect_keys(item, path))
            return keys
        tags_map = collect_keys(data)
    tags = sorted(tags_map.keys())

    # Overview\ n    st.subheader("Overzicht tags/keys")
    overview = []
    for tag in tags:
        total = len(tags_map[tag])
        if data_format == 'xml':
            str_count = sum(1 for elem in tags_map[tag] if elem.text and elem.text.strip())
        else:
            str_count = sum(1 for v in tags_map[tag] if isinstance(v, str))
        overview.append({'Tag/Key': tag, 'Aantal': total, 'String waarden': str_count})
    st.dataframe(overview)

    # Load filter
    filter_placeholder = st.empty()
    if 'filter_cfg' not in st.session_state:
        uploaded_filter = filter_placeholder.file_uploader("Laad filterbestand (.filter.json)", type=["json"], key='filter_uploader')
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

    # Wildcard exclusion
    wildcard_input = st.text_input("Wildcard-patronen om uit te sluiten", key='wildcard_input', help="Gebruik comma-separated fnmatch-patronen")
    patterns = [p.strip() for p in wildcard_input.split(',') if p.strip()]
    wild_excl = sorted({m for pat in patterns for m in fnmatch.filter(tags, pat)})
    if wild_excl:
        st.write(f"Wildcard uitgesloten: {len(wild_excl)} tags")

    # Select tags
    options = [t for t in tags if t not in wild_excl]
    default = st.session_state.get('include', options)
    def format_label(tag):
        import re
        return re.sub(r"\{.*?\}", "", tag).strip()
    include = st.multiselect("Selecteer tags/keys om op te nemen", options, default, format_func=format_label, key='include')
    exclude = [t for t in tags if t not in include or t in wild_excl]

    # Show excluded
    st.write("Uitgesloten tags/keys")
    if exclude:
        badges = [f"<span style='background:#e0e0e0;color:#555;padding:4px 8px;margin:2px;border-radius:4px;'>{format_label(t)}</span>" for t in exclude]
        st.markdown(''.join(badges), unsafe_allow_html=True)

    # Checkbox to show original hierarchy
    show_hierarchy = st.checkbox("Toon hiërarchie van bestand")
    if show_hierarchy:
        st.markdown("## Hiërarchie van het bestand")
        if data_format == 'xml':
            def xml_to_dict(elem):
                children = list(elem)
                if not children:
                    return elem.text or ""
                result = {}
                for c in children:
                    child_dict = xml_to_dict(c)
                    if c.tag in result:
                        if not isinstance(result[c.tag], list):
                            result[c.tag] = [result[c.tag]]
                        result[c.tag].append(child_dict)
                    else:
                        result[c.tag] = child_dict
                return result
            tree_dict = {root.tag: xml_to_dict(root)}
            st.json(tree_dict)
        else:
            st.json(data)

    # Checkbox to show filtered hierarchy
    show_filtered = st.checkbox("Toon gefilterde hiërarchie van bestand")
    if show_filtered:
        st.markdown("## Gefilterde hiërarchie van het bestand")
        if data_format == 'xml':
            def xml_to_dict_filtered(elem, path=""):
                children = list(elem)
                res = {}
                for c in children:
                    full = f"{path}/{c.tag}" if path else c.tag
                    if full in include:
                        child = xml_to_dict_filtered(c, full)
                        if c.tag in res:
                            if not isinstance(res[c.tag], list):
                                res[c.tag] = [res[c.tag]]
                            res[c.tag].append(child)
                        else:
                            res[c.tag] = child
                return res if res else (elem.text or "")
            filtered = {root.tag: xml_to_dict_filtered(root)}
            st.json(filtered)
        else:
            def json_to_dict_filtered(o, path=""):
                if isinstance(o, dict):
                    res = {}
                    for k, v in o.items():
                        full = f"{path}/{k}" if path else k
                        if full in include:
                            filtered_v = json_to_dict_filtered(v, full)
                            res[k] = filtered_v
                    return res
                elif isinstance(o, list):
                    lst = []
                    for item in o:
                        v = json_to_dict_filtered(item, path)
                        lst.append(v)
                    return lst
                else:
                    return o
            filtered_json = json_to_dict_filtered(data)
            st.json(filtered_json)

with col2:
    st.header("Omvang")
    @st.cache_data
    def calc_size(excl):
        if data_format == 'xml':
            temp = deepcopy(root)
            def pr(e, p=[]):
                for c in list(e):
                    full = '/'.join(p + [c.tag])
                    if full in excl:
                        e.remove(c)
                    else:
                        pr(c, p + [c.tag])
            pr(temp)
            return len(ET.tostring(temp, encoding='utf-8'))
        else:
            temp = deepcopy(data)
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
            pr(temp)
            return len(json.dumps(temp).encode())
    new_size = calc_size(exclude)
    st.write(f"Origineel: {orig_size:,} bytes")
    st.write(f"Gefilterd: {new_size:,} bytes")
    st.write(f"Besparing: {orig_size-new_size:,} bytes")

    fn = st.text_input("Naam filter (opslaan als)", key='save_name')
    if fn:
        cfg_json = json.dumps({'include': include, 'wildcards': patterns}, indent=2)
        st.download_button("Opslaan filter", data=cfg_json, file_name=f"{fn}.filter.json", mime='application/json')

    # Prepare output
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = Path(uploaded_name).stem
    if data_format == 'xml':
        out_root = deepcopy(root)
        def prune(e, p=[]):
            for c in list(e):
                full = '/'.join(p + [c.tag])
                if full in exclude:
                    e.remove(c)
                else:
                    prune(c, p + [c.tag])
        prune(out_root)
        output_bytes = ET.tostring(out_root, encoding='utf-8', xml_declaration=True)
        ext = '.xml'
    else:
        out_data = deepcopy(data)
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
        prune_any(out_data)
        output_bytes = json.dumps(out_data, indent=2).encode('utf-8')
        ext = '.json'
    optimized_name = f"{stem}_optimized_{ts}{ext}"
    # Download optimized file
    st.download_button(
        label="Download geoptimaliseerd bestand",
        data=output_bytes,
        file_name=optimized_name,
        mime='application/octet-stream',
        key='download_optimized'
    )
    # Generate and download log file
    log_name = optimized_name.rsplit('.', 1)[0] + '.log'
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines = [
        f"Origineel bestand: {uploaded_name}",
        f"Download timestamp: {timestamp}",
        "",
        "Tags/keys opgenomen:"
    ]
    log_lines.extend(include)
    log_lines.append("")
    log_lines.append("Tags/keys niet opgenomen:")
    log_lines.extend(exclude)
    log_content = "\n".join(log_lines)
    st.download_button(
        label="Download logbestand",
        data=log_content.encode('utf-8'),
        file_name=log_name,
        mime='text/plain',
        key='download_log'
    )
