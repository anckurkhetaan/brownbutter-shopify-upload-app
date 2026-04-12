#!/usr/bin/env python3
"""
BrownButter - Script 1: Download and Rename Images from Google Drive
Downloads images from Google Drive folders, renames them systematically
"""

import os
import sys
import yaml
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image
import io
from tqdm import tqdm
import re

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
        print("Please make sure config.yaml is in the same directory as this script.")
        sys.exit(1)
    except Exception as e:
        print(f" Error loading config: {e}")
        sys.exit(1)

# ============================================================================
# GOOGLE DRIVE AUTHENTICATION
# ============================================================================

def authenticate_google_services(config):
    """Authenticate with Google Drive and Sheets APIs"""
    try:
        creds_file = config['google_sheets']['credentials_file']
        
        if not os.path.exists(creds_file):
            print(f" Error: {creds_file} not found!")
            print("Please download your Google credentials file and save it as google_credentials.json")
            sys.exit(1)
        
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        
        # Google Sheets client
        sheets_client = gspread.authorize(creds)
        
        # Google Drive client
        drive_service = build('drive', 'v3', credentials=creds)
        
        print(" Successfully authenticated with Google services")
        return sheets_client, drive_service
        
    except Exception as e:
        print(f" Error authenticating: {e}")
        sys.exit(1)

# ============================================================================
# GOOGLE SHEETS OPERATIONS
# ============================================================================

def open_spreadsheet(sheets_client, config):
    """Open the Google Sheet"""
    try:
        spreadsheet_name = config['google_sheets']['spreadsheet_name']
        sheet = sheets_client.open(spreadsheet_name)
        print(f" Opened spreadsheet: {spreadsheet_name}")
        return sheet
    except gspread.exceptions.SpreadsheetNotFound:
        print(f" Error: Spreadsheet '{spreadsheet_name}' not found!")
        print("Make sure:")
        print("  1. The spreadsheet name in config.yaml is correct")
        print("  2. The spreadsheet is shared with your service account email")
        sys.exit(1)
    except Exception as e:
        print(f" Error opening spreadsheet: {e}")
        sys.exit(1)

def get_image_links_data(sheet, config):
    """Get data from Image Links tab"""
    try:
        tab_name = config['google_sheets']['tabs']['image_links']
        worksheet = sheet.worksheet(tab_name)

        # Get all values and build records manually (avoids duplicate/empty header errors)
        all_values = worksheet.get_all_values()
        if not all_values:
            print(f" Found 0 products in '{tab_name}' tab")
            return worksheet, []
        headers = all_values[0]
        records = []
        for row in all_values[1:]:
            record = {}
            for col_idx, header in enumerate(headers):
                if not header:  # skip empty header columns
                    continue
                record[header] = row[col_idx] if col_idx < len(row) else ''
            if any(record.values()):
                records.append(record)

        print(f" Found {len(records)} products in '{tab_name}' tab")
        return worksheet, records

    except gspread.exceptions.WorksheetNotFound:
        print(f" Error: Worksheet '{tab_name}' not found!")
        print("Make sure the 'Image Links' tab exists in your spreadsheet")
        sys.exit(1)
    except Exception as e:
        print(f" Error reading worksheet: {e}")
        sys.exit(1)

# ============================================================================
# GOOGLE DRIVE OPERATIONS
# ============================================================================

def extract_folder_id(drive_link):
    """Extract folder ID from Google Drive link"""
    # Handle different Drive URL formats
    patterns = [
        r'folders/([a-zA-Z0-9_-]+)',  # Standard folder link
        r'id=([a-zA-Z0-9_-]+)',        # Legacy format
    ]
    
    for pattern in patterns:
        match = re.search(pattern, drive_link)
        if match:
            return match.group(1)
    
    return None

def list_files_in_folder(drive_service, folder_id):
    """List all image files in a Google Drive folder"""
    try:
        query = f"'{folder_id}' in parents and trashed=false"
        
        results = drive_service.files().list(
            q=query,
            fields="files(id, name, mimeType)",
            pageSize=100
        ).execute()
        
        files = results.get('files', [])
        
        # Filter for image files
        image_files = [
            f for f in files 
            if f['mimeType'].startswith('image/')
        ]
        
        return image_files
        
    except Exception as e:
        print(f"    Error listing files in folder: {e}")
        return []

def download_file(drive_service, file_id, file_name, output_dir):
    """Download a file from Google Drive"""
    try:
        request = drive_service.files().get_media(fileId=file_id)
        
        file_path = os.path.join(output_dir, file_name)
        
        fh = io.FileIO(file_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        fh.close()
        return file_path
        
    except Exception as e:
        print(f"    Error downloading {file_name}: {e}")
        return None

def convert_to_jpg(image_path, quality=90):
    """Convert image to JPG format if needed"""
    try:
        # Open image
        img = Image.open(image_path)
        
        # Convert RGBA to RGB if necessary
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Save as JPG
        jpg_path = os.path.splitext(image_path)[0] + '.jpg'
        img.save(jpg_path, 'JPEG', quality=quality, optimize=True)
        
        # Remove original if different
        if jpg_path != image_path:
            os.remove(image_path)
        
        return jpg_path
        
    except Exception as e:
        print(f"    Error converting image: {e}")
        return image_path

# ============================================================================
# MAIN PROCESSING
# ============================================================================

def process_images(config, sheets_client, drive_service, sheet):
    """Main function to download and rename images"""
    
    # Create output directory
    output_dir = config['images']['temp_download_dir']
    os.makedirs(output_dir, exist_ok=True)
    print(f" Created output directory: {output_dir}/")
    print()
    
    # Get image links data
    worksheet, records = get_image_links_data(sheet, config)
    
    # Process each product
    results = []
    
    print("=" * 70)
    print("PROCESSING IMAGES")
    print("=" * 70)
    print()
    
    for idx, record in enumerate(tqdm(records, desc="Overall Progress")):
        sku = record.get('SKU', '')
        drive_link = record.get('Drive_Folder_Link', '')
        
        if not sku or not drive_link:
            results.append({
                'sku': sku,
                'status': 'Skipped',
                'error': 'Missing SKU or Drive link',
                'image_count': 0,
                'image_urls': []
            })
            continue
        
        print(f"\n[{idx+1}/{len(records)}] Processing SKU: {sku}")
        print(f"  Drive link: {drive_link[:50]}...")
        
        # Extract folder ID
        folder_id = extract_folder_id(drive_link)
        if not folder_id:
            print(f"   Could not extract folder ID from link")
            results.append({
                'sku': sku,
                'status': 'Failed',
                'error': 'Invalid Drive link',
                'image_count': 0,
                'image_urls': []
            })
            continue
        
        # List files in folder
        files = list_files_in_folder(drive_service, folder_id)
        
        if not files:
            print(f"    No images found in folder")
            results.append({
                'sku': sku,
                'status': 'Failed',
                'error': 'No images in folder',
                'image_count': 0,
                'image_urls': []
            })
            continue
        
        print(f"  Found {len(files)} image(s)")
        
        # Create SKU directory
        sku_dir = os.path.join(output_dir, sku)
        os.makedirs(sku_dir, exist_ok=True)
        
        # Sort files by existing _N suffix so Image1/2/3 order is preserved
        def sort_key(f):
            m = re.search(r'_(\d+)\.[^.]+$', f['name'])
            return int(m.group(1)) if m else 0
        files.sort(key=sort_key)

        # Download and rename images
        downloaded_images = []
        for img_num, file in enumerate(files, 1):
            print(f"    Downloading {file['name']}...")

            # Download with temporary name
            temp_path = download_file(drive_service, file['id'], file['name'], sku_dir)

            if temp_path:
                # Convert to JPG if needed
                if config['images'].get('convert_to_jpg', True):
                    jpg_path = convert_to_jpg(temp_path, config['images'].get('jpg_quality', 90))
                else:
                    jpg_path = temp_path

                # Rename to SKU_N.jpg matching source _N order
                final_name = f"{sku}_{img_num}.jpg"
                final_path = os.path.join(sku_dir, final_name)

                if jpg_path != final_path:
                    os.rename(jpg_path, final_path)

                downloaded_images.append(final_path)
                print(f"     Saved as: {final_name}")
        
        # Update results
        if downloaded_images:
            results.append({
                'sku': sku,
                'status': 'Done',
                'error': '',
                'image_count': len(downloaded_images),
                'image_urls': downloaded_images
            })
            print(f"   Successfully processed {len(downloaded_images)} image(s)")
        else:
            results.append({
                'sku': sku,
                'status': 'Failed',
                'error': 'Download failed',
                'image_count': 0,
                'image_urls': []
            })
    
    # Update Google Sheet with results
    print("\n" + "=" * 70)
    print("UPDATING GOOGLE SHEET")
    print("=" * 70)
    
    update_sheet_with_results(worksheet, results, config)
    
    return results

def update_sheet_with_results(worksheet, results, config):
    """Update Google Sheet with processing results"""
    try:
        # Get header row
        headers = worksheet.row_values(1)
        
        # Find or create columns
        status_col = headers.index('Status') + 1 if 'Status' in headers else len(headers) + 1
        count_col = headers.index('Image_Count') + 1 if 'Image_Count' in headers else len(headers) + 2
        error_col = headers.index('Error_Message') + 1 if 'Error_Message' in headers else len(headers) + 3
        
        # Update headers if needed
        if 'Status' not in headers:
            worksheet.update_cell(1, status_col, 'Status')
        if 'Image_Count' not in headers:
            worksheet.update_cell(1, count_col, 'Image_Count')
        if 'Error_Message' not in headers:
            worksheet.update_cell(1, error_col, 'Error_Message')
        
        # Update each row
        for idx, result in enumerate(results, 2):  # Start from row 2
            worksheet.update_cell(idx, status_col, result['status'])
            worksheet.update_cell(idx, count_col, result['image_count'])
            worksheet.update_cell(idx, error_col, result.get('error', ''))
        
        print(" Google Sheet updated with results")
        
    except Exception as e:
        print(f"  Could not update sheet: {e}")

# ============================================================================
# SUMMARY REPORT
# ============================================================================

def print_summary(results, output_dir):
    """Print summary of processing"""
    print("\n" + "=" * 70)
    print("PROCESSING SUMMARY")
    print("=" * 70)
    
    total = len(results)
    success = sum(1 for r in results if r['status'] == 'Done')
    failed = sum(1 for r in results if r['status'] == 'Failed')
    skipped = sum(1 for r in results if r['status'] == 'Skipped')
    total_images = sum(r['image_count'] for r in results)
    
    print(f"\nTotal products: {total}")
    print(f"   Success: {success}")
    print(f"   Failed: {failed}")
    print(f"    Skipped: {skipped}")
    print(f"\nTotal images downloaded: {total_images}")
    print(f"\nImages saved to: {os.path.abspath(output_dir)}/")
    
    if failed > 0:
        print("\n  Failed products:")
        for r in results:
            if r['status'] == 'Failed':
                print(f"  - {r['sku']}: {r['error']}")
    
    print("\n" + "=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print("1. Check the images in the output folder")
    print("2. Upload images to your preferred host (Shopify, Imgur, etc.)")
    print("3. Add image URLs to Google Sheet columns: Image_1_URL, Image_2_URL, Image_3_URL")
    print("4. Run generate_shopify_csv.py to create the final CSV")
    print("=" * 70)

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution"""
    print("=" * 70)
    print("BROWNBUTTER - IMAGE DOWNLOAD & RENAME SCRIPT")
    print("=" * 70)
    print()
    
    # Load configuration
    config = load_config()
    
    # Authenticate
    sheets_client, drive_service = authenticate_google_services(config)
    
    # Open spreadsheet
    sheet = open_spreadsheet(sheets_client, config)
    
    # Process images
    results = process_images(config, sheets_client, drive_service, sheet)
    
    # Print summary
    print_summary(results, config['images']['temp_download_dir'])

if __name__ == "__main__":
    main()
