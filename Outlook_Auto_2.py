import win32com.client
import sys
import traceback
import pythoncom
from datetime import datetime, timedelta
import os
import re
import json
import logging

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

def analyze_email_chain(file_path):
    try:
        log(f"Analyzing email chain from {file_path}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        consolidated_info = {
            "people_involved": set(),
            "server_list": set(),
            "summary": "",
            "key_details": [],
            "contact_details": set(),
            "recommendations": [],
            "current_status": "",
            "connected_items": set(),
        }

        emails = content.split('-' * 80)
        for email in emails:
            if not email.strip():
                continue

            # Extract people involved
            consolidated_info["people_involved"].update(re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', email))

            # Extract server names (assuming they follow a pattern like SRV-XXXX)
            consolidated_info["server_list"].update(re.findall(r'\b(?:SRV|srv)-[A-Za-z0-9]+\b', email))

            # Extract contact details
            consolidated_info["contact_details"].update(re.findall(r'\b(?:\+\d{1,2}\s)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b', email))

            # Extract connected items
            connected_items = re.findall(r'\b(?:INC|CHG|PR|RITM|SR|CTASK)[-\s]?\d+\b', email)
            consolidated_info["connected_items"].update(connected_items)

            # Extract recommendations
            recommendations = re.findall(r'recommend.*?[.!?]', email, re.IGNORECASE | re.DOTALL)
            consolidated_info["recommendations"].extend(recommendations)

            # Extract current status (assuming it's mentioned explicitly)
            status_match = re.search(r'current status:?\s*(.*?)[.!?]', email, re.IGNORECASE)
            if status_match:
                consolidated_info["current_status"] = status_match.group(1).strip()

            # Add key details (first few sentences of each email)
            key_details = ". ".join(email.split('.')[:3]) + "."
            consolidated_info["key_details"].append(key_details)

        # Compile summary
        consolidated_info["summary"] = f"This email chain involves {len(consolidated_info['people_involved'])} people, " \
                                       f"{len(consolidated_info['server_list'])} servers, and has {len(consolidated_info['connected_items'])} connected items."

        # Convert sets to lists for JSON serialization
        for key in consolidated_info:
            if isinstance(consolidated_info[key], set):
                consolidated_info[key] = list(consolidated_info[key])

        log("Email chain analysis completed.")
        return consolidated_info
    except Exception as e:
        log(f"Error analyzing email chain: {str(e)}", 'error')
        raise

def export_consolidated_info(consolidated_info, output_file):
    try:
        log(f"Exporting consolidated information to {output_file}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(consolidated_info, f, indent=2)
        log(f"Consolidated information exported successfully to {output_file}")
        return output_file
    except Exception as e:
        log(f"Error exporting consolidated information: {str(e)}", 'error')
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
            
            log("Stage 4: Exporting consolidated information...")
            output_file = f"Consolidated_Info_{search_term.replace(' ', '_')}.json"
            export_consolidated_info(consolidated_info, output_file)
            
            log("Email analysis process completed successfully.")
            print(f"\nEmail chain has been exported to {email_chain_file}")
            print(f"Consolidated information has been exported to {output_file}")
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