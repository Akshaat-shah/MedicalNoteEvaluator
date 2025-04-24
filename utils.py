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
    data = {
        'Checkboxes': {},
        'PMHx': [],
        'ROS': {},
        'Exam': {},
        'Assessment_Plan': [],
        'Labs': {}
    }
    
    # Extract checkboxes (assume they have input type='checkbox')
    checkboxes = soup.find_all('input', type='checkbox')
    for checkbox in checkboxes:
        # Try to find label text by looking at previous and next text nodes
        if checkbox.parent and checkbox.parent.get_text():
            label_text = checkbox.parent.get_text().strip()
            # Extract just the label part (remove Yes/No if present)
            if ":" in label_text:
                label_parts = label_text.split(":")
                label = label_parts[0].strip()
            else:
                # Just use the full text as a fallback
                label = label_text.strip()
                
            # Clean up the label if needed
            label = label.replace("Yes", "").replace("No", "").strip()
            
            # If label is empty, try to use adjacent text
            if not label:
                # Try using text before checkbox
                prev_sibling = checkbox.previous_sibling
                if prev_sibling and prev_sibling.string:
                    label = prev_sibling.string.strip()
                # If still empty, use next sibling text
                if not label:
                    next_sibling = checkbox.next_sibling
                    if next_sibling and next_sibling.string:
                        label = next_sibling.string.strip()
            
            # Check if we're dealing with a Yes/No pair
            if label in ["Yes", "No"]:
                # Find the previous label
                if checkbox.parent and checkbox.parent.previous_sibling:
                    prev_elem = checkbox.parent.previous_sibling
                    if prev_elem.string:
                        label = prev_elem.string.strip()
        else:
            # Fallback if no parent text found
            label = checkbox.get('name', checkbox.get('id', 'Unknown'))
        
        # Get checkbox state
        checked = checkbox.get('checked') is not None
        
        # Add to data
        data['Checkboxes'][label] = checked
    
    # Find and extract subjective section containing PMHx
    subjective_section = soup.find(string=lambda text: text and "Subjective" in text)
    if subjective_section:
        section_div = subjective_section.find_parent("div")
        if section_div:
            # Find the paragraph containing PMHx info
            pmhx_paragraph = section_div.find("p")
            if pmhx_paragraph:
                pmhx_text = pmhx_paragraph.get_text().strip()
                if "PMHx" in pmhx_text:
                    # Extract PMHx items from the text
                    # Split by commas and identify medical conditions
                    pmhx_items = [item.strip() for item in pmhx_text.split(",")]
                    data['PMHx'] = pmhx_items
                else:
                    # Just add the whole paragraph as a single item
                    data['PMHx'] = [pmhx_text]
    
    # Extract Review of Systems (ROS) from the ROS section
    ros_section = soup.find(string=lambda text: text and "Review of Systems" in text)
    if ros_section:
        section_div = ros_section.find_parent("div")
        if section_div:
            # Find all checkbox elements in the ROS section
            ros_checkboxes = section_div.find_all("input", type="checkbox")
            for checkbox in ros_checkboxes:
                next_sibling = checkbox.next_sibling
                if next_sibling and next_sibling.string:
                    symptom = next_sibling.string.strip()
                    checked = checkbox.get('checked') is not None
                    data['ROS'][symptom] = checked
    
    # Extract Exam findings
    exam_section = soup.find(string=lambda text: text and "Exam" in text)
    if exam_section:
        section_div = exam_section.find_parent("div")
        if section_div:
            # Extract vitals
            vitals_text = section_div.find(string=lambda text: text and "Vitals:" in text)
            if vitals_text:
                vitals_line = vitals_text.find_parent().get_text().strip()
                data['Exam']['Vitals'] = vitals_line
            
            # Extract other exam findings by category
            categories = ["HEENT", "Chest", "CVS", "Abdomen", "Edema", "Neuro", "Skin Issues"]
            for category in categories:
                category_line = section_div.find(string=lambda text: text and category in text)
                if category_line:
                    parent_elem = category_line.find_parent()
                    checkboxes = parent_elem.find_all("input", type="checkbox")
                    findings = []
                    for checkbox in checkboxes:
                        if checkbox.get('checked') is not None:
                            next_sibling = checkbox.next_sibling
                            if next_sibling and next_sibling.string:
                                findings.append(next_sibling.string.strip())
                    
                    data['Exam'][category] = ", ".join(findings) if findings else "None documented"
    
    # Extract Labs
    labs_section = soup.find(string=lambda text: text and "Labs" in text)
    if labs_section:
        section_div = labs_section.find_parent("div")
        if section_div:
            lab_lines = section_div.find_all("div")
            for line in lab_lines:
                text = line.get_text().strip()
                # Check for lab values
                if ":" in text:
                    lab_pairs = text.split("|")
                    for pair in lab_pairs:
                        if ":" in pair:
                            lab_name, lab_value = pair.split(":", 1)
                            lab_name = lab_name.strip()
                            lab_value = lab_value.strip()
                            if lab_value:  # Only add if there's a value
                                data['Labs'][lab_name] = lab_value
                
                # Check for No New Labs checkbox
                no_labs_checkbox = line.find("input", type="checkbox", checked=True)
                if no_labs_checkbox and "No New Labs" in text:
                    data['Labs']['No New Labs'] = True
    
    # Extract Assessment and Plan (may be at the end of the document)
    assessment_section = soup.find(string=lambda text: text and "Assessment" in text)
    if assessment_section:
        section_div = assessment_section.find_parent("div")
        if section_div:
            plan_items = section_div.find_all(["p", "li", "pre"])
            for item in plan_items:
                text = item.get_text().strip()
                if text and not text.startswith("Assessment"):  # Skip the heading
                    data['Assessment_Plan'].append(text)
    
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
    
    # Process checkboxes
    for key, value in html_data['Checkboxes'].items():
        flat_html_data[f"Checkbox: {key}"] = str(value)
    
    # Process PMHx
    for i, item in enumerate(html_data['PMHx']):
        flat_html_data[f"PMHx: {i+1}"] = item
    
    # Process ROS
    for system, findings in html_data['ROS'].items():
        flat_html_data[f"ROS: {system}"] = findings
    
    # Process Exam
    for component, findings in html_data['Exam'].items():
        flat_html_data[f"Exam: {component}"] = findings
    
    # Process Assessment and Plan
    for i, item in enumerate(html_data['Assessment_Plan']):
        flat_html_data[f"A&P: {i+1}"] = item
        
    # Process Labs
    for lab_name, lab_value in html_data['Labs'].items():
        flat_html_data[f"Labs: {lab_name}"] = lab_value
    
    # Iterate through feedback data and compare with HTML data
    for _, row in feedback_df.iterrows():
        category = row.get('Category', 'Unknown')
        field = row.get('Field', 'Unknown')
        expected_value = row.get('Expected Value', '')
        
        # Construct the key to look up in flat_html_data
        key = f"{category}: {field}"
        
        # Check if the key exists in HTML data
        if key in flat_html_data:
            actual_value = flat_html_data[key]
            # Compare values
            if str(actual_value).lower() == str(expected_value).lower():
                status = "✅ Match"
            else:
                status = "❌ Mismatch"
            
            results.append({
                'Category': category,
                'Field': field,
                'Expected Value': expected_value,
                'Actual Value': actual_value,
                'Status': status
            })
            
            # Remove the key from flat_html_data after processing
            del flat_html_data[key]
        else:
            # Item is missing in HTML data
            results.append({
                'Category': category,
                'Field': field,
                'Expected Value': expected_value,
                'Actual Value': "",
                'Status': "➖ Missing"
            })
    
    # Add remaining HTML data items as "Extra"
    for key, value in flat_html_data.items():
        category, field = key.split(': ', 1)
        results.append({
            'Category': category,
            'Field': field,
            'Expected Value': "",
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
