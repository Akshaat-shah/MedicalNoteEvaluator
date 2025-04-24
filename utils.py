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
        'Assessment_Plan': []
    }
    
    # Extract checkboxes (assume they have class or id with 'checkbox')
    checkboxes = soup.find_all('input', type='checkbox')
    for checkbox in checkboxes:
        name = checkbox.get('name', checkbox.get('id', 'Unknown'))
        checked = checkbox.get('checked') is not None
        data['Checkboxes'][name] = checked
    
    # Extract Past Medical History (PMHx)
    pmhx_section = soup.find(id='pmhx') or soup.find(class_='pmhx') or soup.find(string=lambda text: text and 'Past Medical History' in text)
    if pmhx_section:
        # Try to find parent element or sibling list/div
        parent = pmhx_section.parent
        list_items = parent.find_all('li')
        if list_items:
            data['PMHx'] = [item.get_text().strip() for item in list_items]
        else:
            # Alternative approach if no list items found
            paragraphs = parent.find_all('p')
            if paragraphs:
                data['PMHx'] = [p.get_text().strip() for p in paragraphs]
    
    # Extract Review of Systems (ROS)
    ros_section = soup.find(id='ros') or soup.find(class_='ros') or soup.find(string=lambda text: text and 'Review of Systems' in text)
    if ros_section:
        # Find parent or containing section
        parent = ros_section.parent
        # Look for system headings and their values
        headings = parent.find_all(['h3', 'h4', 'strong', 'b'])
        for heading in headings:
            system = heading.get_text().strip()
            # Get the next sibling paragraph or div with the findings
            next_elem = heading.find_next(['p', 'div', 'span'])
            if next_elem:
                data['ROS'][system] = next_elem.get_text().strip()
    
    # Extract Examination findings
    exam_section = soup.find(id='exam') or soup.find(class_='exam') or soup.find(string=lambda text: text and 'Examination' in text)
    if exam_section:
        parent = exam_section.parent
        # Look for exam components
        components = parent.find_all(['h3', 'h4', 'strong', 'b']) 
        for component in components:
            system = component.get_text().strip()
            # Get the findings that follow each component
            next_elem = component.find_next(['p', 'div', 'span'])
            if next_elem:
                data['Exam'][system] = next_elem.get_text().strip()
    
    # Extract Assessment and Plan
    ap_section = soup.find(id='assessment') or soup.find(class_='assessment') or soup.find(string=lambda text: text and ('Assessment' in text or 'Plan' in text))
    if ap_section:
        parent = ap_section.parent
        # Try to find numbered or bulleted list items
        list_items = parent.find_all('li')
        if list_items:
            data['Assessment_Plan'] = [item.get_text().strip() for item in list_items]
        else:
            # If no list, try paragraphs
            paragraphs = parent.find_all('p')
            if paragraphs:
                data['Assessment_Plan'] = [p.get_text().strip() for p in paragraphs]
    
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
