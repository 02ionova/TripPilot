"""Shared typography, rounded search fields and itinerary styling."""

import streamlit as st


def apply_styles() -> None:
    """Travel-service layout with a sans-serif heading/body pair and soft cards."""
    st.markdown(
        """<style>
        :root {--trip-ink:#272B38; --trip-muted:#777B88; --trip-accent:#68465F; --trip-line:#E8E9EF;}
        .block-container {max-width: 1240px; padding-top: 5rem; padding-bottom: 3rem;}
        html, body, input, button, [data-testid="stMarkdownContainer"] {
          font-family: "Avenir Next", "Segoe UI", Arial, sans-serif;
        }
        h1, h2, h3, .day-title {
          font-family: "Trebuchet MS", "Avenir Next", "Segoe UI", sans-serif !important;
          letter-spacing: -.035em; color: var(--trip-ink); font-weight: 700 !important;
        }
        h1 {font-size: 2.8rem !important;}
        [data-testid="stWidgetLabel"] p {font-size: .83rem; color: #666B79; font-weight: 600;}
        [data-baseweb="input"], [data-baseweb="select"] > div,
        .react-aria-ComboBox > [role="group"], [data-testid="stNumberInputContainer"],
        .react-aria-DatePicker > [role="group"] {
          background: #F5F6FA !important; border-color: #ECEEF4 !important; border-radius: 13px !important;
        }
        [data-testid="stNumberInputField"], .react-aria-ComboBox input, [data-baseweb="input"] input {background: transparent !important; font-size: .95rem;}
        [data-baseweb="input"]:focus-within, [data-baseweb="select"]:focus-within > div,
        .react-aria-ComboBox > [role="group"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within {
          border-color: #A793A2 !important; box-shadow: 0 0 0 3px #68465F0C;
        }
        [data-testid="stButton"] button {border-radius: 13px; min-height: 3.1rem; font-weight: 700;}
        .st-key-travel_request_panel {background: #FFFFFF; border-color: var(--trip-line); border-radius: 22px; padding: 1.4rem; box-shadow: 0 8px 32px #272B3805;}
        [class*="st-key-itinerary_day_"] {background: #FFFFFF; border-radius: 20px; padding: 1rem;}
        [data-testid="stMetric"] {background: #FFFFFF; border: 1px solid var(--trip-line); border-radius: 17px; padding: 1rem 1.2rem;}
        [data-testid="stMetricLabel"] {color: var(--trip-muted);}
        [data-testid="stMetricValue"] {color: var(--trip-ink);}
        [data-testid="stVerticalBlockBorderWrapper"] {border-radius: 20px;}
        [data-testid="stTabs"] button {font-weight: 600;}
        .journey-kicker {text-transform: uppercase; letter-spacing: .18em; color: #8A7286; font-size: .68rem; font-weight: 700; margin-bottom: .3rem;}
        .day-number {color: #8A7286; text-transform: uppercase; font-size: .7rem; font-weight: 700; letter-spacing: .12em; margin-bottom: .4rem;}
        .day-title {font-size: 1.45rem; line-height: 1.3; margin: .2rem 0 .8rem;}
        .day-photo {margin: 0 0 .6rem;}
        .day-photo img {width: 100%; height: 215px; object-fit: cover; border-radius: 16px; background: #EDEFF5;}
        .day-photo figcaption {font-size: .72rem; color: var(--trip-muted); padding: .45rem 0;}
        .day-photo a, .stop-links a {color: var(--trip-accent); text-decoration: none;}
        .stop-card {border: 1px solid var(--trip-line); border-left: 4px solid var(--trip-accent); background: #FFFFFF; border-radius: 16px; padding: 1rem 1.1rem; margin: .3rem 0 .8rem;}
        .stop-card.meal {border-left-color: #AF8D55; background: #FBF8F1;}
        .stop-card.visit {border-left-color: #648679; background: #F2F7F4;}
        .stop-card.flight {border-left-color: #736394; background: #F5F3F9;}
        .stop-card.stay {border-left-color: #638398; background: #F1F6FA;}
        .stop-card.transfer {border-left-color: #939BA3; background: #F6F7F9;}
        .stop-top {display: flex; align-items: center; gap: .8rem; flex-wrap: wrap; margin-bottom: .5rem;}
        .stop-time {font-weight: 700; color: #3B3E4A; font-size: .87rem; font-variant-numeric: tabular-nums;}
        .stop-tag {font-size: .65rem; text-transform: uppercase; letter-spacing: .12em; font-weight: 700; color: #557969;}
        .meal .stop-tag {color: #94733C;}
        .flight .stop-tag {color: #736394;}
        .stay .stop-tag {color: #638398;}
        .stop-name {font-weight: 700; color: var(--trip-ink); font-size: 1.02rem; margin-bottom: .3rem;}
        .stop-meta {font-size: .8rem; color: #666B79; line-height: 1.6;}
        .stop-links {font-size: .78rem; padding-top: .5rem; display: flex; gap: 1rem;}
        .transfer-note {font-size: .73rem; color: var(--trip-muted); border-left: 1px dashed #CDD2DC; margin: .15rem 0 .3rem .7rem; padding: .2rem .8rem;}
        .travel-information {position: fixed; right: 18px; top: 112px; z-index: 9999; width: 36px; height: 36px; cursor: help; outline-offset: 4px;}
        .information-symbol {display: grid; place-items: center; width: 36px; height: 36px; border-radius: 50%; background: #FFFFFF; border: 1px solid #DEE1EB; color: #68465F; font-family: "Trebuchet MS", sans-serif; font-weight: 700; box-shadow: 0 3px 14px #272B3810;}
        .information-popover {display: none; position: absolute; right: 38px; top: 0; width: min(390px, calc(100vw - 90px)); max-height: 68vh; overflow-y: auto; overscroll-behavior: contain; padding: 1.2rem; border-radius: 18px; border: 1px solid #E2E5EF; background: #FFFFFF; box-shadow: 0 12px 50px #272B3820; color: #626777; font-size: .8rem; line-height: 1.6; cursor: auto;}
        .travel-information:hover .information-popover, .travel-information:focus-within .information-popover {display: block;}
        .information-popover h2 {font-size: 1.1rem; margin: 0 0 .7rem;}
        .information-popover h3 {font-size: .83rem; margin: 1rem 0 .4rem;}
        .information-popover ul {padding-left: 1.1rem; margin: 0;}
        .information-popover li {margin-bottom: .5rem;}
        @media (max-width: 700px) {
          .block-container {padding: 5rem 1rem 2rem;}
          h1 {font-size: 2.2rem !important;}
          .day-photo img {height: 180px;}
          .stop-card {padding: .85rem;}
          .travel-information {right: 10px; top: 100px;}
        }
        </style>""",
        unsafe_allow_html=True,
    )
