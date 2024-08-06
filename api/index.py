from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import os
import google.generativeai as genai
import PyPDF2
from docx import Document
import io

app = Flask(__name__, template_folder='../templates')

# Configure Google AI
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_ai_response(prompt):
    model = genai.GenerativeModel('gemini-pro')
    response = model.generate_content(prompt)
    return response.text

def extract_text_from_file(file):
    filename = secure_filename(file.filename.lower())
    if filename.endswith('.pdf'):
        return extract_text_from_pdf(file)
    elif filename.endswith('.docx'):
        return extract_text_from_docx(file)
    elif filename.endswith('.txt'):
        return file.read().decode('utf-8')
    else:
        return ""

def extract_text_from_pdf(file):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file.read()))
    return "\n".join(page.extract_text() for page in pdf_reader.pages)

def extract_text_from_docx(file):
    doc = Document(io.BytesIO(file.read()))
    return "\n".join(para.text for para in doc.paragraphs)

@app.route('/')
def index():
    return render_template('interview.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'resume' not in request.files or 'jd' not in request.files:
        return jsonify({"error": "Both resume and job description are required"}), 400
    
    resume = request.files['resume']
    jd = request.files['jd']
    
    if not (resume.filename and jd.filename):
        return jsonify({"error": "Both files must have a name"}), 400

    if not (allowed_file(resume.filename) and allowed_file(jd.filename)):
        return jsonify({"error": "File type not allowed"}), 400

    resume_content = extract_text_from_file(resume)
    jd_content = extract_text_from_file(jd)
    
    prompt = f"""Based on the following resume:\n\n{resume_content}\n\nAnd this job description:\n\n{jd_content}\n\n
    Generate 6 relevant interview questions. The first question should always be 'Could you please introduce yourself?'
    For the remaining questions, focus on the candidate's experience, skills related to the job description, and behavioral questions.
    Format the output as a list of questions, one per line."""
    
    questions = get_ai_response(prompt).split('\n')
    
    return jsonify({"message": "Files processed successfully", "questions": questions})

@app.route('/start_interview', methods=['POST'])
def start_interview():
    questions = request.json.get('questions', [])
    if not questions:
        return jsonify({"error": "No questions provided"}), 400
    
    first_question = questions[0]
    question_number, question_text = first_question.split('. ', 1)
    return jsonify({
        "question_number": question_number,
        "question_text": question_text,
        "remaining_questions": questions[1:],
        "is_last_question": len(questions) == 1
    })

@app.route('/continue_interview', methods=['POST'])
def continue_interview():
    data = request.get_json()
    candidate_response = data.get('response')
    remaining_questions = data.get('remaining_questions', [])
    interview_history = data.get('history', '')
    
    interview_history += f"Candidate: {candidate_response}\n"
    
    response_prompt = f"""Based on the following interview history:

    {interview_history}

    Generate a brief, friendly response to the candidate's last answer. If the answer is good, include a compliment.
    Then, if there are remaining questions, ask the next question. Make the interaction feel natural and human-like.
    Keep the response concise."""

    ai_response = get_ai_response(response_prompt)
    
    if remaining_questions:
        next_question = remaining_questions[0]
        question_number, question_text = next_question.split('. ', 1)
        interview_history += f"Interviewer: {ai_response} {question_text}\n"
        return jsonify({
            "question_number": question_number,
            "question_text": question_text,
            "remaining_questions": remaining_questions[1:],
            "history": interview_history,
            "is_last_question": len(remaining_questions) == 1
        })
    else:
        closing_message = f"{ai_response} Thank you for your time. We'll be in touch regarding the next steps."
        interview_history += f"Interviewer: {closing_message}\n"
        return jsonify({
            "message": closing_message, 
            "remaining_questions": [],
            "history": interview_history,
            "is_last_question": False,
            "interview_completed": True
        })

@app.route('/evaluate', methods=['POST'])
def evaluate_interview():
    data = request.get_json()
    interview_history = data.get('history', '')
    unanswered_questions = data.get('unanswered_questions', 0)
    candidate_responses = data.get('candidate_responses', [])
    
    if unanswered_questions > 0:
        return jsonify({"error": f"The candidate has not answered {unanswered_questions} question(s). Please ensure all questions are answered before evaluation."}), 400
    
    evaluation_prompt = f"""Based on the following interview, provide a detailed and strict evaluation of the candidate's performance:

    {interview_history}

    Evaluate the candidate on the following aspects, with a focus on the quality and depth of their responses:
    1. Technical Skills (0-10)
    2. Communication Skills (0-10)
    3. Problem-solving Ability (0-10)
    4. Cultural Fit (0-10)
    5. Motivation and Enthusiasm (0-10)
    6. Leadership Potential (0-10)

    For each aspect, provide a rating out of 10 and a detailed explanation justifying the score. Be critical and highlight areas where the candidate could have provided better or more detailed responses.

    Candidate's responses to analyze:
    {" ".join(candidate_responses)}

    Based on these specific responses, provide a detailed critique of the quality and depth of the candidate's answers. Highlight any red flags or areas of concern.

    Conclude with an overall recommendation on whether to proceed with the candidate or not, and any additional comments or suggestions for the hiring team. Be honest and direct in your assessment.

    Evaluation:"""
    
    evaluation = get_ai_response(evaluation_prompt)
    return jsonify({"evaluation": evaluation})

@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify(error=str(e)), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return app.send_static_file("index.html")

# Vercel requires a 'handler' function
def handler(event, context):
    return app(event, context)