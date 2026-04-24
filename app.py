from flask import Flask, render_template, request
from google import genai
import os
from dotenv import load_dotenv
import time

# Load API key
load_dotenv()

app = Flask(__name__)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Rate control (avoid multiple calls)
last_call_time = 0


def analyze_resume(resume, jd):
    global last_call_time

    # Prevent multiple rapid calls
    if time.time() - last_call_time < 5:
        return "⚠️ Please wait 5 seconds before trying again."

    last_call_time = time.time()

    prompt = f"""
    Analyze the resume against job description.

    Resume:
    {resume}

    Job Description:
    {jd}

    Give output clearly:

    Resume Skills:
    Job Skills:
    Missing Skills:
    Suggestions:
    """

    # Retry mechanism
    for attempt in range(3):
        try:
            print("🚀 API CALLED")

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )

            return response.text

        except Exception as e:
            print("ERROR:", e)

            if "429" in str(e):
                time.sleep(6)  # wait before retry
            else:
                return f"⚠️ Error: {str(e)}"

    return "⚠️ API busy. Please try after 1 minute."


@app.route("/", methods=["GET", "POST"])
def index():
    result = ""

    if request.method == "POST":
        resume = request.form.get("resume")
        jd = request.form.get("jd")

        if resume and jd:
            result = analyze_resume(resume, jd)
        else:
            result = "⚠️ Please enter both Resume and Job Description."

    return render_template("index.html", result=result)


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False)