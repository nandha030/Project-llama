import win32com.client
import sys
import traceback
import pythoncom
from datetime import datetime, timedelta
import os
import re
import json
import logging
from collections import defaultdict
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from nltk.probability import FreqDist
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from html import escape
import ssl

# SSL context modification (use with caution)
ssl._create_default_https_context = ssl._create_unverified_context

# Download necessary NLTK data
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)

# Set up logging
logging.basicConfig(filename='email_analyzer.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def log(message, level='info'):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    if level == 'info':
        logging.info(message)
    elif level == 'error':
        logging.error(message)
    elif level == 'warning':
        logging.warning(message)

def connect_to_outlook():
    try:
        log("Connecting to Outlook...")
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        log("Successfully connected to Outlook.")
        return outlook
    except Exception as e:
        log(f"Error connecting to Outlook: {str(e)}", 'error')
        log("Please ensure Outlook is installed and running.")
        raise

def fetch_emails(outlook, search_criteria, days_back=30):
    try:
        log(f"Fetching emails related to '{search_criteria}'...")
        folders_to_search = [
            (6, "Inbox"),
            (5, "Sent Items"),
            (3, "Deleted Items"),
            (4, "Outbox"),
            (2, "Drafts")
        ]
        
        all_messages = []
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%m/%d/%Y")
        
        for folder_const, folder_name in folders_to_search:
            try:
                log(f"Searching in {folder_name}...")
                folder = outlook.GetDefaultFolder(folder_const)
                messages = folder.Items
                messages.Sort("[ReceivedTime]", True)
                
                log(f"Applying filter for '{search_criteria}' in {folder_name}...")
                filter_string = (f"@SQL=((\"urn:schemas:httpmail:subject\" LIKE '%{search_criteria}%') OR "
                                 f"(\"urn:schemas:httpmail:textdescription\" LIKE '%{search_criteria}%') OR "
                                 f"(\"urn:schemas:httpmail:fromname\" LIKE '%{search_criteria}%') OR "
                                 f"(\"urn:schemas:httpmail:fromaddress\" LIKE '%{search_criteria}%')) AND "
                                 f"\"urn:schemas:httpmail:datereceived\" >= '{start_date}'")
                filtered_messages = messages.Restrict(filter_string)
                
                log(f"Found {filtered_messages.Count} emails in {folder_name}")
                all_messages.extend(list(filtered_messages))
            except Exception as e:
                log(f"Error searching {folder_name}: {str(e)}", 'error')
                continue
        
        log(f"Total emails found across all folders: {len(all_messages)}")
        return all_messages
    except Exception as e:
        log(f"Error fetching emails: {str(e)}", 'error')
        raise

def get_email_content(message):
    try:
        subject = message.Subject
        sender = message.SenderEmailAddress
        body = message.Body
        received_time = message.ReceivedTime
        return subject, sender, body, received_time
    except Exception as e:
        log(f"Error extracting email content: {str(e)}", 'error')
        return None, None, None, None

def export_to_text(messages, output_file):
    try:
        log(f"Exporting emails to {output_file}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            for message in messages:
                subject, sender, body, received_time = get_email_content(message)
                if subject and sender and body and received_time:
                    f.write(f"Subject: {subject}\n")
                    f.write(f"From: {sender}\n")
                    f.write(f"Received: {received_time}\n")
                    f.write(f"Body:\n{body}\n")
                    f.write("-" * 80 + "\n\n")
        log(f"Emails exported successfully to {output_file}")
        return output_file
    except Exception as e:
        log(f"Error exporting emails to text file: {str(e)}", 'error')
        raise

def simple_summarize(text, num_sentences=3):
    sentences = sent_tokenize(text)
    words = word_tokenize(text.lower())
    stop_words = set(stopwords.words('english'))
    word_frequencies = FreqDist(word for word in words if word not in stop_words)
    
    sentence_scores = {}
    for sentence in sentences:
        for word in word_tokenize(sentence.lower()):
            if word in word_frequencies:
                if sentence not in sentence_scores:
                    sentence_scores[sentence] = word_frequencies[word]
                else:
                    sentence_scores[sentence] += word_frequencies[word]
    
    summary_sentences = sorted(sentence_scores, key=sentence_scores.get, reverse=True)[:num_sentences]
    summary = ' '.join(summary_sentences)
    return summary

def extract_detailed_information(content):
    info = {
        "subject": "",
        "summary": "",
        "current_status": [],
        "teams_involved": defaultdict(list),
        "tasks_and_responsibilities": defaultdict(list),
        "server_list": [],
        "change_numbers": [],
        "next_steps": [],
        "advisory": "",
        "incidents": []
    }

    # Extract subject
    subject_match = re.search(r'Subject: (.*)', content)
    if subject_match:
        info["subject"] = subject_match.group(1).strip()

    # Generate summary
    info["summary"] = simple_summarize(content, num_sentences=3)

    # Extract current status
    status_pattern = r'(?:current status|status update):(.*?)(?:\n\n|\Z)'
    status_match = re.search(status_pattern, content, re.IGNORECASE | re.DOTALL)
    if status_match:
        info["current_status"] = [item.strip() for item in status_match.group(1).split('\n') if item.strip()]

    # Extract teams and responsibilities
    team_pattern = r'([\w\s]+)(?:\s*Team|\s*Department):\s*((?:(?!Team:|Department:).)+)'
    for match in re.finditer(team_pattern, content, re.IGNORECASE | re.DOTALL):
        team_name = match.group(1).strip()
        team_info = match.group(2).strip()
        members = re.findall(r'([\w\s]+)\s*(?:Email: ([\w\.\@]+))?\s*(?:Phone: ([\d\s\+]+))?', team_info)
        for member in members:
            info["teams_involved"][team_name].append({
                "name": member[0].strip(),
                "email": member[1].strip() if member[1] else "",
                "phone": member[2].strip() if member[2] else ""
            })

    # Extract tasks and responsibilities
    task_pattern = r'([\w\s]+)(?:\s*Team|\s*Department)?\s*responsibilities?:\s*((?:(?!Team:|Department:).)+)'
    for match in re.finditer(task_pattern, content, re.IGNORECASE | re.DOTALL):
        team_name = match.group(1).strip()
        tasks = re.findall(r'[-\*]\s*(.*)', match.group(2))
        info["tasks_and_responsibilities"][team_name].extend(tasks)

    # Extract server list
    server_pattern = r'(\w+)\s*\(IP: ([\d\.]+)\)'
    info["server_list"] = re.findall(server_pattern, content)

    # Extract change numbers and related tasks
    change_pattern = r'(CHG\d+):\s*(.*?)(?:\((\w+)\))?'
    for match in re.finditer(change_pattern, content):
        info["change_numbers"].append({
            "number": match.group(1),
            "description": match.group(2).strip(),
            "status": match.group(3) if match.group(3) else "Unknown"
        })

    # Extract next steps
    next_steps_pattern = r'(?:Next Steps|Action Items):(.*?)(?:\n\n|\Z)'
    next_steps_match = re.search(next_steps_pattern, content, re.IGNORECASE | re.DOTALL)
    if next_steps_match:
        info["next_steps"] = [step.strip() for step in re.findall(r'[-\*]\s*(.*)', next_steps_match.group(1))]

    # Extract advisory
    advisory_pattern = r'Advisory:(.*?)(?:\n\n|\Z)'
    advisory_match = re.search(advisory_pattern, content, re.IGNORECASE | re.DOTALL)
    if advisory_match:
        info["advisory"] = advisory_match.group(1).strip()

    # Extract incidents
    incident_pattern = r'(INC\d+)'
    info["incidents"] = re.findall(incident_pattern, content)

    return info

def generate_comprehensive_report(info):
    report = f"""**Subject:** {info['subject']}

**Summary:** {info['summary']}

**Current Status:**
"""
    for i, status in enumerate(info['current_status'], 1):
        report += f"{i}. {status}\n"

    report += "\n**Teams Involved:**\n"
    for i, (team, members) in enumerate(info['teams_involved'].items(), 1):
        report += f"{i}. {team}:\n"
        for member in members:
            report += f"   * {member['name']}"
            if member['email']:
                report += f" Email: {member['email']}"
            if member['phone']:
                report += f" Phone: {member['phone']}"
            report += "\n"

    report += "\n**Tasks and Responsibilities:**\n"
    for i, (team, tasks) in enumerate(info['tasks_and_responsibilities'].items(), 1):
        report += f"{i}. {team}:\n"
        for task in tasks:
            report += f"   * {task}\n"

    report += "\n**List of Servers:**\n"
    for server, ip in info['server_list']:
        report += f"* {server} (IP: {ip})\n"

    report += "\n**Change Numbers & Related Tasks:**\n"
    for i, change in enumerate(info['change_numbers'], 1):
        report += f"{i}. {change['number']}: {change['description']} ({change['status']})\n"

    report += "\n**Next Steps:**\n"
    for i, step in enumerate(info['next_steps'], 1):
        report += f"{i}. {step}\n"

    if info['advisory']:
        report += f"\n**Advisory:**\n{info['advisory']}\n"

    if info['incidents']:
        report += "\n**Incidents:**\n"
        for incident in info['incidents']:
            report += f"* {incident}\n"

    return report

def analyze_email_chain(file_path):
    try:
        log(f"Analyzing email chain from {file_path}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        consolidated_info = extract_detailed_information(content)

        log("Email chain analysis completed.")
        return consolidated_info
    except Exception as e:
        log(f"Error analyzing email chain: {str(e)}", 'error')
        raise

def generate_pdf_report(consolidated_info, output_file):
    try:
        log(f"Generating PDF report: {output_file}")
        doc = SimpleDocTemplate(output_file, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        report_text = generate_comprehensive_report(consolidated_info)
        for line in report_text.split('\n'):
            if line.startswith('**'):
                story.append(Paragraph(line.strip('*'), styles['Heading2']))
            else:
                story.append(Paragraph(line, styles['BodyText']))
            story.append(Spacer(1, 6))

        doc.build(story)
        log(f"PDF report generated successfully: {output_file}")
    except Exception as e:
        log(f"Error generating PDF report: {str(e)}", 'error')
        raise

def main():
    try:
        log("Starting email analysis process...")
        search_term = input("Enter the search term (incident number, keyword, etc.): ")
        days_back = int(input("Enter the number of days to search back (default is 30): ") or 30)
        log(f"Analyzing emails for search term: {search_term}")

        pythoncom.CoInitialize()
        outlook = connect_to_outlook()
        
        log("Stage 1: Fetching emails...")
        messages = fetch_emails(outlook, search_term, days_back)

        if messages:
            log("Stage 2: Exporting email chain to text file...")
            email_chain_file = f"Email_Chain_{search_term.replace(' ', '_')}.txt"
            export_to_text(messages, email_chain_file)
            
            log("Stage 3: Analyzing email chain...")
            consolidated_info = analyze_email_chain(email_chain_file)
            
            log("Stage 4: Generating PDF report...")
            pdf_file = f"Consolidated_Report_{search_term.replace(' ', '_')}.pdf"
            generate_pdf_report(consolidated_info, pdf_file)
            
            log("Stage 5: Exporting consolidated information...")
            json_file = f"Consolidated_Info_{search_term.replace(' ', '_')}.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(consolidated_info, f, indent=2)
            
            log("Email analysis process completed successfully.")
            print(f"\nEmail chain has been exported to {email_chain_file}")
            print(f"Consolidated information has been exported to {json_file}")
            print(f"PDF report has been generated: {pdf_file}")
        else:
            log("No emails found matching the search criteria.", 'warning')
    except Exception as e:
        log(f"An unexpected error occurred: {str(e)}", 'error')
        log("Error details:", 'error')
        log(traceback.format_exc(), 'error')
    finally:
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    main()
    