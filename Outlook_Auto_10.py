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

def identify_search_type(search_criteria):
    # Check if the search is for a ticket/case number
    ticket_pattern = r'^(INC|RITM|CHG|CTASK)\d+$'
    if re.match(ticket_pattern, search_criteria, re.IGNORECASE):
        return "case"
    else:
        # Ask user to specify the type
        while True:
            search_type = input("Is this search for a (1) Person or (2) Case details? Enter 1 or 2: ").strip()
            if search_type in ['1', '2']:
                return "person" if search_type == '1' else "case"
            print("Please enter either 1 for Person or 2 for Case details.")

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
        
        def search_folder(folder, criteria):
            messages = []
            try:
                # Search current folder
                folder_items = folder.Items
                folder_items.Sort("[ReceivedTime]", True)
                
                # Create filter for the current folder
                start_date = (datetime.now() - timedelta(days=days_back)).strftime("%m/%d/%Y")
                filter_string = (f"@SQL=("
                               f"\"urn:schemas:httpmail:subject\" LIKE '%{criteria}%' OR "
                               f"\"urn:schemas:httpmail:textdescription\" LIKE '%{criteria}%' OR "
                               f"\"urn:schemas:httpmail:fromname\" LIKE '%{criteria}%' OR "
                               f"\"urn:schemas:httpmail:fromaddress\" LIKE '%{criteria}%' OR "
                               f"\"urn:schemas:httpmail:displayto\" LIKE '%{criteria}%' OR "
                               f"\"urn:schemas:httpmail:displaycc\" LIKE '%{criteria}%' OR "
                               f"\"urn:schemas:httpmail:displaybcc\" LIKE '%{criteria}%'"
                               f") AND "
                               f"\"urn:schemas:httpmail:datereceived\" >= '{start_date}'")
                
                filtered_items = folder_items.Restrict(filter_string)
                messages.extend(list(filtered_items))
                
                # Search subfolders recursively
                for subfolder in folder.Folders:
                    try:
                        subfolder_messages = search_folder(subfolder, criteria)
                        messages.extend(subfolder_messages)
                    except Exception as e:
                        log(f"Error searching subfolder {subfolder.Name}: {str(e)}", 'warning')
                        continue
                
            except Exception as e:
                log(f"Error searching folder {folder.Name}: {str(e)}", 'warning')
            
            return messages
        
        all_messages = []
        folders_to_search = [
            (6, "Inbox"),
            (5, "Sent Items"),
            (3, "Deleted Items"),
            (4, "Outbox"),
            (2, "Drafts")
        ]
        
        for folder_const, folder_name in folders_to_search:
            try:
                log(f"Searching in {folder_name} and its subfolders...")
                root_folder = outlook.GetDefaultFolder(folder_const)
                folder_messages = search_folder(root_folder, search_criteria)
                all_messages.extend(folder_messages)
                log(f"Found {len(folder_messages)} emails in {folder_name} and its subfolders")
            except Exception as e:
                log(f"Error searching {folder_name}: {str(e)}", 'error')
                continue
        
        log(f"Total emails found across all folders and subfolders: {len(all_messages)}")
        return all_messages
        
    except Exception as e:
        log(f"Error fetching emails: {str(e)}", 'error')
        raise

def analyze_person_emails(messages):
    try:
        log("Analyzing emails for person-specific information...")
        
        tasks_analysis = {
            "assigned_to_me": [],
            "assigned_by_me": [],
            "pending_tasks": [],
            "completed_tasks": [],
            "upcoming_deadlines": [],
            "recent_interactions": [],
            "action_items": []
        }
        
        # Get current time in UTC for consistent comparison
        current_time = datetime.now().replace(tzinfo=None)
        
        for message in messages:
            try:
                subject = message.Subject
                body = message.Body
                # Convert received time to naive datetime for comparison
                date = message.ReceivedTime.replace(tzinfo=None)
                
                # Combine subject and body for analysis
                content = f"{subject}\n{body}"
                
                # Look for task-related keywords and patterns
                task_patterns = [
                    (r'(?i)please\s+(?:can you|could you)?\s*([^.?!]+)[.?!]', 'request'),
                    (r'(?i)(?:deadline|due|by)[:]\s*([^.?!]+)[.?!]', 'deadline'),
                    (r'(?i)(?:pending|outstanding|todo|to-do|to do)[:]\s*([^.?!]+)[.?!]', 'pending'),
                    (r'(?i)(?:completed|done|finished)[:]\s*([^.?!]+)[.?!]', 'completed'),
                    (r'(?i)action(?:\s+required|\s+needed)?[:]\s*([^.?!]+)[.?!]', 'action'),
                    (r'(?i)follow[\s-]up[:]\s*([^.?!]+)[.?!]', 'followup')
                ]
                
                # Extract tasks and categorize them
                for pattern, task_type in task_patterns:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        task_info = {
                            'task': match.group(1).strip(),
                            'date': date,
                            'subject': subject,
                            'type': task_type
                        }
                        
                        # Categorize based on task type and content
                        if task_type in ['request', 'action']:
                            if 'completed' in content.lower() or 'done' in content.lower():
                                tasks_analysis['completed_tasks'].append(task_info)
                            else:
                                tasks_analysis['pending_tasks'].append(task_info)
                                
                        if task_type == 'deadline':
                            tasks_analysis['upcoming_deadlines'].append(task_info)
                            
                        if 'please' in content.lower() or 'request' in content.lower():
                            tasks_analysis['assigned_to_me'].append(task_info)
                
                # Add to recent interactions
                interaction = {
                    'date': date,
                    'subject': subject,
                    'type': 'sent' if message.SenderEmailAddress == message.Session.CurrentUser.Address else 'received'
                }
                tasks_analysis['recent_interactions'].append(interaction)
                
            except Exception as e:
                log(f"Error processing message: {str(e)}", 'warning')
                continue
        
        # Sort all lists by date
        for key in tasks_analysis:
            if key != 'action_items':
                tasks_analysis[key] = sorted(tasks_analysis[key], key=lambda x: x['date'], reverse=True)
        
        # Generate action items summary
        tasks_analysis['action_items'] = [
            task for task in tasks_analysis['pending_tasks']
            if task['date'] >= (current_time - timedelta(days=30))
        ]
        
        return tasks_analysis
        
    except Exception as e:
        log(f"Error analyzing person emails: {str(e)}", 'error')
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

def extract_teams_and_responsibilities(content):
    teams = defaultdict(list)
    responsibilities = defaultdict(list)
    
    team_pattern = r'([\w\s]+)(?:\s*Team|\s*Department):\s*((?:(?!Team:|Department:).)+)'
    responsibility_pattern = r'([\w\s]+)(?:\s*Team|\s*Department)?\s*responsibilities?:\s*((?:(?!Team:|Department:).)+)'
    
    for match in re.finditer(team_pattern, content, re.IGNORECASE | re.DOTALL):
        team_name = match.group(1).strip()
        team_info = match.group(2).strip()
        teams[team_name].extend(re.findall(r'[\w\s]+\s*(?:<[^>]+>)?', team_info))
    
    for match in re.finditer(responsibility_pattern, content, re.IGNORECASE | re.DOTALL):
        team_name = match.group(1).strip()
        team_resp = match.group(2).strip()
        responsibilities[team_name].extend(re.split(r'\s*[;.]\s*', team_resp))
    
    return dict(teams), dict(responsibilities)

def extract_key_details(content):
    important_keywords = ["patching", "server", "update", "change", "task", "issue", "resolution", "impact"]
    key_details = defaultdict(list)
    
    for sentence in sent_tokenize(content):
        for keyword in important_keywords:
            if keyword in sentence.lower():
                key_details[keyword].append(sentence)
                break
    
    return dict(key_details)

def analyze_email_chain(file_path):
    try:
        log(f"Analyzing email chain from {file_path}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        consolidated_info = {
            "subject": "",
            "summary": "",
            "teams_involved": {},
            "tasks_and_responsibilities": {},
            "server_list": set(),
            "change_numbers": set(),
            "related_tasks": set(),
            "advisory": "",
            "incidents": set(),
            "contact_details": set(),
            "current_status": "",
            "key_details": {},
        }

        # Extract subject
        subject_match = re.search(r'Subject: (.*)', content)
        if subject_match:
            consolidated_info["subject"] = subject_match.group(1).strip()

        # Generate summary
        consolidated_info["summary"] = simple_summarize(content)

        # Extract teams and responsibilities
        consolidated_info["teams_involved"], consolidated_info["tasks_and_responsibilities"] = extract_teams_and_responsibilities(content)

        # Extract server list
        consolidated_info["server_list"].update(re.findall(r'\b(?:azw|srv|server-)[a-zA-Z0-9-]+\b', content, re.IGNORECASE))

        # Extract change numbers and related tasks
        consolidated_info["change_numbers"].update(re.findall(r'\bCHG\d+\b', content))
        consolidated_info["related_tasks"].update(re.findall(r'\b(?:RITM|CTASK)\d+\b', content))

        # Extract advisory
        advisory_match = re.search(r'(?:Advisory|Note|Important):\s*((?:(?!\n\n).)+)', content, re.IGNORECASE | re.DOTALL)
        if advisory_match:
            consolidated_info["advisory"] = advisory_match.group(1).strip()

        # Extract incidents
        consolidated_info["incidents"].update(re.findall(r'\bINC\d+\b', content))

        # Extract contact details
        consolidated_info["contact_details"].update(re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', content))
        consolidated_info["contact_details"].update(re.findall(r'\b(?:\+\d{1,2}\s)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b', content))

        # Extract current status
        status_sentences = re.findall(r'([^.]*status[^.]*\.)', content, re.IGNORECASE)
        if status_sentences:
            consolidated_info["current_status"] = status_sentences[-1].strip()

        # Extract key details
        consolidated_info["key_details"] = extract_key_details(content)

        # Convert sets to lists for JSON serialization
        for key in consolidated_info:
            if isinstance(consolidated_info[key], set):
                consolidated_info[key] = list(consolidated_info[key])

        log("Email chain analysis completed.")
        return consolidated_info
    except Exception as e:
        log(f"Error analyzing email chain: {str(e)}", 'error')
        raise

def generate_person_report(tasks_analysis, output_file):
    try:
        log(f"Generating person-specific report: {output_file}")
        doc = SimpleDocTemplate(output_file, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        story.append(Paragraph("Person-Specific Email Analysis Report", styles['Title']))
        story.append(Spacer(1, 12))
        
        # Action Items Section
        story.append(Paragraph("Current Action Items:", styles['Heading2']))
        if tasks_analysis['action_items']:
            for item in tasks_analysis['action_items']:
                story.append(Paragraph(
                    f"• {escape(item['task'])} (From: {item['date'].strftime('%Y-%m-%d')})", 
                    styles['BodyText']
                ))
        else:
            story.append(Paragraph("No pending action items found.", styles['BodyText']))
        story.append(Spacer(1, 12))
        
        # Pending Tasks Section
        story.append(Paragraph("Pending Tasks:", styles['Heading2']))
        if tasks_analysis['pending_tasks']:
            for task in tasks_analysis['pending_tasks'][:10]:  # Show latest 10
                story.append(Paragraph(
                    f"• {escape(task['task'])} (From: {task['date'].strftime('%Y-%m-%d')})", 
                    styles['BodyText']
                ))
        else:
            story.append(Paragraph("No pending tasks found.", styles['BodyText']))
        story.append(Spacer(1, 12))
        
        # Completed Tasks Section
        story.append(Paragraph("Recently Completed Tasks:", styles['Heading2']))
        if tasks_analysis['completed_tasks']:
            for task in tasks_analysis['completed_tasks'][:5]:  # Show latest 5
                story.append(Paragraph(
                    f"• {escape(task['task'])} (Completed: {task['date'].strftime('%Y-%m-%d')})", 
                    styles['BodyText']
                ))
        else:
            story.append(Paragraph("No completed tasks found in the analyzed period.", styles['BodyText']))
        story.append(Spacer(1, 12))
        
        # Upcoming Deadlines Section
        story.append(Paragraph("Upcoming Deadlines:", styles['Heading2']))
        if tasks_analysis['upcoming_deadlines']:
            for deadline in tasks_analysis['upcoming_deadlines']:
                story.append(Paragraph(
                    f"• {escape(deadline['task'])} (Due: {deadline['date'].strftime('%Y-%m-%d')})", 
                    styles['BodyText']
                ))
        else:
            story.append(Paragraph("No upcoming deadlines found.", styles['BodyText']))
        
        doc.build(story)
        log(f"Person-specific report generated successfully: {output_file}")
        
    except Exception as e:
        log(f"Error generating person report: {str(e)}", 'error')
        raise

def generate_pdf_report(consolidated_info, output_file):
    try:
        log(f"Generating PDF report: {output_file}")
        doc = SimpleDocTemplate(output_file, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Title
        story.append(Paragraph("Consolidated Email Analysis Report", styles['Title']))
        story.append(Spacer(1, 12))

        # Subject
        story.append(Paragraph(f"Subject: {escape(consolidated_info['subject'])}", styles['Heading2']))
        story.append(Spacer(1, 12))

        # Summary
        story.append(Paragraph("Summary:", styles['Heading3']))
        story.append(Paragraph(escape(consolidated_info['summary']), styles['BodyText']))
        story.append(Spacer(1, 12))

        # Current Status
        if consolidated_info['current_status']:
            story.append(Paragraph("Current Status:", styles['Heading3']))
            story.append(Paragraph(escape(consolidated_info['current_status']), styles['BodyText']))
            story.append(Spacer(1, 12))

        # Teams Involved
        story.append(Paragraph("Teams Involved:", styles['Heading3']))
        for team, members in consolidated_info['teams_involved'].items():
            story.append(Paragraph(f"{team}:", styles['Heading4']))
            for member in members:
                story.append(Paragraph(f"• {escape(member)}", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Tasks and Responsibilities
        story.append(Paragraph("Tasks and Responsibilities:", styles['Heading3']))
        for team, tasks in consolidated_info['tasks_and_responsibilities'].items():
            story.append(Paragraph(f"{team}:", styles['Heading4']))
            for task in tasks:
                story.append(Paragraph(f"• {escape(task)}", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Server List
        if consolidated_info['server_list']:
            story.append(Paragraph("List of Servers:", styles['Heading3']))
            for server in consolidated_info['server_list']:
                story.append(Paragraph(f"• {escape(server)}", styles['BodyText']))
            story.append(Spacer(1, 12))

        # Change Numbers and Related Tasks
        story.append(Paragraph("Change Numbers and Related Tasks:", styles['Heading3']))
        if consolidated_info['change_numbers']:
            story.append(Paragraph(f"Change Number(s): {', '.join(map(escape, consolidated_info['change_numbers']))}", styles['BodyText']))
        if consolidated_info['related_tasks']:
            story.append(Paragraph(f"Related Task(s): {', '.join(map(escape, consolidated_info['related_tasks']))}", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Advisory
        if consolidated_info['advisory']:
            story.append(Paragraph("Advisory:", styles['Heading3']))
            story.append(Paragraph(escape(consolidated_info['advisory']), styles['BodyText']))
            story.append(Spacer(1, 12))

        # Incidents
        if consolidated_info['incidents']:
            story.append(Paragraph("Incidents:", styles['Heading3']))
            story.append(Paragraph(f"Related Incident(s): {', '.join(map(escape, consolidated_info['incidents']))}", styles['BodyText']))
            story.append(Spacer(1, 12))

        # Contact Details
        if consolidated_info['contact_details']:
            story.append(Paragraph("Contact Details:", styles['Heading3']))
            for contact in consolidated_info['contact_details']:
                story.append(Paragraph(f"• {escape(contact)}", styles['BodyText']))
            story.append(Spacer(1, 12))

        # Key Details
        if consolidated_info['key_details']:
            story.append(Paragraph("Key Details:", styles['Heading3']))
            for keyword, details in consolidated_info['key_details'].items():
                story.append(Paragraph(f"{keyword.capitalize()}:", styles['Heading4']))
                for detail in details:
                    story.append(Paragraph(f"• {escape(detail)}", styles['BodyText']))
            story.append(Spacer(1, 12))

        doc.build(story)
        log(f"PDF report generated successfully: {output_file}")
    except Exception as e:
        log(f"Error generating PDF report: {str(e)}", 'error')
        raise

def main():
    try:
        log("Starting email analysis process...")
        search_term = input("Enter the search term (person name, incident number, keyword, etc.): ")
        days_back = int(input("Enter the number of days to search back (default is 30): ") or 30)
        
        # Identify search type
        search_type = identify_search_type(search_term)
        log(f"Search type identified as: {search_type}")
        
        pythoncom.CoInitialize()
        outlook = connect_to_outlook()
        
        log("Stage 1: Fetching emails...")
        messages = fetch_emails(outlook, search_term, days_back)

        if messages:
            if search_type == "person":
                log("Stage 2: Analyzing person-specific emails...")
                tasks_analysis = analyze_person_emails(messages)
                
                log("Stage 3: Generating person-specific report...")
                pdf_file = f"Person_Analysis_{search_term.replace(' ', '_')}.pdf"
                generate_person_report(tasks_analysis, pdf_file)
                
                log("Stage 4: Exporting analysis data...")
                json_file = f"Person_Analysis_{search_term.replace(' ', '_')}.json"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(tasks_analysis, f, indent=2, default=str)
                
                print(f"\nPerson-specific analysis has been generated:")
                print(f"PDF Report: {pdf_file}")
                print(f"Analysis Data: {json_file}")
                
            else:  # case
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
                
                print(f"\nCase analysis has been generated:")
                print(f"Email chain: {email_chain_file}")
                print(f"PDF Report: {pdf_file}")
                print(f"Analysis Data: {json_file}")
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