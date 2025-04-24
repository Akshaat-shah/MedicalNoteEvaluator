import streamlit as st
import pandas as pd
import io
from bs4 import BeautifulSoup
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.chains import LLMChain
import os
from utils import (
    extract_data_from_html, 
    compare_data_to_feedback, 
    calculate_accuracy_metrics,
    generate_csv_report
)

# Set page configuration
st.set_page_config(
    page_title="Medical Note Feedback Evaluator",
    page_icon="🏥",
    layout="wide"
)

# App title and description
st.title("Medical Note Feedback Evaluator")
st.markdown("""
    This application compares physician-generated HTML notes against Excel feedback data,
    evaluates accuracy, and provides AI-powered explanations for discrepancies.
""")

# Initialize session state variables if they don't exist
if 'html_data' not in st.session_state:
    st.session_state.html_data = None
if 'feedback_data' not in st.session_state:
    st.session_state.feedback_data = None
if 'comparison_results' not in st.session_state:
    st.session_state.comparison_results = None
if 'accuracy_metrics' not in st.session_state:
    st.session_state.accuracy_metrics = None
if 'explanation' not in st.session_state:
    st.session_state.explanation = None
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False

# File uploaders
col1, col2 = st.columns(2)

with col1:
    html_file = st.file_uploader("Upload physician note (HTML file)", type=['html'])
    
with col2:
    excel_file = st.file_uploader("Upload feedback data (Excel file)", type=['xlsx'])

# Process files when both are uploaded
if html_file and excel_file:
    # Process HTML file
    html_content = html_file.read().decode("utf-8")
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract data from HTML
    st.session_state.html_data = extract_data_from_html(soup)
    
    # Process Excel file
    feedback_data = pd.read_excel(excel_file)
    st.session_state.feedback_data = feedback_data
    
    # Compare HTML data to feedback data
    st.session_state.comparison_results = compare_data_to_feedback(
        st.session_state.html_data, 
        st.session_state.feedback_data
    )
    
    # Calculate accuracy metrics
    st.session_state.accuracy_metrics = calculate_accuracy_metrics(st.session_state.comparison_results)
    
    # Mark analysis as complete
    st.session_state.analysis_complete = True

# Display results if analysis is complete
if st.session_state.analysis_complete:
    st.header("Analysis Results")
    
    # Display extracted HTML data
    st.subheader("Data from HTML Note")
    html_data_df = pd.DataFrame([st.session_state.html_data])
    st.dataframe(html_data_df.T, height=300)
    
    # Display accuracy metrics
    st.subheader("Accuracy Metrics")
    metrics_col1, metrics_col2, metrics_col3, metrics_col4, metrics_col5 = st.columns(5)
    
    with metrics_col1:
        st.metric("Total Items", st.session_state.accuracy_metrics["total"])
    with metrics_col2:
        st.metric("✅ Matches", st.session_state.accuracy_metrics["match"])
    with metrics_col3:
        st.metric("❌ Mismatches", st.session_state.accuracy_metrics["mismatch"])
    with metrics_col4:
        st.metric("➕ Extra", st.session_state.accuracy_metrics["extra"])
    with metrics_col5:
        st.metric("➖ Missing", st.session_state.accuracy_metrics["missing"])
    
    # Display comparison results
    st.subheader("Comparison Results")
    
    # Style the dataframe
    def color_status(val):
        colors = {
            '✅ Match': 'background-color: #D4EDDA',  # Light green
            '❌ Mismatch': 'background-color: #F8D7DA',  # Light red
            '➕ Extra': 'background-color: #D1ECF1',  # Light blue
            '➖ Missing': 'background-color: #FFF3CD'  # Light yellow
        }
        return colors.get(val, '')
    
    # Convert results to dataframe and display
    results_df = pd.DataFrame(st.session_state.comparison_results)
    st.dataframe(results_df.style.applymap(color_status, subset=['Status']), height=400)
    
    # Generate LLM explanation
    if st.button("Generate AI Explanation of Discrepancies"):
        with st.spinner("Generating explanation..."):
            # Get OpenAI API key from environment
            openai_api_key = os.environ.get("OPENAI_API_KEY")
            
            if not openai_api_key:
                st.error("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
            else:
                # Prepare data for LLM
                mismatches = results_df[results_df['Status'] == '❌ Mismatch'].to_dict('records')
                missing = results_df[results_df['Status'] == '➖ Missing'].to_dict('records')
                extra = results_df[results_df['Status'] == '➕ Extra'].to_dict('records')
                
                # Create a prompt for the LLM
                template = """
                You are a medical QA assistant. Based on the HTML note and the feedback table, explain why any mismatches or errors occurred in the generated content.
                
                MISMATCHES (items with different values):
                {mismatches}
                
                MISSING (items present in feedback but not in HTML):
                {missing}
                
                EXTRA (items present in HTML but not in feedback):
                {extra}
                
                Please provide a clear, concise explanation of:
                1. What types of errors occurred
                2. Potential reasons for these discrepancies 
                3. Suggestions for improving the accuracy of the notes
                """
                
                # Create LangChain components
                # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
                # do not change this unless explicitly requested by the user
                prompt = ChatPromptTemplate.from_template(template)
                llm = ChatOpenAI(model="gpt-4o", openai_api_key=openai_api_key, temperature=0)
                chain = LLMChain(llm=llm, prompt=prompt)
                
                # Run the chain
                response = chain.run(
                    mismatches=str(mismatches),
                    missing=str(missing),
                    extra=str(extra)
                )
                
                st.session_state.explanation = response
        
    # Display explanation if available
    if st.session_state.explanation:
        st.subheader("AI Explanation")
        st.info(st.session_state.explanation)
    
    # Generate and download CSV report
    csv_data = generate_csv_report(results_df)
    
    st.download_button(
        label="Download Results as CSV",
        data=csv_data,
        file_name="medical_note_evaluation.csv",
        mime="text/csv"
    )
    
# Show instructions if no files are uploaded
if not html_file or not excel_file:
    st.info("Please upload both the HTML medical note and Excel feedback file to begin analysis.")
    
    with st.expander("Instructions"):
        st.markdown("""
        ### How to use this app
        
        1. **Upload HTML File**: This should be the physician-generated note in HTML format
        2. **Upload Excel File**: This should contain the feedback data with expected values
        3. **View Results**: The app will automatically analyze and display:
           - Extracted data from the HTML note
           - Comparison between note and feedback
           - Accuracy metrics (matches, mismatches, extra, missing)
        4. **Generate AI Explanation**: Get an AI-powered analysis of discrepancies
        5. **Download Report**: Save the complete analysis as a CSV file
        """)
