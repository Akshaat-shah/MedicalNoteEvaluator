import pandas as pd
import io
from bs4 import BeautifulSoup

def extract_data_from_html(soup):
    """
    Extract medical note data from HTML using BeautifulSoup.
    
    Args:
        soup: BeautifulSoup object of the HTML content
        
    Returns:
        Dictionary with extracted data categories
    """
    # Initialize data structure for all possible sections
    data = {}
    
    # Find all section divs with class 'section'
    sections = soup.find_all('div', class_='section')
    
    # Process each section
    for section in sections:
        # Find the section title
        section_title_div = section.find('div', class_='section-title')
        if not section_title_div:
            continue
            
        section_title = section_title_div.get_text().strip()
        section_content_div = section_title_div.find_next_sibling('div')
        
        if not section_content_div:
            continue
            
        section_content = section_content_div.get_text().strip()
        
        # Store section content in our data dictionary
        data[section_title] = section_content
        
    # Extract "Patient Seen & Examined" and "Relevant History Taken" checkboxes
    first_section = soup.find('div', class_=None)
    if first_section:
        checkbox_text = first_section.get_text().strip()
        
        # Check for "Patient Seen & Examined"
        if "Patient Seen & Examined" in checkbox_text:
            data["Patient Seen & Examined"] = "Checked" if first_section.find('input', {'type': 'checkbox', 'checked': True}) else "Unchecked"
            
        # Check for "Relevant History Taken"
        if "Relevant History Taken" in checkbox_text:
            data["Relevant History Taken"] = "Checked" if first_section.find_all('input', {'type': 'checkbox', 'checked': True}) else "Unchecked"
    
    # Process Review of Systems section separately due to its checkbox structure
    ros_section = soup.find('div', class_='section-title', string='Review of Systems:')
    if ros_section:
        ros_content = ros_section.find_parent('div', class_='section')
        if ros_content:
            # Process all checkboxes in ROS section
            ros_data = {}
            
            # Get all checkboxes and their labels
            checkboxes = ros_content.find_all('input', type='checkbox')
            for checkbox in checkboxes:
                # Try to get the label by looking at the next sibling
                label = None
                next_sibling = checkbox.next_sibling
                if next_sibling and next_sibling.string:
                    label = next_sibling.string.strip()
                
                # If no label found, use parent text
                if not label and checkbox.parent:
                    parent_text = checkbox.parent.get_text().strip()
                    # Extract the label part (remove extra whitespace)
                    label = parent_text.replace('Yes', '').replace('No', '').strip()
                
                # Set the status based on checked attribute
                checked = checkbox.get('checked') is not None
                
                if label:
                    ros_data[label] = "Checked" if checked else "Unchecked"
            
            data['ROS'] = ros_data
    
    # Process Exam section separately due to its checkbox structure
    exam_section = soup.find('div', class_='section-title', string='Exam')
    if exam_section:
        exam_content = exam_section.find_parent('div', class_='section')
        if exam_content:
            exam_data = {}
            
            # Extract vitals
            vitals_span = exam_content.find('span', string=lambda s: s and 'Vitals:' in s)
            if vitals_span:
                vitals_text = vitals_span.find_parent().get_text().strip()
                exam_data['Vitals'] = vitals_text
            
            # Process exam sections
            for category in ["HEENT", "Chest", "CVS", "Abdomen", "Edema", "Neuro", "Skin Issues"]:
                category_text = exam_content.find(string=lambda s: s and category in s)
                if category_text:
                    line = category_text.find_parent()
                    
                    # Find all checked checkboxes in this section
                    checked_items = []
                    checkboxes = line.find_all('input', type='checkbox', checked=True)
                    
                    for checkbox in checkboxes:
                        next_sibling = checkbox.next_sibling
                        if next_sibling and next_sibling.string:
                            checked_items.append(next_sibling.string.strip())
                    
                    exam_data[category] = ", ".join(checked_items) if checked_items else "None"
            
            data['Exam'] = exam_data
            
    # If any critical sections are missing, look for them using alternative approaches
    if 'HPI' not in data:
        hpi_section = soup.find(string=lambda s: s and 'HPI' in s)
        if hpi_section:
            hpi_div = hpi_section.find_parent('div')
            if hpi_div and 'section-title' in hpi_div.get('class', []):
                hpi_content = hpi_div.find_next_sibling('div')
                if hpi_content:
                    data['HPI'] = hpi_content.get_text().strip()
    
    if 'PMH' not in data:
        pmh_section = soup.find(string=lambda s: s and 'PMH' in s)
        if pmh_section:
            pmh_div = pmh_section.find_parent('div')
            if pmh_div and 'section-title' in pmh_div.get('class', []):
                pmh_content = pmh_div.find_next_sibling('div')
                if pmh_content:
                    data['PMH'] = pmh_content.get_text().strip()
    
    return data

def compare_data_to_feedback(html_data, feedback_df):
    """
    Compare extracted HTML data with feedback data from Excel.
    
    Args:
        html_data: Dictionary containing extracted HTML data
        feedback_df: Pandas DataFrame with feedback data
        
    Returns:
        List of dictionaries with comparison results
    """
    results = []
    
    # Create a flat representation of the HTML data for comparison
    flat_html_data = {}
    
    # Process all sections from the HTML data
    for section_name, section_content in html_data.items():
        if isinstance(section_content, dict):
            # If the section is a dictionary (like ROS or Exam)
            for key, value in section_content.items():
                flat_html_data[f"{section_name}: {key}"] = str(value)
        elif isinstance(section_content, list):
            # If the section is a list
            for i, item in enumerate(section_content):
                flat_html_data[f"{section_name}: {i+1}"] = str(item)
        else:
            # If the section is a string
            flat_html_data[f"{section_name}"] = str(section_content)
    
    # Iterate through feedback data and compare with HTML data
    for _, row in feedback_df.iterrows():
        # Check if the expected columns exist
        section = row.get('Section', row.get('Category', 'Unknown'))
        field = row.get('Field', '')
        expected_value = row.get('Final PN (manually Created)', row.get('Expected Value', ''))
        generated_value = row.get('Generated PN - 23-Apr', '')
        
        # Construct keys to look up in flat_html_data - try different possible formats
        keys_to_try = [
            f"{section}",
            f"{section}: {field}",
            section
        ]
        
        # Find if any key exists in flat_html_data
        matching_key = None
        for key in keys_to_try:
            if key in flat_html_data:
                matching_key = key
                break
        
        if matching_key:
            actual_value = flat_html_data[matching_key]
            # Compare values
            if str(actual_value).lower() == str(expected_value).lower():
                status = "✅ Match"
            else:
                status = "❌ Mismatch"
            
            results.append({
                'Section': section,
                'Field': field,
                'Expected Value': expected_value,
                'Generated Value': generated_value,
                'Actual Value': actual_value,
                'Status': status
            })
            
            # Remove the key from flat_html_data after processing
            del flat_html_data[matching_key]
        else:
            # Item is missing in HTML data
            results.append({
                'Section': section,
                'Field': field,
                'Expected Value': expected_value,
                'Generated Value': generated_value,
                'Actual Value': "",
                'Status': "➖ Missing"
            })
    
    # Add remaining HTML data items as "Extra"
    for key, value in flat_html_data.items():
        if ":" in key:
            section, field = key.split(':', 1)
            field = field.strip()
        else:
            section = key
            field = ""
            
        results.append({
            'Section': section,
            'Field': field,
            'Expected Value': "",
            'Generated Value': "",
            'Actual Value': value,
            'Status': "➕ Extra"
        })
    
    return results

def calculate_accuracy_metrics(comparison_results):
    """
    Calculate accuracy metrics from comparison results.
    
    Args:
        comparison_results: List of dictionaries with comparison results
        
    Returns:
        Dictionary with accuracy metrics
    """
    total = len(comparison_results)
    match_count = sum(1 for item in comparison_results if item['Status'] == "✅ Match")
    mismatch_count = sum(1 for item in comparison_results if item['Status'] == "❌ Mismatch")
    extra_count = sum(1 for item in comparison_results if item['Status'] == "➕ Extra")
    missing_count = sum(1 for item in comparison_results if item['Status'] == "➖ Missing")
    
    return {
        "total": total,
        "match": match_count,
        "mismatch": mismatch_count,
        "extra": extra_count,
        "missing": missing_count
    }

def generate_csv_report(results_df):
    """
    Generate a CSV report from the comparison results.
    
    Args:
        results_df: Pandas DataFrame with comparison results
        
    Returns:
        CSV data as string
    """
    # Create a buffer to hold the CSV data
    csv_buffer = io.StringIO()
    
    # Write DataFrame to CSV in the buffer
    results_df.to_csv(csv_buffer, index=False)
    
    # Get the CSV data as a string
    csv_data = csv_buffer.getvalue()
    
    return csv_data
