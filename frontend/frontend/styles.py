"""Shared frontend typography styles."""

import streamlit as st


GLOBAL_STYLES = """
<style>@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&display=swap');

:root {
    --brand-blue: #00378A;
    --brand-blue-light: #3976BE;
    --brand-orange: #FF6600;
    --brand-white: #FFFFFF;
    --brand-black: #000000;
}

.stApp {
    font-family: 'Hanken Grotesk', sans-serif !important;
    background-color: var(--brand-white);
    color: var(--brand-black);
}

.stApp h1,
.stApp h2,
.stApp h3 {
    color: var(--brand-blue);
    font-family: 'Hanken Grotesk', sans-serif !important;
    font-weight: 700;
}

.stApp button[kind="primary"] {
    background-color: var(--brand-orange);
    color: var(--brand-white);
    border: none;
    font-weight: 700;
}

.stApp button[kind="primary"]:hover {
    background-color: var(--brand-blue);
    color: var(--brand-white);
}

.stApp button[kind="secondary"] {
    border-color: var(--brand-blue);
    color: var(--brand-blue);
}

/* Keep the two-level dashboard navigation compact and visually connected. */
.st-key-dashboard_header [data-testid="stVerticalBlock"] {
    gap: 0.65rem;
}

.st-key-dashboard_header button {
    min-height: 2.65rem;
}

.st-key-dashboard_header [data-testid="stPopover"] button {
    border-color: var(--brand-blue);
    color: var(--brand-blue);
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
