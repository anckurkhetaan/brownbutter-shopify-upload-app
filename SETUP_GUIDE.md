# BrownButter Shopify Automation - Setup Guide

## Prerequisites

- Python 3.8 or higher
- Google account with access to Drive folders
- Shopify store with Admin access
- Internet connection

---

## Step 1: Install Python Dependencies

Open terminal/command prompt and run:

```bash
pip install --upgrade pip
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
pip install gspread oauth2client
pip install requests pillow
pip install pyyaml pandas
pip install tqdm  # For progress bars
```

---

## Step 2: Get Google Drive API Credentials

### 2.1 Enable Google Drive API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing): "BrownButter-ShopifyCatalogue"
3. Enable APIs:
   - Go to **APIs & Services → Library**
   - Search for "Google Drive API" → Click **Enable**
   - Search for "Google Sheets API" → Click **Enable**

### 2.2 Create Service Account Credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → Service Account**
3. Fill in:
   - Name: `brownbutter-shopifycatalogue`
   - Description: `Automation for Shopify uploads`
   - Click **Create and Continue**
4. Skip "Grant access" (click Continue)
5. Skip "Grant users access" (click Done)
6. Click on the created service account email
7. Go to **Keys** tab
8. Click **Add Key → Create New Key**
9. Choose **JSON** format
10. Download the file
11. **Rename it to**: `google_credentials.json`
12. **Save it** in the same folder as your Python scripts

### 2.3 Share Google Sheet with Service Account

1. Open the downloaded `google_credentials.json`
2. Find the `client_email` field (looks like: `brownbutter-automation@project-id.iam.gserviceaccount.com`)
3. Copy this email
4. Open your **BrownButter Google Sheet**
5. Click **Share** button
6. Paste the service account email
7. Set permission to **Editor**
8. Click **Send** (uncheck "Notify people")

---

## Step 3: Get Shopify API Credentials

### 3.1 Create Custom App in Shopify

1. Log in to your Shopify Admin
2. Go to **Settings → Apps and sales channels**
3. Click **Develop apps**
4. Click **Allow custom app development** (if prompted)
5. Click **Create an app**
6. Name: `BrownButter Image Uploader`
7. Click **Create app**

### 3.2 Configure API Scopes

1. Click **Configure Admin API scopes**
2. Enable these permissions:
   - `read_products`
   - `write_products`
   - `read_files`
   - `write_files`
3. Click **Save**

### 3.3 Install App & Get Access Token

1. Click **Install app** (top right)
2. Confirm installation
3. Click **Reveal token once** under "Admin API access token"
4. **Copy the token** (you won't see it again!)
5. Save it securely

### 3.4 Get Your Store Name

Your Shopify store URL format: `https://YOUR-STORE-NAME.myshopify.com`
- Example: If URL is `https://brownbutter.myshopify.com`, store name is `brownbutter`

---

## Step 4: Create Configuration File

Create a file named `config.yaml` in the same folder as scripts:

```yaml
# Shopify Configuration
shopify:
  store_name: "1yqrpp-y7"  # WITHOUT .myshopify.com
  api_version: "2024-01"
  access_token: "shpat_xxxxxxxxxxxxxxxxxxxxx"  # Your Admin API token

# Google Sheets Configuration
google_sheets:
  spreadsheet_name: "BrownButter Shopify Upload - Pilot"
  credentials_file: "google_credentials.json"

# Script Settings
settings:
  batch_size: 10  # Process images in batches
  rate_limit_delay: 0.5  # Seconds between API calls
  max_retries: 3  # Retry failed uploads
  
# Image Settings
images:
  max_size_mb: 20  # Maximum image file size
  allowed_formats: ['.jpg', '.jpeg', '.png', '.webp']
  
# Default Product Values
defaults:
  vendor: "BrownButter"
  weight_grams: 500
  inventory_per_size: 5
  published: true
  requires_shipping: true
  taxable: true
```

**Important**: Replace `your-store-name` and `access_token` with your actual values!

---

## Step 5: Verify Setup

Run this test script to verify everything is configured correctly:

```python
# Save as: test_setup.py
import os
import yaml
import json

print("🔍 Checking BrownButter Automation Setup...\n")

# Check 1: Python packages
print("1. Checking Python packages...")
try:
    import google.auth
    import gspread
    import requests
    import yaml
    import pandas
    print("   ✅ All packages installed\n")
except ImportError as e:
    print(f"   ❌ Missing package: {e}\n")

# Check 2: Config file
print("2. Checking config.yaml...")
if os.path.exists('config.yaml'):
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    if config['shopify']['access_token'] != 'shpat_xxxxxxxxxxxxxxxxxxxxx':
        print("   ✅ Config file exists and updated\n")
    else:
        print("   ⚠️  Config exists but access_token not updated\n")
else:
    print("   ❌ config.yaml not found\n")

# Check 3: Google credentials
print("3. Checking Google credentials...")
if os.path.exists('google_credentials.json'):
    with open('google_credentials.json', 'r') as f:
        creds = json.load(f)
    if 'client_email' in creds:
        print(f"   ✅ Credentials found for: {creds['client_email']}\n")
    else:
        print("   ❌ Invalid credentials file\n")
else:
    print("   ❌ google_credentials.json not found\n")

print("Setup verification complete!")
```

Run: `python test_setup.py`

---

## File Structure

After setup, your folder should look like:

```
brownbutter-automation/
├── config.yaml
├── google_credentials.json
├── process_images.py          (Script 1 - we'll create next)
├── generate_shopify_csv.py    (Script 2 - we'll create next)
├── test_setup.py
└── temp/                      (auto-created for downloads)
```

---

## Troubleshooting

### Google Drive API Issues
- **Error: "Insufficient permissions"**
  → Make sure you shared the Google Sheet with the service account email
  
- **Error: "API not enabled"**
  → Enable both Google Drive API and Google Sheets API in Google Cloud Console

### Shopify API Issues
- **Error: "Unauthorized"**
  → Check your access token is correct in config.yaml
  → Verify API scopes include `write_files` and `write_products`

- **Error: "Rate limited"**
  → Increase `rate_limit_delay` in config.yaml to 1.0

### General Issues
- **Error: "Module not found"**
  → Run `pip install [package_name]` again
  
- **Error: "File not found"**
  → Make sure all files are in the same directory

---

## Next Steps

Once setup is complete:
1. ✅ Verify with `test_setup.py`
2. ✅ Move to Script 1: Image Processing
3. ✅ Move to Script 2: CSV Generation

---

## Support

If you encounter issues:
1. Check the error message carefully
2. Verify all credentials are correct
3. Ensure Google Sheet is shared with service account
4. Confirm Shopify app has correct permissions
