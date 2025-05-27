import os
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import openai
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import sqlite3
import json
import logging
from datetime import datetime
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    # Job search settings
    SEARCH_KEYWORDS = ["Safety Engineer", "HSE Officer", "Oil & Gas jobs Pakistan"]
    TARGET_PLATFORMS = ["rozee", "linkedin", "indeed"]
    
    # OpenAI settings
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    RESUME_TEMPLATE_PATH = "storage/resumes/base_resume.txt"
    COVER_LETTER_TEMPLATE_PATH = "storage/cover_letters/base_cover_letter.txt"
    
    # Email settings
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = os.getenv("SMTP_PORT", 587)
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    
    # Database settings
    DATABASE_FILE = "storage/applications.db"

# Initialize Flask app
app = Flask(__name__)

# Ensure storage directories exist
os.makedirs("storage/resumes", exist_ok=True)
os.makedirs("storage/cover_letters", exist_ok=True)
os.makedirs("storage/pending_applications", exist_ok=True)

# Initialize database
def init_db():
    conn = sqlite3.connect(Config.DATABASE_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS applications
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  job_title TEXT,
                  company TEXT,
                  platform TEXT,
                  application_method TEXT,
                  status TEXT,
                  date_applied TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# Job Scraping Functions
def scrape_rozee(keywords):
    """Scrape job listings from Rozee.pk"""
    jobs = []
    ua = UserAgent()
    
    for keyword in keywords:
        try:
            url = f"https://www.rozee.pk/job/jsearch/q/{keyword.replace(' ', '+')}"
            response = requests.get(url, headers={'User-Agent': ua.random})
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            job_listings = soup.find_all('div', class_='job-listing')
            
            for job in job_listings:
                try:
                    title = job.find('h2').text.strip()
                    company = job.find('div', class_='company').text.strip()
                    location = job.find('div', class_='location').text.strip()
                    description = job.find('div', class_='description').text.strip()
                    apply_url = job.find('a', class_='apply-btn')['href']
                    
                    jobs.append({
                        'title': title,
                        'company': company,
                        'location': location,
                        'description': description,
                        'apply_url': apply_url,
                        'platform': 'rozee',
                        'application_method': 'web_form'
                    })
                except Exception as e:
                    logger.error(f"Error parsing job on Rozee: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error scraping Rozee: {str(e)}")
            continue
    
    return jobs

def scrape_linkedin(keywords):
    """Scrape job listings from LinkedIn (simplified example)"""
    jobs = []
    # Note: LinkedIn scraping is complex and may require API or RSS feeds
    # This is a simplified placeholder
    logger.warning("LinkedIn scraping requires proper API integration")
    return jobs

def scrape_indeed(keywords):
    """Scrape job listings from Indeed"""
    jobs = []
    ua = UserAgent()
    
    for keyword in keywords:
        try:
            url = f"https://pk.indeed.com/jobs?q={keyword.replace(' ', '+')}"
            response = requests.get(url, headers={'User-Agent': ua.random})
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            job_listings = soup.find_all('div', class_='job_seen_beacon')
            
            for job in job_listings:
                try:
                    title = job.find('h2').text.strip()
                    company = job.find('span', class_='companyName').text.strip()
                    location = job.find('div', class_='companyLocation').text.strip()
                    description = job.find('div', class_='job-snippet').text.strip()
                    apply_url = f"https://pk.indeed.com{job.find('a')['href']}"
                    
                    jobs.append({
                        'title': title,
                        'company': company,
                        'location': location,
                        'description': description,
                        'apply_url': apply_url,
                        'platform': 'indeed',
                        'application_method': 'web_form'
                    })
                except Exception as e:
                    logger.error(f"Error parsing job on Indeed: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error scraping Indeed: {str(e)}")
            continue
    
    return jobs

def scrape_all_jobs():
    """Scrape jobs from all platforms"""
    jobs = []
    
    if 'rozee' in Config.TARGET_PLATFORMS:
        jobs.extend(scrape_rozee(Config.SEARCH_KEYWORDS))
    
    if 'linkedin' in Config.TARGET_PLATFORMS:
        jobs.extend(scrape_linkedin(Config.SEARCH_KEYWORDS))
    
    if 'indeed' in Config.TARGET_PLATFORMS:
        jobs.extend(scrape_indeed(Config.SEARCH_KEYWORDS))
    
    return jobs

# Document Generation
class DocumentGenerator:
    def __init__(self):
        openai.api_key = Config.OPENAI_API_KEY
        
    def generate_ats_resume(self, base_resume, job_description):
        """Generate an ATS-optimized resume"""
        try:
            prompt = f"""Based on this base resume and job description, create an ATS-optimized resume.
            
            Base Resume:
            {base_resume}
            
            Job Description:
            {job_description}
            
            Modify to highlight relevant skills and include keywords from the job description.
            Return only the optimized resume content."""
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a professional resume writer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            return response.choices[0].message['content']
        except Exception as e:
            logger.error(f"Error generating resume: {str(e)}")
            raise

    def generate_cover_letter(self, base_cover, job_description, company):
        """Generate a customized cover letter"""
        try:
            prompt = f"""Create a customized cover letter for {company}.
            
            Base Cover Letter:
            {base_cover}
            
            Job Description:
            {job_description}
            
            Address to hiring manager, highlight relevant skills, and show enthusiasm.
            Return only the cover letter content."""
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a professional cover letter writer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            return response.choices[0].message['content']
        except Exception as e:
            logger.error(f"Error generating cover letter: {str(e)}")
            raise

# Email Service
class EmailService:
    def send_email(self, to, subject, body, attachments=None):
        """Send email with attachments"""
        try:
            msg = MIMEMultipart()
            msg['From'] = Config.EMAIL_ADDRESS
            msg['To'] = to
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            if attachments:
                for file_path in attachments:
                    with open(file_path, 'rb') as f:
                        part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
                        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
                        msg.attach(part)
            
            with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
                server.starttls()
                server.login(Config.EMAIL_ADDRESS, Config.EMAIL_PASSWORD)
                server.send_message(msg)
            
            logger.info(f"Email sent to {to}")
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            raise

# Tracking Service
class TrackingService:
    def record_application(self, job_title, company, platform, application_method, status):
        """Record application in database"""
        try:
            conn = sqlite3.connect(Config.DATABASE_FILE)
            c = conn.cursor()
            c.execute('''INSERT INTO applications 
                         (job_title, company, platform, application_method, status)
                         VALUES (?, ?, ?, ?, ?)''',
                      (job_title, company, platform, application_method, status))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error recording application: {str(e)}")

    def generate_daily_report(self):
        """Generate daily application report"""
        try:
            conn = sqlite3.connect(Config.DATABASE_FILE)
            c = conn.cursor()
            
            # Get today's applications
            c.execute('''SELECT job_title, company, platform, status 
                         FROM applications 
                         WHERE date(date_applied) = date('now')''')
            applications = c.fetchall()
            
            # Count stats
            total_applications = len(applications)
            submitted = len([app for app in applications if app[3] == 'submitted'])
            pending = len([app for app in applications if app[3] == 'pending'])
            failed = len([app for app in applications if app[3] == 'failed'])
            
            # Format report
            report = {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'total_applications': total_applications,
                'submitted': submitted,
                'pending': pending,
                'failed': failed,
                'applications': [{'job': app[0], 'company': app[1], 'platform': app[2], 'status': app[3]} 
                               for app in applications]
            }
            
            conn.close()
            return report
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            return None

# Application Service
class ApplicationService:
    def __init__(self):
        self.document_generator = DocumentGenerator()
        self.email_service = EmailService()
        self.tracking_service = TrackingService()
        
    def process_job_application(self, job):
        """Process a single job application"""
        try:
            # Generate documents
            with open(Config.RESUME_TEMPLATE_PATH, 'r') as f:
                base_resume = f.read()
            with open(Config.COVER_LETTER_TEMPLATE_PATH, 'r') as f:
                base_cover = f.read()
            
            ats_resume = self.document_generator.generate_ats_resume(base_resume, job['description'])
            cover_letter = self.document_generator.generate_cover_letter(base_cover, job['description'], job['company'])
            
            # Save temporary files
            resume_path = f"storage/resumes/generated_{job['title'].replace(' ', '_')}.txt"
            cover_path = f"storage/cover_letters/generated_{job['title'].replace(' ', '_')}.txt"
            
            with open(resume_path, 'w') as f:
                f.write(ats_resume)
            with open(cover_path, 'w') as f:
                f.write(cover_letter)
            
            # Handle application
            if job['application_method'] == 'email':
                self._handle_email_application(job, resume_path, cover_path)
                status = 'submitted'
            else:
                self._handle_web_form_application(job, resume_path, cover_path)
                status = 'pending'
            
            # Track application
            self.tracking_service.record_application(
                job['title'], job['company'], job['platform'], job['application_method'], status)
            
            # Clean up
            os.remove(resume_path)
            os.remove(cover_path)
            
        except Exception as e:
            logger.error(f"Error processing application: {str(e)}")
            self.tracking_service.record_application(
                job['title'], job['company'], job['platform'], job['application_method'], 'failed')
    
    def _handle_email_application(self, job, resume_path, cover_path):
        """Handle email-based application"""
        subject = f"Application for {job['title']} Position"
        body = f"""Dear Hiring Manager,
        
        Please find attached my application for the {job['title']} position at {job['company']}.
        
        I believe my skills and experience align well with this role.
        
        Thank you for your consideration.
        
        Best regards,
        [Your Name]"""
        
        self.email_service.send_email(
            to=job.get('application_email', Config.EMAIL_ADDRESS),
            subject=subject,
            body=body,
            attachments=[resume_path, cover_path]
        )
    
    def _handle_web_form_application(self, job, resume_path, cover_path):
        """Handle web form application by saving data for manual submission"""
        application_data = {
            'job_title': job['title'],
            'company': job['company'],
            'apply_url': job['apply_url'],
            'resume_content': open(resume_path, 'r').read(),
            'cover_letter_content': open(cover_path, 'r').read()
        }
        
        output_path = f"storage/pending_applications/{job['title'].replace(' ', '_')}_{job['company'].replace(' ', '_')}.json"
        with open(output_path, 'w') as f:
            json.dump(application_data, f)
        
        logger.info(f"Manual application required. Data saved to {output_path}")

# Scheduled Tasks
def scheduled_job_search():
    """Run daily job search and processing"""
    try:
        logger.info("Starting daily job search...")
        new_jobs = scrape_all_jobs()
        app_service = ApplicationService()
        
        for job in new_jobs:
            app_service.process_job_application(job)
        
        logger.info(f"Processed {len(new_jobs)} new jobs")
    except Exception as e:
        logger.error(f"Error in job search: {str(e)}")

def scheduled_daily_report():
    """Generate and send daily report"""
    try:
        logger.info("Generating daily report...")
        tracking_service = TrackingService()
        report = tracking_service.generate_daily_report()
        
        if report:
            email_service = EmailService()
            subject = f"Daily Job Application Report - {report['date']}"
            body = f"""Daily Application Report:
            
            Total Applications: {report['total_applications']}
            Submitted: {report['submitted']}
            Pending: {report['pending']}
            Failed: {report['failed']}
            
            Details:
            {json.dumps(report['applications'], indent=2)}"""
            
            email_service.send_email(
                to=Config.EMAIL_ADDRESS,
                subject=subject,
                body=body
            )
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")

# Flask Routes
@app.route('/')
def health_check():
    return jsonify({"status": "healthy", "message": "Oil & Gas Job Automation Tool"})

@app.route('/run-now')
def run_now():
    """Endpoint to manually trigger job search"""
    scheduled_job_search()
    return jsonify({"status": "success", "message": "Job search completed"})

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_job_search, 'cron', hour=8, minute=0)  # Run daily at 8 AM
scheduler.add_job(scheduled_daily_report, 'cron', hour=20, minute=0)  # Run daily at 8 PM
scheduler.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
