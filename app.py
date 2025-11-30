from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
import os
import PyPDF2 as pdf
import json
import re
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configure API Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def get_gemini_response(input_text, jd):
    # Use gemini-1.5-flash (It is faster and smarter for this than 2.5 or pro)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
You are a Senior Technical Recruiter for a top-tier tech company. Evaluate how well this resume fits the job description.

JOB DESCRIPTION:
{jd}

RESUME:
{input_text}

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
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error generating content: {e}")
        return "{}"

def extract_text_from_pdf(file):
    try:
        reader = pdf.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or "" # Handle None return
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        jd = request.form.get('jd')
        files = request.files.getlist('resumes')

        if not jd or not files:
            return jsonify({'error': 'Please provide both JD and Resumes'}), 400

        results = []

        for file in files:
            if file.filename == '':
                continue
                
            print(f"Processing: {file.filename}...") # Debug print
            text = extract_text_from_pdf(file)
            
            if not text:
                print(f"Empty text for {file.filename}")
                continue

            # Get AI Analysis
            ai_response = get_gemini_response(text, jd)
            
            # --- ROBUST CLEANING (Fixes the break) ---
            # 1. Remove Markdown code blocks
            clean_json = ai_response.replace("```json", "").replace("```", "")
            
            # 2. Extract strictly the JSON part using Regex (in case AI adds extra text)
            # This looks for the content between the first { and the last }
            match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            if match:
                clean_json = match.group(0)
            
            try:
                data = json.loads(clean_json)
                
                # Standardize Name/Filename
                if "Name" not in data or data["Name"] == "Candidate Name":
                    data["Name"] = file.filename
                data['Filename'] = file.filename
                
                # Ensure Percentage is Integer
                match_pct = str(data.get('MatchPercentage', '0')).replace('%', '')
                if match_pct.isdigit():
                    data['MatchPercentage'] = int(match_pct)
                else:
                    data['MatchPercentage'] = 0
                
                results.append(data)
                
            except json.JSONDecodeError as e:
                print(f"JSON Error for {file.filename}: {e}")
                print(f"Bad JSON Content: {clean_json}") # See what went wrong
                results.append({
                    "Name": file.filename,
                    "MatchPercentage": 0,
                    "Summary": "Error parsing AI response. View Terminal for details.",
                    "GlobalMatch": "N/A"
                })

        # Sort by Score
        results.sort(key=lambda x: x.get('MatchPercentage', 0), reverse=True)

        return jsonify({'results': results})

    except Exception as e:
        print(f"Server Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)