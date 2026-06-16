import streamlit as st

st.set_page_config(page_title="Triathlon Picks", layout="wide")

st.title("Triathlon Picks Dashboard")
st.success("Streamlit is running correctly.")

st.write("Next step: connect Supabase and build the scoring dashboard.")

st.divider()

st.subheader("Connection Test")

try:
    from supabase import create_client
    st.success("Supabase package imported successfully.")

    has_url = "SUPABASE_URL" in st.secrets
    has_key = "SUPABASE_SERVICE_KEY" in st.secrets

    if not has_url or not has_key:
        st.warning("Supabase secrets are not added yet.")
        st.write("Add SUPABASE_URL and SUPABASE_SERVICE_KEY in Streamlit app settings.")
    else:
        supabase = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_SERVICE_KEY"]
        )
        st.success("Supabase client created successfully.")

except Exception as e:
    st.error("Supabase connection test failed.")
    st.exception(e)