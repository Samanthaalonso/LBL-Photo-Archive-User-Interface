import streamlit as st
import pandas as pd
import numpy as np
import json
import io
import re
from datetime import datetime
from collections import Counter
from PIL import Image
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ── Page config ───────────────────────────────────────────
st.set_page_config(
    page_title="LBNL Photo Archive Reviewer",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Styling ───────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

  html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

  .lbl-header {
    background: linear-gradient(135deg, #003262 0%, #1a4a7a 100%);
    color: white;
    padding: 20px 28px;
    border-radius: 10px;
    border-left: 5px solid #FDB515;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .lbl-logo-circle {
    width: 52px; height: 52px;
    background: #FDB515;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 900; font-size: 14px;
    color: #003262; flex-shrink: 0;
  }
  .lbl-title { font-size: 1.4rem; font-weight: 700; line-height: 1.2; }
  .lbl-sub { font-size: 0.78rem; color: #a8c4e0; letter-spacing: 0.5px; margin-top: 3px; }

  .stat-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 14px 18px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,50,98,.06);
  }
  .stat-number { font-size: 1.8rem; font-weight: 800; color: #003262; line-height: 1; }
  .stat-label { font-size: 0.65rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.8px; margin-top: 4px; }

  .badge-high { display:inline-block; background:#dcfce7; color:#16a34a; border:1px solid #bbf7d0; border-radius:4px; padding:2px 8px; font-size:0.72rem; font-weight:700; font-family:'IBM Plex Mono',monospace; }
  .badge-mid  { display:inline-block; background:#fef9c3; color:#ca8a04; border:1px solid #fde047; border-radius:4px; padding:2px 8px; font-size:0.72rem; font-weight:700; font-family:'IBM Plex Mono',monospace; }
  .badge-low  { display:inline-block; background:#fee2e2; color:#dc2626; border:1px solid #fca5a5; border-radius:4px; padding:2px 8px; font-size:0.72rem; font-weight:700; font-family:'IBM Plex Mono',monospace; }
  .badge-corrected { display:inline-block; background:#dbeafe; color:#2563eb; border:1px solid #93c5fd; border-radius:4px; padding:2px 8px; font-size:0.72rem; font-weight:700; font-family:'IBM Plex Mono',monospace; }

  .detail-box {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
  }
  .detail-label { font-size:0.68rem; color:#94a3b8; text-transform:uppercase; letter-spacing:1px; margin-bottom:3px; font-weight:600; }
  .detail-value { font-size:0.9rem; color:#1e293b; font-weight:500; }
  .caption-text { font-size:0.85rem; color:#475569; line-height:1.6; font-style:italic; }

  .score-row { display:flex; align-items:center; gap:8px; margin-bottom:5px; }
  .score-name { font-size:0.72rem; color:#64748b; width:230px; flex-shrink:0; }
  .score-bar-bg { flex:1; background:#e2e8f0; border-radius:3px; height:6px; }
  .score-val { font-family:'IBM Plex Mono',monospace; font-size:0.68rem; color:#94a3b8; width:36px; text-align:right; flex-shrink:0; }

  .filename-mono { font-family:'IBM Plex Mono',monospace; font-size:0.78rem; color:#64748b; }

  /* Sidebar */
  section[data-testid="stSidebar"] { background: #f0f4f8; }
</style>
""", unsafe_allow_html=True)

#  Constants 
CLASS_LABELS = [
    "Buildings and Facilities",
    "Construction, maintenance, and repair work",
    "Equipment and Machinery",
    "Event",
    "Exterior, Aerial, Wildlife, Environment",
    "Group photographs",
    "Headshot or portrait",
    "Illustration or Composite Image",
    "Work and research activities"
]

XLSX_FOLDER_ID = "11uCdrEKxd2X0k5N2LHLDtllbOTW-BdvJ"

BOX_FOLDER_IDS = {
    "Box_001": "1kKtyE6YTCoK_492CcF5Zy53mvsy5UCU9",
    "Box_002": "1Al84ulog5BuZGADHrSkDI6X3Xyvv96sW",
    "Box_003": "1leZAP4zhHd0_kgGdqBAH8rBoTUd8GWIa",
    "Box_004": "1MA5ujOeFG4Y6AfffehPGwXK6rSfP4l8d",
    "Box_005": "1eTGd665LFQ0BcnUPugftyVKB6FbR2EzG",
}

XLSX_NAMES = {
    "Box_001": "Box 01 (1).xlsx",
    "Box_002": "Box 002.xlsx",
    "Box_003": "Box 003.xlsx",
    "Box_004": "Box 004.xlsx",
    "Box_005": "Box 005.xlsx",
}

# ── Session state ─────────────────────────────────────────
for key, default in [
    ("corrections", {}),
    ("selected", None),
    ("df", None),
    ("drive_service", None),
    ("image_index", {}),   # box → {norm_name: file_id}
    ("image_cache", {}),   # file_id → PIL Image
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Normalize filename ────────────────────────────────────
def normalize_name(name: str) -> str:
    name = str(name).strip()
    name = re.sub(r'\.(jpg|jpeg|png|tif|tiff)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[-_]\d+$', '', name)
    name = re.sub(r'[-_][lLmMeEpP]$', '', name)
    name = re.sub(r'(?<=-)(0+)(\d)', r'\2', name)
    name = re.sub(r'(\d+)-Cyc', r'\1Cyc', name, flags=re.IGNORECASE)
    name = re.sub(r'Cycl', 'Cyc', name, flags=re.IGNORECASE)
    return name.upper().strip()

# ── Drive auth ────────────────────────────────────────────
@st.cache_resource
def get_drive_service():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)

# ── Drive helpers ─────────────────────────────────────────
@st.cache_data(ttl=3600)
def list_files_in_folder(folder_id: str) -> list[dict]:
    """List all files in a Drive folder."""
    service = get_drive_service()
    files, page_token = [], None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=1000
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files

@st.cache_data(ttl=3600)
def download_file_bytes(file_id: str) -> bytes:
    """Download a file from Drive as bytes."""
    service = get_drive_service()
    req = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()

@st.cache_data(ttl=3600)
def load_xlsx_from_drive(file_id: str) -> pd.DataFrame:
    data = download_file_bytes(file_id)
    df = pd.read_excel(io.BytesIO(data), usecols=["File Name", "Caption"])
    df = df.dropna(subset=["File Name"])
    df["Caption"]   = df.get("Caption", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    df["File Name"] = df["File Name"].astype(str).str.strip()
    return df

def build_image_index(box_name: str) -> dict:
    """Build norm_name → file_id map for a box folder."""
    folder_id = BOX_FOLDER_IDS[box_name]
    files = list_files_in_folder(folder_id)
    index = {}
    for f in files:
        if f["mimeType"].startswith("image/") and "checkpoint" not in f["name"].lower():
            key = normalize_name(f["name"])
            index[key] = f["id"]
    return index

def get_image(file_id: str) -> Image.Image | None:
    if file_id in st.session_state.image_cache:
        return st.session_state.image_cache[file_id]
    try:
        data = download_file_bytes(file_id)
        img  = Image.open(io.BytesIO(data)).convert("RGB")
        st.session_state.image_cache[file_id] = img
        return img
    except:
        return None

def find_image(file_name: str, box: str) -> Image.Image | None:
    if box not in st.session_state.image_index:
        return None
    key     = normalize_name(file_name)
    file_id = st.session_state.image_index[box].get(key)
    if not file_id:
        return None
    return get_image(file_id)

# ── Load all data from Drive ──────────────────────────────
@st.cache_data(ttl=3600)
def load_all_data() -> pd.DataFrame:
    """Load all xlsx files from Drive and combine into one DataFrame."""
    service = get_drive_service()

    # List xlsx files in the results folder
    xlsx_files = list_files_in_folder(XLSX_FOLDER_ID)
    xlsx_map   = {f["name"]: f["id"] for f in xlsx_files if f["name"].endswith(".xlsx")}

    all_dfs = []
    for box_name, xlsx_name in XLSX_NAMES.items():
        file_id = xlsx_map.get(xlsx_name)
        if not file_id:
            st.warning(f"{xlsx_name} not found in Drive")
            continue
        df = load_xlsx_from_drive(file_id)
        df["box"] = box_name
        all_dfs.append(df)

    if not all_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    combined = combined.rename(columns={"File Name": "file_name", "Caption": "caption"})
    return combined

# ── Helpers ───────────────────────────────────────────────
def confidence_badge(conf: float, corrected: bool = False) -> str:
    if corrected:
        return '<span class="badge-corrected">✏ CORRECTED</span>'
    pct = f"{conf*100:.1f}%"
    if conf >= 0.85:   return f'<span class="badge-high">▲ {pct}</span>'
    elif conf >= 0.60: return f'<span class="badge-mid">◆ {pct}</span>'
    else:              return f'<span class="badge-low">▼ {pct}</span>'

def get_effective_label(file_name: str, top_label: str) -> str:
    return st.session_state.corrections.get(file_name, top_label)

# ── Header ────────────────────────────────────────────────
st.markdown("""
<div class="lbl-header">
  <div class="lbl-logo-circle">LBL</div>
  <div>
    <div class="lbl-title">Photo Archive Reviewer</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("###  Controls")

    if st.button(" Load / Refresh Data", use_container_width=True):
        load_all_data.clear()
        st.session_state.df = None
        st.session_state.image_index = {}
        st.session_state.image_cache = {}
        st.rerun()

    # Load data on first run
    if st.session_state.df is None:
        with st.spinner("Loading xlsx files from Drive…"):
            try:
                st.session_state.df = load_all_data()
                st.success(f"Loaded {len(st.session_state.df)} records")
            except Exception as e:
                st.error(f"Drive error: {e}")
                st.stop()

    df_all = st.session_state.df
    if df_all is None or df_all.empty:
        st.warning("No data loaded.")
        st.stop()

    st.markdown("---")
    st.markdown("### Filters")

    boxes     = ["All"] + sorted(df_all["box"].unique().tolist())
    sel_box   = st.selectbox("Box", boxes)

    has_preds = "top_label" in df_all.columns
    if has_preds:
        labels    = ["All"] + CLASS_LABELS
        sel_label = st.selectbox("Predicted Label", labels)
        conf_range = st.slider("Confidence", 0.0, 1.0, (0.0, 1.0), 0.05, format="%.0f%%")
        show_low   = st.checkbox("Low confidence only (<60%)")
    else:
        sel_label  = "All"
        conf_range = (0.0, 1.0)
        show_low   = False

    show_corrections = st.checkbox("Corrected only")

    st.markdown("---")
    st.markdown("### Image is Loading...")
    load_images = st.checkbox("Load images from Drive", value=True,
                              help="Uncheck to browse metadata only (faster)")
    if load_images:
        boxes_to_index = [sel_box] if sel_box != "All" else list(BOX_FOLDER_IDS.keys())
        for b in boxes_to_index:
            if b not in st.session_state.image_index:
                with st.spinner(f"Indexing {b} images…"):
                    st.session_state.image_index[b] = build_image_index(b)

    st.markdown("---")
    n_corr = len(st.session_state.corrections)
    st.markdown(f'<div class="stat-card"><div class="stat-number">{n_corr}</div><div class="stat-label">Corrections This Session</div></div>', unsafe_allow_html=True)

# ── Apply filters ─────────────────────────────────────────
filtered = df_all.copy()
if sel_box != "All":
    filtered = filtered[filtered["box"] == sel_box]
if has_preds and sel_label != "All":
    filtered = filtered[filtered["top_label"] == sel_label]
if has_preds:
    filtered = filtered[
        (filtered["confidence"] >= conf_range[0]) &
        (filtered["confidence"] <= conf_range[1])
    ]
    if show_low:
        filtered = filtered[filtered["confidence"] < 0.60]
if show_corrections:
    filtered = filtered[filtered["file_name"].isin(st.session_state.corrections)]

filtered = filtered.reset_index(drop=True)

# ── Tabs ──────────────────────────────────────────────────
tab_browse, tab_review, tab_export = st.tabs([
    "  Browse",
    "  Review & Correct",
    "  Export"
])

# TAB — Browse

with tab_browse:
    # Stats row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{len(df_all)}</div><div class="stat-label">Total Records</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{len(filtered)}</div><div class="stat-label">Filtered</div></div>', unsafe_allow_html=True)
    with c3:
        if has_preds:
            high = (df_all["confidence"] >= 0.85).sum()
            st.markdown(f'<div class="stat-card"><div class="stat-number">{high}</div><div class="stat-label">High Conf ≥85%</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="stat-card"><div class="stat-number">{df_all["box"].nunique()}</div><div class="stat-label">Boxes</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{len(st.session_state.corrections)}</div><div class="stat-label">Corrected</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Sort
    s1, s2, _ = st.columns([2, 2, 5])
    with s1:
        sort_opts = ["file_name", "box"]
        if has_preds:
            sort_opts = ["confidence", "caption_similarity"] + sort_opts
        sort_by = st.selectbox("Sort by", sort_opts, label_visibility="collapsed")
    with s2:
        asc = st.selectbox("Order", ["Ascending", "Descending"], label_visibility="collapsed") == "Ascending"
    if sort_by in filtered.columns:
        filtered = filtered.sort_values(sort_by, ascending=asc).reset_index(drop=True)

    st.caption(f"**{len(filtered)} records** — click Inspect to open in Review tab")
    st.markdown("---")

    # Gallery grid
    COLS = 4
    for row_i in range(0, len(filtered), COLS):
        cols = st.columns(COLS)
        for col_i, col in enumerate(cols):
            idx = row_i + col_i
            if idx >= len(filtered):
                break
            row = filtered.iloc[idx]
            is_corr = row["file_name"] in st.session_state.corrections
            eff_label = get_effective_label(row["file_name"], row.get("top_label", "—"))
            conf      = row.get("confidence", None)

            with col:
                if load_images:
                    img = find_image(row["file_name"], row["box"])
                    if img:
                        st.image(img, use_container_width=True)
                    else:
                        st.markdown('<div style="background:#f1f5f9;border:1px dashed #cbd5e1;border-radius:6px;height:130px;display:flex;align-items:center;justify-content:center;color:#94a3b8;font-size:0.72rem;">No image</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;height:80px;display:flex;align-items:center;justify-content:center;color:#64748b;font-size:0.72rem;font-weight:600;">{row["box"]}</div>', unsafe_allow_html=True)

                st.markdown(f'<div class="filename-mono">{row["file_name"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:0.78rem;font-weight:600;color:#1e293b;margin:3px 0;">{eff_label}</div>', unsafe_allow_html=True)
                if conf is not None:
                    st.markdown(confidence_badge(conf, is_corr), unsafe_allow_html=True)

                if st.button("Inspect →", key=f"insp_{idx}", use_container_width=True):
                    st.session_state.selected = row["file_name"]
                    st.info("Switch to **Review & Correct** tab ↑")

# ══════════════════════════════════════════════════════════
# TAB — Review & Correct
# ══════════════════════════════════════════════════════════
with tab_review:
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown("#### Select Record")
        file_names  = filtered["file_name"].tolist()
        default_idx = 0
        if st.session_state.selected in file_names:
            default_idx = file_names.index(st.session_state.selected)

        if not file_names:
            st.warning("No records match current filters.")
            st.stop()

        selected_file = st.selectbox("File", file_names, index=default_idx, label_visibility="collapsed")
        row = filtered[filtered["file_name"] == selected_file].iloc[0]

        # Image
        if load_images:
            img = find_image(row["file_name"], row["box"])
            if img:
                st.image(img, use_container_width=True)
            else:
                st.markdown('<div style="background:#f1f5f9;border:1px dashed #cbd5e1;border-radius:8px;height:280px;display:flex;align-items:center;justify-content:center;color:#94a3b8;">Image not available</div>', unsafe_allow_html=True)
        else:
            st.info("Enable 'Load images from Drive' in the sidebar to see images.")

        # Nav
        nl, nr = st.columns(2)
        with nl:
            if st.button("← Prev", use_container_width=True):
                i = file_names.index(selected_file)
                if i > 0:
                    st.session_state.selected = file_names[i - 1]
                    st.rerun()
        with nr:
            if st.button("Next →", use_container_width=True):
                i = file_names.index(selected_file)
                if i < len(file_names) - 1:
                    st.session_state.selected = file_names[i + 1]
                    st.rerun()

    with right:
        st.markdown("#### Metadata")

        # Metadata
        st.markdown(f"""
        <div class="detail-box">
          <div class="detail-label">File Name</div>
          <div class="filename-mono">{row['file_name']}</div>
          <br>
          <div class="detail-label">Box</div>
          <div class="detail-value">{row['box']}</div>
          <br>
          <div class="detail-label">Caption</div>
          <div class="caption-text">{row['caption'] or '—'}</div>
        </div>
        """, unsafe_allow_html=True)

        # Prediction (if available)
        if has_preds and "top_label" in row and pd.notna(row.get("top_label")):
            is_corr = row["file_name"] in st.session_state.corrections
            st.markdown(f"""
            <div class="detail-box">
              <div class="detail-label">Model Prediction</div>
              <div class="detail-value">{row['top_label']}</div>
              <br>
              <div class="detail-label">Confidence</div>
              <div style="margin-top:4px;">{confidence_badge(row['confidence'], is_corr)}</div>
              <br>
              <div class="detail-label">Caption Similarity</div>
              <div class="detail-value">{row.get('caption_similarity', '—'):.3f if pd.notna(row.get('caption_similarity')) else '—'}</div>
            </div>
            """, unsafe_allow_html=True)

            # Score bars
            if "all_scores" in row and row["all_scores"]:
                scores = row["all_scores"] if isinstance(row["all_scores"], dict) else {}
                if scores:
                    st.markdown("#### Class Scores")
                    bars = ""
                    for lbl, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
                        is_top = lbl == row["top_label"]
                        fill   = "#003262" if is_top else "#cbd5e1"
                        color  = "#003262" if is_top else "#64748b"
                        bars  += f"""
                        <div class="score-row">
                          <div class="score-name" style="color:{color};font-weight:{'700' if is_top else '400'};">{lbl}</div>
                          <div class="score-bar-bg">
                            <div style="width:{score*100:.1f}%;background:{fill};height:6px;border-radius:3px;"></div>
                          </div>
                          <div class="score-val">{score:.2f}</div>
                        </div>"""
                    st.markdown(f'<div class="detail-box">{bars}</div>', unsafe_allow_html=True)

        # Correction
        st.markdown("#### Correct Label")
        current = st.session_state.corrections.get(row["file_name"], row.get("top_label", CLASS_LABELS[0]))
        if current not in CLASS_LABELS:
            current = CLASS_LABELS[0]
        new_label = st.selectbox("Set label", CLASS_LABELS,
                                  index=CLASS_LABELS.index(current),
                                  label_visibility="collapsed")

        sl, sr = st.columns(2)
        with sl:
            if st.button(" Save", use_container_width=True):
                st.session_state.corrections[row["file_name"]] = new_label
                st.success(f"Saved: {new_label}")
        with sr:
            if st.button("✕ Clear", use_container_width=True):
                st.session_state.corrections.pop(row["file_name"], None)
                st.info("Cleared")

# ══════════════════════════════════════════════════════════
# TAB — Export
# ══════════════════════════════════════════════════════════
with tab_export:
    st.markdown("#### Export")

    n_total = len(df_all)
    n_corr  = len(st.session_state.corrections)

    e1, e2, e3 = st.columns(3)
    with e1:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{n_total}</div><div class="stat-label">Total Records</div></div>', unsafe_allow_html=True)
    with e2:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{n_corr}</div><div class="stat-label">Corrected</div></div>', unsafe_allow_html=True)
    with e3:
        st.markdown(f'<div class="stat-card"><div class="stat-number">{n_total - n_corr}</div><div class="stat-label">Unchanged</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if n_corr == 0:
        st.info("No corrections yet — use **Review & Correct** tab to fix predictions.")
    else:
        export_rows = []
        for _, row in df_all.iterrows():
            corrected = row["file_name"] in st.session_state.corrections
            r = {
                "box":           row["box"],
                "file_name":     row["file_name"],
                "caption":       row["caption"],
                "final_label":   st.session_state.corrections.get(row["file_name"], row.get("top_label", "")),
                "was_corrected": corrected,
            }
            if has_preds:
                r["model_label"] = row.get("top_label", "")
                r["confidence"]  = round(row.get("confidence", 0), 4)
                r["caption_sim"] = round(row.get("caption_similarity", 0), 4)
            export_rows.append(r)

        export_df = pd.DataFrame(export_rows)

        st.markdown("**Corrected rows preview:**")
        st.dataframe(export_df[export_df["was_corrected"]].drop(columns=["was_corrected"]),
                     use_container_width=True, height=280)

        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "⬇ Download All (CSV)",
                data=export_df.to_csv(index=False),
                file_name=f"lbnl_labels_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        with d2:
            st.download_button(
                "⬇ Corrections Only",
                data=export_df[export_df["was_corrected"]].to_csv(index=False),
                file_name=f"lbnl_corrections_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        st.markdown("---")
        st.markdown("**Label distribution after corrections:**")
        dist = export_df["final_label"].value_counts().reset_index()
        dist.columns = ["Label", "Count"]
        dist["Pct"] = (dist["Count"] / len(export_df) * 100).round(1).astype(str) + "%"
        st.dataframe(dist, use_container_width=True, hide_index=True)
