#!/usr/bin/env python3
"""
BrownButter - Upload to Cloudinary & Update Sheet
Uploads images to Cloudinary and updates Google Sheet with URLs
"""

import os
import sys
import yaml
import gspread
from google.oauth2.service_account import Credentials
import cloudinary
import cloudinary.uploader
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
        print(" Error: config.yaml not found!")
        sys.exit(1)
    except Exception as e:
        print(f" Error loading config: {e}")
        sys.exit(1)

# ============================================================================
# CLOUDINARY SETUP
# ============================================================================

def setup_cloudinary(config):
    """Configure Cloudinary"""
    try:
        cloudinary_config = config.get('cloudinary', {})
        
        if not cloudinary_config.get('cloud_name'):
            print(" Error: Cloudinary credentials not found in config.yaml!")
            print("Please add cloudinary section with cloud_name, api_key, and api_secret")
            sys.exit(1)
        
        cloudinary.config(
            cloud_name=cloudinary_config['cloud_name'],
            api_key=cloudinary_config['api_key'],
            api_secret=cloudinary_config['api_secret'],
            secure=True
        )
        
        print(f" Cloudinary configured: {cloudinary_config['cloud_name']}")
        return cloudinary_config.get('folder', 'brownbutter_products')
        
    except Exception as e:
        print(f" Error configuring Cloudinary: {e}")
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
        
        print(" Authenticated with Google Sheets")
        return client
        
    except Exception as e:
        print(f" Error authenticating: {e}")
        sys.exit(1)

def open_spreadsheet(client, config):
    """Open the Google Sheet"""
    try:
        spreadsheet_name = config['google_sheets']['spreadsheet_name']
        sheet = client.open(spreadsheet_name)
        print(f" Opened spreadsheet: {spreadsheet_name}")
        return sheet
    except Exception as e:
        print(f" Error opening spreadsheet: {e}")
        sys.exit(1)

# ============================================================================
# IMAGE UPLOAD
# ============================================================================

def upload_image_to_cloudinary(image_path, public_id, folder):
    """Upload single image to Cloudinary"""
    try:
        # Upload with original filename as public_id
        result = cloudinary.uploader.upload(
            image_path,
            public_id=public_id,
            folder=folder,
            overwrite=True,
            resource_type="image",
            format="jpg"
        )
        
        return result['secure_url']
        
    except Exception as e:
        print(f"    Error uploading {os.path.basename(image_path)}: {e}")
        return None

def process_sku_images(sku, sku_dir, cloudinary_folder, config):
    """Process all images for a SKU"""
    results = {
        'sku': sku,
        'urls': [],
        'status': 'Pending',
        'error': ''
    }
    
    # Get all image files in SKU directory
    image_files = sorted([
        f for f in os.listdir(sku_dir) 
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ])
    
    if not image_files:
        results['status'] = 'Failed'
        results['error'] = 'No images found'
        return results
    
    print(f"\n Uploading {len(image_files)} image(s) for SKU: {sku}")
    
    # Upload each image
    for img_file in image_files:
        img_path = os.path.join(sku_dir, img_file)
        
        # Use filename without extension as public_id (keeps naming convention)
        public_id = os.path.splitext(img_file)[0]
        
        print(f"  Uploading {img_file}...", end=' ')
        
        url = upload_image_to_cloudinary(img_path, public_id, cloudinary_folder)
        
        if url:
            results['urls'].append(url)
            print(f"Pass")
        else:
            print(f"Fail")
        
        # Small delay to avoid rate limits
        time.sleep(0.2)
    
    if results['urls']:
        results['status'] = 'Done'
        print(f"   Uploaded {len(results['urls'])} image(s)")
    else:
        results['status'] = 'Failed'
        results['error'] = 'All uploads failed'
    
    return results

# ============================================================================
# MAIN PROCESSING
# ============================================================================

def process_all_images(config, cloudinary_folder):
    """Process all SKU folders and upload to Cloudinary"""
    
    download_dir = config['images']['temp_download_dir']
    
    if not os.path.exists(download_dir):
        print(f" Error: Download directory not found: {download_dir}")
        print("Please run process_images.py first to download images")
        sys.exit(1)
    
    # Get all SKU directories
    sku_dirs = [
        d for d in os.listdir(download_dir)
        if os.path.isdir(os.path.join(download_dir, d))
    ]
    
    if not sku_dirs:
        print(f" Error: No SKU folders found in {download_dir}")
        sys.exit(1)
    
    print(f"\n Found {len(sku_dirs)} SKU folder(s) to process")
    print("=" * 70)
    print("UPLOADING TO CLOUDINARY")
    print("=" * 70)
    
    results = []
    
    for sku in tqdm(sku_dirs, desc="Overall Progress"):
        sku_dir = os.path.join(download_dir, sku)
        result = process_sku_images(sku, sku_dir, cloudinary_folder, config)
        results.append(result)
    
    return results

# ============================================================================
# UPDATE GOOGLE SHEET
# ============================================================================

def update_sheet_with_urls(sheet, config, results):
    """Update Google Sheet with Cloudinary URLs"""
    
    print("\n" + "=" * 70)
    print("UPDATING GOOGLE SHEET")
    print("=" * 70)
    
    try:
        tab_name = config['google_sheets']['tabs']['image_links']
        worksheet = sheet.worksheet(tab_name)
        
        # Get all current data
        all_values = worksheet.get_all_values()
        headers = all_values[0]
        
        # Find column indices
        sku_col = headers.index('SKU') + 1 if 'SKU' in headers else 1
        
        # Find or create URL columns
        url_columns = {}
        for i in range(1, 6):  # Support up to 5 images
            col_name = f'Image_{i}_URL'
            if col_name in headers:
                url_columns[i] = headers.index(col_name) + 1
            else:
                # Add new column
                new_col = len(headers) + 1
                worksheet.update_cell(1, new_col, col_name)
                url_columns[i] = new_col
                headers.append(col_name)
        
        # Update each SKU
        for result in results:
            sku = result['sku']
            urls = result['urls']
            
            # Find row for this SKU
            sku_row = None
            for row_idx, row in enumerate(all_values[1:], start=2):
                if row[sku_col - 1] == sku:
                    sku_row = row_idx
                    break
            
            if not sku_row:
                print(f"    SKU {sku} not found in sheet")
                continue
            
            # Update URLs
            for i, url in enumerate(urls, start=1):
                if i in url_columns:
                    worksheet.update_cell(sku_row, url_columns[i], url)
            
            print(f"   Updated {sku} with {len(urls)} URL(s)")
        
        print("\n Google Sheet updated successfully!")
        
    except Exception as e:
        print(f" Error updating sheet: {e}")

# ============================================================================
# SUMMARY REPORT
# ============================================================================

def print_summary(results):
    """Print summary of upload"""
    
    print("\n" + "=" * 70)
    print("UPLOAD SUMMARY")
    print("=" * 70)
    
    total = len(results)
    success = sum(1 for r in results if r['status'] == 'Done')
    failed = sum(1 for r in results if r['status'] == 'Failed')
    total_images = sum(len(r['urls']) for r in results)
    
    print(f"\nTotal SKUs processed: {total}")
    print(f"   Success: {success}")
    print(f"   Failed: {failed}")
    print(f"\nTotal images uploaded: {total_images}")
    
    if failed > 0:
        print("\n  Failed SKUs:")
        for r in results:
            if r['status'] == 'Failed':
                print(f"  - {r['sku']}: {r['error']}")
    
    print("\n" + "=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print("1. Verify URLs in Google Sheet 'Image Links' tab")
    print("2. Run: python generate_shopify_csv.py")
    print("3. Import CSV to Shopify")
    print("=" * 70)

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution"""
    
    print("=" * 70)
    print("BROWNBUTTER - CLOUDINARY UPLOAD SCRIPT")
    print("=" * 70)
    print()
    
    # Load configuration
    config = load_config()
    
    # Setup Cloudinary
    cloudinary_folder = setup_cloudinary(config)
    
    # Upload all images
    results = process_all_images(config, cloudinary_folder)
    
    # Authenticate with Google Sheets
    client = authenticate_sheets(config)
    sheet = open_spreadsheet(client, config)
    
    # Update Google Sheet
    update_sheet_with_urls(sheet, config, results)
    
    # Print summary
    print_summary(results)

if __name__ == "__main__":
    main()