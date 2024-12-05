import re
from collections import defaultdict
import spacy
from fpdf import FPDF
import textwrap
import logging
import os
from datetime import datetime
from transformers import pipeline
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

# Set up logging
logging.basicConfig(filename='email_parser.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Load the English NLP model
try:
    nlp = spacy.load("en_core_web_sm")
    summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
except Exception as e:
    logging.error(f"Error loading NLP models: {str(e)}")
    raise

def parse_email_chain(file_path):
    logging.info(f"Starting to parse email chain from {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        raise
    except IOError as e:
        logging.error(f"IO error occurred while reading {file_path}: {str(e)}")
        raise

    # Split the content into individual emails
    emails = re.split(r'-{10,}', content)

    parsed_data = {
        "subject": "",
        "summary": "",
        "teams_involved": defaultdict(dict),
        "tasks": defaultdict(list),
        "servers": [],
        "changes": [],
        "next_steps": [],
        "current_status": [],
        "advisory": "",
        "incidents": ""
    }

    for i, email in enumerate(emails, 1):
        logging.info(f"Parsing email {i} of {len(emails)}")
        try:
            parse_single_email(email, parsed_data)
        except Exception as e:
            logging.error(f"Error parsing email {i}: {str(e)}")

    # Generate intelligent summary
    parsed_data["summary"] = generate_intelligent_summary(content, parsed_data)
    logging.info("Finished parsing email chain")
    return parsed_data

def parse_single_email(email, parsed_data):
    # Extract subject
    subject_match = re.search(r'Subject: (.+)', email)
    if subject_match and not parsed_data["subject"]:
        parsed_data["subject"] = subject_match.group(1).strip()

    # Extract server information
    server_matches = re.findall(r'(nw1zslzen\d{3})\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', email)
    for server, ip in server_matches:
        if server not in [s[0] for s in parsed_data["servers"]]:
            parsed_data["servers"].append((server, ip))

    # Extract change numbers
    change_matches = re.findall(r'(CHG\d{8})', email)
    for change in change_matches:
        if change not in parsed_data["changes"]:
            parsed_data["changes"].append(change)

    # Extract team information
    team_matches = re.findall(r'(\w+(?:\s+\w+)*)\s*[:-]\s*([\w.]+@[\w.]+)(?:\s*Phone:\s*(\d+))?', email)
    for name, email, phone in team_matches:
        parsed_data["teams_involved"][name] = {"email": email, "phone": phone if phone else "N/A"}

    # Use NLP for more intelligent extraction
    doc = nlp(email)
    
    for sent in doc.sents:
        sent_text = sent.text.strip()
        
        if any(step in sent_text.lower() for step in ["next step", "todo", "to do", "action item"]):
            parsed_data["next_steps"].append(sent_text)
        
        elif any(status in sent_text.lower() for status in ["current status", "update", "progress"]):
            parsed_data["current_status"].append(sent_text)
        
        elif any(task_word in sent_text.lower() for task_word in ["task", "responsibility", "action required"]):
            for ent in sent.ents:
                if ent.label_ in ["ORG", "PERSON"]:
                    parsed_data["tasks"][ent.text].append(sent_text)
                    break
            else:
                parsed_data["tasks"]["Unassigned"].append(sent_text)

    # Extract advisory information
    advisory_match = re.search(r'Advisory:(.+?)(?=\n\n|\Z)', email, re.DOTALL | re.IGNORECASE)
    if advisory_match:
        parsed_data["advisory"] += advisory_match.group(1).strip() + "\n"

    # Extract incident information
    incident_match = re.search(r'Incident:(.+?)(?=\n\n|\Z)', email, re.DOTALL | re.IGNORECASE)
    if incident_match:
        parsed_data["incidents"] += incident_match.group(1).strip() + "\n"

def generate_intelligent_summary(content, parsed_data):
    logging.info("Generating intelligent summary")
    
    # Use the summarization model to generate a concise summary
    summary = summarizer(content, max_length=150, min_length=50, do_sample=False)[0]['summary_text']
    
    # Enhance the summary with specific details from parsed_data
    enhanced_summary = f"{summary}\n\nKey Details:\n"
    enhanced_summary += f"- This report covers {len(parsed_data['changes'])} changes: {', '.join(parsed_data['changes'])}.\n"
    enhanced_summary += f"- It involves {len(parsed_data['servers'])} servers and {len(parsed_data['teams_involved'])} teams.\n"
    enhanced_summary += f"- There are {sum(len(tasks) for tasks in parsed_data['tasks'].values())} tasks identified across all teams.\n"
    if parsed_data["next_steps"]:
        enhanced_summary += f"- {len(parsed_data['next_steps'])} next steps have been identified.\n"
    if parsed_data["current_status"]:
        enhanced_summary += f"- {len(parsed_data['current_status'])} status updates are available.\n"
    
    return enhanced_summary

def generate_report(parsed_data):
    logging.info("Generating report")
    report = f"""Subject: {parsed_data["subject"]}

Summary: {parsed_data["summary"]}

Current Status:
{chr(10).join(f"- {status}" for status in parsed_data["current_status"])}

Teams Involved:
"""
    for team, info in parsed_data["teams_involved"].items():
        report += f"- {team}: Email: {info['email']}, Phone: {info['phone']}\n"

    report += """
Tasks and Responsibilities:
"""
    for team, tasks in parsed_data["tasks"].items():
        report += f"{team}:\n"
        for task in tasks:
            report += f"- {task}\n"

    report += """
List of Servers:
"""
    for server, ip in parsed_data["servers"]:
        report += f"- {server} (IP: {ip})\n"

    report += """
Change Numbers & Related Tasks:
"""
    for change in parsed_data["changes"]:
        report += f"- {change}\n"

    report += """
Next Steps:
"""
    for step in parsed_data["next_steps"]:
        report += f"- {step}\n"

    report += f"""
Advisory:
{parsed_data["advisory"]}

Incidents:
{parsed_data["incidents"]}
"""

    return report

def save_as_txt(report, filename):
    logging.info(f"Saving report as TXT: {filename}")
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
    except IOError as e:
        logging.error(f"Error saving TXT report: {str(e)}")
        raise

def save_as_pdf(report, filename):
    logging.info(f"Saving report as PDF: {filename}")
    try:
        class PDF(FPDF):
            def header(self):
                self.set_font('Arial', 'B', 12)
                self.cell(0, 10, 'Email Chain Analysis Report', 0, 1, 'C')

            def footer(self):
                self.set_y(-15)
                self.set_font('Arial', 'I', 8)
                self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

        pdf = PDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.set_auto_page_break(auto=True, margin=15)

        for line in report.split('\n'):
            wrapped_lines = textwrap.wrap(line, width=75)
            for wrapped_line in wrapped_lines:
                pdf.cell(0, 10, wrapped_line, ln=True)

        pdf.output(filename)
    except Exception as e:
        logging.error(f"Error saving PDF report: {str(e)}")
        raise

def main():
    logging.info("Starting email chain analysis")
    
    # Get input file path
    file_path = input("Enter the path to your input file: ").strip()
    
    try:
        # Parse email chain
        parsed_data = parse_email_chain(file_path)

        # Generate report
        report = generate_report(parsed_data)

        # Create output directory
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)

        # Generate unique filename based on current timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"email_analysis_report_{timestamp}"

        # Save as TXT
        txt_filename = os.path.join(output_dir, f"{base_filename}.txt")
        save_as_txt(report, txt_filename)

        # Save as PDF
        pdf_filename = os.path.join(output_dir, f"{base_filename}.pdf")
        save_as_pdf(report, pdf_filename)

        print(f"Reports have been generated in the '{output_dir}' directory:")
        print(f"- TXT: {txt_filename}")
        print(f"- PDF: {pdf_filename}")

        logging.info("Email chain analysis completed successfully")

    except Exception as e:
        logging.error(f"An error occurred during email chain analysis: {str(e)}")
        print(f"An error occurred. Please check the log file for details.")

if __name__ == "__main__":
    main()