#!/usr/bin/env python3
"""
BrownButter - Direct Drive to Cloudinary Upload
Downloads images from Google Drive and uploads directly to Cloudinary
No local storage needed - everything in memory
"""

import os
import sys
import yaml
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import cloudinary
import cloudinary.uploader
import io
import time
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
        print("Error: config.yaml not found!")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

# ============================================================================
# GOOGLE SERVICES AUTHENTICATION
# ============================================================================

def authenticate_google_services(config):
    """Authenticate with Google Drive and Sheets APIs"""
    try:
        creds_file = config['google_sheets']['credentials_file']
        
        if not os.path.exists(creds_file):
            print(f"Error: {creds_file} not found!")
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
        
        print("Authenticated with Google services")
        return sheets_client, drive_service
        
    except Exception as e:
        print(f"Error authenticating: {e}")
        sys.exit(1)

# ============================================================================
# CLOUDINARY SETUP
# ============================================================================

def setup_cloudinary(config):
    """Configure Cloudinary"""
    try:
        cloudinary_config = config.get('cloudinary', {})
        
        if not cloudinary_config.get('cloud_name'):
            print("Error: Cloudinary credentials not found in config.yaml!")
            sys.exit(1)
        
        cloudinary.config(
            cloud_name=cloudinary_config['cloud_name'],
            api_key=cloudinary_config['api_key'],
            api_secret=cloudinary_config['api_secret'],
            secure=True
        )
        
        print(f"Cloudinary configured: {cloudinary_config['cloud_name']}")
        return cloudinary_config.get('folder', 'brownbutter_products')
        
    except Exception as e:
        print(f"Error configuring Cloudinary: {e}")
        sys.exit(1)

# ============================================================================
# GOOGLE SHEETS OPERATIONS
# ============================================================================

def open_spreadsheet(sheets_client, config):
    """Open the Google Sheet"""
    try:
        spreadsheet_name = config['google_sheets']['spreadsheet_name']
        sheet = sheets_client.open(spreadsheet_name)
        print(f"Opened spreadsheet: {spreadsheet_name}")
        return sheet
    except Exception as e:
        print(f"Error opening spreadsheet: {e}")
        sys.exit(1)

def get_image_links_data(sheet, config):
    """Get data from Image Links tab"""
    try:
        tab_name = config['google_sheets']['tabs']['image_links']
        worksheet = sheet.worksheet(tab_name)
        
        # Get all values including formulas to extract hyperlinks
        all_values = worksheet.get_all_values()
        
        if not all_values:
            print(f"Error: '{tab_name}' tab is empty!")
            sys.exit(1)
        
        # Get headers
        headers = all_values[0]
        
        # Find the Drive_Folder_Link column index
        try:
            link_col_idx = headers.index('Drive_Folder_Link')
        except ValueError:
            print(f"Error: 'Drive_Folder_Link' column not found in '{tab_name}' tab")
            sys.exit(1)
        
        # Get cell formulas to extract actual URLs from hyperlinks
        link_col_letter = chr(65 + link_col_idx)
        
        # Build records with actual URLs
        records = []
        for row_idx, row in enumerate(all_values[1:], start=2):
            record = dict(zip(headers, row))
            
            # Try to get the actual URL from the cell formula
            try:
                cell_formula = worksheet.acell(f'{link_col_letter}{row_idx}', value_render_option='FORMULA').value
                
                # Check if it's a hyperlink formula
                if cell_formula and cell_formula.startswith('=HYPERLINK'):
                    # Extract URL from formula
                    url_match = re.search(r'HYPERLINK\("([^"]+)"', cell_formula)
                    if url_match:
                        actual_url = url_match.group(1)
                        record['Drive_Folder_Link'] = actual_url
                elif cell_formula and cell_formula.startswith('http'):
                    record['Drive_Folder_Link'] = cell_formula
            except:
                pass
            
            records.append(record)
        
        print(f"Found {len(records)} products in '{tab_name}' tab")
        return worksheet, records
        
    except Exception as e:
        print(f"Error reading worksheet: {e}")
        sys.exit(1)

# ============================================================================
# GOOGLE DRIVE OPERATIONS
# ============================================================================

def extract_folder_id(drive_link):
    """Extract folder ID from Google Drive link"""
    patterns = [
        r'folders/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
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
        print(f"  Error listing files in folder: {e}")
        return []

def download_file_to_memory(drive_service, file_id):
    """Download a file from Google Drive to memory (BytesIO)"""
    try:
        request = drive_service.files().get_media(fileId=file_id)
        
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        file_buffer.seek(0)  # Reset buffer position
        return file_buffer
        
    except Exception as e:
        print(f"  Error downloading file: {e}")
        return None

# ============================================================================
# CLOUDINARY UPLOAD
# ============================================================================

def upload_to_cloudinary_from_memory(file_buffer, public_id, folder):
    """Upload image from memory buffer to Cloudinary"""
    try:
        result = cloudinary.uploader.upload(
            file_buffer,
            public_id=public_id,
            folder=folder,
            overwrite=True,
            resource_type="image",
            format="jpg"
        )
        
        return result['secure_url']
        
    except Exception as e:
        print(f"  Error uploading to Cloudinary: {e}")
        return None

# ============================================================================
# MAIN PROCESSING
# ============================================================================

def process_direct_upload(config, sheets_client, drive_service, sheet, cloudinary_folder):
    """Main function to process images directly from Drive to Cloudinary"""
    
    print("\n" + "=" * 70)
    print("PROCESSING: GOOGLE DRIVE → CLOUDINARY")
    print("=" * 70)
    print()
    
    # Get image links data
    worksheet, records = get_image_links_data(sheet, config)
    
    # Process each product
    results = []
    
    for idx, record in enumerate(tqdm(records, desc="Overall Progress")):
        sku = record.get('SKU', '')
        drive_link = record.get('Drive_Folder_Link', '')
        
        if not sku or not drive_link:
            results.append({
                'sku': sku,
                'status': 'Failed',
                'error': 'Missing SKU or Drive link',
                'image_count': 0,
                'urls': []
            })
            continue
        
        print(f"\n[{idx+1}/{len(records)}] Processing SKU: {sku}")
        print(f"  Drive link: {drive_link[:50]}...")
        
        # Extract folder ID
        folder_id = extract_folder_id(drive_link)
        if not folder_id:
            print(f"  Error: Could not extract folder ID from link")
            results.append({
                'sku': sku,
                'status': 'Failed',
                'error': 'Invalid Drive link',
                'image_count': 0,
                'urls': []
            })
            continue
        
        # List files in folder
        files = list_files_in_folder(drive_service, folder_id)
        
        if not files:
            print(f"  Warning: No images found in folder")
            results.append({
                'sku': sku,
                'status': 'Failed',
                'error': 'No images in folder',
                'image_count': 0,
                'urls': []
            })
            continue
        
        print(f"  Found {len(files)} image(s)")
        
        # Process each image: Download → Upload → Delete from memory
        uploaded_urls = []
        for img_num, file in enumerate(files, 1):
            print(f"    Processing {file['name']}...", end=' ')
            
            # Download to memory
            file_buffer = download_file_to_memory(drive_service, file['id'])
            
            if file_buffer:
                # Generate Cloudinary public_id
                public_id = f"{sku}_{img_num}"
                
                # Upload to Cloudinary
                url = upload_to_cloudinary_from_memory(file_buffer, public_id, cloudinary_folder)
                
                # Clear buffer from memory
                file_buffer.close()
                
                if url:
                    uploaded_urls.append(url)
                    print(f"Uploaded as {public_id}.jpg")
                else:
                    print(f"Upload failed")
            else:
                print(f"Download failed")
            
            # Small delay
            time.sleep(0.2)
        
        # Update results
        if uploaded_urls:
            results.append({
                'sku': sku,
                'status': 'Done',
                'error': '',
                'image_count': len(uploaded_urls),
                'urls': uploaded_urls
            })
            print(f"  Successfully uploaded {len(uploaded_urls)} image(s)")
        else:
            results.append({
                'sku': sku,
                'status': 'Failed',
                'error': 'All uploads failed',
                'image_count': 0,
                'urls': []
            })
    
    # Update Google Sheet with results
    print("\n" + "=" * 70)
    print("UPDATING GOOGLE SHEET")
    print("=" * 70)
    
    update_sheet_with_status(worksheet, results)
    
    return results

def update_sheet_with_status(worksheet, results):
    """Update Google Sheet with processing status and error messages"""
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
        for idx, result in enumerate(results, 2):
            worksheet.update_cell(idx, status_col, result['status'])
            worksheet.update_cell(idx, count_col, result['image_count'])
            worksheet.update_cell(idx, error_col, result.get('error', ''))
        
        print("Google Sheet updated with results")
        
    except Exception as e:
        print(f"Warning: Could not update sheet: {e}")

# ============================================================================
# SUMMARY
# ============================================================================

def print_summary(results):
    """Print summary of processing"""
    print("\n" + "=" * 70)
    print("PROCESSING SUMMARY")
    print("=" * 70)
    
    total = len(results)
    success = sum(1 for r in results if r['status'] == 'Done')
    failed = sum(1 for r in results if r['status'] == 'Failed')
    total_images = sum(r['image_count'] for r in results)
    
    print(f"\nTotal products: {total}")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    print(f"\nTotal images uploaded: {total_images}")
    
    if failed > 0:
        print("\nFailed products:")
        for r in results:
            if r['status'] == 'Failed':
                print(f"  - {r['sku']}: {r['error']}")
    
    print("\n" + "=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print("1. Check 'Image Links' tab for Status and Error_Message")
    print("2. Run: python sync_urls_to_sheet.py")
    print("3. Run: python generate_shopify_csv.py")
    print("=" * 70)

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution"""
    print("=" * 70)
    print("BROWNBUTTER - DIRECT DRIVE TO CLOUDINARY UPLOAD")
    print("No local storage - all in memory")
    print("=" * 70)
    print()
    
    # Load configuration
    config = load_config()
    
    # Authenticate
    sheets_client, drive_service = authenticate_google_services(config)
    
    # Setup Cloudinary
    cloudinary_folder = setup_cloudinary(config)
    
    # Open spreadsheet
    sheet = open_spreadsheet(sheets_client, config)
    
    # Process images
    results = process_direct_upload(config, sheets_client, drive_service, sheet, cloudinary_folder)
    
    # Print summary
    print_summary(results)

if __name__ == "__main__":
    main()