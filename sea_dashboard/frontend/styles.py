"""Shared frontend typography styles."""

import streamlit as st


GLOBAL_STYLES = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&display=swap');

body,
.stApp,
.stApp p,
.stApp label,
.stApp button,
.stApp input,
.stApp textarea,
.stApp select,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stWidgetLabel"] {
    font-family: 'Hanken Grotesk', sans-serif !important;
    font-weight: 400;
}

.stApp h1 {
    font-family: 'Hanken Grotesk', sans-serif !important;
    font-size: 44px !important;
    font-weight: 700 !important;
    line-height: 52px !important;
    color: #00378A !important;
    -webkit-font-smoothing: antialiased;
}

.stApp h2,
.stApp h3 {
    font-family: 'Hanken Grotesk', sans-serif !important;
    font-weight: 700 !important;
}
</style>
"""


def apply_global_styles():
    """Apply shared typography to the Streamlit frontend."""
    st.markdown(GLOBAL_STYLES, unsafe_allow_html=True)
