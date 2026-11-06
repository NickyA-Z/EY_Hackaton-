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
</style>
"""


def apply_global_styles():
    """Apply shared typography to the Streamlit frontend."""
    st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)
