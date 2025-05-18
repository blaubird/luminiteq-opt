"""
Simple test script to validate the bulk FAQ import functionality.
Run this script to test the bulk import endpoint.
"""

import requests
import json
import time

# Configuration
BASE_URL = "http://api.luminiteq.eu/"  # Change to your API URL
ADMIN_TOKEN = "lumi-zelensky_god!1"    # Change to your admin token
TENANT_ID = "test_faq_tenant"           # Change to an existing tenant ID

headers = {
    "X-Admin-Token": ADMIN_TOKEN,
    "Content-Type": "application/json"
}

def test_bulk_import():
    """Test bulk FAQ import functionality"""
    print("\n=== Testing Bulk FAQ Import ===")
    
    # Sample data for bulk import
    import_data = {
        "items": [
            {
                "question": "What is your return policy?",
                "answer": "You can return any item within 30 days of purchase with a receipt."
            },
            {
                "question": "How do I track my order?",
                "answer": "You can track your order by logging into your account and viewing your order history."
            },
            {
                "question": "Do you ship internationally?",
                "answer": "Yes, we ship to most countries worldwide. Shipping costs vary by location."
            }
        ]
    }
    
    # Send bulk import request
    response = requests.post(
        f"{BASE_URL}/admin/tenants/{TENANT_ID}/faq/bulk-import/",
        headers=headers,
        json=import_data
    )
    
    print(f"Bulk import request status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Total items: {data['total_items']}")
        print("Import started in background. Waiting for processing...")
        
        # Wait a bit for background processing
        time.sleep(5)
        
        # Check if FAQs were imported by listing them
        check_response = requests.get(
            f"{BASE_URL}/admin/tenants/{TENANT_ID}/faq/",
            headers=headers
        )
        
        if check_response.status_code == 200:
            check_data = check_response.json()
            print(f"Found {check_data['total']} FAQs after import")
        else:
            print(f"Failed to check FAQs: {check_response.status_code}")
    else:
        print(f"Bulk import failed: {response.text}")

if __name__ == "__main__":
    print("Starting bulk import validation test...")
    test_bulk_import()
    print("\nBulk import validation test completed.")
