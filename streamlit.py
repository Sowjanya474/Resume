# streamlit_app.py
import streamlit as st
import os
import io
import json
import re
import html
from dotenv import load_dotenv

# AI client
import google.generativeai as genai

# File handling
import PyPDF2
from docx import Document  # python-docx import pattern

load_dotenv()

# Configure Gemini / Generative API
API_KEY = os.getenv("GOOGLE_API_KEY") or (st.secrets.get("GOOGLE_API_KEY") if hasattr(st, "secrets") else None)
if not API_KEY:
    st.warning("No GOOGLE_API_KEY found in environment variables or Streamlit secrets. Set GOOGLE_API_KEY before running.")
else:
    genai.configure(api_key=API_KEY)

# --- Helpers -----------------------------------------------------------------

def file_key(name, size, last_modified):
    return f"{name}::{size}::{last_modified}"

def extract_text_from_pdf_bytes(bio: io.BytesIO):
    try:
        reader = PyPDF2.PdfReader(bio)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        try:
            st.write(f"PDF extraction error: {e}")
        except Exception:
            pass
        return ""

def extract_text_from_docx_bytes(bio: io.BytesIO):
    try:
        bio.seek(0)
        document = Document(bio)
        paragraphs = [p.text for p in document.paragraphs]
        return "\n".join(paragraphs)
    except Exception as e:
        try:
            st.write(f"DOCX extraction error: {e}")
        except Exception:
            pass
        return ""

def extract_text_from_txt_bytes(bio: io.BytesIO):
    try:
        bio.seek(0)
        return bio.read().decode(errors="ignore")
    except Exception as e:
        try:
            st.write(f"TXT extraction error: {e}")
        except Exception:
            pass
        return ""

def safe_int_percent(val):
    if val is None:
        return 0
    s = str(val).strip().replace("%", "")
    try:
        f = float(s)
        return int(round(f))
    except:
        return 0

def clean_ai_json(ai_text: str):
    if not ai_text:
        return "{}"
    cleaned = ai_text.replace("```json", "").replace("```", "")
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        return m.group(0)
    return cleaned

def build_prompt(resume_text: str, jd_text: str):
    return f"""
You are a Senior Technical Recruiter for a top-tier tech company. Evaluate how well this resume fits the job description.

JOB DESCRIPTION:
{jd_text}

RESUME:
{resume_text}

INSTRUCTIONS:
1. Score the resume on a 0-100 scale based on actual skill alignment.
2. Do not inflate scores.
3. "GlobalMatch" should reflect market position based on typical applicants.
   Use exactly one: "Top 5%", "Top 20%", "Average", "Below Average".
4. "MarketTier" must be one of:
   "Tier 1 (Elite)", "Tier 2 (Strong)", "Tier 3 (Average)", "Tier 4 (Weak)".
5. Extract keywords from the JD and match them strictly. No guessing.
6. Identify missing skills that materially weaken the candidate.

OUTPUT:
Return ONLY valid JSON. No commentary.

{{
  "Name": "Candidate Name",
  "MatchPercentage": 0,
  "GlobalMatch": "",
  "MarketTier": "",
  "MatchedKeywords": [],
  "MissingKeywords": [],
  "Summary": ""
}}
"""

def get_gemini_response(resume_text: str, jd_text: str, model_name: str = "gemini-2.5-flash"):
    if not API_KEY:
        return "{}"
    try:
        model = genai.GenerativeModel(model_name)
        prompt = build_prompt(resume_text, jd_text)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        try:
            st.write(f"AI request failed: {e}")
        except Exception:
            pass
        return "{}"

# --- Streamlit UI -----------------------------------------------------------

st.set_page_config(page_title="Resume Ranker (Streamlit)", layout="centered", initial_sidebar_state="collapsed")

st.markdown("<h1 style='text-align:center'>Resume Ranker</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;color:#6b7280'>Rank uploaded resumes against a job description using Gemini AI</p>", unsafe_allow_html=True)
st.write("---")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Job description")
    jd = st.text_area("Paste the job description here", height=240, placeholder="Paste the job description here...")
    st.caption("Supports PDF, DOCX, TXT. Max 10MB per file.")

with col2:
    st.subheader("Upload resumes")
    uploaded_files = st.file_uploader("Upload resumes (PDF, DOCX, TXT). Multiple files allowed.", accept_multiple_files=True, type=["pdf","docx","txt","doc"])
    if uploaded_files:
        st.write(f"Files selected: {len(uploaded_files)}")
        for u in uploaded_files:
            st.write(f"- {u.name} ({round(u.size / 1024, 1)} KB)")
    else:
        st.write("No files selected")

st.write("---")

run_btn = st.button("Rank Resumes")

# Handle run
if run_btn:
    if not uploaded_files:
        st.error("Select at least one resume before ranking.")
    else:
        if not jd or not jd.strip():
            st.warning("No job description provided. Continuing without JD — results will be based only on the resume text.")

        results = []
        max_size = 10 * 1024 * 1024  # 10MB

        with st.spinner("Processing Resume..."):
            for uploaded in uploaded_files:
                name = uploaded.name
                size = uploaded.size
                if size > max_size:
                    st.warning(f'"{name}" skipped: exceeds 10MB.')
                    continue

                try:
                    uploaded.seek(0)
                except Exception:
                    pass
                bio = io.BytesIO(uploaded.read())
                text = ""
                lower = name.lower()
                if lower.endswith(".pdf"):
                    bio.seek(0)
                    text = extract_text_from_pdf_bytes(bio)
                elif lower.endswith(".docx"):
                    bio.seek(0)
                    text = extract_text_from_docx_bytes(bio)
                elif lower.endswith(".txt"):
                    bio.seek(0)
                    text = extract_text_from_txt_bytes(bio)
                elif lower.endswith(".doc"):
                    bio.seek(0)
                    text = extract_text_from_docx_bytes(bio)
                    if not text:
                        st.warning(f"Could not parse '{name}' (.doc). Convert to .docx or PDF for better results.")
                else:
                    st.warning(f"Unsupported file type for '{name}'. Skipping.")
                    continue

                if not text or text.strip() == "":
                    st.warning(f"No extractable text for '{name}'. Skipping.")
                    continue

                ai_raw = get_gemini_response(text, jd)
                cleaned = clean_ai_json(ai_raw)

                try:
                    parsed = json.loads(cleaned)
                except json.JSONDecodeError:
                    st.error(f"AI returned invalid JSON for '{name}'. Placing placeholder result. See raw output below.")
                    st.code(ai_raw[:2000])
                    parsed = {
                        "Name": name,
                        "MatchPercentage": 0,
                        "GlobalMatch": "N/A",
                        "MarketTier": "",
                        "MatchedKeywords": [],
                        "MissingKeywords": [],
                        "Summary": "Error parsing AI response."
                    }

                if parsed.get("Name") in (None, "", "Candidate Name"):
                    parsed["Name"] = name
                parsed["Filename"] = name
                parsed["MatchPercentage"] = safe_int_percent(parsed.get("MatchPercentage", 0))
                parsed.setdefault("GlobalMatch", parsed.get("GlobalMatch", "N/A"))
                parsed.setdefault("MarketTier", parsed.get("MarketTier", ""))
                parsed.setdefault("MatchedKeywords", parsed.get("MatchedKeywords", []))
                parsed.setdefault("MissingKeywords", parsed.get("MissingKeywords", []))
                parsed.setdefault("Summary", parsed.get("Summary", ""))

                results.append(parsed)

        if not results:
            st.info("No results to display (all files skipped or failed).")
            st.stop()

        # sort descending by MatchPercentage
        results.sort(key=lambda x: x.get("MatchPercentage", 0), reverse=True)

        # Display results (moved inside run_btn handler)
        st.markdown("### Ranking Results")
        for r in results:
            pct = r.get("MatchPercentage", 0)
            if pct >= 75:
                score_tag = f"<span style='background:#d4f7d2;color:#1c6a2f;padding:6px 10px;border-radius:8px;font-weight:700'>{pct}% Match</span>"
            elif pct >= 50:
                score_tag = f"<span style='background:#fff3cc;color:#7a5f04;padding:6px 10px;border-radius:8px;font-weight:700'>{pct}% Match</span>"
            else:
                score_tag = f"<span style='background:#ffdede;color:#8a2525;padding:6px 10px;border-radius:8px;font-weight:700'>{pct}% Match</span>"

            name_html = html.escape(r.get("Name", "Candidate"))
            market_tier_html = html.escape(r.get("MarketTier") or "Unranked")
            global_match_html = html.escape(r.get("GlobalMatch") or "N/A")
            summary_html = html.escape(r.get("Summary") or "No summary available")

            if r.get("MissingKeywords"):
                missing_html = "".join([
                    f"<span style='display:inline-block;padding:4px 10px;border-radius:999px;background:#fff4e6;color:#7a4a00;margin-right:6px;margin-top:6px;font-size:13px'>{html.escape(x)}</span>"
                    for x in r.get("MissingKeywords")
                ])
            else:
                missing_html = "<span style='color:#16a34a;font-weight:600'>None detected</span>"

            st.markdown(
                f"""
                <div style="border:1px solid #eef2f6;border-radius:10px;padding:12px;margin-bottom:12px">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start">
                    <div>
                      <div style="font-size:16px;font-weight:700;color:#0f1724">{name_html}</div>
                      <div style="margin-top:6px">
                        <span style="display:inline-block;background:#1768e8;color:white;padding:6px 10px;border-radius:6px;font-weight:600;font-size:12px">{market_tier_html}</span>
                        <span style="color:#6b7280;font-size:13px;margin-left:8px">Global Standing: <strong>{global_match_html}</strong></span>
                      </div>
                    </div>
                    <div style="text-align:center">{score_tag}</div>
                  </div>

                  <hr style="margin:12px 0;border-color:#eef2f6">

                  <div style="font-size:14px;color:#334155;margin-bottom:8px"><strong>Summary</strong>
                    <div style="color:#6b7280;margin-top:6px">{summary_html}</div>
                  </div>

                  <div><strong>Missing Critical Skills</strong>
                    <div style="margin-top:8px">{missing_html}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True
            )
