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
                               f"\"urn:schemas:httpmail:displaybcc\" LIKE '%{criteria}%' OR "
                               f"\"urn:schemas:httpmail:displayfrom\" LIKE '%{criteria}%'"
                               f") AND "
                               f"\"urn:schemas:httpmail:datereceived\" >= '{start_date}'")
                
                filtered_items = folder_items.Restrict(filter_string)
                for item in filtered_items:
                    try:
                        # Include folder path in message info
                        messages.append({
                            'message': item,
                            'folder': folder.FolderPath,
                            'subject': item.Subject,
                            'date': item.ReceivedTime,
                            'sender': item.SenderName
                        })
                    except Exception as e:
                        continue
                
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
        
        # Sort all messages by date
        all_messages.sort(key=lambda x: x['date'], reverse=True)
        log(f"Total emails found across all folders and subfolders: {len(all_messages)}")
        return all_messages
        
    except Exception as e:
        log(f"Error fetching emails: {str(e)}", 'error')
        raise

def display_email_list(messages):
    print("\nFound Emails:")
    print("-" * 100)
    print(f"{'Index':^6} | {'Date':^12} | {'Sender':^25} | {'Subject':^40} | {'Location':^15}")
    print("-" * 100)
    
    for idx, msg in enumerate(messages, 1):
        date_str = msg['date'].strftime('%Y-%m-%d')
        sender = (msg['sender'][:22] + '...') if len(msg['sender']) > 25 else msg['sender']
        subject = (msg['subject'][:37] + '...') if len(msg['subject']) > 40 else msg['subject']
        folder = msg['folder'].split('\\')[-1]  # Get last part of folder path
        
        print(f"{idx:^6} | {date_str:^12} | {sender:<25} | {subject:<40} | {folder:<15}")
    
    print("-" * 100)

def select_emails_for_analysis(messages):
    while True:
        try:
            print("\nEnter the indices of emails to analyze (comma-separated), or 'all' for all emails:")
            selection = input("Selection: ").strip().lower()
            
            if selection == 'all':
                return [msg['message'] for msg in messages]
            
            indices = [int(idx.strip()) for idx in selection.split(',')]
            selected_messages = []
            
            for idx in indices:
                if 1 <= idx <= len(messages):
                    selected_messages.append(messages[idx-1]['message'])
                else:
                    print(f"Invalid index: {idx}. Please enter numbers between 1 and {len(messages)}")
                    break
            else:
                return selected_messages
                
        except ValueError:
            print("Invalid input. Please enter numbers separated by commas or 'all'")