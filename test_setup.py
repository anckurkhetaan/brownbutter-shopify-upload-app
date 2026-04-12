#!/usr/bin/env python3
"""
BrownButter Automation - Setup Verification Script
Run this to verify all dependencies and credentials are configured correctly
"""

import os
import sys

print("=" * 70)
print("🔍 BrownButter Shopify Automation - Setup Verification")
print("=" * 70)
print()

errors = []
warnings = []

# ============================================================================
# Check 1: Python Version
# ============================================================================
print("1. Checking Python version...")
python_version = sys.version_info
if python_version >= (3, 8):
    print(f"  Python {python_version.major}.{python_version.minor}.{python_version.micro}")
else:
    errors.append(f"Python version too old: {python_version.major}.{python_version.minor}")
    print(f"  Python {python_version.major}.{python_version.minor} (requires 3.8+)")
print()

# ============================================================================
# Check 2: Required Python Packages
# ============================================================================
print("2. Checking required Python packages...")
required_packages = {
    'google.auth': 'google-auth',
    'gspread': 'gspread',
    'requests': 'requests',
    'yaml': 'pyyaml',
    'pandas': 'pandas',
    'PIL': 'pillow',
    'tqdm': 'tqdm'
}

missing_packages = []
for module, package in required_packages.items():
    try:
        __import__(module)
        print(f"  {package}")
    except ImportError:
        missing_packages.append(package)
        print(f"  {package} - NOT INSTALLED")

if missing_packages:
    errors.append(f"Missing packages: {', '.join(missing_packages)}")
    print(f"\n  Install with: pip install {' '.join(missing_packages)}")
print()

# ============================================================================
# Check 3: Configuration File
# ============================================================================
print("3. Checking config.yaml...")
if os.path.exists('config.yaml'):
    try:
        import yaml
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Check if values are updated
        if config['shopify']['store_name'] == 'your-store-name':
            warnings.append("Shopify store_name not updated in config.yaml")
            print("   File exists but 'store_name' not updated")
        elif config['shopify']['access_token'] == 'shpat_xxxxxxxxxxxxxxxxxxxxx':
            warnings.append("Shopify access_token not updated in config.yaml")
            print("    File exists but 'access_token' not updated")
        else:
            print(f"  Config loaded - Store: {config['shopify']['store_name']}")
            
    except Exception as e:
        errors.append(f"Error reading config.yaml: {str(e)}")
        print(f"   Error reading file: {str(e)}")
else:
    errors.append("config.yaml not found")
    print("    config.yaml not found")
    print("    Copy config.yaml template and update with your credentials")
print()

# ============================================================================
# Check 4: Google Credentials
# ============================================================================
print("4. Checking Google credentials...")
if os.path.exists('google_credentials.json'):
    try:
        import json
        with open('google_credentials.json', 'r') as f:
            creds = json.load(f)
        
        if 'client_email' in creds:
            print(f"    Credentials found")
            print(f"      Service account: {creds['client_email'][:40]}...")
            print(f"    IMPORTANT: Share your Google Sheet with this email!")
        else:
            errors.append("Invalid google_credentials.json file")
            print("    Invalid credentials file format")
    except Exception as e:
        errors.append(f"Error reading credentials: {str(e)}")
        print(f"    Error reading file: {str(e)}")
else:
    errors.append("google_credentials.json not found")
    print("    google_credentials.json not found")
    print("    Download from Google Cloud Console and save here")
print()

# ============================================================================
# Check 5: Directory Structure
# ============================================================================
print("5. Checking directory structure...")
expected_files = ['config.yaml', 'google_credentials.json']
optional_files = ['process_images.py', 'generate_shopify_csv.py']

for file in expected_files:
    if os.path.exists(file):
        print(f"    {file}")
    else:
        print(f"    {file} - MISSING")

for file in optional_files:
    if os.path.exists(file):
        print(f"    {file}")
    else:
        print(f"    {file} - Not yet created")
print()

# ============================================================================
# Check 6: Test Shopify Connection (if configured)
# ============================================================================
print("6. Testing Shopify API connection...")
try:
    import yaml
    import requests
    
    if os.path.exists('config.yaml'):
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        store_name = config['shopify']['store_name']
        access_token = config['shopify']['access_token']
        api_version = config['shopify']['api_version']
        
        if store_name != 'your-store-name' and access_token != 'shpat_xxxxxxxxxxxxxxxxxxxxx':
            url = f"https://{store_name}.myshopify.com/admin/api/{api_version}/shop.json"
            headers = {
                'X-Shopify-Access-Token': access_token,
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                shop_data = response.json()
                print(f"    Connected to: {shop_data['shop']['name']}")
                print(f"      Shop email: {shop_data['shop']['email']}")
            else:
                errors.append(f"Shopify API error: {response.status_code}")
                print(f"    Connection failed: {response.status_code}")
                print(f"      Error: {response.text[:100]}")
        else:
            print("     Skipped - config not yet updated")
    else:
        print("     Skipped - config.yaml not found")
        
except Exception as e:
    warnings.append(f"Could not test Shopify connection: {str(e)}")
    print(f"    Could not test connection: {str(e)}")
print()

# ============================================================================
# Check 7: Test Google Sheets Connection (if configured)
# ============================================================================
print("7. Testing Google Sheets connection...")
try:
    if os.path.exists('config.yaml') and os.path.exists('google_credentials.json'):
        import yaml
        import gspread
        from google.oauth2.service_account import Credentials
        
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = Credentials.from_service_account_file(
            'google_credentials.json',
            scopes=scopes
        )
        client = gspread.authorize(creds)
        
        spreadsheet_name = config['google_sheets']['spreadsheet_name']
        sheet = client.open(spreadsheet_name)
        
        print(f"    Connected to: {sheet.title}")
        print(f"      Worksheets: {', '.join([ws.title for ws in sheet.worksheets()])}")
        
    else:
        print("     Skipped - credentials not configured")
        
except gspread.exceptions.SpreadsheetNotFound:
    errors.append(f"Google Sheet '{spreadsheet_name}' not found or not shared")
    print(f"  Sheet not found: {spreadsheet_name}")
    print("   Make sure sheet is shared with service account email")
except Exception as e:
    warnings.append(f"Could not test Google Sheets: {str(e)}")
    print(f"    Could not test connection: {str(e)}")
print()

# ============================================================================
# Summary
# ============================================================================
print("=" * 70)
print(" SETUP VERIFICATION SUMMARY")
print("=" * 70)

if not errors and not warnings:
    print("✅ ALL CHECKS PASSED! Setup is complete.")
    print("\n You're ready to run:")
    print("   1. python process_images.py")
    print("   2. python generate_shopify_csv.py")
elif not errors:
    print(f"⚠️  Setup complete with {len(warnings)} warning(s):")
    for w in warnings:
        print(f"   - {w}")
    print("\n You can proceed, but review warnings above")
else:
    print(f"❌ Setup incomplete - {len(errors)} error(s) found:")
    for e in errors:
        print(f"   - {e}")
    if warnings:
        print(f"\n Also {len(warnings)} warning(s):")
        for w in warnings:
            print(f"   - {w}")
    print("\n🔧 Fix the errors above before proceeding")

print("=" * 70)
