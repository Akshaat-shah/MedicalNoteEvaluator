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
if 'extracted_html_data' not in st.session_state:
    st.session_state.extracted_html_data = None
if 'accuracy_score' not in st.session_state:
    st.session_state.accuracy_score = None
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
        st.session_state.accuracy_score = None
        st.session_state.explanation = None
    
with col2:
    excel_file = st.file_uploader("Upload feedback data (Excel file)", type=['xlsx'])
    if excel_file and excel_file.name != st.session_state.excel_filename:
        st.session_state.excel_filename = excel_file.name
        st.session_state.feedback_data = pd.read_excel(excel_file)
        # Reset results when a new file is uploaded
        st.session_state.accuracy_score = None
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
        st.subheader("Feedback Data")
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
                You are a medical documentation quality auditor. You need to evaluate the accuracy of a generated physician note (in HTML) against expert feedback.

                HTML NOTE CONTENT:
                {html_data}

                FEEDBACK DATA:
                {feedback_data}

                Instructions:
                1. Compare the HTML note with the feedback data
                2. Identify what information is correct, incorrect, or missing
                3. Calculate an accuracy percentage score based on how well the HTML note matches the expert feedback
                4. Provide a detailed explanation of the strengths and weaknesses of the note
                5. Suggest improvements

                Respond with a JSON object with the following structure:
                {{
                  "accuracy_score": number,  // The accuracy percentage (0-100)
                  "explanation": string,     // Detailed explanation of the evaluation
                  "strengths": [string],     // List of strengths in the note
                  "weaknesses": [string],    // List of weaknesses in the note
                  "improvement_suggestions": [string]  // Suggestions for improving accuracy
                }}
                
                Ensure the accuracy_score is a number between 0 and 100 representing the percentage accuracy.
                Be thorough in your analysis, focusing on the medical content's accuracy.
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
                    st.session_state.accuracy_score = result.get("accuracy_score")
                    st.session_state.explanation = result
                except Exception as e:
                    st.error(f"Error parsing LLM response: {e}")
                    st.session_state.explanation = response.content

# Display results if available
if st.session_state.accuracy_score is not None and st.session_state.explanation:
    st.header("Accuracy Evaluation Results")
    
    # Display accuracy score
    st.subheader(f"Accuracy Score: {st.session_state.accuracy_score}%")
    
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
    st.subheader("Detailed Analysis")
    st.markdown(st.session_state.explanation.get("explanation", ""))
    
    # Display improvement suggestions
    st.subheader("Improvement Suggestions")
    suggestions = st.session_state.explanation.get("improvement_suggestions", [])
    for suggestion in suggestions:
        st.markdown(f"→ {suggestion}")
    
    # Generate downloadable report
    report = f"""# Medical Note Accuracy Evaluation Report

## Accuracy Score: {st.session_state.accuracy_score}%

## Detailed Analysis
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
        3. **Click "Evaluate Note Accuracy"**: The app will use AI to analyze the content and provide:
           - An accuracy percentage score
           - Strengths and weaknesses of the note
           - Detailed analysis of what was correct/incorrect
           - Improvement suggestions
        4. **Download Report**: Save the complete evaluation as a text file
        """)
