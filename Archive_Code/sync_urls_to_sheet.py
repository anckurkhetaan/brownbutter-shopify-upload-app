#!/usr/bin/env python3
"""
BrownButter - Sync Cloudinary URLs to Google Sheet
Fetches all image URLs from Cloudinary and maps them to Google Sheet by SKU.
Images are named as SKU_1, SKU_2, SKU_3 on Cloudinary.
"""

import os
import sys
import yaml
import gspread
from google.oauth2.service_account import Credentials
import cloudinary
import cloudinary.api
from collections import defaultdict

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
    try:
        spreadsheet_name = config['google_sheets']['spreadsheet_name']
        sheet = client.open(spreadsheet_name)
        print(f"Opened spreadsheet: {spreadsheet_name}")
        return sheet
    except Exception as e:
        print(f"Error opening spreadsheet: {e}")
        sys.exit(1)

# ============================================================================
# FETCH FROM CLOUDINARY
# ============================================================================

def fetch_all_cloudinary_urls(cloudinary_folder):
    """
    List all images in the Cloudinary folder and group by SKU.
    Images are named: SKU_1, SKU_2, SKU_3 ...
    Returns dict: { 'SKU123': ['url1', 'url2', ...], ... }
    """
    print("\n" + "=" * 70)
    print("FETCHING IMAGE LIST FROM CLOUDINARY")
    print("=" * 70)

    sku_map = defaultdict(list)
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
    return result

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


def update_sheet_with_urls(sheet, config, sku_url_map):
    """Write Cloudinary URLs into the Image Links tab, matched by SKU.
    Iterates sheet rows so the source of truth is the sheet's SKU list.
    All writes are batched into a single API call to avoid quota errors.
    """

    print("\n" + "=" * 70)
    print("UPDATING GOOGLE SHEET")
    print("=" * 70)

    tab_name = config['google_sheets']['tabs']['image_links']
    worksheet = sheet.worksheet(tab_name)

    all_values = worksheet.get_all_values()
    headers = all_values[0]

    sku_col_idx = headers.index('SKU') if 'SKU' in headers else 0  # 0-based

    # Find or create Image_1_URL ... Image_5_URL columns (header row only, one call)
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

    if header_updates:
        worksheet.batch_update(header_updates)
        print(f"  Added {len(header_updates)} missing header column(s)")

    # Build batch updates by iterating sheet rows (sheet is source of truth)
    batch = []
    updated = 0
    no_cloudinary_data = 0

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

        for i, url in enumerate(urls, start=1):
            if i in url_col_indices:
                col_idx = url_col_indices[i]  # 0-based
                cell = f'{col_letter(col_idx + 1)}{row_idx}'
                batch.append({'range': cell, 'values': [[url]]})

        print(f"  {sku}: {len(urls)} URL(s) queued")
        updated += 1

    # Single API call for all updates
    if batch:
        worksheet.batch_update(batch)
        print(f"\nBatch write complete — {len(batch)} cell(s) updated.")
    else:
        print("\nNothing to write.")

    print(f"Done. Updated: {updated} | No Cloudinary data: {no_cloudinary_data}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("BROWNBUTTER - SYNC CLOUDINARY URLS TO SHEET")
    print("=" * 70)
    print()

    config = load_config()

    cloudinary_folder = setup_cloudinary(config)

    # Fetch all URLs from Cloudinary grouped by SKU
    sku_url_map = fetch_all_cloudinary_urls(cloudinary_folder)

    # Update Google Sheet
    client = authenticate_sheets(config)
    sheet = open_spreadsheet(client, config)
    update_sheet_with_urls(sheet, config, sku_url_map)

    print("\nAll done! Now run: python generate_shopify_csv.py")

if __name__ == "__main__":
    main()
