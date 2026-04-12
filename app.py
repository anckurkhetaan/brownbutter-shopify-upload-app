"""
BrownButter Automation - Flask Web Application
Hosts Python automation scripts as web endpoints
Designed for Render deployment
"""

from flask import Flask, request, jsonify, render_template
import os
import sys
import threading
import traceback
from datetime import datetime
import json

# Import automation functions
import yaml
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import cloudinary
import cloudinary.uploader
import cloudinary.api

app = Flask(__name__)

# Global variables to track job status
job_status = {}
job_logs = {}

# ============================================================================
# CONFIGURATION
# ============================================================================

def load_config():
    """Load configuration from config.yaml"""
    try:
        with open('config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        return {'error': str(e)}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def log_message(job_id, message):
    """Add message to job logs"""
    if job_id not in job_logs:
        job_logs[job_id] = []
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    job_logs[job_id].append(f"[{timestamp}] {message}")
    print(f"[{job_id}] {message}")

def update_job_status(job_id, status, progress=0, message=""):
    """Update job status"""
    job_status[job_id] = {
        'status': status,  # pending, running, completed, failed
        'progress': progress,
        'message': message,
        'timestamp': datetime.now().isoformat()
    }
    log_message(job_id, message)

# ============================================================================
# AUTHENTICATION HELPERS
# ============================================================================

def authenticate_google_services():
    """Authenticate with Google Drive and Sheets APIs"""
    try:
        # Check for credentials in environment variable (Render deployment)
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        
        if creds_json:
            # Load from environment variable
            import json
            from google.oauth2 import service_account
            
            creds_dict = json.loads(creds_json)
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=scopes
            )
        else:
            # Load from file (local development)
            creds_file = 'google_credentials.json'
            if not os.path.exists(creds_file):
                raise Exception("Google credentials not found")
            
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        
        sheets_client = gspread.authorize(creds)
        drive_service = build('drive', 'v3', credentials=creds)
        
        return sheets_client, drive_service
        
    except Exception as e:
        raise Exception(f"Authentication failed: {str(e)}")

def setup_cloudinary():
    """Configure Cloudinary from environment or config"""
    try:
        # Try environment variables first (Render deployment)
        cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
        api_key = os.environ.get('CLOUDINARY_API_KEY')
        api_secret = os.environ.get('CLOUDINARY_API_SECRET')
        folder = os.environ.get('CLOUDINARY_FOLDER', 'brownbutter_products')
        
        if not cloud_name:
            # Load from config file (local development)
            config = load_config()
            cloudinary_config = config.get('cloudinary', {})
            cloud_name = cloudinary_config.get('cloud_name')
            api_key = cloudinary_config.get('api_key')
            api_secret = cloudinary_config.get('api_secret')
            folder = cloudinary_config.get('folder', 'brownbutter_products')
        
        if not cloud_name:
            raise Exception("Cloudinary credentials not found")
        
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True
        )
        
        return folder
        
    except Exception as e:
        raise Exception(f"Cloudinary setup failed: {str(e)}")

# ============================================================================
# WEB ROUTES
# ============================================================================

@app.route('/')
def index():
    """Home page with status dashboard"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/status/<job_id>')
def get_status(job_id):
    """Get status of a job"""
    if job_id in job_status:
        return jsonify({
            'job_id': job_id,
            'status': job_status[job_id],
            'logs': job_logs.get(job_id, [])
        })
    else:
        return jsonify({
            'job_id': job_id,
            'status': {'status': 'not_found'},
            'logs': []
        }), 404

# ============================================================================
# JOB 1: DRIVE TO CLOUDINARY
# ============================================================================

def run_drive_to_cloudinary(job_id, sheet_name):
    """Background task: Upload from Drive to Cloudinary"""
    try:
        update_job_status(job_id, 'running', 10, 'Starting upload process...')
        
        # Import and run the actual upload script
        import direct_drive_to_cloudinary as upload_script
        
        # Run the main process
        config = upload_script.load_config()
        sheets_client, drive_service = upload_script.authenticate_google_services(config)
        cloudinary_folder = upload_script.setup_cloudinary(config)
        sheet = upload_script.open_spreadsheet(sheets_client, config)
        
        update_job_status(job_id, 'running', 30, 'Processing images...')
        
        results = upload_script.process_direct_upload(config, sheets_client, drive_service, sheet, cloudinary_folder)
        
        # Count results
        success = sum(1 for r in results if r['status'] == 'Done')
        failed = sum(1 for r in results if r['status'] == 'Failed')
        
        update_job_status(job_id, 'completed', 100, f'Complete! Success: {success}, Failed: {failed}')
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        update_job_status(job_id, 'failed', 0, error_msg)

@app.route('/api/jobs/drive-to-cloudinary', methods=['POST'])
def start_drive_to_cloudinary():
    """Start Drive to Cloudinary upload job"""
    try:
        data = request.json
        sheet_name = data.get('sheet_name')
        
        if not sheet_name:
            return jsonify({'error': 'sheet_name required'}), 400
        
        # Generate job ID
        job_id = f"drive_cloudinary_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Initialize job
        update_job_status(job_id, 'pending', 0, 'Job queued')
        
        # Start background thread
        thread = threading.Thread(
            target=run_drive_to_cloudinary,
            args=(job_id, sheet_name)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'job_id': job_id,
            'status': 'started',
            'message': 'Job started successfully'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# JOB 2: SYNC URLS TO SHEET
# ============================================================================

def run_sync_urls(job_id, sheet_name):
    """Background task: Sync URLs and generate AI titles"""
    try:
        update_job_status(job_id, 'running', 10, 'Starting...')
        
        import sync_urls_to_sheet as sync_script
        
        config = sync_script.load_config()
        cloudinary_folder = sync_script.setup_cloudinary(config)
        
        update_job_status(job_id, 'running', 30, 'Fetching URLs from Cloudinary...')
        
        sku_url_map, sku_public_ids = sync_script.fetch_all_cloudinary_urls(cloudinary_folder)
        
        update_job_status(job_id, 'running', 50, 'Updating Google Sheet...')
        
        sheets_client = sync_script.authenticate_sheets(config)
        sheet = sync_script.open_spreadsheet(sheets_client, config)
        sync_script.update_sheet_with_urls(sheet, config, sku_url_map, sku_public_ids)
        
        update_job_status(job_id, 'completed', 100, f'Done! Processed {len(sku_url_map)} SKUs')
        
    except Exception as e:
        update_job_status(job_id, 'failed', 0, str(e))


@app.route('/api/jobs/sync-urls', methods=['POST'])
def start_sync_urls():
    """Start sync URLs and generate titles job"""
    try:
        data = request.json
        sheet_name = data.get('sheet_name')
        
        if not sheet_name:
            return jsonify({'error': 'sheet_name required'}), 400
        
        job_id = f"sync_urls_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        update_job_status(job_id, 'pending', 0, 'Job queued')
        
        # Start background thread
        thread = threading.Thread(target=run_sync_urls, args=(job_id, sheet_name))
        thread.daemon = True
        thread.start()
        
        return jsonify({'job_id': job_id, 'status': 'started'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# JOB 3: GENERATE SHOPIFY CSV
# ============================================================================

def run_generate_csv(job_id, sheet_name):
    """Background task: Generate Shopify CSV"""
    try:
        update_job_status(job_id, 'running', 10, 'Starting...')
        
        import generate_shopify_csv as csv_script
        
        config = csv_script.load_config()
        
        update_job_status(job_id, 'running', 30, 'Reading product data...')
        
        sheets_client = csv_script.authenticate_sheets(config)
        sheet = csv_script.open_spreadsheet(sheets_client, config)
        
        update_job_status(job_id, 'running', 50, 'Generating CSV...')
        
        csv_file = csv_script.main()
        file_url = f"/{csv_file}"
        update_job_status(job_id, 'completed', 100, f'Done! <a href="{file_url}" download>Download CSV</a>')
        
    except Exception as e:
        update_job_status(job_id, 'failed', 0, str(e))

@app.route('/api/jobs/generate-csv', methods=['POST'])
def start_generate_csv():
    """Start generate Shopify CSV job"""
    try:
        data = request.json
        sheet_name = data.get('sheet_name')
        
        if not sheet_name:
            return jsonify({'error': 'sheet_name required'}), 400
        
        job_id = f"generate_csv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        update_job_status(job_id, 'pending', 0, 'Job queued')
        
        # Start background thread
        thread = threading.Thread(target=run_generate_csv, args=(job_id, sheet_name))
        thread.daemon = True
        thread.start()
        
        return jsonify({'job_id': job_id, 'status': 'started'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)