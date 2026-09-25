from __future__ import annotations

import streamlit as st

from english_ui import install
from onboarding import render_onboarding
from server_ui import initialize_access
from smart_ui import render_smart_mode
from templyfier.server_storage import server_mode


st.set_page_config(
    page_title="G-Sight Templyfier",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="auto",
)

install()
initialize_access()
privacy_text = (
    "Internal server processing · files are not sent to an external AI service"
    if server_mode()
    else "Session-only processing · files are not sent to an external AI service"
)

st.markdown(
    """
    <style>
      .block-container {max-width:1440px; padding-top:4rem; padding-bottom:3rem;}
      .hero {padding:1rem 1.3rem; border-radius:12px; background:#183d45; color:white; margin-bottom:.7rem;}
      .hero h1 {margin:0; font-size:1.8rem; line-height:1.2;}
      .hero p {margin:.55rem 0 0; opacity:.92; font-size:1rem;}
      .privacy {display:inline-block; margin-top:.8rem; padding:.25rem .65rem; border-radius:999px; background:rgba(255,255,255,.15); font-size:.8rem;}
      .step-title {display:flex; align-items:center; gap:.65rem; margin-top:1.25rem; margin-bottom:.25rem; font-size:1.12rem; font-weight:750; color:#183d45; scroll-margin-top:5rem;}
      .step-number {display:inline-flex; align-items:center; justify-content:center; width:28px; height:28px; border-radius:50%; background:#087f83; color:white; font-size:.85rem;}
      .hint {color:#696777; font-size:.9rem; margin-bottom:.8rem;}
      .ok-card {padding:.8rem 1rem; border:1px solid #d9eadf; border-radius:12px; background:#f5fbf7; color:#245c38;}
      .route-card {padding:.65rem 1rem; border:1px solid #dbe5e5; border-radius:10px; background:#f7fafa; margin:.35rem 0 .8rem;}
      .route-card b {color:#183d45;}
      [data-testid="stMetric"] {background:#f7fafa; border:1px solid #dbe5e5; padding:10px 14px; border-radius:10px;}
      [data-testid="stFileUploader"] {border-radius:14px;}
      [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {min-height:2.75rem;}
      div[data-testid="stButton"] button[kind="primary"], div[data-testid="stDownloadButton"] button {min-height:3rem; font-weight:700; border-radius:12px;}
    </style>
    <div class="hero">
      <h1>G-Sight Templyfier <span style="font-size:.85rem;opacity:.75">v56</span></h1>
      <p>Turn your G-Sight outputs into review-ready Excel toplines.</p>
      <span class="privacy">🔒 PRIVACY_TEXT</span>
    </div>
    """.replace("PRIVACY_TEXT", privacy_text),
    unsafe_allow_html=True,
)

render_onboarding()
render_smart_mode()
