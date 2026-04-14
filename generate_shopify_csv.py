#!/usr/bin/env python3
"""
BrownButter - Generate Shopify CSV (New Format 2025)
Generates Shopify-compliant CSV with metafields and AI-generated titles
"""

import os
import sys
import json
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
        print("Error: config.yaml not found!")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

# ============================================================================
# GOOGLE SHEETS AUTHENTICATION
# ============================================================================

def authenticate_sheets(config):
    """Authenticate with Google Sheets API"""
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

def get_product_data(sheet, config):
    """Get product data from Product Data tab"""
    try:
        tab_name = config['google_sheets']['tabs']['product_data']
        worksheet = sheet.worksheet(tab_name)
        records = worksheet.get_all_records()
        
        print(f"Loaded {len(records)} products from '{tab_name}' tab")
        return pd.DataFrame(records)
        
    except Exception as e:
        print(f"Error reading product data: {e}")
        sys.exit(1)

def get_image_urls(sheet, config):
    """Get image URLs from Image Links tab"""
    try:
        tab_name = config['google_sheets']['tabs']['image_links']
        worksheet = sheet.worksheet(tab_name)
        records = worksheet.get_all_records()
        
        print(f"Loaded {len(records)} image mappings from '{tab_name}' tab")
        return pd.DataFrame(records)
        
    except Exception as e:
        print(f"Error reading image URLs: {e}")
        sys.exit(1)

def get_ai_titles(sheet, config):
    """Get AI-generated titles from Image Links tab (Image_1_Title column)"""
    try:
        tab_name = config['google_sheets']['tabs']['image_links']
        worksheet = sheet.worksheet(tab_name)
        records = worksheet.get_all_records()
        
        df = pd.DataFrame(records)
        
        # Check if Image_1_Title column exists
        if 'Image_1_Title' in df.columns:
            print(f"Loaded {len(df)} AI titles from '{tab_name}' tab")
            return df[['SKU', 'Image_1_Title']].rename(columns={'Image_1_Title': 'AI_Title'})
        # Fallback to AI_Title if exists
        elif 'AI_Title' in df.columns:
            print(f"Loaded {len(df)} AI titles from '{tab_name}' tab (AI_Title column)")
            return df[['SKU', 'AI_Title']]
        else:
            print(f"Warning: 'Image_1_Title' column not found in '{tab_name}' - will use generated titles")
            return pd.DataFrame()
        
    except Exception as e:
        print(f"Error reading AI titles: {e}")
        return pd.DataFrame()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def normalize_category_key(category):
    """Convert category name to config key format"""
    # Convert to lowercase, replace spaces with underscores
    return category.lower().replace(' ', '_').replace('-', '_')


def generate_handle(category, color):
    """Generate URL handle"""
    category_clean = category.lower().replace(' ', '-').replace('&', 'and')
    color_clean = color.lower().replace(' ', '-')
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{category_clean}-{color_clean}-{random_suffix}"

def generate_fallback_title(category, color):
    """Generate fallback title if AI title not available"""
    return f"{category} - {color}"

def normalize_category_key(category):
    """Convert category name to config key format"""
    return category.lower().replace(' ', '_').replace('-', '_')

def generate_description(title, category):
    """Generate simple description"""
    templates = [
        f"<p>Premium quality {title.lower()}</p>",
        f"<p>Stylish {title.lower()} for everyday wear</p>",
        f"<p>Trending {title.lower()} collection</p>",
        f"<p>Comfortable and fashionable {title.lower()}</p>"
    ]
    return random.choice(templates)

def get_size_range(category, config):
    """Get size range for category"""
    size_mappings = config.get('size_mappings', {})
    
    # Normalize category key
    category_key = normalize_category_key(category)
    
    if category_key in size_mappings:
        return size_mappings[category_key]
    
    # Default fallback
    return ['XS', 'S', 'M', 'L', 'XL']

def get_tags(category, gender, config):
    """Generate tags for product"""
    tags = []
    
    # Normalize category key
    category_key = normalize_category_key(category)
    
    # Universal tags
    universal = config.get('tags', {}).get('universal', [])
    tags.extend(universal)
    
    # Gender tags
    gender_tags = config.get('tags', {}).get('gender_tags', {}).get(gender, [])
    tags.extend(gender_tags)
    
    # Category tags
    category_tags = config.get('tags', {}).get('category_specific', {}).get(category_key, [])
    tags.extend(category_tags)
    
    return ', '.join(tags)

def get_shopify_category(gender, category, config):
    """Get Shopify product category by combining gender + category"""
    gender_key = normalize_category_key(gender)
    category_key = normalize_category_key(category)
    full_key = f"{gender_key}_{category_key}"
    
    categories = config.get('shopify_categories', {})
    return categories.get(full_key, '')

def generate_sku(product_code, size_index):
    """Generate SKU"""
    return f"{product_code}-{size_index}"

def get_size_metafield_value(sizes):
    """Format size values for metafield"""
    return '; '.join([s.lower() for s in sizes])

# ============================================================================
# CSV GENERATION (NEW SHOPIFY FORMAT)
# ============================================================================

def create_shopify_rows(product, image_data, ai_title_data, config):
    """Create Shopify CSV rows for a single product (NEW FORMAT)"""
    rows = []
    
    # Get configuration defaults
    defaults = config.get('defaults', {})
    seo = config.get('seo', {})
    metafields = config.get('metafields', {})
    
    # Product basic info
    sku = product['SKU']
    
    # Get AI title if available, otherwise use fallback
    if not ai_title_data.empty and sku in ai_title_data['SKU'].values:
        ai_row = ai_title_data[ai_title_data['SKU'] == sku].iloc[0]
        title = ai_row.get('AI_Title', '') if pd.notna(ai_row.get('AI_Title')) else generate_fallback_title(product['Category'], product['Color'])
    else:
        title = generate_fallback_title(product['Category'], product['Color'])
    
    handle = generate_handle(product['Category'], product['Color'])
    description = generate_description(title, product['Category'])
    vendor = defaults.get('vendor', 'BrownButter')
    
    # Generate category key from Gender + Category
    gender_key = normalize_category_key(product['Gender'])
    category_key = normalize_category_key(product['Category'])
    full_key = f"{gender_key}_{category_key}"
    
    category = get_shopify_category(product['Gender'], product['Category'], config)
    tags = get_tags(full_key, product['Gender'], config)
    
    # Pricing
    price = product.get('Price_After_Discount', 0)
    compare_price = product.get('MRP_Compare_At_Price', 0)
    cost_per_item = product.get('India_Landed_Price', '')
    
    # SEO
    seo_title = title + seo.get('title_suffix', '')
    seo_description = seo.get('description_template', '').format(title=title)
    
    # Get sizes for this category
    gender_key = normalize_category_key(product['Gender'])
    category_key = normalize_category_key(product['Category'])
    full_key = f"{gender_key}_{category_key}"
    sizes = get_size_range(full_key, config)
    
    # Metafields
    age_group = metafields.get('age_group', 'adults')
    color_metafield = product.get('Color', 'blue')
    fabric_metafield = product.get('Material', 'polyester')
    target_gender = product['Gender'].lower() if product.get('Gender') else 'female'
    size_metafield = get_size_metafield_value(sizes)
    
    # Get image URLs for this SKU
    image_urls = []
    if not image_data.empty and sku in image_data['SKU'].values:
        img_row = image_data[image_data['SKU'] == sku].iloc[0]
        for i in range(1, 6):
            url_col = f'Image_{i}_URL'
            if url_col in img_row.index:
                url = img_row[url_col]
                if pd.notna(url) and str(url).strip():
                    image_urls.append(str(url).strip())
    
    if not image_urls:
        image_urls = ['']
    
    # Create rows for each size with images distributed
    for size_idx, size in enumerate(sizes):
        # Determine which image to use (distribute images across sizes)
        if size_idx < len(image_urls):
            image_url = image_urls[size_idx]
            image_position = size_idx + 1
        else:
            image_url = ''
            image_position = ''
        
        # First row has all product info, subsequent rows are minimal
        row = {
            'Handle': handle,
            'Title': title if size_idx == 0 else '',
            'Body (HTML)': description if size_idx == 0 else '',
            'Vendor': vendor if size_idx == 0 else '',
            'Product Category': category if size_idx == 0 else '',
            'Type': product['Category'] if size_idx == 0 else '',
            'Tags': tags if size_idx == 0 else '',
            'Published': 'TRUE' if defaults.get('published', True) else 'FALSE',
            'Option1 Name': 'Size',
            'Option1 Value': size,
            'Option1 Linked To': 'product.metafields.shopify.size',
            'Option2 Name': '',
            'Option2 Value': '',
            'Option2 Linked To': '',
            'Option3 Name': '',
            'Option3 Value': '',
            'Option3 Linked To': '',
            'Variant SKU': generate_sku(product['Product_Code'], size_idx + 1),
            'Variant Grams': defaults.get('weight_grams', 500),
            'Variant Inventory Tracker': 'shopify',
            'Variant Inventory Qty': defaults.get('inventory_per_size', 5),
            'Variant Inventory Policy': 'deny' if defaults.get('inventory_policy', 'deny') == 'deny' else 'continue',
            'Variant Fulfillment Service': 'manual',
            'Variant Price': price,
            'Variant Compare At Price': compare_price if compare_price > 0 else '',
            'Variant Requires Shipping': 'TRUE' if defaults.get('requires_shipping', True) else 'FALSE',
            'Variant Taxable': 'TRUE' if defaults.get('taxable', True) else 'FALSE',
            'Unit Price Total Measure': '',
            'Unit Price Total Measure Unit': '',
            'Unit Price Base Measure': '',
            'Unit Price Base Measure Unit': '',
            'Variant Barcode': '',
            'Image Src': image_url,
            'Image Position': image_position if image_url else '',
            'Image Alt Text': '' if not image_url else '',
            'Gift Card': 'FALSE',
            'SEO Title': seo_title if size_idx == 0 else '',
            'SEO Description': seo_description if size_idx == 0 else '',
            'Age group (product.metafields.shopify.age-group)': age_group if size_idx == 0 else '',
            'Color (product.metafields.shopify.color-pattern)': color_metafield if size_idx == 0 else '',
            'Costume theme (product.metafields.shopify.costume-theme)': '',
            'Dress occasion (product.metafields.shopify.dress-occasion)': 'casual; everyday' if size_idx == 0 else '',
            'Dress style (product.metafields.shopify.dress-style)': '',
            'Fabric (product.metafields.shopify.fabric)': fabric_metafield if size_idx == 0 else '',
            'Size (product.metafields.shopify.size)': size_metafield if size_idx == 0 else '',
            'Skirt/Dress length type (product.metafields.shopify.skirt-dress-length-type)': '',
            'Sleeve length type (product.metafields.shopify.sleeve-length-type)': '',
            'Target gender (product.metafields.shopify.target-gender)': target_gender if size_idx == 0 else '',
            'Variant Image': '',
            'Variant Weight Unit': 'kg',
            'Variant Tax Code': '',
            'Cost per item': cost_per_item if size_idx == 0 else '',
            'Status': defaults.get('status', 'active')
        }
        
        rows.append(row)
    
    return rows

def generate_csv(product_df, image_df, ai_title_df, config):
    """Generate complete Shopify CSV"""
    print("\n" + "=" * 70)
    print("GENERATING SHOPIFY CSV (NEW FORMAT)")
    print("=" * 70)
    print()
    
    all_rows = []
    
    for idx, (_, product) in enumerate(product_df.iterrows()):
        sku = product['SKU']
        print(f"Processing {idx+1}/{len(product_df)}: {sku}")
        
        # Generate rows for this product
        rows = create_shopify_rows(product, image_df, ai_title_df, config)
        all_rows.extend(rows)
        
        print(f"  Created {len(rows)} rows")
    
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
    print("New Shopify Format 2025 with Metafields")
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
    ai_title_df = get_ai_titles(sheet, config)
    
    # Generate CSV
    shopify_df = generate_csv(product_df, image_df, ai_title_df, config)
    
    # Save CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"shopify_upload_{timestamp}.csv"
    shopify_df.to_csv(output_file, index=False)
    
    print("\n" + "=" * 70)
    print("CSV GENERATION COMPLETE")
    print("=" * 70)
    print(f"\nCreated: {output_file}")
    print(f"   Total rows: {len(shopify_df)}")
    print(f"   Total products: {len(product_df)}")
    print("\n" + "=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print("1. Review the CSV file")
    print("2. Verify AI titles and image URLs")
    print("3. Go to Shopify Admin -> Products -> Import")
    print("4. Upload the CSV file")
    print("=" * 70)

if __name__ == "__main__":
    main()