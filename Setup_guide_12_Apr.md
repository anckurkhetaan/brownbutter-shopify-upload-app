# BrownButter - Final Workflow Summary

## Updated System (With Cloudinary AI)

### Key Changes:
1. AI titles generated using Cloudinary's built-in AI
2. Titles stored in "Image Links" tab (AI_Title column)
3. Only main images (_1 suffix) get AI analysis

---

## Complete Workflow

### Step 1: Download Images from Google Drive
```powershell
python process_images.py
```
- Downloads images from Drive folders
- Renames as SKU_1.jpg, SKU_2.jpg, etc.
- Saves to temp_downloads/

### Step 2: Upload to Cloudinary
```powershell
python upload_to_cloudinary.py
```
- Uploads all images to Cloudinary
- Enables AI tagging during upload
- Gets Cloudinary URLs

### Step 3: Sync URLs + Generate AI Titles
```powershell
python sync_urls_to_sheet.py
```
**What it does:**
- Fetches all image URLs from Cloudinary (by SKU)
- For SKUs in Image_Links tab main image (SKU_1):
  - Calls Cloudinary AI to analyze image
  - Generates 5-7 word product title
- Updates "Image Links" tab with:
  - Image_1_URL, Image_2_URL, Image_3_URL, etc.
  - AI_Title column

**Time:** 5-10 minutes for 100 products

### Step 4: Generate Shopify CSV
```powershell
python generate_shopify_csv.py
```
**What it does:**
- Reads Product Data tab (SKU, Category, Color, prices, fabric, etc.)
- Reads Image Links tab (URLs + AI titles)
- Uses AI title if available, falls back to "Category - Color"
- Generates new Shopify format CSV with metafields
- Creates 5 rows per product (one per size)

### Step 5: Import to Shopify
- Shopify Admin → Products → Import
- Upload generated CSV
- Done!

---

## Google Sheet Structure

### Image Links Tab (Updated):
```
| SKU    | Drive_Folder_Link | Image_1_URL | Image_2_URL | Image_3_URL | AI_Title                     | Status | Error |
|--------|-------------------|-------------|-------------|-------------|------------------------------|--------|-------|
| 8125   | https://...       | https://... | https://... | https://... | Elegant Blue Evening Dress   | Done   |       |
| 309    | https://...       | https://... | https://... |             | Comfortable Black Daily Top  | Done   |       |
```

### Product Data Tab:
```
| SKU  | Category | Shopify_Category | Gender | Color | Material  | Price | MRP  |
|------|----------|------------------|--------|-------|-----------|-------|------|
| 8125 | Dress    | women_dress      | Women  | Blue  | Polyester | 1300  | 1690 |
```

---

## How AI Title Generation Works

### Cloudinary AI Analysis:
1. Script calls `cloudinary.uploader.explicit()` with captioning enabled
2. Cloudinary analyzes the image using AI
3. Returns:
   - Caption (description of image)
   - Tags (object detection keywords)
4. Script formats caption/tags into 5-7 word title

### Example:
- **Image:** Photo of a black blouse
- **AI Caption:** "A woman wearing a comfortable black blouse"
- **Generated Title:** "Comfortable Black Daily Blouse"

### Fallback:
- If Cloudinary AI fails, CSV generator uses: "Category - Color"
- Example: "Dress - Blue"

---

## Configuration

### config.yaml - Key Sections:

```yaml
# Cloudinary (required)
cloudinary:
  cloud_name: "your_cloud_name"
  api_key: "your_api_key"
  api_secret: "your_api_secret"
  folder: "brownbutter_products"

# Google Sheets (required)
google_sheets:
  spreadsheet_name: "BrownButter Shopify Upload - Pilot"
  credentials_file: "google_credentials.json"
  tabs:
    product_data: "Product Data"
    image_links: "Image Links"
    config: "Config"
    shopify_csv: "Shopify CSV"

# Metafields (for Shopify)
metafields:
  age_group: "adults"

# Size mappings by category
size_mappings:
  women_dress: ['XS', 'S', 'M', 'L', 'XL']
  women_top: ['XS', 'S', 'M', 'L', 'XL']
  women_bottom: ['26', '28', '30', '32', '34']
  men_shirt: ['S', 'M', 'L', 'XL', 'XXL']
```

---

## Shopify CSV Output Format

### New 2025 Format with Metafields:

Key columns:
- Handle, Title, Body (HTML)
- Variant SKU, Variant Price, Variant Compare At Price
- Image Src, Image Position
- Option1 Name = "Size", Option1 Value = size
- Metafields:
  - Color (product.metafields.shopify.color-pattern)
  - Fabric (product.metafields.shopify.fabric)
  - Size (product.metafields.shopify.size)
  - Target gender (product.metafields.shopify.target-gender)
  - Age group (product.metafields.shopify.age-group)

---

## Cost Analysis

### Cloudinary AI (Included in Free Tier):
- AI analysis is part of Cloudinary's transformation features
- Free tier: 25 credits/month
- Each AI analysis uses minimal credits
- 100-500 products easily within free tier

### No Additional API Costs:
- No Anthropic API needed
- No OpenAI API needed
- All AI processing through Cloudinary

---

## Troubleshooting

### "AI title generation failed"
- Cloudinary AI might not be enabled on your account
- Check Cloudinary dashboard → Settings → Add-ons
- Enable "AI Content Analysis" if available

### "AI_Title column is empty"
- Run sync_urls_to_sheet.py again
- Check Cloudinary AI is working (test with one image)
- Fallback: CSV will use "Category - Color" format

### CSV has wrong format
- Make sure using latest generate_shopify_csv.py
- Check Product Data tab has all required columns
- Verify Shopify_Category values match config.yaml size_mappings

---

## Quick Reference

### Category Mapping (Shopify_Category):
This column in Product Data determines:
1. Which sizes to use (from size_mappings in config)
2. Which tags to apply (category_specific tags)
3. Shopify product category path

Examples:
- women_dress → sizes: XS, S, M, L, XL
- women_bottom → sizes: 26, 28, 30, 32, 34
- men_shirt → sizes: S, M, L, XL, XXL

### File Dependencies:
- config.yaml (settings)
- google_credentials.json (Google API)
- Product Data tab (product info)
- Image Links tab (URLs + AI titles)

### Script Order:
1. process_images.py
2. upload_to_cloudinary.py
3. sync_urls_to_sheet.py (NEW - includes AI)
4. generate_shopify_csv.py
5. Import CSV to Shopify

---

## Next Batch

For your next 50-100 products:
1. Add to Product Data tab
2. Add Drive links to Image Links tab
3. Run all 4 scripts in order
4. Import CSV to Shopify

Scripts remember progress, safe to re-run.

---

**System is ready! Test with your 5 products first.**