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
</style>
"""


def apply_global_styles():
    """Apply shared typography to the Streamlit frontend."""
    st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)
