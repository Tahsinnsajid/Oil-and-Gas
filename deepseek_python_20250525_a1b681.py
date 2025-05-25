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
import openai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import schedule

# Configuration
CONFIG = {
    "job_keywords": ["Safety Engineer", "HSE Officer", "Oil & Gas jobs Pakistan"],
    "job_sites": {
        "Rozee.pk": "https://www.rozee.pk/search-jobs/?q={query}",
        "Indeed": "https://pk.indeed.com/jobs?q={query}",
        "LinkedIn": "https://www.linkedin.com/jobs/search/?keywords={query}"
    },
    "smtp": {
        "server": "smtp.gmail.com",
        "port": 587,
        "email": "your.email@gmail.com",
        "password": "your_app_password"
    },
    "openai_api_key": "your_openai_api_key",
    "google_sheets_creds": "credentials.json",
    "base_resume": "base_resume.json",
    "base_cover_letter": "base_cover_letter.txt",
    "user_info": {
        "name": "Your Name",
        "phone": "03001234567",
        "address": "Islamabad, Pakistan"
    }
}

# Initialize APIs
openai.api_key = CONFIG["openai_api_key"]

# Initialize Google Sheets if credentials exist
if os.path.exists(CONFIG["google_sheets_creds"]):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CONFIG["google_sheets_creds"], scope)
    gc = gspread.authorize(creds)
    sheet = gc.open("Job Applications").sheet1
else:
    sheet = None

class JobScraper:
    def __init__(self):
        self.jobs = []
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def scrape_rozee(self, query):
        url = CONFIG["job_sites"]["Rozee.pk"].format(query=query.replace(" ", "+"))
        try:
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Rozee.pk specific parsing - adjust selectors as needed
            listings = soup.find_all('div', class_='job-listing')
            
            for job in listings:
                title = job.find('h2').text.strip()
                company = job.find('div', class_='company-name').text.strip()
                location = job.find('div', class_='job-location').text.strip()
                desc = job.find('div', class_='job-description').text.strip()
                link = job.find('a')['href']
                
                self.jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": desc,
                    "url": link,
                    "source": "Rozee.pk",
                    "application_method": "web_form"
                })
                
        except Exception as e:
            print(f"Error scraping Rozee.pk: {e}")

    def scrape_indeed(self, query):
        url = CONFIG["job_sites"]["Indeed"].format(query=query.replace(" ", "+"))
        try:
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Indeed specific parsing - adjust selectors as needed
            listings = soup.find_all('div', class_='job_seen_beacon')
            
            for job in listings:
                title = job.find('h2').text.strip()
                company = job.find('span', class_='companyName').text.strip()
                location = job.find('div', class_='companyLocation').text.strip()
                desc = job.find('div', class_='job-snippet').text.strip()
                link = "https://pk.indeed.com" + job.find('a')['href']
                
                self.jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": desc,
                    "url": link,
                    "source": "Indeed",
                    "application_method": "web_form"
                })
                
        except Exception as e:
            print(f"Error scraping Indeed: {e}")

    def scrape_linkedin(self, query):
        # LinkedIn is more complex to scrape - this is a basic example
        # Note: LinkedIn may block scraping attempts
        url = CONFIG["job_sites"]["LinkedIn"].format(query=query.replace(" ", "%20"))
        try:
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # LinkedIn specific parsing - adjust selectors as needed
            listings = soup.find_all('div', class_='base-card')
            
            for job in listings:
                title = job.find('h3').text.strip()
                company = job.find('h4').text.strip()
                location = job.find('span', class_='job-search-card__location').text.strip()
                link = job.find('a')['href']
                
                # LinkedIn descriptions are usually on separate pages
                desc = self._scrape_linkedin_description(link)
                
                self.jobs.append({
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": desc,
                    "url": link,
                    "source": "LinkedIn",
                    "application_method": "web_form"
                })
                
        except Exception as e:
            print(f"Error scraping LinkedIn: {e}")

    def _scrape_linkedin_description(self, url):
        try:
            response = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            desc_div = soup.find('div', class_='description__text')
            return desc_div.text.strip() if desc_div else "Description not available"
        except:
            return "Description not available"

    def scrape_all(self):
        for keyword in CONFIG["job_keywords"]:
            self.scrape_rozee(keyword)
            self.scrape_indeed(keyword)
            self.scrape_linkedin(keyword)
        
        # Remove duplicates
        seen = set()
        unique_jobs = []
        for job in self.jobs:
            identifier = (job['title'], job['company'], job['url'])
            if identifier not in seen:
                seen.add(identifier)
                unique_jobs.append(job)
        
        self.jobs = unique_jobs
        return self.jobs

class DocumentGenerator:
    @staticmethod
    def generate_ats_resume(job_description):
        """Generate an ATS-optimized resume based on job description"""
        try:
            # Load base resume
            with open(CONFIG["base_resume"], 'r') as f:
                base_resume = json.load(f)
            
            # Use GPT to optimize resume
            prompt = f"""
            Optimize this resume for the following job description. 
            Focus on matching keywords and highlighting relevant experience.
            
            Job Description:
            {job_description}
            
            Current Resume:
            {json.dumps(base_resume, indent=2)}
            
            Return the optimized resume in the exact same JSON format, only updating:
            - The professional summary
            - Experience bullet points (to better match the job)
            - Skills section (to include keywords from the job description)
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a professional resume writer that optimizes resumes for ATS systems."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            optimized_resume = json.loads(response.choices[0].message.content)
            return optimized_resume
        except Exception as e:
            print(f"Error generating resume: {e}")
            return None

    @staticmethod
    def generate_cover_letter(job_title, company_name, job_description):
        """Generate a customized cover letter"""
        try:
            # Load base cover letter template
            with open(CONFIG["base_cover_letter"], 'r') as f:
                template = f.read()
            
            # Use GPT to generate cover letter
            prompt = f"""
            Write a professional cover letter for the position of {job_title} at {company_name}.
            Incorporate details from the job description and highlight relevant skills and experience.
            
            Job Description:
            {job_description}
            
            Candidate Information:
            {CONFIG['user_info']['name']}
            {CONFIG['user_info']['address']}
            {CONFIG['user_info']['phone']}
            
            Use the following template as a starting point:
            {template}
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a professional cover letter writer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating cover letter: {e}")
            return None

    @staticmethod
    def save_documents(job, resume, cover_letter):
        """Save generated documents to files"""
        try:
            # Create directory for this application if it doesn't exist
            dir_name = f"applications/{job['company']}_{job['title']}".replace(" ", "_").replace("/", "_")
            os.makedirs(dir_name, exist_ok=True)
            
            # Save resume
            resume_file = f"{dir_name}/resume_{job['company']}.json"
            with open(resume_file, 'w') as f:
                json.dump(resume, f, indent=2)
            
            # Save cover letter
            cover_file = f"{dir_name}/cover_letter_{job['company']}.txt"
            with open(cover_file, 'w') as f:
                f.write(cover_letter)
            
            return resume_file, cover_file
        except Exception as e:
            print(f"Error saving documents: {e}")
            return None, None

class ApplicationManager:
    @staticmethod
    def apply_via_email(job, resume_file, cover_letter_file):
        """Send application via email"""
        try:
            # Create email
            msg = MIMEMultipart()
            msg['From'] = CONFIG["smtp"]["email"]
            msg['To'] = job.get('application_email', 'hr@' + job['company'].replace(" ", "").lower() + '.com')
            msg['Subject'] = f"Application for {job['title']} Position"
            
            # Email body
            body = f"""
            Dear Hiring Manager,
            
            Please find attached my application for the {job['title']} position at {job['company']}.
            
            Sincerely,
            {CONFIG['user_info']['name']}
            """
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach resume and cover letter
            with open(resume_file, 'rb') as f:
                attach = MIMEApplication(f.read(), _subtype="json")
                attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(resume_file))
                msg.attach(attach)
            
            with open(cover_letter_file, 'rb') as f:
                attach = MIMEText(f.read())
                attach.add_header('Content-Disposition', 'attachment', filename=os.path.basename(cover_letter_file))
                msg.attach(attach)
            
            # Send email
            with smtplib.SMTP(CONFIG["smtp"]["server"], CONFIG["smtp"]["port"]) as server:
                server.starttls()
                server.login(CONFIG["smtp"]["email"], CONFIG["smtp"]["password"])
                server.send_message(msg)
            
            return True
        except Exception as e:
            print(f"Error sending email application: {e}")
            return False

    @staticmethod
    def handle_web_form(job, resume_file, cover_letter_file):
        """Generate instructions for manual form submission"""
        try:
            # Create a JSON file with application data
            application_data = {
                "job": job,
                "resume_path": os.path.abspath(resume_file),
                "cover_letter_path": os.path.abspath(cover_letter_file),
                "timestamp": datetime.now().isoformat()
            }
            
            dir_name = f"applications/{job['company']}_{job['title']}".replace(" ", "_").replace("/", "_")
            data_file = f"{dir_name}/application_data.json"
            
            with open(data_file, 'w') as f:
                json.dump(application_data, f, indent=2)
            
            print(f"\nManual application required for: {job['title']} at {job['company']}")
            print(f"Application data saved to: {data_file}")
            print(f"Job URL: {job['url']}")
            
            return data_file
        except Exception as e:
            print(f"Error handling web form application: {e}")
            return None

    @staticmethod
    def track_application(job, application_method, status="Applied"):
        """Track application in Google Sheets or local CSV"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data = [
                job['title'],
                job['company'],
                job['source'],
                timestamp,
                application_method,
                status,
                job.get('url', '')
            ]
            
            # Try Google Sheets first
            if sheet:
                sheet.append_row(data)
                return True
            
            # Fallback to local CSV
            csv_file = "job_applications.csv"
            file_exists = os.path.isfile(csv_file)
            
            with open(csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow([
                        "Job Title", "Company", "Source", "Date Applied", 
                        "Application Method", "Status", "URL"
                    ])
                writer.writerow(data)
            
            return True
        except Exception as e:
            print(f"Error tracking application: {e}")
            return False

class ReportGenerator:
    @staticmethod
    def generate_daily_report():
        """Generate and send/print daily report"""
        try:
            # Get today's applications
            today = datetime.now().strftime("%Y-%m-%d")
            
            if sheet:
                # Get all records from Google Sheet
                records = sheet.get_all_records()
                today_apps = [r for r in records if r['Date Applied'].startswith(today)]
            else:
                # Get from local CSV
                today_apps = []
                if os.path.exists("job_applications.csv"):
                    with open("job_applications.csv", 'r') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row['Date Applied'].startswith(today):
                                today_apps.append(row)
            
            # Generate report
            report = f"""
            Daily Job Application Report - {today}
            ====================================
            
            Total Jobs Applied: {len(today_apps)}
            
            Applications:
            """
            
            for app in today_apps:
                report += f"\n- {app.get('Job Title', 'N/A')} at {app.get('Company', 'N/A')} via {app.get('Application Method', 'N/A')}"
            
            # Check for pending manual submissions
            manual_pending = [app for app in today_apps if app.get('Application Method') == "web_form" and app.get('Status') != "Completed"]
            if manual_pending:
                report += "\n\nPending Manual Submissions:"
                for app in manual_pending:
                    report += f"\n- {app.get('Job Title', 'N/A')} at {app.get('Company', 'N/A')}"
            
            # Print report (could also email it)
            print(report)
            
            return report
        except Exception as e:
            print(f"Error generating daily report: {e}")
            return None

def main():
    print("Starting Oil & Gas Job Application Automation...")
    
    # Step 1: Scrape for new jobs
    print("\nScraping for new jobs...")
    scraper = JobScraper()
    jobs = scraper.scrape_all()
    print(f"Found {len(jobs)} new job postings")
    
    # Step 2: Process each job
    for job in jobs:
        print(f"\nProcessing: {job['title']} at {job['company']}")
        
        # Generate documents
        print("Generating ATS-optimized resume...")
        resume = DocumentGenerator.generate_ats_resume(job['description'])
        
        print("Generating cover letter...")
        cover_letter = DocumentGenerator.generate_cover_letter(
            job['title'], job['company'], job['description']
        )
        
        if not resume or not cover_letter:
            print("Failed to generate documents, skipping...")
            continue
        
        # Save documents
        resume_file, cover_letter_file = DocumentGenerator.save_documents(
            job, resume, cover_letter
        )
        
        if not resume_file or not cover_letter_file:
            print("Failed to save documents, skipping...")
            continue
        
        # Submit application
        if job['application_method'] == "email":
            print("Submitting via email...")
            success = ApplicationManager.apply_via_email(job, resume_file, cover_letter_file)
            if success:
                print("Email application sent successfully!")
                ApplicationManager.track_application(job, "email")
            else:
                print("Failed to send email application")
                ApplicationManager.track_application(job, "email", "Failed")
        else:
            print("Preparing for web form submission...")
            data_file = ApplicationManager.handle_web_form(job, resume_file, cover_letter_file)
            if data_file:
                ApplicationManager.track_application(job, "web_form", "Pending")
    
    # Step 3: Generate daily report
    print("\nGenerating daily report...")
    ReportGenerator.generate_daily_report()
    
    print("\nJob application process completed!")

if __name__ == "__main__":
    # Run main function immediately
    main()
    
    # Schedule to run daily at 9 AM
    schedule.every().day.at("09:00").do(main)
    
    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(60)