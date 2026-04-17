#!/usr/bin/env python3
"""
BrownButter - Sync Cloudinary URLs to Google Sheet
Fetches all image URLs from Cloudinary and maps them to Google Sheet by SKU.
Images are named as SKU_1, SKU_2, SKU_3 on Cloudinary.
"""

import os
import sys
import json
import yaml
import gspread
from google.oauth2.service_account import Credentials
import cloudinary
import cloudinary.api
import cloudinary.uploader
from collections import defaultdict
import time

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
# CLOUDINARY SETUP
# ============================================================================

def setup_cloudinary(config):
    cloudinary_config = config.get('cloudinary', {})
    cloudinary.config(
        cloud_name=cloudinary_config['cloud_name'],
        api_key=cloudinary_config['api_key'],
        api_secret=cloudinary_config['api_secret'],
        secure=True
    )
    print(f"Cloudinary configured: {cloudinary_config['cloud_name']}")
    return cloudinary_config.get('folder', 'brownbutter_products')

# ============================================================================
# GOOGLE SHEETS AUTHENTICATION
# ============================================================================

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
            creds_dict = json.loads(google_creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            # Local - use file
            creds_file = config['google_sheets']['credentials_file']
            print(f"Using credentials file: {creds_file}")
            creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        
        client = gspread.authorize(creds)
        print("Authenticated with Google Sheets")
        return client
    except Exception as e:
        print(f"Error authenticating: {e}")
        sys.exit(1)

def open_spreadsheet(client, config):
    try:
        spreadsheet_name = config['google_sheets']['spreadsheet_name']
        sheet = client.open(spreadsheet_name)
        print(f"Opened spreadsheet: {spreadsheet_name}")
        return sheet
    except Exception as e:
        print(f"Error opening spreadsheet: {e}")
        sys.exit(1)

# ============================================================================
# AI TITLE GENERATION
# ============================================================================

def generate_ai_title_from_cloudinary(public_id, category='clothing'):
    """
    Fetch full AI caption from Cloudinary without processing.
    Returns the raw caption for manual editing in Google Sheets.
    """
    try:
        print(f"\n    Fetching caption for {public_id}")
        
        # First, check if captioning already exists
        check_result = cloudinary.api.resource(
            public_id,
            type="upload"
        )
        
        # Check if captioning data already exists
        existing_info = check_result.get('info', {})
        existing_detection = existing_info.get('detection', {})
        existing_captioning = existing_detection.get('captioning', {})
        
        if existing_captioning and existing_captioning.get('status') == 'complete':
            print(f"    Captioning already exists, using cached")
            data = existing_captioning.get('data', {})
            caption = data.get('caption', '')
            
            if caption:
                print(f"    Caption: {caption[:80]}...")
                return caption  # Return raw caption as-is
        
        # If no existing captioning, request new analysis
        print(f"    Requesting new caption...")
        result = cloudinary.api.update(
            public_id,
            detection="captioning",
            invalidate=False  # Use cache if available
        )
        
        # Extract caption
        info = result.get('info', {})
        detection = info.get('detection', {})
        captioning_data = detection.get('captioning', {})
        data = captioning_data.get('data', {})
        caption = data.get('caption', '')
        
        if caption:
            print(f"    Caption: {caption[:80]}...")
            return caption  # Return raw caption as-is
        
        return None
        
    except Exception as e:
        print(f"    ERROR: {str(e)}")
        return None

def format_caption_as_title(caption):
    """
    Convert AI caption to product title format (5-7 words).
    Example: "A young woman wearing a vibrant red halter dress..." 
    -> "Vibrant Red Halter Dress"
    """
    # Clean the caption
    caption = caption.strip().lower()
    
    # Remove common filler words and photography-related terms
    filler_words = [
        'a', 'an', 'the', 'is', 'are', 'was', 'were', 'of', 'in', 'on', 'at', 'to', 'for', 
        'with', 'wearing', 'woman', 'man', 'person', 'someone', 'young', 'stands', 'against',
        'plain', 'white', 'background', 'her', 'his', 'their', 'long', 'wavy', 'hair', 
        'cascading', 'over', 'shoulders', 'framing', 'face', 'looking', 'posing'
    ]
    
    # Split into words
    words = caption.split()
    
    # Filter out filler words, keep meaningful fashion words
    meaningful_words = []
    for word in words:
        # Remove punctuation
        clean_word = word.strip('.,;:!?')
        if clean_word not in filler_words and len(clean_word) > 2:
            meaningful_words.append(clean_word)
    
    # If we filtered too much, use original approach
    if len(meaningful_words) < 3:
        meaningful_words = [w for w in words if w not in ['a', 'an', 'the', 'is', 'are']]
    
    # Take 5-7 most relevant words (prioritize adjectives and nouns)
    if len(meaningful_words) > 7:
        title_words = meaningful_words[:7]
    else:
        title_words = meaningful_words[:min(7, len(meaningful_words))]
    
    # Ensure we have at least 3 words
    if len(title_words) < 3 and len(words) >= 3:
        title_words = words[:5]
    
    # Capitalize each word
    title = ' '.join(word.capitalize() for word in title_words)
    
    return title

def format_tags_as_title(tags):
    """Build title from AI tags (fallback method)"""
    # Filter relevant fashion tags
    fashion_keywords = ['dress', 'top', 'blouse', 'shirt', 'skirt', 'pants', 'clothing', 
                        'black', 'white', 'red', 'blue', 'green', 'casual', 'formal']
    
    relevant_tags = [tag for tag in tags if any(kw in tag.lower() for kw in fashion_keywords)]
    
    if relevant_tags:
        # Take first 3-5 relevant tags
        selected = relevant_tags[:5]
        title = ' '.join(word.capitalize() for word in selected)
        return title
    
    return None

# ============================================================================
# FETCH FROM CLOUDINARY
# ============================================================================

def fetch_all_cloudinary_urls(cloudinary_folder):
    """
    List all images in the Cloudinary folder and group by SKU.
    Images are named: SKU_1, SKU_2, SKU_3 ...
    Returns tuple: (sku_url_map, sku_public_id_map)
    - sku_url_map: { 'SKU123': ['url1', 'url2', ...], ... }
    - sku_public_id_map: { 'SKU123': 'folder/SKU123_1', ... } (only _1 images for AI)
    """
    print("\n" + "=" * 70)
    print("FETCHING IMAGE LIST FROM CLOUDINARY")
    print("=" * 70)

    sku_map = defaultdict(list)
    sku_public_ids = {}  # Store public_id for _1 images only
    next_cursor = None
    total_fetched = 0

    while True:
        params = {
            'type': 'upload',
            'prefix': cloudinary_folder + '/',
            'max_results': 500,
            'resource_type': 'image'
        }
        if next_cursor:
            params['next_cursor'] = next_cursor

        response = cloudinary.api.resources(**params)
        resources = response.get('resources', [])
        total_fetched += len(resources)

        for resource in resources:
            secure_url = resource['secure_url']
            public_id = resource['public_id']  # e.g. folder/SKU_1

            # Extract just the filename part after the folder
            filename = public_id.split('/')[-1]  # e.g. SKU_1

            # Split on last underscore to get SKU and image index
            # Handles SKUs that may themselves contain underscores
            parts = filename.rsplit('_', 1)
            if len(parts) == 2 and parts[1].isdigit():
                sku = parts[0]
                img_index = int(parts[1])
                sku_map[sku].append((img_index, secure_url))
                
                # Store public_id for main image (_1) for AI title generation
                if img_index == 1:
                    sku_public_ids[sku] = public_id
            else:
                print(f"  Skipping unrecognised filename: {filename}")

        print(f"  Fetched {total_fetched} image(s) so far...")

        next_cursor = response.get('next_cursor')
        if not next_cursor:
            break

    # Sort URLs by image index for each SKU
    result = {}
    for sku, entries in sku_map.items():
        sorted_urls = [url for _, url in sorted(entries, key=lambda x: x[0])]
        result[sku] = sorted_urls

    print(f"\nTotal images fetched: {total_fetched}")
    print(f"Total SKUs found:     {len(result)}")
    print(f"Main images for AI:   {len(sku_public_ids)}")
    return result, sku_public_ids

# ============================================================================
# UPDATE GOOGLE SHEET
# ============================================================================

def col_letter(n):
    """Convert 1-based column index to letter (e.g. 1 -> A, 27 -> AA)."""
    result = ''
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def update_sheet_with_urls(sheet, config, sku_url_map, sku_public_ids):
    """Write Cloudinary URLs and AI titles into the Image Links tab, matched by SKU.
    Iterates sheet rows so the source of truth is the sheet's SKU list.
    All writes are batched into a single API call to avoid quota errors.
    Generates AI titles for main images (_1) using Cloudinary AI.
    """

    print("\n" + "=" * 70)
    print("UPDATING GOOGLE SHEET")
    print("=" * 70)

    tab_name = config['google_sheets']['tabs']['image_links']
    worksheet = sheet.worksheet(tab_name)

    all_values = worksheet.get_all_values()
    headers = all_values[0]

    # Use SKU Clean if available, fallback to SKU
    if 'SKU Clean' in headers:
        sku_col_idx = headers.index('SKU Clean')
        print("  Using 'SKU Clean' column")
    elif 'SKU' in headers:
        sku_col_idx = headers.index('SKU')
        print("  Using 'SKU' column (SKU Clean not found)")
    else:
        sku_col_idx = 0
        print("  WARNING: Neither SKU Clean nor SKU column found, using column A")

    # Find or create Image_1_URL ... Image_5_URL columns + AI_Title column
    url_col_indices = {}  # 1-based image number -> 0-based col index
    header_updates = []
    
    for i in range(1, 6):
        col_name = f'Image_{i}_URL'
        if col_name in headers:
            url_col_indices[i] = headers.index(col_name)
        else:
            new_idx = len(headers)
            headers.append(col_name)
            url_col_indices[i] = new_idx
            header_updates.append({
                'range': f'{col_letter(new_idx + 1)}1',
                'values': [[col_name]]
            })
    
    # Add Image_1_Title column
    if 'Image_1_Title' in headers:
        ai_title_col_idx = headers.index('Image_1_Title')
    else:
        ai_title_col_idx = len(headers)
        headers.append('Image_1_Title')
        header_updates.append({
            'range': f'{col_letter(ai_title_col_idx + 1)}1',
            'values': [['Image_1_Title']]
        })

    if header_updates:
        worksheet.batch_update(header_updates)
        print(f"  Added {len(header_updates)} missing header column(s)")

    # Get list of SKUs and Categories from Image Links tab (source of truth)
    sheet_skus = set()
    sku_categories = {}  # SKU -> Category mapping
    
    # Get category column index if exists
    category_col_idx = headers.index('Category') if 'Category' in headers else -1
    
    for row in all_values[1:]:
        if len(row) > sku_col_idx:
            sku = row[sku_col_idx].strip()
            if sku:
                sheet_skus.add(sku)
                
                # Get category if column exists
                if category_col_idx >= 0 and len(row) > category_col_idx:
                    category = row[category_col_idx].strip()
                    if category:
                        sku_categories[sku] = category
    
    print(f"\nFound {len(sheet_skus)} SKU(s) in Image Links tab")
    if sku_categories:
        print(f"Found {len(sku_categories)} SKU(s) with category information")

    # # Generate AI titles
    # # Script will check Cloudinary to see if captioning already exists
    # print("\n" + "=" * 70)
    # print("GENERATING AI TITLES (Main Images Only)")
    # print("=" * 70)
    
    # ai_titles = {}  # SKU -> title
    
    # for sku, public_id in sku_public_ids.items():
    #     # Skip if this SKU is not in the Image Links tab
    #     if sku not in sheet_skus:
    #         continue
        
    #     # Get category for this SKU (default to 'clothing' if not specified)
    #     category = sku_categories.get(sku, 'clothing')
            
    #     print(f"  {sku} ({category}): ", end='')
    #     title = generate_ai_title_from_cloudinary(public_id, category)
    #     if title:
    #         ai_titles[sku] = title
    #         print(f"'{title}'")
    #     else:
    #         print("Failed (will use fallback)")
        
    #     # Small delay to respect rate limits
    #     time.sleep(0.3)
    
    # print(f"\nGenerated {len(ai_titles)} AI title(s)")

    # # Build batch updates by iterating sheet rows (sheet is source of truth)
    # print("\n" + "=" * 70)
    # print("UPDATING URLS AND TITLES")
    # print("=" * 70)
    
    # batch = []
    # updated = 0
    # no_cloudinary_data = 0

    for row_idx, row in enumerate(all_values[1:], start=2):  # row_idx is 1-based sheet row
        if len(row) <= sku_col_idx:
            continue
        sku = row[sku_col_idx].strip()
        if not sku:
            continue

        urls = sku_url_map.get(sku)
        if not urls:
            print(f"  {sku}: not found in Cloudinary — skipping")
            no_cloudinary_data += 1
            continue

        # Update URLs
        for i, url in enumerate(urls, start=1):
            if i in url_col_indices:
                col_idx = url_col_indices[i]  # 0-based
                cell = f'{col_letter(col_idx + 1)}{row_idx}'
                batch.append({'range': cell, 'values': [[url]]})
        
        # Update AI title if available
        if sku in ai_titles:
            title_cell = f'{col_letter(ai_title_col_idx + 1)}{row_idx}'
            batch.append({'range': title_cell, 'values': [[ai_titles[sku]]]})

        print(f"  {sku}: {len(urls)} URL(s) + AI title queued")
        updated += 1

    # Single API call for all updates
    if batch:
        worksheet.batch_update(batch)
        print(f"\nBatch write complete — {len(batch)} cell(s) updated.")
    else:
        print("\nNothing to write.")

    print(f"Done. Updated: {updated} | No Cloudinary data: {no_cloudinary_data}")
    print(f"AI titles generated: {len(ai_titles)}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("BROWNBUTTER - SYNC CLOUDINARY URLS TO SHEET")
    print("With AI Title Generation")
    print("=" * 70)
    print()

    config = load_config()

    cloudinary_folder = setup_cloudinary(config)

    # Fetch all URLs from Cloudinary grouped by SKU
    sku_url_map, sku_public_ids = fetch_all_cloudinary_urls(cloudinary_folder)

    # Update Google Sheet with URLs and AI titles
    client = authenticate_sheets(config)
    sheet = open_spreadsheet(client, config)
    update_sheet_with_urls(sheet, config, sku_url_map, sku_public_ids)

    print("\n" + "=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print("1. Review AI titles in 'Image Links' tab")
    print("2. Edit any titles if needed")
    print("3. Run: python generate_shopify_csv.py")
    print("=" * 70)

if __name__ == "__main__":
    main()