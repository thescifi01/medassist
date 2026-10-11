import streamlit as st
from PIL import Image

from pipeline import analyze
from report import DISCLAIMER

st.set_page_config(page_title="Multimodal Medical Assistant", page_icon="🩻", layout="wide")
st.title("🩻 Multimodal Medical Assistant")
st.warning(DISCLAIMER)

left, right = st.columns(2)
with left:
    file = st.file_uploader("Chest X-ray (PNG/JPG)", type=["png", "jpg", "jpeg"])
    symptoms = st.text_area("Symptoms (optional)", placeholder="e.g. cough for 2 weeks, fever, chest pain")
    run = st.button("Analyze", type="primary", disabled=file is None)

if run and file:
    img = Image.open(file)
    with st.spinner("Analyzing..."):
        out = analyze(img, symptoms)
    with left:
        st.image(img, caption="Uploaded X-ray", use_container_width=True)
    with right:
        st.subheader(f"Grad-CAM: where the model looked ({out['heatmap_label']})")
        st.image(out["heatmap"], use_container_width=True)
        st.subheader("Top findings")
        for name, p in out["findings"]:
            st.progress(min(max(p, 0.0), 1.0), text=f"{name}: {p:.0%}")
        st.subheader("Draft report")
        st.markdown(out["report"])
