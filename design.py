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
        .weather-card {min-height: 310px; border: 1px solid #E4E6ED; border-radius: 22px; padding: 1.7rem; background: linear-gradient(135deg,#EDF2F7,#FAFBFD); color: #323D52;}
        .weather-sun {background: linear-gradient(135deg,#F9EBCB,#FFFCF5); color: #74562B; border-color: #EDE1C5;}
        .weather-rain, .weather-fog {background: linear-gradient(135deg,#E3EDF0,#F5F8FA); color: #385D69;}
        .weather-snow {background: linear-gradient(135deg,#E9EEF9,#FCFDFF); color: #4D6385;}
        .overview-eyebrow {text-transform: uppercase; letter-spacing: .12em; font-size: .68rem; font-weight: 700; opacity: .8; margin-bottom: 1.1rem;}
        .weather-head {display: flex; align-items: center; gap: .8rem;}
        .weather-symbol {font-size: 2.7rem; line-height: 1.1;}
        .weather-condition {font-size: 1.1rem; font-weight: 650;}
        .weather-range {font-size: clamp(1.7rem,3.5vw,2.8rem); font-weight: 700; letter-spacing: -.04em; margin: .8rem 0; line-height: 1.2;}
        .weather-range span {font-size: 1rem; font-weight: 400; opacity: .7; margin: 0 .15rem;}
        .overview-note {font-size: .77rem; line-height: 1.6; opacity: .85; margin: .5rem 0 0;}
        .packing-card {background: linear-gradient(145deg,#F2EEF4,#FFFFFF); border-color: #E9E1EC; color: #68465F;}
        .packing-card h3 {font-size: 1.6rem; margin: 0 0 .7rem;}
        .packing-list {padding-left: 1.1rem; margin: 0; color: #5D5967; font-size: .86rem; line-height: 1.65;}
        .packing-list li {margin: .5rem 0; padding-left: .25rem;}
        .packing-list li::marker {color: #A58B9E;}
        .budget-overview {display: grid; grid-template-columns: minmax(260px,1fr) minmax(280px,1.15fr); gap: 2.4rem; align-items: center; padding: 2rem; background: #FFFFFF; border: 1px solid var(--trip-line); border-radius: 24px; margin: .3rem 0 1.5rem;}
        .budget-donut-wrap {display: flex; justify-content: center; padding: 1rem 0;}
        .budget-donut {width: min(100%,300px); aspect-ratio: 1; border-radius: 50%; display: grid; place-items: center; box-shadow: 0 8px 26px #272B3809;}
        .budget-donut-hole {width: 74%; height: 74%; border-radius: 50%; background: #FFFFFF; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;}
        .budget-donut-hole span, .budget-donut-hole small {font-size: .75rem; color: var(--trip-muted);}
        .budget-donut-hole strong {font-size: clamp(1.35rem,3vw,2.2rem); line-height: 1.6; letter-spacing: -.035em; color: var(--trip-ink); overflow-wrap: anywhere; max-width: 92%;}
        .budget-legend-row {display: flex; gap: .8rem; align-items: center; padding: .8rem 0; border-bottom: 1px solid #F0F1F5;}
        .budget-dot {width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0;}
        .budget-category {flex: 1; font-size: .88rem; font-weight: 600; color: #404451;}
        .budget-category small {display: block; color: var(--trip-muted); font-size: .72rem; font-weight: 400; margin-top: .2rem;}
        .budget-legend-row strong {font-size: 1rem; font-variant-numeric: tabular-nums; color: var(--trip-ink); white-space: nowrap;}
        .budget-balance {margin-top: 1rem; border-radius: 12px; padding: .8rem 1rem; background: #F3F6F5; color: #42695F; display: flex; justify-content: space-between; gap: 1rem; font-size: .88rem;}
        .budget-balance.over-target {color: #8A5546; background: #FAF1EC;}
        .expense-row {display: flex; align-items: center; gap: .9rem; padding: .9rem .2rem; border-bottom: 1px solid #EDEEF3;}
        .expense-row:last-child {border-bottom: 0;}
        .expense-icon {width: 38px; height: 38px; flex: 0 0 38px; border-radius: 12px; background: #F5F4F7; display: grid; place-items: center; font-size: 1.35rem;}
        .expense-description {flex: 1; min-width: 0;}
        .expense-name {font-size: .91rem; font-weight: 600; color: #383D4A; overflow-wrap: anywhere;}
        .expense-meta {display: flex; align-items: center; gap: .7rem; flex-wrap: wrap; color: var(--trip-muted); font-size: .74rem; margin-top: .35rem;}
        .cost-badge {display: inline-block; border-radius: 7px; padding: .15rem .5rem; font-size: .67rem; font-weight: 600;}
        .cost-badge.retrieved {color: #45685B; background: #EDF4EF;}
        .cost-badge.estimated {color: #856B3E; background: #F8F1E6;}
        .expense-amount {white-space: nowrap; font-size: 1.03rem; color: var(--trip-ink); font-variant-numeric: tabular-nums;}
        @media (max-width: 700px) {
          .budget-overview {grid-template-columns: minmax(0,1fr); gap: .5rem; padding: 1.2rem;}
          .budget-donut {max-width: 250px;}
          .weather-card {min-height: auto; padding: 1.3rem;}
          .expense-row {gap: .55rem;}
          .expense-icon {width: 28px; height: 32px; flex-basis: 28px; font-size: 1.1rem;}
          .expense-amount {font-size: .9rem;}
          .block-container {padding: 5rem 1rem 2rem;}
          h1 {font-size: 2.2rem !important;}
          .day-photo img {height: 180px;}
          .stop-card {padding: .85rem;}
          .travel-information {right: 10px; top: 100px;}
        }
        </style>""",
        unsafe_allow_html=True,
    )
