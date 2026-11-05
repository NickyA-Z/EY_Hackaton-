"""Shared frontend typography styles."""

import streamlit as st


GLOBAL_STYLES = """
<style>@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&display=swap');

:root {
    --teamnl-blue: #00378A;
    --teamnl-blue-light: #3976BE;
    --teamnl-orange: #FF6600;
    --teamnl-white: #FFFFFF;
    --teamnl-black: #000000;
}

.stApp {
    font-family: 'Hanken Grotesk', sans-serif !important;
    background-color: var(--teamnl-white);
    color: var(--teamnl-black);
}

.stApp h1,
.stApp h2,
.stApp h3 {
    color: var(--teamnl-blue);
    font-family: 'Hanken Grotesk', sans-serif !important;
    font-weight: 700;
}

.stApp button[kind="primary"] {
    background-color: var(--teamnl-orange);
    color: var(--teamnl-white);
    border: none;
    font-weight: 700;
}

.stApp button[kind="primary"]:hover {
    background-color: var(--teamnl-blue);
    color: var(--teamnl-white);
}

.stApp button[kind="secondary"] {
    border-color: var(--teamnl-blue);
    color: var(--teamnl-blue);
}

/* Navigation floats: frozen at the top while the page scrolls (below Streamlit's toolbar).
   Sticky goes on Streamlit's wrapper: the keyed block's own parent is only as tall as the block. */
[data-testid="stLayoutWrapper"]:has(> .st-key-dashboard_header) {
    position: sticky;
    top: 3.75rem;
    z-index: 990;
}

.st-key-dashboard_header {
    background: var(--teamnl-white);
    box-shadow: 0 6px 16px rgba(0, 55, 138, 0.08);
}

/* Keep the two-level dashboard navigation compact and visually connected. */
.st-key-dashboard_header [data-testid="stVerticalBlock"] {
    gap: 0.65rem;
}

.st-key-dashboard_header button {
    min-height: 2.65rem;
}

.st-key-dashboard_header [data-testid="stPopover"] button {
    border-color: var(--teamnl-blue);
    color: var(--teamnl-blue);
    font-weight: 600;
}

.st-key-dashboard_header .header-divider {
    height: 1px;
    margin: 0.1rem 0 0.05rem;
    background: #E1E7EF;
}

.st-key-dashboard_header [data-testid="stSegmentedControl"] button {
    min-height: 2.45rem;
}

@media (max-width: 760px) {
    .st-key-dashboard_header button {
        min-height: 2.4rem;
    }
}
</style>
"""


def apply_global_styles():
    """Apply shared typography to the Streamlit frontend."""
    st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)
