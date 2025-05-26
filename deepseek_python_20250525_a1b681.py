import os
import json
import csv
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import requests
from bs4 import BeautifulSoup
from openai import OpenAI  # Updated for v1.0+
import gspread
from google.oauth2.service_account import Credentials  # Updated auth
from datetime import datetime, timedelta
import schedule
from dotenv import load_dotenv
from flask import Flask, jsonify  # Added for Render deployment

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration - Now uses environment variables
CONFIG = {
    "job_keywords": ["Safety Engineer", "HSE Officer", "Oil & Gas jobs Pakistan"],
    "job_sites": {
        "Rozee.pk": "https://www.rozee.pk/search-jobs/?q={query}",
        "Indeed": "https://pk.indeed.com/jobs?q={query}",
        "LinkedIn": "https://www.linkedin.com/jobs/search/?keywords={query}"
    },
    "smtp": {
        "server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", 587)),
        "email": os.getenv("SMTP_EMAIL"),
        "password": os.getenv("SMTP_PASSWORD")
    },
    "openai_api_key": os.getenv("OPENAI_API_KEY"),
    "google_sheets_creds": "credentials.json",
    "base_resume": "base_resume.json",
    "base_cover_letter": "base_cover_letter.txt",
    "user_info": {
        "name": os.getenv("USER_NAME", "Your Name"),
        "phone": os.getenv("USER_PHONE", "03001234567"),
        "address": os.getenv("USER_ADDRESS", "Islamabad, Pakistan")
    }
}

# Initialize OpenAI client (v1.0+)
client = OpenAI(api_key=CONFIG["openai_api_key"])

# Initialize Google Sheets if credentials exist
if os.path.exists(CONFIG["google_sheets_creds"]):
    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(CONFIG["google_sheets_creds"], scopes=scope)
    gc = gspread.authorize(creds)
    try:
        sheet = gc.open("Job Applications").sheet1
    except:
        sheet = None
else:
    sheet = None

# Create required files if they don't exist
if not os.path.exists("applications"):
    os.makedirs("applications")

if not os.path.exists(CONFIG["base_resume"]):
    with open(CONFIG["base_resume"], 'w') as f:
        json.dump({
            "basics": {
                "name": CONFIG["user_info"]["name"],
                "email": CONFIG["smtp"]["email"],
                "phone": CONFIG["user_info"]["phone"],
                "address": CONFIG["user_info"]["address"]
            },
            "skills": ["Safety Management", "OSHA Compliance", "Risk Assessment"],
            "experience": [
                {
                    "title": "HSE Officer",
                    "company": "Example Company",
                    "duration": "2020-Present",
                    "description": "Implemented safety protocols and conducted risk assessments"
                }
            ]
        }, f, indent=2)

if not os.path.exists(CONFIG["base_cover_letter"]):
    with open(CONFIG["base_cover_letter"], 'w') as f:
        f.write(f"""Dear Hiring Manager,

I am excited to apply for the {{position}} position at {{company}}. With my background in {{skill}}, I believe I would be a valuable asset to your team.

Key qualifications:
- X years of experience in oil & gas safety
- Certified in {{certification}}
- Proven track record in {{achievement}}

Sincerely,
{CONFIG["user_info"]["name"]}""")

class JobScraper:
    # ... (keep all scraping methods exactly the same as in your original code)
    # Only changed the class name reference in the methods to use self.CONFIG

class DocumentGenerator:
    @staticmethod
    def generate_ats_resume(job_description):
        """Generate an ATS-optimized resume based on job description"""
        try:
            with open(CONFIG["base_resume"], 'r') as f:
                base_resume = json.load(f)
            
            prompt = f"""Optimize this resume for the following job description: 
            {job_description}
            
            Current Resume:
            {json.dumps(base_resume, indent=2)}
            
            Return the optimized resume in JSON format matching the original structure."""
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a professional resume writer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Error generating resume: {e}")
            return None

    @staticmethod
    def generate_cover_letter(job_title, company_name, job_description):
        """Generate a customized cover letter"""
        try:
            with open(CONFIG["base_cover_letter"], 'r') as f:
                template = f.read()
            
            prompt = f"""Write a cover letter for {job_title} at {company_name} using:
            Job Description: {job_description}
            Template: {template}
            Candidate Info: {CONFIG['user_info']}"""
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a cover letter writer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating cover letter: {e}")
            return None

    # ... (keep other DocumentGenerator methods the same)

class ApplicationManager:
    # ... (keep all methods exactly the same as in your original code)

class ReportGenerator:
    # ... (keep all methods exactly the same as in your original code)

@app.route('/')
def home():
    return "Oil & Gas Job Application Automation is Running!"

@app.route('/run', methods=['POST'])
def run_automation():
    try:
        main()
        return jsonify({"status": "success", "message": "Job automation completed"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def main():
    print("Starting job application automation...")
    scraper = JobScraper()
    jobs = scraper.scrape_all()
    
    for job in jobs:
        resume = DocumentGenerator.generate_ats_resume(job['description'])
        cover_letter = DocumentGenerator.generate_cover_letter(
            job['title'], job['company'], job['description'])
        
        if resume and cover_letter:
            resume_file, cover_letter_file = DocumentGenerator.save_documents(
                job, resume, cover_letter)
            
            if resume_file and cover_letter_file:
                if job['application_method'] == "email":
                    ApplicationManager.apply_via_email(job, resume_file, cover_letter_file)
                else:
                    ApplicationManager.handle_web_form(job, resume_file, cover_letter_file)
    
    ReportGenerator.generate_daily_report()

if __name__ == '__main__':
    # Run on port 10000 for Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
    
    # Schedule daily runs (will only work on always-on services)
    schedule.every().day.at("09:00").do(main)
    while True:
        schedule.run_pending()
        time.sleep(60)
