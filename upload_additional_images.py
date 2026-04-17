#!/usr/bin/env python3
"""
BrownButter - Upload Additional Images
Uploads missing images (_2, _3, _4, _5) for SKUs that already have _1 on Cloudinary
"""

import os
import sys
import json
import yaml
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import cloudinary
import cloudinary.uploader
import cloudinary.api
import io
import time
import re

# ============================================================================
# CONFIGURATION
# ============================================================================

def load_config():
    """Load configuration from config.yaml"""
    try:
        # Check if running on Render (Secret File)
        if os.path.exists('/etc/secrets/config.yaml'):
            config_path = '/etc/secrets/config.yaml'
            print("Using config.yaml from Secret File (Render)")
        else:
            config_path = 'config.yaml'
            print("Using local config.yaml")
        
        with open(config_path, 'r') as f:
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
        # Check if running on Render (environment variable)
        google_creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        if google_creds_json:
            # Render deployment - use environment variable
            print("Using GOOGLE_CREDENTIALS_JSON from environment")
            creds_dict = json.loads(google_creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            # Local - use file
            creds_file = config['google_sheets']['credentials_file']
            if not os.path.exists(creds_file):
                print(f"Error: {creds_file} not found!")
                sys.exit(1)
            print(f"Using credentials file: {creds_file}")
            creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        
        # Google Sheets client
        sheets_client = gspread.authorize(creds)
        
        # Google Drive service
        drive_service = build('drive', 'v3', credentials=creds)
        
        print("✓ Authenticated with Google Services")
        return sheets_client, drive_service
        
    except Exception as e:
        print(f"Error authenticating: {e}")
        sys.exit(1)

def setup_cloudinary(config):
    """Setup Cloudinary configuration"""
    cloudinary_config = config.get('cloudinary', {})
    cloudinary.config(
        cloud_name=cloudinary_config['cloud_name'],
        api_key=cloudinary_config['api_key'],
        api_secret=cloudinary_config['api_secret'],
        secure=True
    )
    print(f"✓ Cloudinary configured: {cloudinary_config['cloud_name']}")
    return cloudinary_config.get('folder', 'brownbutter_products')

# ============================================================================
# CLOUDINARY HELPERS
# ============================================================================

def get_existing_images(sku, cloudinary_folder):
    """Check which images already exist for a SKU on Cloudinary"""
    existing = []
    for i in range(1, 6):
        public_id = f"{cloudinary_folder}/{sku}_{i}"
        try:
            cloudinary.api.resource(public_id)
            existing.append(i)
        except:
            pass
    return existing

# ============================================================================
# GOOGLE DRIVE HELPERS
# ============================================================================

def extract_folder_id(drive_link):
    """Extract folder ID from Google Drive link"""
    patterns = [
        r'folders/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
        r'https://drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, drive_link)
        if match:
            return match.group(1)
    
    return None

def list_images_in_folder(drive_service, folder_id):
    """List all images in a Google Drive folder"""
    try:
        query = f"'{folder_id}' in parents and (mimeType contains 'image/')"
        results = drive_service.files().list(
            q=query,
            fields="files(id, name, mimeType)",
            orderBy="name"
        ).execute()
        
        files = results.get('files', [])
        
        # Sort by filename to ensure consistent ordering
        files.sort(key=lambda x: x['name'].lower())
        
        return files
        
    except Exception as e:
        print(f"  Error listing folder: {e}")
        return []

def download_image_to_memory(drive_service, file_id):
    """Download image from Google Drive to memory"""
    try:
        request = drive_service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        buffer.seek(0)
        return buffer
        
    except Exception as e:
        print(f"  Error downloading: {e}")
        return None

# ============================================================================
# MAIN UPLOAD LOGIC
# ============================================================================

def upload_additional_images(config, sheets_client, drive_service, cloudinary_folder):
    """Upload additional images for SKUs"""
    
    print("\n" + "=" * 70)
    print("UPLOADING ADDITIONAL IMAGES")
    print("=" * 70)
    
    # Open spreadsheet
    spreadsheet_name = config['google_sheets']['spreadsheet_name']
    sheet = sheets_client.open(spreadsheet_name)
    
    # Get Image Links tab
    tab_name = config['google_sheets']['tabs']['image_links']
    worksheet = sheet.worksheet(tab_name)
    records = worksheet.get_all_records()
    
    print(f"\n✓ Found {len(records)} SKUs in Image Links tab")
    
    results = []
    
    for idx, record in enumerate(records, 1):
        # Use SKU Clean if available, fallback to SKU
        sku = record.get('SKU Clean', record.get('SKU', '')).strip()
        drive_link = record.get('Drive_Folder_Link', '').strip()
        
        if not sku or not drive_link:
            continue
        
        print(f"\n[{idx}/{len(records)}] Processing SKU: {sku}")
        
        # Check which images already exist
        existing_images = get_existing_images(sku, cloudinary_folder)
        
        if not existing_images:
            print(f"  ⚠️  No existing images found - use main upload script instead")
            continue
        
        print(f"  Existing images: {existing_images}")
        
        # Get folder ID
        folder_id = extract_folder_id(drive_link)
        if not folder_id:
            print(f"  ❌ Invalid Drive link")
            continue
        
        # List images in folder
        files = list_images_in_folder(drive_service, folder_id)
        if not files:
            print(f"  ⚠️  No images found in folder")
            continue
        
        print(f"  Found {len(files)} image(s) in Drive folder")
        
        # Upload missing images
        uploaded_count = 0
        
        for img_idx in range(1, min(6, len(files) + 1)):  # Max 5 images
            if img_idx in existing_images:
                print(f"    Image {img_idx}: Already exists, skipping")
                continue
            
            if img_idx > len(files):
                break
            
            file = files[img_idx - 1]
            print(f"    Image {img_idx}: Uploading '{file['name']}'...", end=' ')
            
            # Download to memory
            image_buffer = download_image_to_memory(drive_service, file['id'])
            
            if not image_buffer:
                print("❌ Download failed")
                continue
            
            # Upload to Cloudinary
            public_id = f"{cloudinary_folder}/{sku}_{img_idx}"
            
            try:
                result = cloudinary.uploader.upload(
                    image_buffer,
                    public_id=public_id,
                    overwrite=True,
                    resource_type='image',
                    format='jpg'
                )
                print(f"✓ Uploaded")
                uploaded_count += 1
                
            except Exception as e:
                print(f"❌ Upload failed: {e}")
        
        if uploaded_count > 0:
            print(f"  ✓ Successfully uploaded {uploaded_count} additional image(s)")
            results.append({
                'sku': sku,
                'status': 'Success',
                'uploaded': uploaded_count
            })
        else:
            print(f"  ℹ️  No new images to upload")
            results.append({
                'sku': sku,
                'status': 'No new images',
                'uploaded': 0
            })
        
        # Rate limiting
        time.sleep(1.0)
    
    # Summary
    print("\n" + "=" * 70)
    print("UPLOAD SUMMARY")
    print("=" * 70)
    
    total_uploaded = sum(r['uploaded'] for r in results)
    success_count = sum(1 for r in results if r['uploaded'] > 0)
    
    print(f"Total SKUs processed: {len(results)}")
    print(f"SKUs with new uploads: {success_count}")
    print(f"Total images uploaded: {total_uploaded}")
    
    return results

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("BROWNBUTTER - UPLOAD ADDITIONAL IMAGES")
    print("Uploads missing images (_2, _3, _4, _5) for existing SKUs")
    print("=" * 70)
    print()
    
    config = load_config()
    sheets_client, drive_service = authenticate_google_services(config)
    cloudinary_folder = setup_cloudinary(config)
    
    results = upload_additional_images(config, sheets_client, drive_service, cloudinary_folder)
    
    print("\n" + "=" * 70)
    print("COMPLETE!")
    print("=" * 70)
    print("\nNext step: Run sync_urls_to_sheet.py to update Image Links with new URLs")

if __name__ == "__main__":
    main()