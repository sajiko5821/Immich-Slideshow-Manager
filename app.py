import os
import json
import threading
import logging
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from transform import process_job, fetch_album_assets

# Configure logging format and verbosity level
log_level_name = os.environ.get('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, log_level_name, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('immich_slideshow.app')

# Adjust level of third-party library loggers
logging.getLogger('werkzeug').setLevel(log_level)
logging.getLogger('apscheduler').setLevel(logging.WARNING if log_level_name != 'DEBUG' else logging.DEBUG)

class SuppressPollingFilter(logging.Filter):
    def filter(self, record):
        # Suppress status polling requests from the Web UI to prevent log spam
        msg = record.getMessage()
        if '/api/jobs' in msg or 'favicon.ico' in msg:
            return False
        return True

logging.getLogger('werkzeug').addFilter(SuppressPollingFilter())

logger.info(f"Initializing Immich Digital Photo Frame (LOG_LEVEL={log_level_name})")

app = Flask(__name__)

DATA_DIR = 'data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                cfg = json.load(f)
                logger.info(f"Loaded configuration from '{CONFIG_FILE}'. Found {len(cfg.get('jobs', []))} configured jobs.")
                return cfg
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing '{CONFIG_FILE}': {e}. Falling back to default empty config.")
            return {'jobs': []}
    logger.info(f"No config file found at '{CONFIG_FILE}'. Initializing empty configuration.")
    return {'jobs': []}

config_lock = threading.Lock()

def save_config(config):
    with config_lock:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        logger.debug("Configuration file updated successfully.")

config = load_config()

job_status = {}

def trigger_job(job_id, job_data):
    job_name = job_data.get('name', f'Job #{job_id}')
    logger.info(f"Starting execution of sync job '{job_name}' (ID: {job_id})...")
    job_status[job_id] = {'status': 'running', 'message': 'Processing images...'}
    
    def save_job_status(status_obj):
        for j in config.get('jobs', []):
            if str(j['id']) == str(job_id):
                j['last_status'] = status_obj
                break
        save_config(config)
        
    try:
        # Inject ENV var if present, or if job api_key is empty
        job_data_to_run = job_data.copy()
        if os.environ.get('IMMICH_API_KEY'):
            job_data_to_run['api_key'] = os.environ.get('IMMICH_API_KEY').strip().strip('"').strip("'")
            
        count = process_job(job_data_to_run)
        success_status = {'status': 'success', 'message': f'Processed {count} images.'}
        job_status[job_id] = success_status
        save_job_status(success_status)
    except Exception as e:
        logger.error(f"Sync job '{job_name}' (ID: {job_id}) encountered an error: {e}", exc_info=True)
        error_status = {'status': 'error', 'message': str(e)}
        job_status[job_id] = error_status
        save_job_status(error_status)

def schedule_job(job):
    job_id = f"sync_job_{job['id']}"
    sync_time = job.get('sync_time', '02:00')
    try:
        hour, minute = map(int, sync_time.split(':'))
    except ValueError:
        hour, minute = 2, 0
    
    # Remove existing job if it exists to replace it
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        
    scheduler.add_job(
        func=trigger_job,
        trigger="cron",
        hour=hour,
        minute=minute,
        id=job_id,
        args=[job['id'], job],
        replace_existing=True
    )
    logger.info(f"Scheduled job '{job['name']}' (ID: {job['id']}) to run daily at {hour:02d}:{minute:02d} cron time.")

def unschedule_job(job_id):
    sched_id = f"sync_job_{job_id}"
    if scheduler.get_job(sched_id):
        scheduler.remove_job(sched_id)
        logger.info(f"Removed scheduled job ID {job_id}.")

scheduler = BackgroundScheduler()
scheduler.start()
logger.info("Background job scheduler started.")

# Schedule all loaded jobs on startup
for job in config.get('jobs', []):
    schedule_job(job)

@app.route('/')
def index():
    from flask import send_from_directory
    return send_from_directory(app.root_path, 'index.html')

@app.route('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.svg', mimetype='image/svg+xml')

@app.route('/api/settings', methods=['GET'])
def get_settings():
    return jsonify({
        'env_api_key': bool(os.environ.get('IMMICH_API_KEY'))
    })

@app.route('/api/jobs', methods=['GET', 'POST'])
def handle_jobs():
    global config
    if request.method == 'GET':
        jobs_with_status = []
        for job in config.get('jobs', []):
            job_copy = job.copy()
            
            # Check if currently running in memory
            if job['id'] in job_status and job_status[job['id']]['status'] == 'running':
                status_info = job_status[job['id']]
            else:
                # Fallback to saved status
                status_info = job.get('last_status', {'status': 'idle', 'message': ''})
                
            job_copy['last_status'] = status_info['status']
            job_copy['last_message'] = status_info['message']
            job_copy['has_env_api_key'] = bool(os.environ.get('IMMICH_API_KEY'))
                
            jobs_with_status.append(job_copy)
        return jsonify(jobs_with_status)
    
    if request.method == 'POST':
        job_data = request.json
        new_id = 1 if not config['jobs'] else max(j['id'] for j in config['jobs']) + 1
        new_job = {
            'id': new_id,
            'name': job_data.get('name', 'New Job'),
            'immich_url': job_data.get('immich_url', ''),
            'api_key': job_data.get('api_key', ''),
            'dest_dir': job_data.get('dest_dir', ''),
            'num_images': int(job_data.get('num_images', 30)),
            'sync_time': job_data.get('sync_time', '02:00')
        }
        config['jobs'].append(new_job)
        save_config(config)
        schedule_job(new_job)
        logger.info(f"Created new sync job '{new_job['name']}' (ID: {new_id}).")
        return jsonify({'success': True, 'job': new_job})

@app.route('/api/jobs/<int:job_id>', methods=['PUT', 'DELETE'])
def manage_job(job_id):
    global config
    if request.method == 'DELETE':
        config['jobs'] = [j for j in config['jobs'] if j['id'] != job_id]
        save_config(config)
        unschedule_job(job_id)
        if job_id in job_status:
            del job_status[job_id]
        logger.info(f"Deleted job ID {job_id}.")
        return jsonify({'success': True})
        
    if request.method == 'PUT':
        job_data = request.json
        for job in config['jobs']:
            if job['id'] == job_id:
                api_key = job_data.get('api_key') or job.get('api_key', '')
                job.update({
                    'name': job_data.get('name', job['name']),
                    'immich_url': job_data.get('immich_url', job['immich_url']),
                    'api_key': api_key,
                    'dest_dir': job_data.get('dest_dir', job['dest_dir']),
                    'num_images': int(job_data.get('num_images', job['num_images'])),
                    'sync_time': job_data.get('sync_time', job.get('sync_time', '02:00'))
                })
                save_config(config)
                schedule_job(job)
                logger.info(f"Updated configuration for job '{job['name']}' (ID: {job_id}).")
                return jsonify({'success': True, 'job': job})
        return jsonify({'success': False, 'error': 'Job not found'})

@app.route('/api/jobs/<int:job_id>/trigger', methods=['POST'])
def trigger_job_endpoint(job_id):
    job = next((j for j in config['jobs'] if j['id'] == job_id), None)
    if not job:
        logger.warning(f"Manual trigger requested for non-existent job ID {job_id}.")
        return jsonify({'success': False, 'error': 'Job not found'})
    
    logger.info(f"Received manual trigger request for job '{job['name']}' (ID: {job_id}).")
    thread = threading.Thread(target=trigger_job, args=(job_id, job))
    thread.start()
    return jsonify({'success': True, 'message': 'Job started'})

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    data = request.json
    immich_url = data.get('immich_url')
    api_key = data.get('api_key') or os.environ.get('IMMICH_API_KEY')
    
    if not immich_url or not api_key:
        return jsonify({'success': False, 'error': 'Please enter both URL and API Key (or set the IMMICH_API_KEY environment variable).'})
        
    logger.info(f"Testing Immich connection to: {immich_url}")
    try:
        assets, corrected_url = fetch_album_assets(immich_url, api_key)
        if assets:
            logger.info(f"Connection test successful for {corrected_url}. Found {len(assets)} assets.")
            return jsonify({
                'success': True, 
                'message': f'Connection successful! Found {len(assets)} images in album.',
                'corrected_url': corrected_url
            })
        else:
            logger.warning(f"Connection test connected to {corrected_url}, but returned no assets.")
            return jsonify({'success': False, 'error': 'Connected, but no assets found or invalid album.'})
    except Exception as e:
        logger.error(f"Connection test failed for {immich_url}: {e}")
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    logger.info(f"Starting Web Server on host 0.0.0.0, port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
