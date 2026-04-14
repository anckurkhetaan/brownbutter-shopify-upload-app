#!/usr/bin/env python3
"""
BrownButter - REGENERATE AI Titles (Force Override)
Forces regeneration of ALL AI titles - ignores existing captions
Use this when you want to update titles with category context
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
import re

# ============================================================================
# CONFIGURATION
# ============================================================================

def load_config():
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
# AI TITLE GENERATION - FORCE REGENERATE
# ============================================================================

def generate_ai_title_from_cloudinary(public_id, category='clothing'):
    """
    FORCE REGENERATE AI title - always requests new analysis.
    Extracts product description from 'wearing' pattern in caption.
    """
    try:
        print(f"\n    Generating for {public_id}")
        
        # Request captioning
        result = cloudinary.api.update(
            public_id,
            detection="captioning",
            invalidate=True
        )
        
        # Extract caption
        info = result.get('info', {})
        detection = info.get('detection', {})
        captioning_data = detection.get('captioning', {})
        data = captioning_data.get('data', {})
        caption = data.get('caption', '')
        
        if not caption:
            return None
        
        print(f"    Full caption: {caption}")
        
        # Extract product description
        title = extract_product_from_caption(caption, category)
        
        return title
        
    except Exception as e:
        print(f"    ERROR: {str(e)}")
        return None

def extract_product_from_caption(caption, category):
    """
    Extract product description from caption.
    Pattern: "...wearing a [PRODUCT], standing..."
    Handles multi-garment: "wearing a black top and white pants"
    Returns: 2-4 word title without category duplication
    """
    caption_lower = caption.lower()
    
    # Check for "wearing" pattern
    if 'wearing' not in caption_lower:
        return f"{category} Premium"
    
    # Extract everything after "wearing a/an"
    after_wearing = re.split(r'wearing\s+(?:a|an)?\s*', caption_lower, 1)
    if len(after_wearing) < 2:
        return f"{category} Premium"
    
    after_wearing = after_wearing[1]
    
    # Split by "and" for multi-garment images
    garments = re.split(r'\s+and\s+', after_wearing)
    
    # Family-based grouping
    garment_families = {
        'tops_family': {
            'categories': ['tops', 'top', 'tank tops', 'blouses', 'blouse', 'shirts', 'shirt'],
            'keywords': ['top', 'tops', 'blouse', 'blouses', 'shirt', 'shirts', 't-shirt', 'tank']
        },
        'bottoms_family': {
            'categories': ['pants', 'trousers', 'shorts', 'jeans', 'trouser'],
            'keywords': ['pants', 'trousers', 'shorts', 'jeans', 'trouser']
        },
        'dresses_family': {
            'categories': ['dresses', 'dress', 'one-pieces', 'one-piece'],
            'keywords': ['dress', 'dresses', 'gown', 'jumpsuit', 'romper']
        },
        'skirts_family': {
            'categories': ['skirts', 'skirt'],
            'keywords': ['skirt', 'skirts']
        },
        'sets_family': {
            'categories': ['outfit sets', 'outfit set'],
            'keywords': ['set', 'outfit', 'co-ord']
        }
    }
    
    # Find which family our category belongs to
    category_lower = category.lower()
    category_keywords = []
    
    for family_name, family_data in garment_families.items():
        if category_lower in family_data['categories']:
            category_keywords = family_data['keywords']
            break
    
    if not category_keywords:
        category_keywords = [category_lower]
    
    # Add individual words from multi-word categories
    category_parts = category_lower.split()
    for part in category_parts:
        if part not in category_keywords and len(part) > 2:
            category_keywords.append(part)
    
    # Find the garment that matches our category
    selected_garment = garments[0]  # Default to first
    for garment in garments:
        # Check if any keyword exists in this garment (case-insensitive)
        if any(keyword in garment.lower() for keyword in category_keywords):
            selected_garment = garment
            print(f"    Matched '{garment}' to category '{category}'")
            break
    else:
        print(f"    WARNING: No match for '{category}', using first garment: '{garments[0]}'")
    
    # Clean: stop at punctuation or common ending phrases
    selected_garment = re.split(r'[,\.]|standing|stands|posing|against|background|with her|with his', selected_garment)[0].strip()
    
    print(f"    Extracted: '{selected_garment}'")
    
    # Extract meaningful words, remove category keywords and filler
    words = selected_garment.split()
    filler = {'a', 'an', 'the', 'with', 'and', 'very'}
    
    clean_words = []
    for word in words:
        cleaned = word.strip('-,.')
        # Skip if it's a category keyword or filler
        if cleaned in category_keywords or cleaned in filler:
            continue
        if len(cleaned) > 1:
            clean_words.append(cleaned.capitalize())
    
    # Build title: [Category] + [2-3 descriptors]
    # Use singular form (remove trailing 's' if present)
    category_singular = category.rstrip('s') if category.lower().endswith('s') and len(category) > 3 else category
    title_parts = [category_singular.capitalize()] + clean_words[:3]
    
    final_title = ' '.join(title_parts)
    print(f"    Title: '{final_title}'")
    
    return final_title

# ============================================================================
# FETCH FROM CLOUDINARY
# ============================================================================

def fetch_all_cloudinary_urls(cloudinary_folder):
    """List all images and group by SKU"""
    print("\n" + "=" * 70)
    print("FETCHING IMAGE LIST FROM CLOUDINARY")
    print("=" * 70)

    sku_map = defaultdict(list)
    sku_public_ids = {}
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
            public_id = resource['public_id']
            filename = public_id.split('/')[-1]
            parts = filename.rsplit('_', 1)
            
            if len(parts) == 2 and parts[1].isdigit():
                sku = parts[0]
                img_index = int(parts[1])
                sku_map[sku].append((img_index, secure_url))
                
                if img_index == 1:
                    sku_public_ids[sku] = public_id

        print(f"  Fetched {total_fetched} image(s) so far...")
        next_cursor = response.get('next_cursor')
        if not next_cursor:
            break

    result = {}
    for sku, entries in sku_map.items():
        sorted_urls = [url for _, url in sorted(entries, key=lambda x: x[0])]
        result[sku] = sorted_urls

    print(f"\nTotal images: {total_fetched}, SKUs: {len(result)}, Main images: {len(sku_public_ids)}")
    return result, sku_public_ids

# ============================================================================
# UPDATE GOOGLE SHEET
# ============================================================================

def col_letter(n):
    """Convert 1-based column index to letter"""
    result = ''
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result

def update_sheet_with_urls(sheet, config, sku_url_map, sku_public_ids):
    """Write URLs and AI titles to sheet"""
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
    
    # Find/create columns
    url_col_indices = {}
    header_updates = []
    
    for i in range(1, 6):
        col_name = f'Image_{i}_URL'
        if col_name in headers:
            url_col_indices[i] = headers.index(col_name)
        else:
            new_idx = len(headers)
            headers.append(col_name)
            url_col_indices[i] = new_idx
            header_updates.append({'range': f'{col_letter(new_idx + 1)}1', 'values': [[col_name]]})
    
    if 'Image_1_Title' in headers:
        ai_title_col_idx = headers.index('Image_1_Title')
    else:
        ai_title_col_idx = len(headers)
        headers.append('Image_1_Title')
        header_updates.append({'range': f'{col_letter(ai_title_col_idx + 1)}1', 'values': [['Image_1_Title']]})

    if header_updates:
        worksheet.batch_update(header_updates)
        print(f"  Added {len(header_updates)} header(s)")

    # Get SKUs and Categories
    sheet_skus = set()
    sku_categories = {}
    category_col_idx = headers.index('Category') if 'Category' in headers else -1
    
    for row in all_values[1:]:
        if len(row) > sku_col_idx:
            sku = row[sku_col_idx].strip()
            if sku:
                sheet_skus.add(sku)
                if category_col_idx >= 0 and len(row) > category_col_idx:
                    category = row[category_col_idx].strip()
                    if category:
                        sku_categories[sku] = category
    
    print(f"\nFound {len(sheet_skus)} SKU(s), {len(sku_categories)} with category")

    # Generate AI titles
    print("\n" + "=" * 70)
    print("GENERATING AI TITLES (FORCE REGENERATE)")
    print("=" * 70)
    
    ai_titles = {}
    
    for sku, public_id in sku_public_ids.items():
        if sku not in sheet_skus:
            continue
        
        category = sku_categories.get(sku, 'clothing')
        print(f"  {sku} ({category}): ", end='')
        
        title = generate_ai_title_from_cloudinary(public_id, category)
        if title:
            ai_titles[sku] = title
        else:
            print("Failed")
        
        time.sleep(0.3)
    
    print(f"\nGenerated {len(ai_titles)} AI title(s)")

    # Update sheet
    batch = []
    updated = 0
    
    for row_idx, row in enumerate(all_values[1:], start=2):
        if len(row) <= sku_col_idx:
            continue
        sku = row[sku_col_idx].strip()
        if not sku:
            continue

        urls = sku_url_map.get(sku)
        if not urls:
            continue

        for i, url in enumerate(urls, start=1):
            if i in url_col_indices:
                col_idx = url_col_indices[i]
                cell = f'{col_letter(col_idx + 1)}{row_idx}'
                batch.append({'range': cell, 'values': [[url]]})
        
        if sku in ai_titles:
            title_cell = f'{col_letter(ai_title_col_idx + 1)}{row_idx}'
            batch.append({'range': title_cell, 'values': [[ai_titles[sku]]]})

        updated += 1

    if batch:
        worksheet.batch_update(batch)
        print(f"\nBatch write complete — {len(batch)} cell(s) updated")
    
    print(f"Done. Updated: {updated} SKU(s)")

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("BROWNBUTTER - REGENERATE AI TITLES (FORCE OVERRIDE)")
    print("Ignores existing captions - regenerates all titles")
    print("=" * 70)
    print()

    config = load_config()
    cloudinary_folder = setup_cloudinary(config)
    sku_url_map, sku_public_ids = fetch_all_cloudinary_urls(cloudinary_folder)
    
    client = authenticate_sheets(config)
    sheet = open_spreadsheet(client, config)
    update_sheet_with_urls(sheet, config, sku_url_map, sku_public_ids)

    print("\n" + "=" * 70)
    print("COMPLETE!")
    print("=" * 70)

if __name__ == "__main__":
    main()