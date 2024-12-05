import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from langchain import PromptTemplate, LLMChain
from langchain.llms import HuggingFacePipeline
from langchain.text_splitter import RecursiveCharacterTextSplitter
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
from tqdm import tqdm
from huggingface_hub import login

# Configuration
os.environ["HUGGINGFACE_TOKEN"] = "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"
login(token=os.environ["HUGGINGFACE_TOKEN"])

# SSL context modification
ssl._create_default_https_context = ssl._create_unverified_context

# Set up logging
logging.basicConfig(filename='email_analyzer.log', level=logging.INFO,
                   format='%(asctime)s - %(levelname)s - %(message)s')

def log(message, level='info'):
    """Enhanced logging function with console output"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
    if level == 'info':
        logging.info(message)
    elif level == 'error':
        logging.error(message)
    elif level == 'warning':
        logging.warning(message)

class LLMInitializer:
    @staticmethod
    def initialize_llm(model_name="meta-llama/Llama-2-7b-chat-hf"):
        """Initialize the LLM model with optimized settings"""
        try:
            log(f"Initializing LLM model: {model_name}")
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                token=os.environ["HUGGINGFACE_TOKEN"]
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                token=os.environ["HUGGINGFACE_TOKEN"],
                torch_dtype=torch.float16,
                device_map="auto",
                load_in_8bit=True
            )
            
            pipe = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                max_length=2048,
                temperature=0.7,
                top_p=0.95,
                repetition_penalty=1.15
            )
            
            return HuggingFacePipeline(pipeline=pipe)
        except Exception as e:
            log(f"Error initializing LLM: {str(e)}", 'error')
            raise

class LLMEmailAnalyzer:
    def __init__(self, llm):
        self.llm = llm
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200
        )
        self.setup_prompt_templates()
    
    def setup_prompt_templates(self):
        self.templates = {
            'summary': PromptTemplate(
                input_variables=["content"],
                template="""
                Analyze this email content and provide:
                1. Key points and decisions
                2. Action items with owners
                3. Critical deadlines
                4. Risks or concerns
                
                Email content:
                {content}
                """
            ),
            'sentiment': PromptTemplate(
                input_variables=["content"],
                template="""
                Analyze the sentiment and urgency:
                1. Overall sentiment (positive/negative/neutral)
                2. Urgency level (high/medium/low)
                3. Key concerns
                4. Satisfaction indicators
                
                Content:
                {content}
                """
            ),
            'technical': PromptTemplate(
                input_variables=["content"],
                template="""
                Analyze technical aspects and provide:
                1. Technical issues identified
                2. System components mentioned
                3. Technical requirements
                4. Proposed solutions
                
                Content:
                {content}
                """
            )
        }

    def analyze_chunk(self, chunk, analysis_type="summary"):
        try:
            template = self.templates.get(analysis_type, self.templates['summary'])
            chain = LLMChain(llm=self.llm, prompt=template)
            return chain.run(content=chunk)
        except Exception as e:
            log(f"Error analyzing chunk: {str(e)}", 'error')
            return None

    def analyze_full_content(self, content):
        try:
            chunks = self.text_splitter.split_text(content)
            analysis_results = defaultdict(list)
            
            for chunk in tqdm(chunks, desc="Analyzing chunks"):
                for analysis_type in self.templates.keys():
                    result = self.analyze_chunk(chunk, analysis_type)
                    if result:
                        analysis_results[f"{analysis_type}_analysis"].append(result)
            
            return self.consolidate_analyses(analysis_results)
        except Exception as e:
            log(f"Error in full content analysis: {str(e)}", 'error')
            raise

    def consolidate_analyses(self, analyses):
        consolidated = {
            "key_points": [],
            "action_items": [],
            "deadlines": [],
            "risks": [],
            "technical_aspects": {
                "issues": [],
                "components": [],
                "requirements": [],
                "solutions": []
            },
            "sentiment": {
                "overall": None,
                "urgent_matters": [],
                "concerns": [],
                "satisfaction_level": None
            }
        }
        
        for summary in analyses.get("summary_analysis", []):
            self._extract_summary_elements(summary, consolidated)
        
        for sentiment in analyses.get("sentiment_analysis", []):
            self._extract_sentiment_elements(sentiment, consolidated)
        
        for technical in analyses.get("technical_analysis", []):
            self._extract_technical_elements(technical, consolidated)
        
        return consolidated

    def _extract_summary_elements(self, summary, consolidated):
        lines = summary.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if any(keyword in line.lower() for keyword in ['key point', 'decision']):
                consolidated['key_points'].append(line)
            elif any(keyword in line.lower() for keyword in ['action', 'task']):
                consolidated['action_items'].append(line)
            elif any(keyword in line.lower() for keyword in ['deadline', 'due', 'by']):
                consolidated['deadlines'].append(line)
            elif any(keyword in line.lower() for keyword in ['risk', 'concern', 'issue']):
                consolidated['risks'].append(line)

    def _extract_sentiment_elements(self, sentiment, consolidated):
        lines = sentiment.split('\n')
        sentiment_info = consolidated['sentiment']
        
        for line in lines:
            line = line.strip().lower()
            if not line:
                continue
            
            if 'sentiment' in line:
                for sentiment_type in ['positive', 'negative', 'neutral']:
                    if sentiment_type in line:
                        sentiment_info['overall'] = sentiment_type
                        break
            elif any(keyword in line for keyword in ['urgent', 'priority']):
                sentiment_info['urgent_matters'].append(line)
            elif 'concern' in line:
                sentiment_info['concerns'].append(line)
            elif 'satisfaction' in line:
                sentiment_info['satisfaction_level'] = line

    def _extract_technical_elements(self, technical, consolidated):
        lines = technical.split('\n')
        tech_info = consolidated['technical_aspects']
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if any(keyword in line.lower() for keyword in ['issue:', 'problem:']):
                tech_info['issues'].append(line)
            elif any(keyword in line.lower() for keyword in ['component:', 'system:']):
                tech_info['components'].append(line)
            elif 'require' in line.lower():
                tech_info['requirements'].append(line)
            elif any(keyword in line.lower() for keyword in ['solution:', 'fix:']):
                tech_info['solutions'].append(line)

class OutlookInterface:
    @staticmethod
    def connect_to_outlook():
        try:
            log("Connecting to Outlook...")
            outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
            log("Successfully connected to Outlook.")
            return outlook
        except Exception as e:
            log(f"Error connecting to Outlook: {str(e)}", 'error')
            raise

    @staticmethod
    def fetch_emails(outlook, search_criteria, days_back=30):
        try:
            log(f"Fetching emails for '{search_criteria}'...")
            folders = [
                (6, "Inbox"),
                (5, "Sent Items"),
                (3, "Deleted Items"),
                (4, "Outbox"),
                (2, "Drafts")
            ]
            
            all_messages = []
            start_date = (datetime.now() - timedelta(days=days_back)).strftime("%m/%d/%Y")
            
            for folder_const, folder_name in folders:
                try:
                    folder = outlook.GetDefaultFolder(folder_const)
                    messages = folder.Items
                    messages.Sort("[ReceivedTime]", True)
                    
                    filter_string = (
                        f"@SQL=((\"urn:schemas:httpmail:subject\" LIKE '%{search_criteria}%') OR "
                        f"(\"urn:schemas:httpmail:textdescription\" LIKE '%{search_criteria}%') OR "
                        f"(\"urn:schemas:httpmail:fromname\" LIKE '%{search_criteria}%') OR "
                        f"(\"urn:schemas:httpmail:fromaddress\" LIKE '%{search_criteria}%')) AND "
                        f"\"urn:schemas:httpmail:datereceived\" >= '{start_date}'"
                    )
                    
                    filtered_messages = messages.Restrict(filter_string)
                    all_messages.extend(list(filtered_messages))
                    log(f"Found {filtered_messages.Count} emails in {folder_name}")
                except Exception as e:
                    log(f"Error searching {folder_name}: {str(e)}", 'error')
                    continue
            
            return all_messages
        except Exception as e:
            log(f"Error fetching emails: {str(e)}", 'error')
            raise

class EmailProcessor:
    @staticmethod
    def export_to_text(messages, output_file):
        try:
            log(f"Exporting emails to {output_file}...")
            with open(output_file, 'w', encoding='utf-8') as f:
                for message in messages:
                    try:
                        subject = message.Subject
                        sender = message.SenderEmailAddress
                        body = message.Body
                        received_time = message.ReceivedTime
                        
                        f.write(f"Subject: {subject}\n")
                        f.write(f"From: {sender}\n")
                        f.write(f"Received: {received_time}\n")
                        f.write(f"Body:\n{body}\n")
                        f.write("-" * 80 + "\n\n")
                    except Exception as e:
                        log(f"Error processing message: {str(e)}", 'error')
                        continue
            
            log(f"Emails exported successfully to {output_file}")
            return output_file
        except Exception as e:
            log(f"Error exporting emails: {str(e)}", 'error')
            raise

class ReportGenerator:
    def __init__(self, analysis_info):
        self.analysis_info = analysis_info
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        self.styles.add(ParagraphStyle(
            name='CustomHeading1',
            parent=self.styles['Heading1'],
            fontSize=16,
            spaceAfter=20
        ))
    
    def generate_pdf(self, output_file):
        try:
            doc = SimpleDocTemplate(output_file, pagesize=letter)
            story = []
            
            story.append(Paragraph("Email Analysis Report", self.styles['Title']))
            story.append(Spacer(1, 20))
            
            self._add_summary_section(story)
            self._add_technical_section(story)
            self._add_sentiment_section(story)
            self._add_action_items_section(story)
            
            doc.build(story)
            log(f"PDF report generated: {output_file}")
        except Exception as e:
            log(f"Error generating PDF: {str(e)}", 'error')
            raise

    def _add_summary_section(self, story):
        story.append(Paragraph("Summary Analysis", self.styles['CustomHeading1']))
        story.append(Spacer(1, 12))
        
        sections = [
            ("Key Points", self.analysis_info['key_points']),
            ("Action Items", self.analysis_info['action_items']),
            ("Deadlines", self.analysis_info['deadlines']),
            ("Risks", self.analysis_info['risks'])
        ]
        
        for title, items in sections:
            if items:
                story.append(Paragraph(title, self.styles['Heading2']))
                for item in items:
                    story.append(Paragraph(f"• {escape(item)}", self.styles['Normal']))
                story.append(Spacer(1, 12))

    def _add_technical_section(self, story):
        story.append(Paragraph("Technical Analysis", self.styles['CustomHeading1']))
        story.append(Spacer(1, 12))
        
        tech_aspects = self.analysis_info['technical_aspects']
        sections = [
            ("Technical Issues", tech_aspects['issues']),
            ("System Components", tech_aspects['components']),
            ("Requirements", tech_aspects['requirements']),
            ("Solutions", tech_aspects['solutions'])
        ]
        
        for title, items in sections:
            if items:
                story.append(Paragraph(title, self.styles['Heading2']))
                for item in items:
                    story.append(Paragraph(f"• {escape(item)}", self.styles['Normal']))
                story.append(Spacer(1, 12))

    def _add_sentiment_section(self, story):
        story.append(Paragraph("Sentiment Analysis", self.styles['CustomHeading1']))
        story.append(Spacer(1, 12))
        
        sentiment = self.analysis_info['sentiment']
        
        if sentiment['overall']:
            story.append(Paragraph(f"Overall Sentiment: {sentiment['overall'].title()}", 
                                self.styles['Heading2']))
        
        sections = [
            ("Urgent Matters", sentiment['urgent_matters']),
            ("Concerns", sentiment['concerns'])
        ]
        
        for title, items in sections:
            if items:
                story.append(Paragraph(title, self.styles['Heading2']))
                for item in items:
                    story.append(Paragraph(f"• {escape(item)}", self.styles['Normal']))
                story.append(Spacer(1, 12))

    def _add_action_items_section(self, story):
        if self.analysis_info['action_items']:
            story.append(Paragraph("Action Items", self.styles['CustomHeading1']))
            story.append(Spacer(1, 12))
            
            for item in self.analysis_info['action_items']:
                story.append(Paragraph(f"• {escape(item)}", self.styles['Normal']))
            story.append(Spacer(1, 12))

def main():
    try:
        # Initialize LLM
        log("Starting email analysis process...")
        llm = LLMInitializer.initialize_llm()
        llm_analyzer = LLMEmailAnalyzer(llm)
        
        # Get user input
        search_term = input("Enter search term for email analysis: ")
        days_back = int(input("Enter number of days to search back [30]: ") or 30)
        
        # Initialize Outlook
        pythoncom.CoInitialize()
        outlook = OutlookInterface.connect_to_outlook()
        
        # Process emails
        messages = OutlookInterface.fetch_emails(outlook, search_term, days_back)
        
        if messages:
            # Generate file names with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = f"{search_term.replace(' ', '_')}_{timestamp}"
            
            # Export and analyze emails
            email_file = f"Email_Chain_{base_name}.txt"
            EmailProcessor.export_to_text(messages, email_file)
            
            # Perform LLM analysis
            log("Performing content analysis...")
            with open(email_file, 'r', encoding='utf-8') as f:
                content = f.read()
            analysis_results = llm_analyzer.analyze_full_content(content)
            
            # Generate reports
            pdf_file = f"Analysis_Report_{base_name}.pdf"
            json_file = f"Analysis_Data_{base_name}.json"
            
            log("Generating PDF report...")
            ReportGenerator(analysis_results).generate_pdf(pdf_file)
            
            log("Exporting analysis data...")
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(analysis_results, f, indent=2)
            
            log("Analysis process completed successfully")
            print("\nGenerated files:")
            print(f"1. Email Chain: {email_file}")
            print(f"2. PDF Report: {pdf_file}")
            print(f"3. Analysis Data: {json_file}")
        else:
            log("No matching emails found", 'warning')
            print("\nNo emails found matching the search criteria.")
    
    except Exception as e:
        log(f"Error in main execution: {str(e)}", 'error')
        log(traceback.format_exc(), 'error')
        print("\nAn error occurred during execution. Check the log file for details.")
    finally:
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    try:
        nltk.download('punkt', quiet=True)
        nltk.download('stopwords', quiet=True)
        main()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    except Exception as e:
        print(f"\nCritical error: {str(e)}")