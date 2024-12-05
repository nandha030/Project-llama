import win32com.client
import sys
import traceback
import pythoncom
from datetime import datetime, timedelta
import os
import re
import spacy

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def connect_to_outlook():
    try:
        log("Connecting to Outlook...")
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        log("Successfully connected to Outlook.")
        return outlook
    except Exception as e:
        log(f"Error connecting to Outlook: {str(e)}")
        log("Please ensure Outlook is installed and running.")
        sys.exit(1)

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
                log(f"Error searching {folder_name}: {str(e)}")
                continue
        
        log(f"Total emails found across all folders: {len(all_messages)}")
        return all_messages
    except Exception as e:
        log(f"Error fetching emails: {str(e)}")
        return []

def get_email_content(message):
    try:
        subject = message.Subject
        sender = message.SenderEmailAddress
        body = message.Body
        received_time = message.ReceivedTime
        return subject, sender, body, received_time
    except Exception as e:
        log(f"Error extracting email content: {str(e)}")
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
    except Exception as e:
        log(f"Error exporting emails to text file: {str(e)}")

def analyze_text_file(file_path, search_term):
    try:
        log("Loading NLP model...")
        nlp = spacy.load("en_core_web_sm")
        
        log(f"Analyzing text file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        emails = re.split(r'-{80}', content)
        consolidated_summary = f"Incident Summary for {search_term}\n\n"
        
        for i, email in enumerate(emails, 1):
            if not email.strip():
                continue
            
            email_lines = email.strip().split('\n')
            subject = next((line.split('Subject: ')[1] for line in email_lines if line.startswith('Subject: ')), "N/A")
            sender = next((line.split('From: ')[1] for line in email_lines if line.startswith('From: ')), "N/A")
            body = '\n'.join(email_lines[email_lines.index('Body:') + 1:])
            
            doc = nlp(body)
            summary = ' '.join(sent.text for sent in doc.sents)[:200] + "..."  # First 200 characters as summary
            
            entities = []
            for ent in doc.ents:
                if ent.label_ in ['PERSON', 'ORG', 'TIME', 'DATE']:
                    entities.append(f"{ent.text} ({ent.label_})")
            
            consolidated_summary += f"Email {i}:\n"
            consolidated_summary += f"From: {sender}\n"
            consolidated_summary += f"Subject: {subject}\n"
            consolidated_summary += f"Summary: {summary}\n"
            consolidated_summary += f"Entities Identified: {', '.join(entities)}\n\n"
        
        return consolidated_summary
    except Exception as e:
        log(f"Error analyzing text file: {str(e)}")
        return None

def main():
    try:
        search_term = input("Enter the search term (incident number, keyword, etc.): ")
        days_back = int(input("Enter the number of days to search back (default is 30): ") or 30)
        log(f"Analyzing emails for search term: {search_term}")

        pythoncom.CoInitialize()
        outlook = connect_to_outlook()
        messages = fetch_emails(outlook, search_term, days_back)

        if messages:
            output_file = f"Email_Content_{search_term.replace(' ', '_')}.txt"
            export_to_text(messages, output_file)
            print(f"\nEmail content has been exported to {output_file}")
            
            log("Generating consolidated summary...")
            summary = analyze_text_file(output_file, search_term)
            if summary:
                summary_file = f"Summary_{search_term.replace(' ', '_')}.txt"
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write(summary)
                print(f"\nConsolidated summary has been saved to {summary_file}")
            else:
                print("Unable to generate summary.")
        else:
            log("No emails found matching the search criteria.")
    except Exception as e:
        log(f"An unexpected error occurred: {str(e)}")
        log("Error details:")
        traceback.print_exc()
    finally:
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    main()
    