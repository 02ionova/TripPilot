"""Shared visual styling for the Streamlit travel planner."""

import streamlit as st


def apply_styles() -> None:
    """Warm ivory, aubergine, forest and brass with readable venue cards."""
    st.markdown(
        """<style>
        .block-container {max-width: 1220px; padding-top: 5rem; padding-bottom: 3rem;}
        h1, h2, h3 {letter-spacing: -.035em;}
        h1 {font-family: Georgia, serif; font-weight: 500 !important; color: #493343;}
        [data-testid="stForm"], .st-key-travel_request_panel {background: #FFFEFC; border-color: #E4DCD2; border-radius: 18px; padding: 1.35rem;}
        [data-testid="stMetric"] {background: #FFFEFC; border: 1px solid #E4DCD2; border-radius: 14px; padding: 1rem 1.2rem;}
        [data-testid="stMetricLabel"] {color: #66605A;}
        [data-testid="stMetricValue"] {color: #493343;}
        [data-testid="stVerticalBlockBorderWrapper"] {border-radius: 16px;}
        [data-testid="stTabs"] button {font-weight: 600;}
        .provider-note {display: flex; align-items: flex-start; gap: .65rem; color: #746E67; font-size: .78rem; line-height: 1.6; padding: .3rem 0 .8rem; border-bottom: 1px solid #E5DED4;}
        .provider-note-icon {flex: 0 0 1rem; width: 1rem; height: 1rem; margin-top: .14rem; border: 1px solid #A7B4A6; border-radius: 50%; color: #657A68; font-size: .67rem; line-height: 1rem; text-align: center; font-family: Georgia, serif;}
        .journey-kicker {text-transform: uppercase; letter-spacing: .2em; color: #8C7049; font-size: .7rem; font-weight: 700; margin-bottom: .3rem;}
        .day-number {color: #92764E; text-transform: uppercase; font-size: .72rem; font-weight: 700; letter-spacing: .15em; margin-bottom: .35rem;}
        .day-title {color: #493343; font-family: Georgia, serif; font-size: 1.55rem; line-height: 1.3; margin: .2rem 0 .6rem;}
        .day-photo {margin: 0 0 .6rem;}
        .day-photo img {width: 100%; height: 235px; object-fit: cover; border-radius: 12px; background: #EAE2D8;}
        .day-photo figcaption {font-size: .74rem; color: #746A61; padding: .45rem 0;}
        .day-photo a, .stop-links a {color: #68465F; text-decoration: none;}
        .stop-card {border: 1px solid #E5DDD2; border-left: 4px solid #68465F; background: #FFFDFC; border-radius: 12px; padding: 1rem 1.1rem; margin: .3rem 0 .75rem;}
        .stop-card.meal {border-left-color: #977640; background: #F7F1E6;}
        .stop-card.visit {border-left-color: #466558; background: #EFF4F0;}
        .stop-top {display: flex; align-items: center; gap: .8rem; flex-wrap: wrap; margin-bottom: .45rem;}
        .stop-time {font-weight: 700; color: #3B3A3A; font-size: .88rem; font-variant-numeric: tabular-nums;}
        .stop-tag {font-size: .66rem; text-transform: uppercase; letter-spacing: .12em; font-weight: 700; color: #466558;}
        .meal .stop-tag {color: #81612E;}
        .stop-name {font-weight: 650; color: #292D32; font-size: 1.04rem; margin-bottom: .3rem;}
        .stop-meta {font-size: .8rem; color: #5D625F; line-height: 1.6;}
        .stop-links {font-size: .78rem; padding-top: .45rem; display: flex; gap: 1rem;}
        .transfer-note {font-size: .74rem; color: #6F726F; border-left: 1px dashed #CFC6B9; margin: .15rem 0 .3rem .7rem; padding: .2rem .8rem;}
        @media (max-width: 700px) {
          .block-container {padding: 5rem 1rem 2rem;}
          .day-photo img {height: 190px;}
          .stop-card {padding: .8rem;}
        }
        </style>""",
        unsafe_allow_html=True,
    )
