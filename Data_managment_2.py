import os
import json
import logging
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Union

# Core processing imports
import pandas as pd
import numpy as np
from PyPDF2 import PdfReader
import docx
import chardet
from llama_cpp import Llama

# Text processing
import nltk
from nltk.tokenize import sent_tokenize
from nltk.corpus import stopwords
from nltk.probability import FreqDist

# Report generation
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# Exchange server handling
from exchangelib import Credentials, Account, DELEGATE, Configuration, Folder

# Configure system settings
class SystemConfig:
    BASE_DIR = Path(os.getcwd())
    LOGS_DIR = BASE_DIR / "logs"
    OUTPUT_DIR = BASE_DIR / "output"
    DATA_DIR = BASE_DIR / "data"

    # LLaMA Model Configuration
    LLAMA_CONFIG = {
        "model_path": "/home/nandha/llama_models/llama-2-7b-chat.Q4_K_M.gguf",  # Using 7B for better speed/memory balance      
        "n_ctx": 4096,                # Increased context window
        "n_batch": 512,
        "n_threads": 8,
        "temp": 0.1,                  # Lower temperature for more focused output
        "max_tokens": 1000,
        "top_p": 0.9,
        "stop": ["</s>"]
    }

    # Report Configuration
    REPORT_STYLE = {
        "font_size": 10,
        "leading": 14,
        "space_before": 6,
        "space_after": 6,
        "page_margins": 0.75 * inch
    }

    @classmethod
    def initialize(cls):
        """Initialize system directories and configurations"""
        for directory in [cls.LOGS_DIR, cls.OUTPUT_DIR, cls.DATA_DIR]:
            directory.mkdir(exist_ok=True)

class DataProcessor:
    """Handles multiple input file formats and data preprocessing"""

    @staticmethod
    def read_file(file_path: Path) -> str:
        """Read and extract text from various file formats"""
        file_type = file_path.suffix.lower()

        try:
            if file_type == '.txt':
                return DataProcessor._read_text_file(file_path)
            elif file_type == '.pdf':
                return DataProcessor._read_pdf_file(file_path)
            elif file_type == '.docx':
                return DataProcessor._read_docx_file(file_path)
            elif file_type == '.json':
                return DataProcessor._read_json_file(file_path)
            elif file_type == '.csv':
                return DataProcessor._read_csv_file(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
        except Exception as e:
            logging.error(f"Error reading file {file_path}: {str(e)}")
            raise

    @staticmethod
    def _read_text_file(file_path: Path) -> str:
        """Read text file with encoding detection"""
        with open(file_path, 'rb') as file:
            raw_data = file.read()
            encoding = chardet.detect(raw_data)['encoding']
        return raw_data.decode(encoding)

    @staticmethod
    def _read_pdf_file(file_path: Path) -> str:
        """Extract text from PDF"""
        reader = PdfReader(file_path)
        return " ".join(page.extract_text() for page in reader.pages)

    @staticmethod
    def _read_docx_file(file_path: Path) -> str:
        """Extract text from DOCX"""
        doc = docx.Document(file_path)
        return " ".join(paragraph.text for paragraph in doc.paragraphs)

    @staticmethod
    def _read_json_file(file_path: Path) -> str:
        """Read JSON and convert to string"""
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return json.dumps(data, indent=2)

    @staticmethod
    def _read_csv_file(file_path: Path) -> str:
        """Read CSV and convert to string"""
        df = pd.read_csv(file_path)
        return df.to_string()

class TextAnalyzer:
    """Handles text analysis using LLaMA model"""

    def __init__(self):
        #self.llm = Llama(**SystemConfig.LLAMA_CONFIG)
        self.llm = Llama(model_path=SystemConfig.LLAMA_CONFIG["model_path"])
        self.prompt_template = """<s>[INST]Analyze the following content and provide a concise executive summary (maximum 2 pages) with the following sections:

Consolidated Email Analysis Report
Date: {current_date}

Summary:
[Provide 3-4 key points about the change/incident]

Current Status:
[List current implementation status with bullet points]

Teams Involved:
[List key teams and roles]

Tasks and Responsibilities:
[List key personnel and primary responsibilities]

Change Numbers and Related Tasks:
[List change numbers and core implementation details]

Advisory:
[List critical notifications or warnings]

Contact Details:
[List primary contacts]

Key Details:
[List critical technical specifications]

Impact:
[Summarize business and technical impact]

Next Action Plan:
[List immediate next steps if any]

Content for analysis:
{content}[/INST]"""

    def analyze_content(self, content: str) -> str:
        """Analyze content using LLaMA model"""
        prompt = self.prompt_template.format(
            current_date=datetime.now().strftime("%B %d, %Y"),
            content=content
        )

        # Pass only the required arguments
        response = self.llm(prompt=prompt, 
                            n_ctx=SystemConfig.LLAMA_CONFIG["n_ctx"],
                            max_tokens=SystemConfig.LLAMA_CONFIG["max_tokens"],
                            temperature=SystemConfig.LLAMA_CONFIG["temp"],
                            top_p=SystemConfig.LLAMA_CONFIG["top_p"],
                            stop=SystemConfig.LLAMA_CONFIG["stop"])
        return response['choices'][0]['text'].strip()

class ReportGenerator:
    """Handles PDF report generation"""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom styles for PDF generation"""
        self.styles.add(ParagraphStyle(
            name='ExecutiveSummary',
            parent=self.styles['Normal'],
            fontSize=SystemConfig.REPORT_STYLE['font_size'],
            leading=SystemConfig.REPORT_STYLE['leading'],
            spaceBefore=SystemConfig.REPORT_STYLE['space_before'],
            spaceAfter=SystemConfig.REPORT_STYLE['space_after']
        ))

    def generate_report(self, content: str, output_file: Path):
        """Generate PDF report"""
        doc = SimpleDocTemplate(
            str(output_file),
            pagesize=letter,
            rightMargin=SystemConfig.REPORT_STYLE['page_margins'],
            leftMargin=SystemConfig.REPORT_STYLE['page_margins'],
            topMargin=SystemConfig.REPORT_STYLE['page_margins'],
            bottomMargin=SystemConfig.REPORT_STYLE['page_margins']
        )

        story = []
        sections = content.split('\n\n')

        for section in sections:
            if section.strip():
                para = Paragraph(
                    section.replace('\n', '<br/>'),
                    self.styles['ExecutiveSummary']
                )
                story.append(para)
                story.append(Spacer(1, 6))

        doc.build(story)

def main():
    try:
        # Initialize system
        SystemConfig.initialize()

        # Setup logging
        logging.basicConfig(
            filename=SystemConfig.LOGS_DIR / "analyzer.log",
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

        # Get input file
        input_file = Path(input("Enter the path to your input file: ").strip())
        if not input_file.exists():
            raise FileNotFoundError(f"File not found: {input_file}")

        # Process input file
        logging.info(f"Processing file: {input_file}")
        content = DataProcessor.read_file(input_file)

        # Analyze content
        analyzer = TextAnalyzer()
        analysis_result = analyzer.analyze_content(content)

        # Generate report
        output_file = SystemConfig.OUTPUT_DIR / f"Executive_Summary_{input_file.stem}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        report_generator = ReportGenerator()
        report_generator.generate_report(analysis_result, output_file)

        logging.info(f"Report generated successfully: {output_file}")
        print(f"\nExecutive summary has been generated: {output_file}")

    except Exception as e:
        logging.error(f"Error occurred: {str(e)}")
        logging.debug(traceback.format_exc())
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()