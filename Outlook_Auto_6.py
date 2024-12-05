import os
import json
import logging
import traceback
from datetime import datetime, timedelta
from collections import defaultdict
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from nltk.probability import FreqDist
from llama_cpp import Llama
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from html import escape
import re
import win32com.client
import pythoncom
import ssl
import nltk

# SSL context modification (use with caution)
ssl._create_default_https_context = ssl._create_unverified_context

# Download necessary NLTK data
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)

# Directory Setup
BASE_DIR = os.getcwd()
LOGS_DIR = os.path.join(BASE_DIR, "logs")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Configure Logging
LOG_FILE = os.path.join(LOGS_DIR, "email_analyzer.log")
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

def log(message, level='info'):
    """Enhanced logging with console output."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    getattr(logging, level)(message)

def connect_to_outlook():
    """Connect to Outlook using MAPI."""
    try:
        log("Connecting to Outlook...")
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        log("Successfully connected to Outlook.")
        return outlook
    except Exception as e:
        log(f"Error connecting to Outlook: {str(e)}", 'error')
        raise

def fetch_emails(outlook, search_criteria, days_back=30):
    """Fetch emails based on search criteria and look through all subfolders."""
    try:
        log(f"Fetching emails for '{search_criteria}' in the past {days_back} days...")
        all_messages = []
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%m/%d/%Y")

        def search_folder(folder):
            messages = []
            try:
                items = folder.Items
                items.Sort("[ReceivedTime]", True)

                filter_string = (
                    f"@SQL=((\"urn:schemas:httpmail:subject\" LIKE '%{search_criteria}%') OR "
                    f"(\"urn:schemas:httpmail:textdescription\" LIKE '%{search_criteria}%')) AND "
                    f"\"urn:schemas:httpmail:datereceived\" >= '{start_date}'"
                )

                filtered_items = items.Restrict(filter_string)
                messages.extend(list(filtered_items))

                for subfolder in folder.Folders:
                    messages.extend(search_folder(subfolder))
            except Exception as e:
                log(f"Error searching folder {folder.Name}: {str(e)}", 'warning')
            return messages

        inbox = outlook.GetDefaultFolder(6)  # Inbox
        all_messages.extend(search_folder(inbox))

        log(f"Total emails found: {len(all_messages)}")
        return all_messages
    except Exception as e:
        log(f"Error fetching emails: {str(e)}", 'error')
        raise

def initialize_llama(model_path):
    """Initialize the LLaMA model."""
    try:
        log(f"Initializing LLaMA model from: {model_path}")
        llm = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_batch=512,
            n_threads=6
        )
        log("LLaMA model initialized successfully.")
        return llm
    except Exception as e:
        log(f"Error initializing LLaMA model: {str(e)}", 'error')
        raise

def generate_prompt(content, search_term):
    """Generate a prompt for LLaMA to analyze content."""
    return f"""<s>[INST]You are an expert analyst. Analyze the following email chain and provide a consolidated report in the following format:
    - Summary:
    - Current Status:
    - Teams Involved:
    - Tasks and Responsibilities:
    - Change Numbers and Related Tasks:
    - Advisory:
    - Contact Details:
    - Key Details:
    - Impact:
    - Next Action Plan (if any):

    Search term: {search_term}

    Content:
    {content}[/INST]"""

def analyze_with_llama(llm, prompt):
    """Analyze content using the LLaMA model."""
    try:
        log("Analyzing content with LLaMA...")
        response = llm.create_completion(
            prompt,
            max_tokens=1024,
            temperature=0.7,
            top_p=0.9,
            stop=["</s>"]
        )
        return response['choices'][0]['text'].strip()
    except Exception as e:
        log(f"Error during LLaMA analysis: {str(e)}", 'error')
        raise

def generate_pdf_report(consolidated_info, output_file):
    """Generate a PDF report based on the consolidated analysis."""
    try:
        log(f"Generating PDF report: {output_file}")
        doc = SimpleDocTemplate(output_file, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Title
        story.append(Paragraph("Consolidated Email Analysis Report", styles['Title']))
        story.append(Spacer(1, 12))

        # Add each section
        for section, content in consolidated_info.items():
            story.append(Paragraph(section + ":", styles['Heading2']))
            story.append(Paragraph(escape(content if content else "No data available"), styles['BodyText']))
            story.append(Spacer(1, 12))

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
            email_chain_file = os.path.join(OUTPUT_DIR, f"Email_Chain_{search_term.replace(' ', '_')}.txt")
            with open(email_chain_file, 'w', encoding='utf-8') as f:
                for message in messages:
                    f.write(f"Subject: {message.Subject}\n")
                    f.write(f"From: {message.SenderEmailAddress}\n")
                    f.write(f"Received: {message.ReceivedTime}\n")
                    f.write(f"Body:\n{message.Body}\n")
                    f.write("-" * 80 + "\n\n")
            
            log("Stage 3: Analyzing email chain...")
            with open(email_chain_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Initialize LLaMA model
            llama_model_path = "llama.cpp/models/llama-2-13b-chat.Q4_K_M.gguf"
            llm = initialize_llama(llama_model_path)

            # Generate prompt and analyze with LLaMA
            prompt = generate_prompt(content, search_term)
            consolidated_info = analyze_with_llama(llm, prompt)

            # Save analysis to PDF and JSON
            log("Stage 4: Generating PDF report...")
            pdf_file = os.path.join(OUTPUT_DIR, f"Consolidated_Report_{search_term.replace(' ', '_')}.pdf")
            generate_pdf_report(json.loads(consolidated_info), pdf_file)

            log("Stage 5: Exporting consolidated information...")
            json_file = os.path.join(OUTPUT_DIR, f"Consolidated_Info_{search_term.replace(' ', '_')}.json")
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(json.loads(consolidated_info), f, indent=2)
            
            log("Email analysis process completed successfully.")
            print(f"\nEmail chain has been exported to {email_chain_file}")
            print(f"Consolidated information has been exported to {json_file}")
            print(f"PDF report has been generated: {pdf_file}")
        else:
            log("No emails found matching the search criteria.", 'warning')
    except Exception as e:
        log(f"An unexpected error occurred: {str(e)}", 'error')
        traceback.print_exc()
    finally:
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    main()
