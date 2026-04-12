#!/usr/bin/env python3
"""
BrownButter - AI Title Generator using Claude Vision API
Analyzes product images and generates creative titles
"""

import os
import sys
import yaml
import gspread
from google.oauth2.service_account import Credentials
import anthropic
from tqdm import tqdm
import time

# ============================================================================
# CONFIGURATION
# ============================================================================

def load_config():
    """Load configuration from config.yaml"""
    try:
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: config.yaml not found!")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

# ============================================================================
# ANTHROPIC CLIENT SETUP
# ============================================================================

def setup_anthropic_client(config):
    """Initialize Anthropic client"""
    try:
        anthropic_config = config.get('anthropic', {})
        
        if not anthropic_config.get('api_key') or anthropic_config['api_key'] == 'your_anthropic_api_key_here':
            print("Error: Anthropic API key not configured in config.yaml!")
            print("Get your API key from: https://console.anthropic.com")
            print("Add it to config.yaml under anthropic: api_key:")
            sys.exit(1)
        
        client = anthropic.Anthropic(api_key=anthropic_config['api_key'])
        
        print(f"Anthropic client configured: {anthropic_config['model']}")
        return client, anthropic_config
        
    except Exception as e:
        print(f"Error setting up Anthropic: {e}")
        sys.exit(1)

# ============================================================================
# GOOGLE SHEETS AUTHENTICATION
# ============================================================================

def authenticate_sheets(config):
    """Authenticate with Google Sheets API"""
    try:
        creds_file = config['google_sheets']['credentials_file']
        
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        client = gspread.authorize(creds)
        
        print("Authenticated with Google Sheets")
        return client
        
    except Exception as e:
        print(f"Error authenticating: {e}")
        sys.exit(1)

def open_spreadsheet(client, config):
    """Open the Google Sheet"""
    try:
        spreadsheet_name = config['google_sheets']['spreadsheet_name']
        sheet = client.open(spreadsheet_name)
        print(f"Opened spreadsheet: {spreadsheet_name}")
        return sheet
    except Exception as e:
        print(f"Error opening spreadsheet: {e}")
        sys.exit(1)

# ============================================================================
# DATA RETRIEVAL
# ============================================================================

def get_image_links_data(sheet, config):
    """Get image URLs from Image Links tab"""
    try:
        tab_name = config['google_sheets']['tabs']['image_links']
        worksheet = sheet.worksheet(tab_name)
        records = worksheet.get_all_records()
        
        print(f"Loaded {len(records)} products from '{tab_name}' tab")
        return records
        
    except Exception as e:
        print(f"Error reading image links: {e}")
        sys.exit(1)

def setup_title_description_tab(sheet, config):
    """Setup or get Title and Description Generator tab"""
    try:
        tab_name = config['google_sheets']['tabs']['title_description']
        
        try:
            worksheet = sheet.worksheet(tab_name)
            print(f"Found existing '{tab_name}' tab")
        except gspread.exceptions.WorksheetNotFound:
            # Create new tab
            worksheet = sheet.add_worksheet(title=tab_name, rows=1000, cols=5)
            
            # Add headers
            headers = ['SKU', 'Image_1_URL', 'AI_Title', 'Status', 'Error_Message']
            worksheet.append_row(headers)
            
            print(f"Created new '{tab_name}' tab")
        
        return worksheet
        
    except Exception as e:
        print(f"Error setting up tab: {e}")
        sys.exit(1)

# ============================================================================
# AI TITLE GENERATION
# ============================================================================

def generate_title_from_image(client, image_url, anthropic_config):
    """Generate product title using Claude Vision API"""
    try:
        prompt = """Analyze this product image and generate a catchy, descriptive product title.

Requirements:
- Exactly 5-7 words
- Include: style descriptor + color + occasion/style + product type
- Examples: "Comfortable Black Daily Blouse", "Elegant Blue Evening Dress", "Trendy White Casual Top"
- Be creative but accurate to what you see
- Use fashion-appropriate adjectives: Comfortable, Elegant, Stylish, Trendy, Chic, Classic, Modern

Respond with ONLY the title, nothing else."""

        message = client.messages.create(
            model=anthropic_config['model'],
            max_tokens=anthropic_config['max_tokens'],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": image_url,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ],
                }
            ],
        )
        
        # Extract title from response
        title = message.content[0].text.strip()
        
        # Clean up any markdown or extra formatting
        title = title.replace('"', '').replace("'", "").strip()
        
        return title
        
    except Exception as e:
        print(f"  Error generating title: {e}")
        return None

# ============================================================================
# MAIN PROCESSING
# ============================================================================

def process_titles(client, anthropic_config, image_data, title_worksheet, config):
    """Generate titles for all products"""
    
    print("\n" + "=" * 70)
    print("GENERATING AI TITLES")
    print("=" * 70)
    print()
    
    results = []
    
    # Get existing data from title worksheet to avoid re-processing
    existing_data = {}
    try:
        existing_records = title_worksheet.get_all_records()
        for record in existing_records:
            if record.get('SKU') and record.get('Status') == 'Done':
                existing_data[record['SKU']] = record
    except:
        pass
    
    for idx, record in enumerate(tqdm(image_data, desc="Processing")):
        sku = record.get('SKU', '')
        image_1_url = record.get('Image_1_URL', '')
        
        if not sku:
            continue
        
        # Skip if already processed
        if sku in existing_data:
            print(f"\n[{idx+1}/{len(image_data)}] SKU: {sku} - Already processed, skipping")
            results.append({
                'sku': sku,
                'image_url': image_1_url,
                'title': existing_data[sku].get('AI_Title', ''),
                'status': 'Done',
                'error': ''
            })
            continue
        
        if not image_1_url:
            print(f"\n[{idx+1}/{len(image_data)}] SKU: {sku} - No image URL")
            results.append({
                'sku': sku,
                'image_url': '',
                'title': '',
                'status': 'Failed',
                'error': 'No image URL'
            })
            continue
        
        print(f"\n[{idx+1}/{len(image_data)}] Generating title for SKU: {sku}")
        print(f"  Image: {image_1_url[:60]}...")
        
        # Generate title
        title = generate_title_from_image(client, image_1_url, anthropic_config)
        
        if title:
            print(f"  Generated: {title}")
            results.append({
                'sku': sku,
                'image_url': image_1_url,
                'title': title,
                'status': 'Done',
                'error': ''
            })
        else:
            results.append({
                'sku': sku,
                'image_url': image_1_url,
                'title': '',
                'status': 'Failed',
                'error': 'API call failed'
            })
        
        # Small delay to respect rate limits
        time.sleep(0.5)
    
    return results

def update_title_worksheet(worksheet, results):
    """Update Google Sheet with generated titles"""
    
    print("\n" + "=" * 70)
    print("UPDATING GOOGLE SHEET")
    print("=" * 70)
    
    try:
        # Get existing data
        all_values = worksheet.get_all_values()
        headers = all_values[0] if all_values else []
        
        # Create a mapping of SKU to row number
        sku_to_row = {}
        for row_idx, row in enumerate(all_values[1:], start=2):
            if row and row[0]:  # If SKU exists
                sku_to_row[row[0]] = row_idx
        
        # Update or append results
        for result in results:
            sku = result['sku']
            
            if sku in sku_to_row:
                # Update existing row
                row_num = sku_to_row[sku]
                worksheet.update_cell(row_num, 2, result['image_url'])
                worksheet.update_cell(row_num, 3, result['title'])
                worksheet.update_cell(row_num, 4, result['status'])
                worksheet.update_cell(row_num, 5, result['error'])
            else:
                # Append new row
                worksheet.append_row([
                    result['sku'],
                    result['image_url'],
                    result['title'],
                    result['status'],
                    result['error']
                ])
        
        print("Google Sheet updated successfully")
        
    except Exception as e:
        print(f"Error updating sheet: {e}")

# ============================================================================
# SUMMARY
# ============================================================================

def print_summary(results):
    """Print summary of title generation"""
    
    print("\n" + "=" * 70)
    print("TITLE GENERATION SUMMARY")
    print("=" * 70)
    
    total = len(results)
    success = sum(1 for r in results if r['status'] == 'Done')
    failed = sum(1 for r in results if r['status'] == 'Failed')
    
    print(f"\nTotal products: {total}")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    
    if failed > 0:
        print("\nFailed products:")
        for r in results:
            if r['status'] == 'Failed':
                print(f"  - {r['sku']}: {r['error']}")
    
    print("\n" + "=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print("1. Review titles in 'Title and Description Generator' tab")
    print("2. Edit any titles if needed")
    print("3. Run: python generate_shopify_csv.py")
    print("=" * 70)

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution"""
    
    print("=" * 70)
    print("BROWNBUTTER - AI TITLE GENERATOR")
    print("Powered by Claude Haiku 4.5 Vision")
    print("=" * 70)
    print()
    
    # Load configuration
    config = load_config()
    
    # Setup Anthropic client
    client, anthropic_config = setup_anthropic_client(config)
    
    # Authenticate with Google Sheets
    sheets_client = authenticate_sheets(config)
    sheet = open_spreadsheet(sheets_client, config)
    
    # Get image data
    image_data = get_image_links_data(sheet, config)
    
    # Setup title/description tab
    title_worksheet = setup_title_description_tab(sheet, config)
    
    # Generate titles
    results = process_titles(client, anthropic_config, image_data, title_worksheet, config)
    
    # Update worksheet
    update_title_worksheet(title_worksheet, results)
    
    # Print summary
    print_summary(results)

if __name__ == "__main__":
    main()