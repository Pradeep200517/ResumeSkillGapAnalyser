from flask import Flask, render_template, request, flash, redirect, url_for
from google import genai
import os
from dotenv import load_dotenv
import time
from werkzeug.utils import secure_filename
import PyPDF2
import docx
from werkzeug.exceptions import RequestEntityTooLarge

# Load API key
load_dotenv()

app = Flask(__name__)
app.secret_key = "resume_analyzer_secret_key"

# File upload configuration
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'doc'}

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Rate control (avoid multiple calls)
last_call_time = 0

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(file_path):
    """Extract text from uploaded file (PDF, DOCX, or TXT)"""
    try:
        print(f"Extracting text from: {file_path}")
        
        if file_path.endswith('.pdf'):
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page_num, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    text += page_text
                    print(f"Extracted from page {page_num + 1}: {len(page_text)} characters")
                print(f"Total PDF text extracted: {len(text)} characters")
                return text
        
        elif file_path.endswith(('.docx', '.doc')):
            doc = docx.Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            print(f"Total DOCX text extracted: {len(text)} characters")
            return text
        
        elif file_path.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
                print(f"Total TXT text extracted: {len(text)} characters")
                return text
        
        print(f"Unsupported file type: {file_path}")
        return ""
    except Exception as e:
        print(f"Error extracting text from {file_path}: {e}")
        return ""

def analyze_resume(resume, jd):
    global last_call_time

    # Prevent multiple rapid calls
    if time.time() - last_call_time < 5:
        return {"error": "⚠️ Please wait 5 seconds before trying again."}

    last_call_time = time.time()

    prompt = f"""
    Analyze the following resume against the job description.
    
    Resume:
    {resume}

    Job Description:
    {jd}

    Please provide the analysis in the following structured format exactly:
    
    [MATCH_SCORE]: (a single number from 0 to 100 representing the percentage match)
    
    [RESUME_SKILLS]: (comma-separated list of skills found in the resume)
    
    [JOB_SKILLS]: (comma-separated list of skills required by the job)
    
    [MISSING_SKILLS]: (comma-separated list of skills missing from the resume but required by the job)
    
    [RESUME_OPTIMIZATION]: (3-5 specific bullet points on how to improve the resume content or structure for this specific job)
    
    [LEARNING_PATH]: (3-5 specific learning resources or topics for the missing skills)
    
    [GENERAL_SUGGESTIONS]: (overall advice for the candidate)
    """

    # Retry mechanism
    for attempt in range(3):
        try:
            print("🚀 API CALLED")

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            text = response.text
            
            # Simple parsing of structured output
            data = {}
            sections = [
                "[MATCH_SCORE]", "[RESUME_SKILLS]", "[JOB_SKILLS]", 
                "[MISSING_SKILLS]", "[RESUME_OPTIMIZATION]", 
                "[LEARNING_PATH]", "[GENERAL_SUGGESTIONS]"
            ]
            
            for i in range(len(sections)):
                start = text.find(sections[i]) + len(sections[i])
                end = text.find(sections[i+1]) if i < len(sections)-1 else len(text)
                if start > len(sections[i]):
                    data[sections[i].strip("[]")] = text[start:end].strip(": \n")
            
            return data

        except Exception as e:
            print("ERROR:", e)

            if "429" in str(e):
                time.sleep(6)  # wait before retry
            else:
                return {"error": f"⚠️ Error: {str(e)}"}

    return {"error": "⚠️ API busy. Please try after 1 minute."}


@app.route("/", methods=["GET", "POST"])
def index():
    result = ""
    resume_text = ""
    jd_text = ""

    if request.method == "POST":
        try:
            print("=== POST REQUEST RECEIVED ===")
            
            # Handle file uploads
            resume_file = request.files.get('resume_file')
            jd_file = request.files.get('jd_file')
            
            print(f"Resume file: {resume_file}")
            print(f"JD file: {jd_file}")
            print(f"All files: {list(request.files.keys())}")
            
            if resume_file:
                print(f"Resume filename: '{resume_file.filename}'")
                print(f"Resume file object: {resume_file}")
            if jd_file:
                print(f"JD filename: '{jd_file.filename}'")
                print(f"JD file object: {jd_file}")
            
            # Get text inputs
            resume_text = request.form.get("resume", "")
            jd_text = request.form.get("jd", "")
            
            print(f"Pasted resume text length: {len(resume_text)}")
            print(f"Pasted JD text length: {len(jd_text)}")
            
            # Extract text from resume file if uploaded
            if resume_file and resume_file.filename != '':
                print(f"Processing resume file: {resume_file.filename}")
                if allowed_file(resume_file.filename):
                    filename = secure_filename(resume_file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    print(f"Saving resume to: {file_path}")
                    resume_file.save(file_path)
                    resume_text = extract_text_from_file(file_path)
                    print(f"Extracted resume text length: {len(resume_text)}")
                    os.remove(file_path)  # Clean up uploaded file
                else:
                    flash('⚠️ Invalid resume file format. Please upload PDF, DOCX, DOC, or TXT files.')
                    return render_template("index.html", result="", resume_text=resume_text, jd_text=jd_text)
            
            # Extract text from job description file if uploaded
            if jd_file and jd_file.filename != '':
                print(f"Processing JD file: {jd_file.filename}")
                if allowed_file(jd_file.filename):
                    filename = secure_filename(jd_file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    print(f"Saving JD to: {file_path}")
                    jd_file.save(file_path)
                    jd_text = extract_text_from_file(file_path)
                    print(f"Extracted JD text length: {len(jd_text)}")
                    os.remove(file_path)  # Clean up uploaded file
                else:
                    flash('⚠️ Invalid job description file format. Please upload PDF, DOCX, DOC, or TXT files.')
                    return render_template("index.html", result="", resume_text=resume_text, jd_text=jd_text)

            print(f"Final resume text length: {len(resume_text.strip())}")
            print(f"Final JD text length: {len(jd_text.strip())}")
            
            # Validate we have content for both
            if resume_text.strip() and jd_text.strip():
                print("Both texts have content, proceeding with analysis")
                result = analyze_resume(resume_text, jd_text)
            else:
                print("Missing content - one or both texts are empty")
                result = "⚠️ Please provide both Resume and Job Description content."
                
        except RequestEntityTooLarge:
            flash('⚠️ File too large. Please upload files smaller than 16MB.')
        except Exception as e:
            flash(f'⚠️ Error processing files: {str(e)}')

    return render_template("index.html", result=result, resume_text=resume_text, jd_text=jd_text)


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False)