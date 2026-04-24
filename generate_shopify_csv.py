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
        df = pd.DataFrame(records)
        
        # Use SKU Clean if available, fallback to SKU
        print(f"Loaded {len(records)} products from '{tab_name}' tab")
        return df
        print(f"Loaded {len(records)} products from '{tab_name}' tab")
        return df
        
    except Exception as e:
        print(f"Error reading product data: {e}")
        sys.exit(1)

def get_image_urls(sheet, config):
    """Get image URLs from Image Links tab"""
    try:
        tab_name = config['google_sheets']['tabs']['image_links']
        worksheet = sheet.worksheet(tab_name)
        records = worksheet.get_all_records()
        df = pd.DataFrame(records)
        
        # Use SKU Clean
        
        print(f"Loaded {len(records)} image mappings from '{tab_name}' tab")
        return df
        
    except Exception as e:
        print(f"Error reading image URLs: {e}")
        sys.exit(1)

def get_product_content(sheet, config):
    """Get product content (Title, Description, Tags, Occasion) from Image Links tab"""
    try:
        tab_name = config['google_sheets']['tabs']['image_links']
        worksheet = sheet.worksheet(tab_name)
        records = worksheet.get_all_records()
        
        df = pd.DataFrame(records)
        
        # Columns to extract
        columns_to_extract = ['SKU Clean']
        column_mapping = {}
        
        # Check for Image_1_Title
        if 'Image_1_Title' in df.columns:
            columns_to_extract.append('Image_1_Title')
            column_mapping['Image_1_Title'] = 'Title'
            print(f"✓ Found Image_1_Title column")
        
        # Check for Description
        if 'Description' in df.columns:
            columns_to_extract.append('Description')
            column_mapping['Description'] = 'Description'
            print(f"✓ Found Description column")
        
        # Check for Tags
        if 'Tags' in df.columns:
            columns_to_extract.append('Tags')
            column_mapping['Tags'] = 'Tags'
            print(f"✓ Found Tags column")
        
        # Check for Occasion
        if 'Occasion' in df.columns:
            columns_to_extract.append('Occasion')
            column_mapping['Occasion'] = 'Occasion'
            print(f"✓ Found Occasion column")
        
        if len(columns_to_extract) > 1:
            result_df = df[columns_to_extract].rename(columns=column_mapping)
            print(f"Loaded product content for {len(result_df)} SKUs from '{tab_name}' tab")
            return result_df
        else:
            print(f"Warning: No content columns found in '{tab_name}'")
            return pd.DataFrame()
        
    except Exception as e:
        print(f"Error reading product content: {e}")
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

# DEPRECATED - No longer used (Title, Description, Tags now come from Excel)
def generate_fallback_title(category, color):
    """Generate fallback title if AI title not available"""
    return f"{category} - {color}"

def normalize_category_key(category):
    """Convert category name to config key format"""
    return category.lower().replace(' ', '_').replace('-', '_')

# DEPRECATED - No longer used (Description now comes from Excel)
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

# DEPRECATED - No longer used (Tags now come from Excel)
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
    
    categories = config.get('shopify_categories')
    if categories is None:
        print(f"WARNING: shopify_categories not found in config for key '{full_key}'")
        return ''
    
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

def create_shopify_rows(product, image_data, product_content_data, config):
    """Create Shopify CSV rows for a single product (NEW FORMAT)"""
    rows = []
    
    # Get configuration defaults
    defaults = config.get('defaults', {})
    seo = config.get('seo', {})
    metafields = config.get('metafields', {})
    
    # Product basic info
    sku = product['SKU Clean']
    
    # Get product content (Title, Description, Tags, Occasion) from Image Links tab
    title = ''
    description = ''
    search_tags = ''  # Style tags from Claude (e.g., "Wrap & Tie Ups", "Midi")
    occasion = ''
    
    if not product_content_data.empty and sku in product_content_data['SKU Clean'].values:
        content_row = product_content_data[product_content_data['SKU Clean'] == sku].iloc[0]
        
        # Get Title (from Image_1_Title)
        title = content_row.get('Title', '') if pd.notna(content_row.get('Title')) else ''
        
        # Get Description
        description = content_row.get('Description', '') if pd.notna(content_row.get('Description')) else ''
        
        # Get Tags (style tags like "Wrap & Tie Ups", "Midi", etc.)
        search_tags = content_row.get('Tags', '') if pd.notna(content_row.get('Tags')) else ''
        
        # Get Occasion
        occasion = content_row.get('Occasion', '') if pd.notna(content_row.get('Occasion')) else ''
    
    # Remove "None" from search_tags if present
    if search_tags and search_tags.strip().lower() != 'none':
        search_tags_clean = search_tags.strip()
    else:
        search_tags_clean = ''
    
    # Build metafields based on category and tags
    category = product['Category']
    
    # Category-specific metafields (custom namespace)
    active_wear_metafield = search_tags_clean if category == 'ActiveWear' else ''
    
    # Bottom Type: Pants (from tags), Shorts (literal "Shorts"), Skirts (literal "Skirts")
    if category == 'Pants':
        bottom_type_metafield = search_tags_clean
    elif category == 'Shorts':
        bottom_type_metafield = 'Shorts'
    elif category == 'Skirts':
        bottom_type_metafield = 'Skirts'
    else:
        bottom_type_metafield = ''
    
    jackets_metafield = search_tags_clean if category == 'Jackets' else ''
    top_style_metafield = search_tags_clean if category == 'Tops' else ''
    skirt_dress_length_custom = search_tags_clean if category in ['Dresses', 'Skirts'] else ''
    
    # Shopify namespace metafields
    dress_occasion_metafield = occasion if category == 'Dresses' else ''
    skirt_dress_length_shopify = search_tags_clean if category in ['Dresses', 'Skirts'] else ''
    
    # Build final Tags column (combine search_tags + occasion + standard tags)
    tags_list = []
    
    # Add search tags
    if search_tags_clean:
        tags_list.append(search_tags_clean)
    
    # Add occasion
    if occasion:
        tags_list.append(occasion)
    
    # Add standard tags
    tags_list.append('brownbutter')
    tags_list.append(product['Gender'].lower())
    tags_list.append(category.lower())
    
    final_tags = ', '.join(tags_list)
    
    # Fallback for title if empty
    if not title:
        title = f"{product['Category']} - {product['Color']}"
    
    # Wrap description in HTML paragraph tags if present
    if description:
        description = f"<p>{description}</p>"
    
    # Generate handle and vendor
    handle = generate_handle(product['Category'], product['Color'])
    vendor = defaults.get('vendor', 'BrownButter')
    
    # Generate category key from Gender + Category
    gender_key = normalize_category_key(product['Gender'])
    category_key = normalize_category_key(product['Category'])
    full_key = f"{gender_key}_{category_key}"
    
    category = get_shopify_category(product['Gender'], product['Category'], config)
    
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
    gender_value = product.get('Gender', '').lower()
    target_gender = 'female' if gender_value == 'women' else 'male' if gender_value == 'men' else 'female'
    size_metafield = get_size_metafield_value(sizes)
    
    # Get image URLs for this SKU
    image_urls = []
    if not image_data.empty and sku in image_data['SKU Clean'].values:
        img_row = image_data[image_data['SKU Clean'] == sku].iloc[0]
        for i in range(1, 6):
            url_col = f'Image_{i}_URL'
            if url_col in img_row.index:
                url = img_row[url_col]
                if pd.notna(url) and str(url).strip():
                    image_urls.append(str(url).strip())
    
    if not image_urls:
        image_urls = ['']
    
    # Create rows for each size with images distributed across sizes
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
            'Tags': final_tags if size_idx == 0 else '',
            'Published': 'TRUE' if defaults.get('published', True) else 'FALSE',
            'Option1 Name': 'Size',
            'Option1 Value': size,
            'Option1 Linked To': 'product.metafields.shopify.size' if size_idx == 0 else '',
            'Option2 Name': '',
            'Option2 Value': '',
            'Option2 Linked To': '',
            'Option3 Name': '',
            'Option3 Value': '',
            'Option3 Linked To': '',
            'Variant SKU': generate_sku(product['SKU Clean'], size_idx + 1),
            'Variant Grams': 0,
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
            'Active Wear (product.metafields.custom.active_wear)': active_wear_metafield if size_idx == 0 else '',
            'Bottom Type (product.metafields.custom.bottom_type)': bottom_type_metafield if size_idx == 0 else '',
            'Denim Type (product.metafields.custom.denim_type)': '',  # Blank for now
            'Jackets (product.metafields.custom.jackets)': jackets_metafield if size_idx == 0 else '',
            'Skirts (product.metafields.custom.skirts)': '',  # Blank for now
            'Skirt/Dress length type (product.metafields.custom.skirt_dress_length_type)': skirt_dress_length_custom if size_idx == 0 else '',
            'Top Style (product.metafields.custom.top_style)': top_style_metafield if size_idx == 0 else '',
            'Age group (product.metafields.shopify.age-group)': age_group if size_idx == 0 else '',
            'Color (product.metafields.shopify.color-pattern)': color_metafield if size_idx == 0 else '',
            'Costume theme (product.metafields.shopify.costume-theme)': '',
            'Dress occasion (product.metafields.shopify.dress-occasion)': dress_occasion_metafield if size_idx == 0 else '',
            'Dress style (product.metafields.shopify.dress-style)': '',
            'Fabric (product.metafields.shopify.fabric)': fabric_metafield if size_idx == 0 else '',
            'Neckline (product.metafields.shopify.neckline)': '',
            'Size (product.metafields.shopify.size)': size_metafield if size_idx == 0 else '',
            'Skirt/Dress length type (product.metafields.shopify.skirt-dress-length-type)': skirt_dress_length_shopify if size_idx == 0 else '',
            'Sleeve length type (product.metafields.shopify.sleeve-length-type)': '',
            'Target gender (product.metafields.shopify.target-gender)': target_gender if size_idx == 0 else '',
            'Complementary products (product.metafields.shopify--discovery--product_recommendation.complementary_products)': '',
            'Related products (product.metafields.shopify--discovery--product_recommendation.related_products)': '',
            'Related products settings (product.metafields.shopify--discovery--product_recommendation.related_products_display)': '',
            'Search product boosts (product.metafields.shopify--discovery--product_search_boost.queries)': '',
            'Variant Image': '',
            'Variant Weight Unit': 'kg',
            'Variant Tax Code': '',
            'Cost per item': cost_per_item if size_idx == 0 else '',
            'Status': 'active'  # Always active
        }
        
        rows.append(row)
    
    return rows

def generate_csv(product_df, image_df, product_content_df, config):
    """Generate complete Shopify CSV"""
    print("\n" + "=" * 70)
    print("GENERATING SHOPIFY CSV (NEW FORMAT)")
    print("=" * 70)
    print()
    
    all_rows = []
    
    for idx, (_, product) in enumerate(product_df.iterrows()):
        sku = product['SKU Clean']
        print(f"Processing {idx+1}/{len(product_df)}: {sku}")
        
        # Generate rows for this product
        rows = create_shopify_rows(product, image_df, product_content_df, config)
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
    product_content_df = get_product_content(sheet, config)
    
    # Generate CSV
    shopify_df = generate_csv(product_df, image_df, product_content_df, config)
    
    # Save CSV
    os.makedirs('static/downloads', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"static/downloads/shopify_upload_{timestamp}.csv"
    shopify_df.to_csv(output_file, index=False)

    print(f"\n{'='*70}")
    print(f"CSV SAVED: {output_file}")
    print(f"{'='*70}")

    return output_file  # ← ADD THIS LINE!
    
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