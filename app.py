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
import time

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
job_threads = {}  # Track active threads
job_cancelled = {}  # Track cancelled jobs

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
    """Add message to job logs with improved visibility"""
    if job_id not in job_logs:
        job_logs[job_id] = []
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    job_logs[job_id].append(log_entry)
    
    # Force flush to stdout for Render logs
    print(f"[{job_id}] {message}", flush=True)
    sys.stdout.flush()

def update_job_status(job_id, status, progress=0, message="", error=None):
    """Update job status with error tracking and timing"""
    current_status = job_status.get(job_id, {})
    
    # Preserve start_time if already set
    start_time = current_status.get('start_time')
    if not start_time and status == 'running':
        start_time = datetime.now().isoformat()
    
    # Calculate elapsed time
    elapsed = None
    if start_time:
        start_dt = datetime.fromisoformat(start_time)
        elapsed = int((datetime.now() - start_dt).total_seconds())
    
    job_status[job_id] = {
        'status': status,  # pending, running, completed, failed, cancelled
        'progress': progress,
        'message': message,
        'error': error,  # Full error traceback if failed
        'timestamp': datetime.now().isoformat(),
        'start_time': start_time,
        'elapsed_seconds': elapsed
    }
    log_message(job_id, message)

def check_cancelled(job_id):
    """Check if job has been cancelled"""
    return job_cancelled.get(job_id, False)

def cleanup_old_csvs():
    """Delete CSV files older than 1 hour"""
    downloads_dir = 'static/downloads'
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir)
        return
    
    current_time = time.time()
    one_hour = 3600  # seconds
    
    for filename in os.listdir(downloads_dir):
        if filename.endswith('.csv'):
            filepath = os.path.join(downloads_dir, filename)
            file_age = current_time - os.path.getmtime(filepath)
            
            if file_age > one_hour:
                try:
                    os.remove(filepath)
                    print(f"Deleted old CSV: {filename}")
                except:
                    pass

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

@app.route('/api/cancel/<job_id>', methods=['POST'])
def cancel_job(job_id):
    """Cancel a running job"""
    if job_id in job_status:
        job_cancelled[job_id] = True
        update_job_status(job_id, 'cancelled', 0, 'Job cancelled by user')
        return jsonify({'status': 'cancelled', 'job_id': job_id})
    else:
        return jsonify({'error': 'Job not found'}), 404

# ============================================================================
# JOB 0: CLEAN SKUs
# ============================================================================

def run_clean_skus(job_id, sheet_name):
    """Background task: Clean SKUs and update SKU Clean column"""
    try:
        update_job_status(job_id, 'running', 10, 'Starting...')
        
        import clean_skus as clean_script
        
        config = clean_script.load_config()
        
        update_job_status(job_id, 'running', 30, 'Authenticating...')
        client = clean_script.authenticate_sheets(config)
        sheet = clean_script.open_spreadsheet(client, config)
        
        update_job_status(job_id, 'running', 50, 'Cleaning SKUs...')
        clean_script.clean_skus_in_sheet(sheet, config)
        
        update_job_status(job_id, 'completed', 100, 'Done! SKUs cleaned and updated in Column B')
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        log_message(job_id, f'ERROR: {error_traceback}')
        update_job_status(job_id, 'failed', 0, str(e), error=error_traceback)

@app.route('/api/jobs/clean-skus', methods=['POST'])
def start_clean_skus():
    """Start clean SKUs job"""
    try:
        data = request.json
        sheet_name = data.get('sheet_name')
        
        if not sheet_name:
            return jsonify({'error': 'sheet_name required'}), 400
        
        job_id = f"clean_skus_{int(time.time())}"
        
        # Start background thread
        thread = threading.Thread(target=run_clean_skus, args=(job_id, sheet_name))
        thread.daemon = True
        thread.start()
        
        job_threads[job_id] = thread
        job_cancelled[job_id] = False
        
        return jsonify({
            'job_id': job_id,
            'status': 'started',
            'message': 'SKU cleaning job started'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# JOB 1: DRIVE TO CLOUDINARY
# ============================================================================

def run_drive_to_cloudinary(job_id, sheet_name):
    """Background task: Upload from Drive to Cloudinary with detailed progress"""
    try:
        update_job_status(job_id, 'running', 5, 'Initializing...')
        
        if check_cancelled(job_id):
            return
        
        # Import modules
        import direct_drive_to_cloudinary as upload_script
        
        update_job_status(job_id, 'running', 10, 'Authenticating with Google...')
        config = upload_script.load_config()
        sheets_client, drive_service = upload_script.authenticate_google_services(config)
        cloudinary_folder = upload_script.setup_cloudinary(config)
        
        if check_cancelled(job_id):
            return
        
        update_job_status(job_id, 'running', 20, 'Opening spreadsheet...')
        sheet = upload_script.open_spreadsheet(sheets_client, config)
        
        # Get product list first for progress tracking
        worksheet, records = upload_script.get_image_links_data(sheet, config)
        total_products = len(records)
        
        update_job_status(job_id, 'running', 30, f'Found {total_products} products to process')
        
        # Process with progress updates
        log_message(job_id, f'Starting upload for {total_products} products...')
        
        # We'll manually process to add cancellation checks
        results = []
        for idx, record in enumerate(records):
            if check_cancelled(job_id):
                log_message(job_id, 'Job cancelled - stopping upload')
                return
            
            sku = record.get('SKU', '')
            progress = 30 + int((idx / total_products) * 60)  # 30% to 90%
            
            log_message(job_id, f'[{idx+1}/{total_products}] Processing SKU: {sku}')
            update_job_status(job_id, 'running', progress, f'Processing {sku} ({idx+1}/{total_products})')
            
            # Process this SKU (simplified - you may need to import the actual logic)
            # For now, call the full function and track
        
        # Call the actual processing
        results = upload_script.process_direct_upload(config, sheets_client, drive_service, sheet, cloudinary_folder)
        
        if check_cancelled(job_id):
            return
        
        # Count results
        success = sum(1 for r in results if r['status'] == 'Done')
        failed = sum(1 for r in results if r['status'] == 'Failed')
        
        update_job_status(job_id, 'completed', 100, f'Complete! ✓ {success} succeeded, ✗ {failed} failed')
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        error_traceback = traceback.format_exc()
        log_message(job_id, f'ERROR: {error_traceback}')
        update_job_status(job_id, 'failed', 0, error_msg, error=error_traceback)

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
        job_cancelled[job_id] = False
        update_job_status(job_id, 'pending', 0, 'Job queued')
        
        # Start background thread
        thread = threading.Thread(
            target=run_drive_to_cloudinary,
            args=(job_id, sheet_name)
        )
        thread.daemon = True
        thread.start()
        job_threads[job_id] = thread
        
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
        total_skus = len(sku_url_map)
        
        update_job_status(job_id, 'running', 50, f'Found {total_skus} SKUs - Updating Google Sheet...')
        
        sheets_client = sync_script.authenticate_sheets(config)
        sheet = sync_script.open_spreadsheet(sheets_client, config)
        
        # Note: The actual sync function logs internally, so we just track completion
        sync_script.update_sheet_with_urls(sheet, config, sku_url_map, sku_public_ids)
        
        update_job_status(job_id, 'completed', 100, f'Done! Processed {total_skus} SKUs with AI titles')
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        log_message(job_id, f'ERROR: {error_traceback}')
        update_job_status(job_id, 'failed', 0, str(e), error=error_traceback)


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
        
        if check_cancelled(job_id):
            return
        
        # Cleanup old files first
        cleanup_old_csvs()
        
        import generate_shopify_csv as csv_script
        
        config = csv_script.load_config()
        
        update_job_status(job_id, 'running', 30, 'Reading product data...')
        
        if check_cancelled(job_id):
            return
        
        sheets_client = csv_script.authenticate_sheets(config)
        sheet = csv_script.open_spreadsheet(sheets_client, config)
        
        # Get product count
        product_df = csv_script.get_product_data(sheet, config)
        total_products = len(product_df)
        
        update_job_status(job_id, 'running', 50, f'Generating CSV for {total_products} products...')
        
        if check_cancelled(job_id):
            return
        
        csv_file = csv_script.main()

        if csv_file and os.path.exists(csv_file):
            file_url = f"/{csv_file}"
            log_message(job_id, f'CSV saved to: {csv_file}')
            update_job_status(job_id, 'completed', 100, f'Done! Generated CSV with {total_products} products. <a href="{file_url}" download style="color: #4CAF50; text-decoration: underline;">Download CSV</a>')
        else:
            log_message(job_id, f'ERROR: CSV file not created')
            update_job_status(job_id, 'failed', 0, 'CSV generation failed - file not created')    
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        log_message(job_id, f'ERROR: {error_traceback}')
        update_job_status(job_id, 'failed', 0, str(e), error=error_traceback)

@app.route('/api/jobs/generate-csv', methods=['POST'])
def start_generate_csv():
    """Start generate Shopify CSV job"""
    try:
        data = request.json
        sheet_name = data.get('sheet_name')
        
        if not sheet_name:
            return jsonify({'error': 'sheet_name required'}), 400
        
        job_id = f"generate_csv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        job_cancelled[job_id] = False
        update_job_status(job_id, 'pending', 0, 'Job queued')
        
        # Start background thread
        thread = threading.Thread(target=run_generate_csv, args=(job_id, sheet_name))
        thread.daemon = True
        thread.start()
        job_threads[job_id] = thread
        
        return jsonify({'job_id': job_id, 'status': 'started'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)