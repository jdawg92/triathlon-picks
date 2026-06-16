import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Triathlon Picks", layout="wide")

st.title("Triathlon Picks Dashboard")

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_SERVICE_KEY"]
supabase = create_client(url, key)

st.success("Supabase client created successfully.")

st.subheader("Database connection test")

try:
    result = supabase.table("athletes").select("*").limit(5).execute()
    st.success("Connected to Supabase and found the athletes table.")
    st.write(result.data)
except Exception as e:
    st.error("Could not read from Supabase.")
    st.exception(e)