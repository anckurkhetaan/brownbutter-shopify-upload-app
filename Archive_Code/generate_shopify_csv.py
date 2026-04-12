#!/usr/bin/env python3
"""
BrownButter - Script 2: Generate Shopify CSV
Reads product data and image URLs from Google Sheet and generates Shopify-compliant CSV
"""

import os
import sys
import yaml
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import random
import string
from datetime import datetime

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
# DATA RETRIEVAL
# ============================================================================

def get_product_data(sheet, config):
    """Get product data from Product Data tab"""
    try:
        tab_name = config['google_sheets']['tabs']['product_data']
        worksheet = sheet.worksheet(tab_name)
        records = worksheet.get_all_records()
        
        print(f" Loaded {len(records)} products from '{tab_name}' tab")
        return pd.DataFrame(records)
        
    except Exception as e:
        print(f" Error reading product data: {e}")
        sys.exit(1)

def get_image_urls(sheet, config):
    """Get image URLs from Image Links tab"""
    try:
        tab_name = config['google_sheets']['tabs']['image_links']
        worksheet = sheet.worksheet(tab_name)

        # Use get_all_values() so dynamically-added columns (Image_1_URL etc.)
        # are never silently dropped, unlike get_all_records()
        all_values = worksheet.get_all_values()
        if not all_values:
            print(f" Warning: '{tab_name}' tab is empty")
            return pd.DataFrame()

        headers = all_values[0]
        rows = all_values[1:]
        df = pd.DataFrame(rows, columns=headers)

        # Strip whitespace from SKU column to prevent match failures
        df['SKU'] = df['SKU'].str.strip()

        print(f" Loaded {len(df)} image mappings from '{tab_name}' tab")
        print(f"   Columns: {list(df.columns)}")
        return df

    except Exception as e:
        print(f" Error reading image URLs: {e}")
        sys.exit(1)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_handle(category, color):
    """Generate URL handle"""
    # Clean and lowercase
    category_clean = category.lower().replace(' ', '-')
    color_clean = color.lower().replace(' ', '-')
    
    # Generate random 4-character suffix
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    
    return f"{category_clean}-{color_clean}-{random_suffix}"

def generate_title(category, color):
    """Generate product title"""
    return f"{category} - {color}"

def generate_description(title):
    """Generate simple AI-like description"""
    descriptions = [
        f"Premium quality {title.lower()}",
        f"Stylish {title.lower()} for everyday wear",
        f"Trending {title.lower()} collection",
        f"Must-have {title.lower()}",
        f"Comfortable and fashionable {title.lower()}"
    ]
    return random.choice(descriptions)

def get_size_range(category, config):
    """Get size range for category"""
    size_mappings = config.get('size_mappings', {})
    
    # Try to find exact match
    if category in size_mappings:
        return size_mappings[category]
    
    # Default fallback
    return ['XS', 'S', 'M', 'L', 'XL']

def get_tags(category, gender, config):
    """Generate tags for product"""
    tags = []
    
    # Universal tags
    universal = config.get('tags', {}).get('universal', [])
    tags.extend(universal)
    
    # Gender tags
    gender_tags = config.get('tags', {}).get('gender_tags', {}).get(gender, [])
    tags.extend(gender_tags)
    
    # Category tags
    category_tags = config.get('tags', {}).get('category_specific', {}).get(category, [])
    tags.extend(category_tags)
    
    return ', '.join(tags)

def get_shopify_category(category, config):
    """Get Shopify product category"""
    categories = config.get('shopify_categories', {})
    return categories.get(category, 'Apparel & Accessories > Clothing')

def generate_sku(product_code, size_index):
    """Generate SKU"""
    return f"{product_code}-{size_index}"

# ============================================================================
# CSV GENERATION
# ============================================================================

def create_shopify_rows(product, image_data, config):
    """Create Shopify CSV rows for a single product"""
    rows = []
    
    # Get configuration defaults
    defaults = config.get('defaults', {})
    seo = config.get('seo', {})
    
    # Product basic info
    sku = product['SKU']
    title = generate_title(product['Category'], product['Color'])
    handle = generate_handle(product['Category'], product['Color'])
    description = generate_description(title)
    vendor = defaults.get('vendor', 'BrownButter')
    category = get_shopify_category(product.get('Shopify_Category', ''), config)
    tags = get_tags(product.get('Shopify_Category', ''), product['Gender'], config)
    
    # Pricing
    price = product.get('Price_After_Discount', 0)
    compare_price = product.get('MRP_Compare_At_Price', 0)
    
    # SEO
    seo_title = title + seo.get('title_suffix', '')
    seo_description = seo.get('description_template', '').format(title=title)
    
    # Get sizes for this category
    sizes = get_size_range(product.get('Shopify_Category', ''), config)
    
    # Get image URLs for this SKU
    image_urls = []
    for i in range(1, 6):  # Check up to 5 images
        url_col = f'Image_{i}_URL'
        # Check if column exists in the Series
        if url_col in image_data.index:
            url = image_data[url_col]
            if pd.notna(url) and str(url).strip():
                image_urls.append(str(url).strip())
    
    # If no image URLs from sheet, add placeholder
    if not image_urls:
        image_urls = ['']  # Will need to be filled manually
    
    # Create rows for each size with images distributed
    for size_idx, size in enumerate(sizes):
        # Determine which image to use (Option B: distribute images across sizes)
        if size_idx < len(image_urls):
            image_url = image_urls[size_idx]
        else:
            image_url = ''
        
        row = {
            'Title': title if size_idx == 0 else '',
            'URL handle': handle,
            'Description': description if size_idx == 0 else '',
            'Vendor': vendor if size_idx == 0 else '',
            'Product category': category if size_idx == 0 else '',
            'Type': product['Category'] if size_idx == 0 else '',
            'Tags': tags if size_idx == 0 else '',
            'Published on online store': 'TRUE' if defaults.get('published', True) else 'FALSE',
            'Status': defaults.get('status', 'active'),
            'SKU': generate_sku(product['Product_Code'], size_idx + 1),
            'Barcode': '',
            'Option1 name': 'Size',
            'Option1 value': size,
            'Option1 Linked To': '',
            'Option2 name': '',
            'Option2 value': '',
            'Option2 Linked To': '',
            'Option3 name': '',
            'Option3 value': '',
            'Option3 Linked To': '',
            'Price': price,
            'Compare-at price': compare_price if compare_price > 0 else '',
            'Cost per item': product.get('India_Landed_Price', ''),
            'Charge tax': 'TRUE' if defaults.get('taxable', True) else 'FALSE',
            'Tax code': '',
            'Unit price total measure': '',
            'Unit price total measure unit': '',
            'Unit price base measure': '',
            'Unit price base measure unit': '',
            'Inventory tracker': 'shopify',
            'Inventory quantity': defaults.get('inventory_per_size', 5),
            'Continue selling when out of stock': 'DENY' if defaults.get('inventory_policy', 'deny') == 'deny' else 'CONTINUE',
            'Weight value (grams)': defaults.get('weight_grams', 500),
            'Weight unit for display': 'g',
            'Requires shipping': 'TRUE' if defaults.get('requires_shipping', True) else 'FALSE',
            'Fulfillment service': 'manual',
            'Product image URL': image_url,
            'Image position': size_idx + 1 if image_url else '',
            'Image alt text': f"{title} - {size}" if image_url else '',
            'Variant image URL': '',
            'Gift card': 'FALSE',
            'SEO title': seo_title if size_idx == 0 else '',
            'SEO description': seo_description if size_idx == 0 else '',
            'Color (product.metafields.shopify.color-pattern)': product['Color'] if size_idx == 0 else '',
            'Google Shopping / Google product category': category if size_idx == 0 else '',
            'Google Shopping / Gender': product['Gender'] if size_idx == 0 else '',
            'Google Shopping / Age group': 'Adult (13+ years old)' if size_idx == 0 else '',
            'Google Shopping / Manufacturer part number (MPN)': product.get('Product_Code', '') if size_idx == 0 else '',
            'Google Shopping / Ad group name': '',
            'Google Shopping / Ads labels': '',
            'Google Shopping / Condition': 'New' if size_idx == 0 else '',
            'Google Shopping / Custom product': 'FALSE',
            'Google Shopping / Custom label 0': '',
            'Google Shopping / Custom label 1': '',
            'Google Shopping / Custom label 2': '',
            'Google Shopping / Custom label 3': '',
            'Google Shopping / Custom label 4': ''
        }
        
        rows.append(row)
    
    return rows

def generate_csv(product_df, image_df, config):
    """Generate complete Shopify CSV"""
    print("\n" + "=" * 70)
    print("GENERATING SHOPIFY CSV")
    print("=" * 70)
    print()
    
    all_rows = []
    
    for idx, product in product_df.iterrows():
        sku = str(product['SKU']).strip()
        print(f"Processing {idx+1}/{len(product_df)}: {sku}")

        # Find image data for this SKU
        image_data = image_df[image_df['SKU'] == sku]
        
        if image_data.empty:
            print(f"    No image data found for {sku}")
            image_data = pd.Series({'SKU': sku})
        else:
            image_data = image_data.iloc[0]
        
        # Generate rows for this product
        rows = create_shopify_rows(product, image_data, config)
        all_rows.extend(rows)
        
        print(f"   Created {len(rows)} rows")
    
    # Convert to DataFrame
    df = pd.DataFrame(all_rows)
    
    return df

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution"""
    print("=" * 70)
    print("BROWNBUTTER - SHOPIFY CSV GENERATOR")
    print("=" * 70)
    print()
    
    # Load configuration
    config = load_config()
    
    # Authenticate
    client = authenticate_sheets(config)
    
    # Open spreadsheet
    sheet = open_spreadsheet(client, config)
    
    # Get data
    product_df = get_product_data(sheet, config)
    image_df = get_image_urls(sheet, config)
    
    # Generate CSV
    shopify_df = generate_csv(product_df, image_df, config)
    
    # Save CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"shopify_upload_{timestamp}.csv"
    shopify_df.to_csv(output_file, index=False)
    
    print("\n" + "=" * 70)
    print("CSV GENERATION COMPLETE")
    print("=" * 70)
    print(f"\n Created: {output_file}")
    print(f"   Total rows: {len(shopify_df)}")
    print(f"   Total products: {len(product_df)}")
    print("\n" + "=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print("1. Review the CSV file")
    print("2. Verify image URLs are populated")
    print("3. Go to Shopify Admin → Products → Import")
    print("4. Upload the CSV file")
    print("=" * 70)

if __name__ == "__main__":
    main()