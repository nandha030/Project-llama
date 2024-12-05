import re
from nltk import sent_tokenize
from fpdf import FPDF

# Function to extract specific sections using regex
def extract_sections(email_text):
    sections = {}

    # Regex patterns for various sections
    sections['Teams_Involved'] = re.search(r"(Teams Involved|Involved Teams):\s*(.*)", email_text, re.IGNORECASE)
    sections['Tasks_and_Responsibilities'] = re.search(r"(Tasks and Responsibilities|Tasks|Responsibilities):\s*(.*)", email_text, re.IGNORECASE)
    sections['Team_Advisory'] = re.search(r"(Team Advisory|Advisory):\s*(.*)", email_text, re.IGNORECASE)
    sections['Action_Items'] = re.search(r"(Action Items|Actions):\s*(.*)", email_text, re.IGNORECASE)

    # Clean and format extracted sections
    for key, match in sections.items():
        if match:
            sections[key] = match.group(2).strip()
        else:
            sections[key] = f"No {key.replace('_', ' ')} Provided"

    return sections

# Function to extract consolidated email content
def extract_email_content(email_text):
    emails = re.split(r'From:', email_text)
    structured_emails = []

    for email in emails:
        if not email.strip():
            continue

        email_data = {}

        from_match = re.search(r"From:\s*(.+)", email)
        to_match = re.search(r"To:\s*(.+)", email)
        date_match = re.search(r"Date:\s*(.+)", email)
        subject_match = re.search(r"Subject:\s*(.+)", email)

        email_data['From'] = from_match.group(1) if from_match else "Unknown"
        email_data['To'] = to_match.group(1) if to_match else "Unknown"
        email_data['Date'] = date_match.group(1) if date_match else "Unknown"
        email_data['Subject'] = subject_match.group(1) if subject_match else "No Subject"

        sections = extract_sections(email)
        email_data.update(sections)

        body_match = re.split(r'On.*wrote:', email)
        if len(body_match) > 1:
            email_data['Body'] = body_match[0].strip()
        else:
            email_data['Body'] = email.strip()

        structured_emails.append(email_data)

    return structured_emails

# Function to generate summary
def summarize_email_chain(structured_emails):
    summary = []

    for email in structured_emails:
        body_summary = ' '.join(sent_tokenize(email['Body'])[:2])

        summary.append({
            "From": email['From'],
            "To": email['To'],
            "Date": email['Date'],
            "Subject": email['Subject'],
            "Body_Summary": body_summary,
            "Teams_Involved": email['Teams_Involved'],
            "Tasks_and_Responsibilities": email['Tasks_and_Responsibilities'],
            "Team_Advisory": email['Team_Advisory'],
            "Action_Items": email['Action_Items']
        })

    return summary

# Function to write summary to txt file
def export_summary_to_txt(filepath, summary):
    with open(filepath, 'w') as f:
        for idx, email in enumerate(summary, 1):
            f.write(f"Email {idx}:\n")
            f.write(f"From: {email['From']}\n")
            f.write(f"To: {email['To']}\n")
            f.write(f"Date: {email['Date']}\n")
            f.write(f"Subject: {email['Subject']}\n")
            f.write(f"Summary: {email['Body_Summary']}\n")
            f.write(f"Teams Involved: {email['Teams_Involved']}\n")
            f.write(f"Tasks and Responsibilities: {email['Tasks_and_Responsibilities']}\n")
            f.write(f"Team Advisory: {email['Team_Advisory']}\n")
            f.write(f"Action Items: {email['Action_Items']}\n\n")

# Function to write summary to PDF
def export_summary_to_pdf(filepath, summary, report_title):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, report_title, ln=True, align='C')

    pdf.set_font("Arial", size=12)
    for idx, email in enumerate(summary, 1):
        pdf.ln(10)
        pdf.cell(200, 10, f"Email {idx}:", ln=True)
        pdf.multi_cell(0, 10, f"From: {email['From']}")
        pdf.multi_cell(0, 10, f"To: {email['To']}")
        pdf.multi_cell(0, 10, f"Date: {email['Date']}")
        pdf.multi_cell(0, 10, f"Subject: {email['Subject']}")
        pdf.multi_cell(0, 10, f"Summary: {email['Body_Summary']}")
        pdf.multi_cell(0, 10, f"Teams Involved: {email['Teams_Involved']}")
        pdf.multi_cell(0, 10, f"Tasks and Responsibilities: {email['Tasks_and_Responsibilities']}")
        pdf.multi_cell(0, 10, f"Team Advisory: {email['Team_Advisory']}")
        pdf.multi_cell(0, 10, f"Action Items: {email['Action_Items']}")
    
    pdf.output(filepath)

# Load email chain from .txt file
def load_email_txt(filepath):
    with open(filepath, 'r') as file:
        return file.read()

# Main function to process email chain and generate summary, saving as both txt and PDF
def process_email_chain(filepath, output_txt, output_pdf):
    email_text = load_email_txt(filepath)
    structured_emails = extract_email_content(email_text)
    summary = summarize_email_chain(structured_emails)

    # Use the subject of the first email as the report title
    report_title = summary[0]['Subject'] if summary else "Email Chain Report"

    # Export to .txt and .pdf
    export_summary_to_txt(output_txt, summary)
    export_summary_to_pdf(output_pdf, summary, report_title)
    print(f"Summary exported to {output_txt} and {output_pdf}")

# Example usage: replace 'email_chain.txt', 'summary_report.txt', and 'summary_report.pdf' with actual paths
process_email_chain('Email_Content_CHG00341335.txt', 'summary_report.txt', 'summary_report.pdf')
