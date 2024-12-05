import re
from transformers import GPTNeoForCausalLM, GPT2Tokenizer, pipeline
import fitz  # PyMuPDF to handle PDF extraction
from fpdf import FPDF
import requests
from transformers import GPTNeoForCausalLM, GPT2Tokenizer

# Use the custom requests session to disable SSL verification
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
model = GPTNeoForCausalLM.from_pretrained('EleutherAI/gpt-neo-2.7B', use_auth_token=False, trust_remote_code=True, revision="main", _request_kwargs={'verify': False})
tokenizer = GPT2Tokenizer.from_pretrained('EleutherAI/gpt-neo-2.7B')


# Initialize a pipeline for text generation and document analysis
generator = pipeline('text-generation', model=model, tokenizer=tokenizer)

# Function to extract text from a PDF file using PyMuPDF
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

# Function to read a text file
def read_file(file_path):
    if file_path.endswith('.pdf'):
        return extract_text_from_pdf(file_path)
    else:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

# Function to extract relevant information dynamically from the email chain
def extract_information(text):
    # Generate a detailed summary using the GPT-Neo model
    summary_prompt = (
        "Analyze the following text and provide a detailed summary with "
        "subject, teams involved, persons involved, advisory, next action plan, "
        "current status, related tasks (CHG/INC/RITM/CTASK), and list of servers:\n"
        f"{text}\n"
    )
    # Generate summary using GPT-Neo
    summary = generator(summary_prompt, max_length=500, num_return_sequences=1)[0]['generated_text']
    
    # Extract persons involved from the text using regex (emails and phone numbers)
    people_pattern = r'([\w\s]+)\s*\((.*?)\)\s*Email:\s*([\w\.-]+@[\w\.-]+)\s*Phone:\s*([\+\d\s-]+)'
    people_matches = re.findall(people_pattern, text)
    
    teams_involved = {}
    persons_involved = []
    
    for match in people_matches:
        name, role, email, phone = match
        person_info = {"name": name, "role": role, "email": email, "phone": phone}
        persons_involved.append(person_info)
        team_name = role.split(' ')[-1] if ' ' in role else "General Team"
        if team_name not in teams_involved:
            teams_involved[team_name] = []
        teams_involved[team_name].append(person_info)
    
    # Extract server details dynamically (server names can vary)
    server_pattern = r'[a-zA-Z0-9\-\.]+\d+'  # Capture different server naming formats
    servers = re.findall(server_pattern, text) if re.search(server_pattern, text) else ["No servers listed"]
    
    # Extract related change tasks (CHG/INC/RITM/CTASK)
    related_tasks = re.findall(r'(CHG\d+|INC\d+|RITM\d+|CTASK\d+)', text)
    
    # Extract attachments if any are mentioned
    attachments = re.findall(r'Attachment: (.*)', text)
    attachments = attachments if attachments else ["No attachments found"]
    
    # Extract advisory, next steps, and current status dynamically using the model
    advisory_prompt = f"Based on the text, what is the advisory and next action plan?\n{text}\n"
    advisory_and_next_steps = generator(advisory_prompt, max_length=200, num_return_sequences=1)[0]['generated_text']
    
    # Extract current status (terms like completed, successful, pending)
    current_status_match = re.search(r'(completed|successful|pending)', text, re.IGNORECASE)
    current_status = current_status_match.group(1).capitalize() if current_status_match else "Status not mentioned"

    # Compile all extracted information into a structured dictionary
    summary_info = {
        "Summary": summary,
        "Teams Involved": teams_involved,
        "Persons Involved": persons_involved,
        "Servers": servers,
        "Related Tasks (CHG/INC/RITM/CTASK)": related_tasks if related_tasks else ["No related tasks found"],
        "Attachments": attachments,
        "Advisory and Next Steps": advisory_and_next_steps,
        "Current Status": current_status
    }
    
    return summary_info

# Function to generate text summary
def generate_txt_summary(summary_info, output_file):
    with open(output_file, 'w') as file:
        file.write(f"Summary:\n{summary_info['Summary']}\n\n")
        file.write(f"Teams Involved:\n")
        for team, members in summary_info['Teams Involved'].items():
            file.write(f"{team}:\n")
            for person in members:
                file.write(f"  - {person['name']} ({person['role']})\n    Email: {person['email']}\n    Phone: {person['phone']}\n")
        file.write("\nPersons Involved:\n")
        for person in summary_info['Persons Involved']:
            file.write(f"  - {person['name']} ({person['role']})\n    Email: {person['email']}\n    Phone: {person['phone']}\n")
        file.write("\nServers:\n")
        for server in summary_info['Servers']:
            file.write(f"  - {server}\n")
        file.write("\nRelated Tasks (CHG/INC/RITM/CTASK):\n")
        for task in summary_info['Related Tasks (CHG/INC/RITM/CTASK)']:
            file.write(f"  - {task}\n")
        file.write("\nAttachments:\n")
        for attachment in summary_info['Attachments']:
            file.write(f"  - {attachment}\n")
        file.write(f"\nAdvisory and Next Steps:\n{summary_info['Advisory and Next Steps']}\n")
        file.write(f"\nCurrent Status:\n{summary_info['Current Status']}\n")

# Function to generate PDF summary
def generate_pdf_summary(summary_info, output_file):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.multi_cell(0, 10, txt=f"Summary:\n{summary_info['Summary']}\n")
    pdf.ln(10)
    
    pdf.cell(200, 10, txt="Teams Involved:", ln=True)
    for team, members in summary_info['Teams Involved'].items():
        pdf.cell(200, 10, txt=f"{team}:", ln=True)
        for person in members:
            pdf.multi_cell(0, 10, txt=f"  - {person['name']} ({person['role']})\n    Email: {person['email']}\n    Phone: {person['phone']}")
    pdf.ln(10)
    
    pdf.cell(200, 10, txt="Servers:", ln=True)
    for server in summary_info['Servers']:
        pdf.cell(200, 10, txt=f"  - {server}", ln=True)
    pdf.ln(10)
    
    pdf.cell(200, 10, txt="Related Tasks (CHG/INC/RITM/CTASK):", ln=True)
    for task in summary_info['Related Tasks (CHG/INC/RITM/CTASK)']:
        pdf.cell(200, 10, txt=f"  - {task}", ln=True)
    pdf.ln(10)
    
    pdf.cell(200, 10, txt="Attachments:", ln=True)
    for attachment in summary_info['Attachments']:
        pdf.cell(200, 10, txt=f"  - {attachment}", ln=True)
    pdf.ln(10)
    
    pdf.cell(200, 10, txt=f"Advisory and Next Steps: {summary_info['Advisory and Next Steps']}", ln=True)
    pdf.ln(10)
    
    pdf.cell(200, 10, txt=f"Current Status: {summary_info['Current Status']}", ln=True)
    
    pdf.output(output_file)

# Main function to analyze the email chain
def analyze_email_chain(file_path, output_txt, output_pdf):
    text = read_file(file_path)
    summary_info = extract_information(text)
    
    generate_txt_summary(summary_info, output_txt)
    generate_pdf_summary(summary_info, output_pdf)

# Example usage
if __name__ == "__main__":
    # Input and output file paths
    input_file = "Email_Content_RITM2242575.txt"  # It could be .txt or .pdf
    output_txt = "email_chain_summary.txt"
    output_pdf = "email_chain_summary.pdf"
    
    # Analyze the email chain and generate the summary
    analyze_email_chain(input_file, output_txt, output_pdf)
