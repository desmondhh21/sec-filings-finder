import streamlit as st

st.set_page_config(page_title="Biz Filing Docs", layout="wide")

# Import the real app
import app

# Run it
if hasattr(app, "main"):
    app.main()
else:
    st.error("app.py does not have a main() function")
