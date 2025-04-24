import streamlit as st
import pandas as pd
import io
from bs4 import BeautifulSoup
from langchain.prompts import ChatPromptTemplate
from langchain_community.chat_models import ChatOpenAI
import os
import json
from utils import extract_data_from_html

# Set page configuration
st.set_page_config(
    page_title="Medical Note Accuracy Evaluator",
    page_icon="🏥",
    layout="wide"
)

# App title and description
st.title("Medical Note Accuracy Evaluator")
st.markdown("""
    This application uses AI to evaluate the accuracy of physician-generated HTML notes 
    compared to expert feedback data. Upload your files to get an accuracy score and detailed explanation.
""")

# Initialize session state variables if they don't exist
if 'html_content' not in st.session_state:
    st.session_state.html_content = None
if 'feedback_data' not in st.session_state:
    st.session_state.feedback_data = None
if 'excel_sheets' not in st.session_state:
    st.session_state.excel_sheets = []
if 'selected_sheet' not in st.session_state:
    st.session_state.selected_sheet = None
if 'extracted_html_data' not in st.session_state:
    st.session_state.extracted_html_data = None
if 'accuracy_scores' not in st.session_state:
    st.session_state.accuracy_scores = None
if 'explanation' not in st.session_state:
    st.session_state.explanation = None
if 'html_filename' not in st.session_state:
    st.session_state.html_filename = None
if 'excel_filename' not in st.session_state:
    st.session_state.excel_filename = None

# File uploaders
col1, col2 = st.columns(2)

with col1:
    html_file = st.file_uploader("Upload physician note (HTML file)", type=['html'])
    if html_file and html_file.name != st.session_state.html_filename:
        st.session_state.html_filename = html_file.name
        st.session_state.html_content = html_file.read().decode("utf-8")
        soup = BeautifulSoup(st.session_state.html_content, 'html.parser')
        st.session_state.extracted_html_data = extract_data_from_html(soup)
        # Reset results when a new file is uploaded
        st.session_state.accuracy_scores = None
        st.session_state.explanation = None
    
with col2:
    excel_file = st.file_uploader("Upload feedback data (Excel file)", type=['xlsx'])
    if excel_file and excel_file.name != st.session_state.excel_filename:
        st.session_state.excel_filename = excel_file.name
        
        # Read all sheets from the Excel file
        excel = pd.ExcelFile(excel_file)
        st.session_state.excel_sheets = excel.sheet_names
        
        # Default to the first sheet
        if st.session_state.excel_sheets:
            st.session_state.selected_sheet = st.session_state.excel_sheets[0]
            st.session_state.feedback_data = pd.read_excel(excel, sheet_name=st.session_state.selected_sheet)
        
        # Reset results when a new file is uploaded
        st.session_state.accuracy_scores = None
        st.session_state.explanation = None

# Sheet selector if multiple sheets exist
if st.session_state.excel_sheets and len(st.session_state.excel_sheets) > 1:
    selected_sheet = st.selectbox(
        "Select Excel Sheet",
        st.session_state.excel_sheets,
        index=st.session_state.excel_sheets.index(st.session_state.selected_sheet) if st.session_state.selected_sheet else 0
    )
    
    if selected_sheet != st.session_state.selected_sheet:
        st.session_state.selected_sheet = selected_sheet
        # Re-read the Excel data with the selected sheet
        excel_file = pd.ExcelFile(excel_file)
        st.session_state.feedback_data = pd.read_excel(excel_file, sheet_name=selected_sheet)
        # Reset results when a new sheet is selected
        st.session_state.accuracy_scores = None
        st.session_state.explanation = None

# Display extracted HTML data if available
if st.session_state.extracted_html_data:
    with st.expander("View Extracted HTML Data", expanded=False):
        st.subheader("Data from HTML Note")
        # Convert nested dictionaries to string for display
        html_data_display = {}
        for key, value in st.session_state.extracted_html_data.items():
            if isinstance(value, dict):
                html_data_display[key] = str(value)
            else:
                html_data_display[key] = value
                
        html_data_df = pd.DataFrame([html_data_display])
        st.dataframe(html_data_df.T, height=300)

# Display feedback data if available
if st.session_state.feedback_data is not None:
    with st.expander("View Feedback Data", expanded=False):
        st.subheader(f"Feedback Data (Sheet: {st.session_state.selected_sheet})")
        st.dataframe(st.session_state.feedback_data, height=300)

# Evaluate accuracy if both files are uploaded
if st.session_state.html_content and st.session_state.feedback_data is not None:
    if st.button("Evaluate Note Accuracy"):
        with st.spinner("Analyzing note accuracy..."):
            # Get OpenAI API key from environment
            openai_api_key = os.environ.get("OPENAI_API_KEY")
            
            if not openai_api_key:
                st.error("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
            else:
                # Prepare data for LLM
                # Convert extracted HTML data to a readable format
                html_data_str = ""
                for section, content in st.session_state.extracted_html_data.items():
                    html_data_str += f"\n## {section}:\n"
                    if isinstance(content, dict):
                        for key, value in content.items():
                            html_data_str += f"- {key}: {value}\n"
                    elif isinstance(content, list):
                        for item in content:
                            html_data_str += f"- {item}\n"
                    else:
                        html_data_str += f"{content}\n"
                
                # Convert feedback data to a readable format
                feedback_str = st.session_state.feedback_data.to_string()
                
                # Create a prompt for the LLM with structured JSON output format
                template = """
                You are a medical documentation quality auditor. You need to evaluate the accuracy of a generated physician note (in HTML) against expert feedback in an Excel spreadsheet.

                HTML NOTE CONTENT:
                {html_data}

                FEEDBACK DATA:
                {feedback_data}

                Instructions:
                1. Focus ONLY on these 6 specific sections: Subjective, Review Of Systems, Vitals, Labs, Assessment & Plan, Code Status
                2. For each of these sections, calculate accuracy based on the "Comments" column and "Status" column in the feedback data
                3. If the Status is "Correct", assign 100% accuracy
                4. If the Status has issues mentioned in Comments, assign a lower accuracy score based on severity:
                   - Low severity issues: 80-90%
                   - Medium severity issues: 60-80%
                   - High severity issues: <60%
                   - If Status is "Incorrect": Maximum 50%
                5. Calculate an overall accuracy score as the average of these 6 sections (only count sections that exist)
                6. For each section, analyze what was correct and what needs improvement based on the comments

                Respond with a JSON object with the following structure:
                {{
                  "overall_accuracy_score": number,  // The overall accuracy percentage (0-100)
                  "section_scores": {{
                    "Subjective": number,  // Section accuracy percentage (0-100)
                    "Review Of Systems": number,
                    "Vitals": number,
                    "Labs": number,
                    "Assessment & Plan": number,
                    "Code Status": number
                  }},
                  "explanation": string,     // Detailed explanation of the overall evaluation
                  "section_analyses": {{
                    "Subjective": string,  // Analysis for this section based on comments
                    "Review Of Systems": string,
                    "Vitals": string,
                    "Labs": string,
                    "Assessment & Plan": string,
                    "Code Status": string
                  }},
                  "strengths": [string],     // List of strengths in the note
                  "weaknesses": [string],    // List of weaknesses in the note
                  "improvement_suggestions": [string]  // Suggestions for improving accuracy
                }}
                
                Ensure the accuracy scores are numbers between 0 and 100 representing percentage accuracy.
                If a section is missing from the feedback data or HTML, mark it as "not evaluated" in the analysis 
                and don't include it in the overall score calculation.
                """
                
                # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
                # do not change this unless explicitly requested by the user
                prompt = ChatPromptTemplate.from_template(template)
                llm = ChatOpenAI(
                    model="gpt-4o", 
                    openai_api_key=openai_api_key, 
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                
                # Create the chain using the newer pipe operator pattern
                chain = prompt | llm
                
                # Run the chain
                response = chain.invoke({
                    "html_data": html_data_str,
                    "feedback_data": feedback_str
                })
                
                # Extract the JSON content
                try:
                    result = json.loads(response.content)
                    st.session_state.accuracy_scores = {
                        "overall": result.get("overall_accuracy_score"),
                        "sections": result.get("section_scores", {})
                    }
                    st.session_state.explanation = result
                except Exception as e:
                    st.error(f"Error parsing LLM response: {e}")
                    st.session_state.explanation = response.content

# Display results if available
if st.session_state.accuracy_scores and st.session_state.explanation:
    st.header("Accuracy Evaluation Results")
    
    # Display overall accuracy score
    st.subheader(f"Overall Accuracy Score: {st.session_state.accuracy_scores['overall']}%")
    
    # Display section-by-section accuracy scores
    if st.session_state.accuracy_scores.get("sections"):
        st.subheader("Section-by-Section Accuracy")
        
        # Create a bar chart for section scores
        section_scores = st.session_state.accuracy_scores["sections"]
        sections_df = pd.DataFrame({
            "Section": list(section_scores.keys()),
            "Accuracy (%)": list(section_scores.values())
        })
        
        st.bar_chart(sections_df.set_index("Section"))
        
        # Display section analysis
        st.subheader("Section-by-Section Analysis")
        section_analyses = st.session_state.explanation.get("section_analyses", {})
        
        for section, analysis in section_analyses.items():
            with st.expander(f"{section} - {section_scores.get(section, 'N/A')}% Accurate"):
                st.markdown(analysis)
    
    # Use columns for strengths and weaknesses
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Strengths")
        strengths = st.session_state.explanation.get("strengths", [])
        for strength in strengths:
            st.markdown(f"✓ {strength}")
    
    with col2:
        st.subheader("Weaknesses")
        weaknesses = st.session_state.explanation.get("weaknesses", [])
        for weakness in weaknesses:
            st.markdown(f"× {weakness}")
    
    # Display detailed explanation
    st.subheader("Overall Analysis")
    st.markdown(st.session_state.explanation.get("explanation", ""))
    
    # Display improvement suggestions
    st.subheader("Improvement Suggestions")
    suggestions = st.session_state.explanation.get("improvement_suggestions", [])
    for suggestion in suggestions:
        st.markdown(f"→ {suggestion}")
    
    # Generate downloadable report
    section_report = ""
    if st.session_state.accuracy_scores.get("sections"):
        section_report = "## Section-by-Section Scores\n"
        for section, score in st.session_state.accuracy_scores["sections"].items():
            section_report += f"- {section}: {score}%\n"
        
        # Get section analyses from explanation
        section_analyses = st.session_state.explanation.get("section_analyses", {})
        
        section_report += "\n## Section-by-Section Analysis\n"
        for section, analysis in section_analyses.items():
            section_report += f"### {section}\n{analysis}\n\n"
    
    report = f"""# Medical Note Accuracy Evaluation Report

## Overall Accuracy Score: {st.session_state.accuracy_scores['overall']}%

{section_report}

## Overall Analysis
{st.session_state.explanation.get("explanation", "")}

## Strengths
{chr(10).join(['- ' + s for s in strengths])}

## Weaknesses
{chr(10).join(['- ' + w for w in weaknesses])}

## Improvement Suggestions
{chr(10).join(['- ' + s for s in suggestions])}
"""
    
    # Download button
    st.download_button(
        label="Download Evaluation Report",
        data=report,
        file_name="medical_note_accuracy_evaluation.txt",
        mime="text/plain"
    )
    
# Show instructions if no files are uploaded
if not html_file or not excel_file:
    st.info("Please upload both the HTML medical note and Excel feedback file to begin analysis.")
    
    with st.expander("Instructions"):
        st.markdown("""
        ### How to use this app
        
        1. **Upload HTML File**: This should be the physician-generated note in HTML format
        2. **Upload Excel File**: This should contain the expert feedback data for the note
           - If your Excel file has multiple sheets, you can select which one to use
           - The Excel should have columns for Section, Status (correct/incorrect), and Comments
        3. **Click "Evaluate Note Accuracy"**: The app will use AI to analyze the content and provide:
           - An overall accuracy percentage score based on 6 key sections:
             * Subjective
             * Review Of Systems
             * Vitals
             * Labs
             * Assessment & Plan
             * Code Status
           - Section-by-section accuracy scores based on the Comments and Status columns
           - Detailed analysis of what was correct/incorrect in each section
           - Strengths and weaknesses of the note
           - Improvement suggestions
        4. **Download Report**: Save the complete evaluation as a text file
        """)
