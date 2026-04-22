#!/usr/bin/env python3
"""
BrownButter - Fashion Product Tagging (Job 3)
Integrated into main Shopify workflow
Analyzes fashion product images and generates tags, titles, and descriptions using Claude Vision API
Reads from Google Sheets, writes back to Image Links tab
"""

import os
import sys
import yaml
import anthropic
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import base64
import requests
import time
import json

# ============================================================================
# CONFIGURATION
# ============================================================================

def load_config():
    """Load configuration from config.yaml"""
    try:
        # Check if running on Render (Secret File)
        if os.path.exists('/etc/secrets/config.yaml'):
            config_path = '/etc/secrets/config.yaml'
        else:
            config_path = 'config.yaml'
        
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: config.yaml not found!")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

# Tag lists - organized by category (matching website filters)
SEARCH_TAGS_BY_CATEGORY = {
    'Dresses': ['Mini', 'Midi', 'Maxi'],
    'Skirts': ['Mini', 'Midi', 'Maxi'],
    'Tops': ['Peplum', 'Sheer', 'Halter Necks', 'Tube Tops', 
             'Asymmetric', 'Wrap & Tie Ups', 'Corsets', 'Bodysuits', 'Tank Tops', 'Tees'],
    'Pants': ['Cargos', 'Trousers', 'Shorts'],
    'ActiveWear': ['Skorts', 'Sports Bra', 'Activewear Sets', 'Joggers & Sweatpants', 
                   'Tights', 'Shorts', 'Jackets'],
    'Shorts': ['Shorts'],
    'Co-ords': ['Co-ords'],
    'Jackets': ['Denim', 'Bomber', 'Blazer', 'Leather', 'Puffer', 'Trench']          
}

OCCASION_TAGS = [
    "party",
    "work",
    "casual",
    "everyday",
    "travel"
]

# ============================================================================
# GOOGLE SHEETS AUTHENTICATION
# ============================================================================

def authenticate_sheets(config):
    """Authenticate with Google Sheets API"""
    try:
        google_creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        if google_creds_json:
            creds_dict = json.loads(google_creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            creds_file = config['google_sheets']['credentials_file']
            creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        
        client = gspread.authorize(creds)
        return client
        
    except Exception as e:
        print(f"Error authenticating: {e}")
        sys.exit(1)

def open_spreadsheet(client, config):
    """Open the Google Spreadsheet"""
    try:
        spreadsheet_name = config['google_sheets']['spreadsheet_name']
        sheet = client.open(spreadsheet_name)
        return sheet
    except Exception as e:
        print(f"Error opening spreadsheet: {e}")
        sys.exit(1)

# ============================================================================
# DATA RETRIEVAL
# ============================================================================

def get_products_to_tag(sheet, config):
    """Get products from Image Links tab that need tagging"""
    try:
        # Get Image Links tab
        image_tab = config['google_sheets']['tabs']['image_links']
        image_worksheet = sheet.worksheet(image_tab)
        image_records = image_worksheet.get_all_records()
        image_df = pd.DataFrame(image_records)
        
        # Filter out rows with no Image_1_URL
        if 'Image_1_URL' in image_df.columns:
            image_df = image_df[image_df['Image_1_URL'].notna() & (image_df['Image_1_URL'] != '')]
        
        # Keep only needed columns: SKU Clean, Category, Image_1_URL
        products_df = image_df[['SKU Clean', 'Category', 'Image_1_URL']].copy()
        
        print(f"Found {len(products_df)} products to tag")
        
        return products_df, image_worksheet
        
    except Exception as e:
        print(f"Error reading product data: {e}")
        sys.exit(1)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def download_image_as_base64(image_url):
    """Download image from URL and convert to base64"""
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        
        image_data = base64.standard_b64encode(response.content).decode("utf-8")
        content_type = response.headers.get('content-type', 'image/jpeg')
        
        return image_data, content_type
        
    except Exception as e:
        return None, None

def estimate_cost(num_products, config):
    """Estimate cost for processing products"""
    claude_config = config.get('claude', {})
    cost_per_1k = claude_config.get('cost_per_1k_images', 3.0)
    total_cost = (num_products / 1000) * cost_per_1k
    return round(total_cost, 2)

# ============================================================================
# CLAUDE VISION API
# ============================================================================

def analyze_fashion_image(client, image_url, category, occasion_tags):
    """
    Analyze fashion image using Claude Vision API
    Returns: dict with search_tags, occasion_tags, title, description
    """
    
    search_tags = SEARCH_TAGS_BY_CATEGORY.get(category, [])
    
    if not search_tags:
        print(f"    No style filters for '{category}' - will generate title/description only")
    
    image_data, media_type = download_image_as_base64(image_url)
    
    if not image_data:
        return None
    
    # Create prompt (same as your current file)
    prompt = f"""You are an expert fashion cataloguer with 10+ years at Zara, Bershka, and Mango. Your specialty is writing product descriptions that sell while staying true to the item.

BRAND VOICE: Mid-premium accessible fashion (Zara/H&M tier) with playful energy. Smart, not stuffy. Fun, not juvenile.

CATEGORY TO ANALYZE: {category}

YOUR TASK:
Analyze this image and focus ONLY on the {category} item. Identify its style from the filters below.

Return your analysis in this EXACT format (no additional text):

SEARCH_TAGS: [ONE tag from category filters below + "Denim" if fabric is denim]
OCCASION_TAGS: [EXACTLY ONE tag - the PRIMARY occasion]
TITLE: [5-7 word Zara-style product title]
DESCRIPTION: [EXACTLY 12-15 words with Zara/H&M playful energy]

AVAILABLE SEARCH TAGS FOR {category.upper()}:
{', '.join(search_tags) if search_tags else 'No style filters available - return "None" for search tags'}

AVAILABLE OCCASION TAGS (choose EXACTLY ONE):
{', '.join(occasion_tags)}

OCCASION DEFINITIONS:
- party: Evening wear, festive, dressy occasions
- work: Professional, office-appropriate, business casual
- casual: Relaxed everyday wear, weekend outings
- everyday: Basic wardrobe essentials, daily wear
- travel: Comfortable, wrinkle-resistant, versatile for packing (activewear, casual jackets, easy pants)

DENIM RULE:
- If the {category} is made from DENIM fabric (blue jean material), ADD "Denim" to search tags
- Examples: 
  * Denim midi dress → "SEARCH_TAGS: Midi, Denim"
  * Denim cargo pants → "SEARCH_TAGS: Cargos, Denim"
  * Cotton top → "SEARCH_TAGS: Peplum" (no denim)

FILTER DEFINITIONS FOR {category.upper()}:
"""

    # Add category-specific definitions (keeping your exact definitions)
    if category == 'Dresses' or category == 'Skirts':
        prompt += """
- Mini: Above knee length
- Midi: Knee to mid-calf length  
- Maxi: Ankle length or floor-length
"""
    elif category == 'Tops':
        prompt += """
CRITICAL - LOOK CAREFULLY AT BOTTOM OF GARMENT:

- Peplum: Flared ruffle at waist/hem (like a small skirt attached at bottom)
- Sheer: See-through or semi-transparent fabric (you can see skin through it)
- Halter Necks: Straps tie or fasten BEHIND NECK - shoulders are completely bare
- Tube Tops: Completely STRAPLESS - straight across chest like a bandeau, no straps at all
- Asymmetric: Uneven hemline OR one-shoulder design (not symmetrical)
- Wrap & Tie Ups: Wrapped/crossover bodice with tie closure (usually at side or back)
- Corsets: Structured, boned bodice with visible lacing or boning
- Bodysuits: ONE-PIECE with SNAP CLOSURE at crotch/bottom - look for this! The garment extends below the waist and fastens between legs
- Tank Tops: Basic sleeveless top - NO special features, just simple armholes and regular hem at waist

MOST IMPORTANT: 
- If it's just a basic sleeveless top with no special features → return "None"
- Bodysuits EXTEND BELOW THE WAIST and have a bottom closure
- Tank Tops END AT THE WAIST and are separate from bottoms
"""
    elif category == 'Pants':
        prompt += """
- Cargos: Utility pants with side/leg pockets
- Trousers: Tailored dress pants
- Shorts: shorts
"""
    elif category == 'ActiveWear':
        prompt += """
- Skorts: Shorts with skirt overlay
- Sports Bra: Athletic cropped top for workouts
- Activewear Sets: Matching top + bottom set
- Joggers & Sweatpants: Relaxed athletic pants
- Tights: Form-fitting athletic leggings
- Shorts: Athletic shorts
- Jackets: Athletic outerwear
"""
    elif category == 'Jackets':
        prompt += """
FILTER CATEGORIES FOR JACKETS:
**MATERIAL/FABRIC TYPE:**
- Denim: Made from denim/jean fabric (blue jean material)
- Leather: Genuine or faux leather material
- Puffer: Quilted, padded insulation (puffy appearance)

**STYLE/SILHOUETTE:**
- Bomber: Short waist-length jacket with ribbed cuffs and hem, zip front
- Blazer: Tailored, structured jacket with lapels (formal/business style)
- Trench: Long coat with belt, usually double-breasted (classic outerwear)

IMPORTANT:
- Choose ONE primary characteristic that best defines the jacket
- Material tags (Denim, Leather, Puffer) take priority if obvious
- If it's a cropped denim jacket → choose "Denim" (material over length)
- If it's basic jacket with no special features → return "None"
"""
    elif category == 'Co-ords':
        prompt += """
- No specific style filters for Co-ords
- Only add "Denim" if the co-ord set is made from denim fabric
- Otherwise leave search tags as "Co-ords"
"""

    prompt += f"""
CRITICAL RULES:
- For {category}: {"Choose EXACTLY ONE search tag that BEST matches" if search_tags else "No style filters - return 'SEARCH_TAGS: None'"}
- If the item is DENIM fabric, add "Denim" to search tags (even if no other filters exist)
- IMPORTANT: Always provide Title, Description, and Occasion - even if search tags are "None"
- Be 100% certain before choosing a tag - accuracy over completion

TITLE GUIDELINES:
- 5-7 words maximum
- Format: [Color] [Style Detail] [Category]
- Use specific color names (emerald, mustard, navy) not basic (green, yellow, blue)
- Include "Denim" in title if it's denim fabric

DESCRIPTION GUIDELINES:
- EXACTLY 12-15 words
- Zara/H&M voice: playful, smart, accessible
- Focus on: fabric/texture, fit/silhouette, styling versatility

Example output for denim item:
SEARCH_TAGS: Midi, Denim
OCCASION_TAGS: casual
TITLE: Blue Denim Midi Shirt Dress
DESCRIPTION: Classic denim in relaxed midi silhouette. Button-front detail perfect for effortless weekend styling.

Example output for non-denim item:
SEARCH_TAGS: Wrap & Tie Ups
OCCASION_TAGS: party
TITLE: Golden Yellow Wrap Crop Top
DESCRIPTION: Lightweight fabric with wrap tie detail. Cropped silhouette pairs beautifully with high-waisted bottoms.

Example output for basic item:
SEARCH_TAGS: None
OCCASION_TAGS: casual
TITLE: White Relaxed Cotton Tank
DESCRIPTION: Soft cotton jersey in crisp white. Easy everyday essential for layering or solo wear.
"""
    
    try:
        # Get Claude API key and model from config
        config = load_config()
        claude_config = config.get('claude', {})
        api_key = claude_config.get('api_key', '')
        model = claude_config.get('model', 'claude-sonnet-4-5-20250929')
        
        client = anthropic.Anthropic(api_key=api_key)
        
        message = client.messages.create(
            model=model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ],
                }
            ],
        )
        
        # Parse response
        response_text = message.content[0].text.strip()
        
        # Extract fields
        result = {
            'search_tags': '',
            'occasion': '',
            'title': '',
            'description': ''
        }
        
        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('SEARCH_TAGS:'):
                result['search_tags'] = line.replace('SEARCH_TAGS:', '').strip()
            elif line.startswith('OCCASION_TAGS:'):
                result['occasion'] = line.replace('OCCASION_TAGS:', '').strip()
            elif line.startswith('TITLE:'):
                result['title'] = line.replace('TITLE:', '').strip()
            elif line.startswith('DESCRIPTION:'):
                result['description'] = line.replace('DESCRIPTION:', '').strip()
        
        return result
        
    except Exception as e:
        print(f"    ERROR: {e}")
        return None

# ============================================================================
# MAIN PROCESSING FOR WORKFLOW
# ============================================================================

def process_fashion_tagging(config, sheets_client, sheet):
    """
    Main function called by app.py
    Processes all products and updates Image Links tab
    Returns: dict with success/error counts
    """
    
    print("\n" + "=" * 70)
    print("FASHION PRODUCT TAGGING (JOB 3)")
    print("=" * 70)
    print()
    
    # Get products to tag
    products_df, image_worksheet = get_products_to_tag(sheet, config)
    
    if len(products_df) == 0:
        print("No products to tag!")
        return {'success': 0, 'failed': 0, 'total': 0}
    
    # Estimate cost
    estimated_cost = estimate_cost(len(products_df), config)
    print(f"Processing {len(products_df)} products (estimated cost: ${estimated_cost})")
    print()
    
    # Process each product
    results = []
    success_count = 0
    failed_count = 0
    
    for idx, row in products_df.iterrows():
        sku = row['SKU Clean']
        image_url = row['Image_1_URL']
        category = row['Category']
        
        print(f"[{idx + 1}/{len(products_df)}] {sku} ({category})")
        
        # Analyze image
        result = analyze_fashion_image(
            None,  # client created inside function
            image_url,
            category,
            OCCASION_TAGS
        )
        
        if result and result['title']:
            results.append({
                'SKU Clean': sku,
                'Image_1_Title': result['title'],
                'Description': result['description'],
                'Tags': result['search_tags'],
                'Occasion': result['occasion']
            })
            success_count += 1
            print(f"  ✓ {result['title']}")
        else:
            failed_count += 1
            print(f"  ✗ Failed")
        
        # Rate limiting
        time.sleep(2)
    
    # Update Google Sheets
    if results:
        print(f"\nUpdating Google Sheets...")
        update_image_links_tab(image_worksheet, results)
        print(f"✓ Updated {len(results)} products")
    
    print("\n" + "=" * 70)
    print("COMPLETE!")
    print(f"Success: {success_count}, Failed: {failed_count}")
    print("=" * 70)
    
    return {
        'success': success_count,
        'failed': failed_count,
        'total': len(products_df),
        'cost': estimated_cost
    }

def update_image_links_tab(worksheet, results):
    """Update Image Links tab with generated content"""
    try:
        # Get all data
        all_values = worksheet.get_all_values()
        headers = all_values[0]
        
        # Find column indices
        sku_col = headers.index('SKU Clean')
        title_col = headers.index('Image_1_Title') if 'Image_1_Title' in headers else -1
        desc_col = headers.index('Description') if 'Description' in headers else -1
        tags_col = headers.index('Tags') if 'Tags' in headers else -1
        occasion_col = headers.index('Occasion') if 'Occasion' in headers else -1
        
        # Build batch update
        updates = []
        
        for result in results:
            sku = result['SKU Clean']
            
            # Find row for this SKU
            for row_idx, row in enumerate(all_values[1:], start=2):
                if len(row) > sku_col and row[sku_col] == sku:
                    # Update columns
                    if title_col >= 0:
                        updates.append({
                            'range': f'{chr(65 + title_col)}{row_idx}',
                            'values': [[result['Image_1_Title']]]
                        })
                    if desc_col >= 0:
                        updates.append({
                            'range': f'{chr(65 + desc_col)}{row_idx}',
                            'values': [[result['Description']]]
                        })
                    if tags_col >= 0:
                        updates.append({
                            'range': f'{chr(65 + tags_col)}{row_idx}',
                            'values': [[result['Tags']]]
                        })
                    if occasion_col >= 0:
                        updates.append({
                            'range': f'{chr(65 + occasion_col)}{row_idx}',
                            'values': [[result['Occasion']]]
                        })
                    break
        
        # Execute batch update
        if updates:
            worksheet.batch_update(updates)
        
    except Exception as e:
        print(f"Error updating sheet: {e}")

# ============================================================================
# MAIN (for standalone testing)
# ============================================================================

def main():
    """Standalone execution"""
    config = load_config()
    sheets_client = authenticate_sheets(config)
    sheet = open_spreadsheet(sheets_client, config)
    
    result = process_fashion_tagging(config, sheets_client, sheet)
    
    print(f"\nFinal: {result}")

if __name__ == "__main__":
    main()