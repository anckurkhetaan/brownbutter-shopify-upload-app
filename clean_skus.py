#!/usr/bin/env python3
"""
BrownButter - SKU Cleaner
Cleans SKU values by replacing /n, hyphens, spaces with underscores
Updates Column B (SKU Clean) in Image Links tab
"""

import os
import sys
import json
import yaml
import gspread
from google.oauth2.service_account import Credentials
import re

def load_config():
    try:
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: config.yaml not found!")
        sys.exit(1)

def authenticate_sheets(config):
    try:
        # Check if running on Render (environment variable)
        google_creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        if google_creds_json:
            # Render deployment - use environment variable
            print("Using GOOGLE_CREDENTIALS_JSON from environment")
            import json
            creds_dict = json.loads(google_creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            # Local - use file
            creds_file = config['google_sheets']['credentials_file']
            print(f"Using credentials file: {creds_file}")
            creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        
        client = gspread.authorize(creds)
        print("✓ Authenticated with Google Sheets")
        return client
    except Exception as e:
        print(f"Error authenticating: {e}")
        sys.exit(1)

def open_spreadsheet(client, config):
    try:
        spreadsheet_name = config['google_sheets']['spreadsheet_name']
        print(f"Opening spreadsheet: {spreadsheet_name}...")
        sheet = client.open(spreadsheet_name)
        print(f"✓ Opened spreadsheet: {spreadsheet_name}")
        return sheet
    except Exception as e:
        print(f"Error opening spreadsheet: {e}")
        sys.exit(1)

def clean_sku(sku):
    """
    Clean SKU by:
    - Removing /n (newlines) and extra whitespace
    - Replacing hyphens with underscores
    - Replacing spaces with underscores
    - Removing special characters like # @ $ %
    """
    if not sku:
        return ""
    
    # First strip all leading/trailing whitespace
    cleaned = sku.strip()
    
    # Remove /n and actual newlines
    cleaned = cleaned.replace('/n', '').replace('\n', '').replace('\r', '')
    
    # Remove special characters (keep only letters, numbers, hyphens, spaces, underscores)
    cleaned = re.sub(r'[^\w\s\-]', '', cleaned)
    
    # Replace hyphens and spaces with underscores
    cleaned = cleaned.replace('-', '_').replace(' ', '_')
    
    # Remove any duplicate underscores
    cleaned = re.sub(r'_+', '_', cleaned)
    
    # Strip leading/trailing underscores and whitespace again
    cleaned = cleaned.strip('_').strip()
    
    return cleaned

def clean_skus_in_sheet(sheet, config):
    """Clean SKUs and update Image Links tab"""
    print("\n" + "=" * 70)
    print("CLEANING SKUs")
    print("=" * 70)
    
    tab_name = config['google_sheets']['tabs']['image_links']
    worksheet = sheet.worksheet(tab_name)
    
    # Get all data
    all_values = worksheet.get_all_values()
    headers = all_values[0]
    
    # Find SKU column (should be column A)
    if 'SKU' not in headers:
        print("Error: SKU column not found!")
        return
    
    sku_col_idx = headers.index('SKU')
    
    # Check if SKU Clean column exists (column B)
    if 'SKU Clean' in headers:
        clean_col_idx = headers.index('SKU Clean')
        print(f"✓ Found 'SKU Clean' column at position {clean_col_idx + 1}")
    else:
        # Add SKU Clean column as column B
        clean_col_idx = 1  # Column B (0-indexed)
        worksheet.insert_cols([[]], col=clean_col_idx + 1)  # Insert at position 2 (B)
        worksheet.update_cell(1, clean_col_idx + 1, 'SKU Clean')
        print(f"✓ Added 'SKU Clean' column at position B")
        # Refresh headers
        all_values = worksheet.get_all_values()
        headers = all_values[0]
    
    # Process each row
    batch_updates = []
    cleaned_count = 0
    
    for row_idx, row in enumerate(all_values[1:], start=2):
        if len(row) <= sku_col_idx:
            continue
        
        original_sku = row[sku_col_idx].strip()
        if not original_sku:
            continue
        
        cleaned_sku = clean_sku(original_sku)
        
        if original_sku != cleaned_sku:
            print(f"  Row {row_idx}: '{original_sku}' → '{cleaned_sku}'")
            cleaned_count += 1
        
        # Update SKU Clean column (column B)
        cell_address = f'B{row_idx}'
        batch_updates.append({
            'range': cell_address,
            'values': [[cleaned_sku]]
        })
    
    # Batch update
    if batch_updates:
        print(f"\nUpdating {len(batch_updates)} rows...")
        worksheet.batch_update(batch_updates)
        print(f"✓ Done! Cleaned {cleaned_count} SKUs")
    else:
        print("No SKUs to update")

def main():
    print("=" * 70)
    print("BROWNBUTTER - SKU CLEANER")
    print("Cleans SKUs and updates 'SKU Clean' column")
    print("=" * 70)
    print()
    
    config = load_config()
    client = authenticate_sheets(config)
    sheet = open_spreadsheet(client, config)
    clean_skus_in_sheet(sheet, config)
    
    print("\n" + "=" * 70)
    print("COMPLETE!")
    print("=" * 70)

if __name__ == "__main__":
    main()