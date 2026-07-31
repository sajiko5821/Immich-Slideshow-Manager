import os
import json
import threading
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from transform import process_job, fetch_album_assets

app = Flask(__name__)

DATA_DIR = 'data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {'jobs': []}
    return {'jobs': []}

def save_config(config):
    # Ensure we don't accidentally save env variables back to disk if they were injected
    config_to_save = config.copy()
    if os.environ.get('IMMICH_API_KEY') and 'immich_api_key' in config_to_save:
        del config_to_save['immich_api_key']

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_to_save, f, indent=4)

config = load_config()

job_status = {}

def trigger_job(job_id, job_data):
    job_status[job_id] = {'status': 'running', 'message': 'Processing images...'}
    try:
        # Inject ENV vars if they exist so transform.py can use them
        job_data_to_run = job_data.copy()
        if os.environ.get('IMMICH_API_KEY'):
            job_data_to_run['immich_api_key'] = os.environ.get('IMMICH_API_KEY')
            
        count = process_job(job_data_to_run)
        job_status[job_id] = {'status': 'success', 'message': f'Processed {count} images.'}
    except Exception as e:
        job_status[job_id] = {'status': 'error', 'message': str(e)}

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
        func=process_job,
        trigger="cron",
        hour=hour,
        minute=minute,
        id=job_id,
        args=[job],
        replace_existing=True
    )
    print(f"Scheduled job {job['name']} to run daily at {hour:02d}:{minute:02d}.")

def unschedule_job(job_id):
    sched_id = f"sync_job_{job_id}"
    if scheduler.get_job(sched_id):
        scheduler.remove_job(sched_id)
        print(f"Removed scheduled job {sched_id}.")

scheduler = BackgroundScheduler()
scheduler.start()

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
            status_info = job_status.get(job['id'], {'status': 'idle', 'message': ''})
            job_copy['last_status'] = status_info['status']
            job_copy['last_message'] = status_info['message']
            
            # Mask API key if it's from env
            if os.environ.get('IMMICH_API_KEY'):
                job_copy['api_key'] = '*******************'
                job_copy['env_api_key'] = True
                
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
        return jsonify({'success': True})
        
    if request.method == 'PUT':
        job_data = request.json
        for job in config['jobs']:
            if job['id'] == job_id:
                job.update({
                    'name': job_data.get('name', job['name']),
                    'immich_url': job_data.get('immich_url', job['immich_url']),
                    'api_key': job_data.get('api_key', job['api_key']),
                    'dest_dir': job_data.get('dest_dir', job['dest_dir']),
                    'num_images': int(job_data.get('num_images', job['num_images'])),
                    'sync_time': job_data.get('sync_time', job.get('sync_time', '02:00'))
                })
                save_config(config)
                schedule_job(job)
                return jsonify({'success': True, 'job': job})
        return jsonify({'success': False, 'error': 'Job not found'})

@app.route('/api/jobs/<int:job_id>/trigger', methods=['POST'])
def trigger_job_endpoint(job_id):
    job = next((j for j in config['jobs'] if j['id'] == job_id), None)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'})
    
    thread = threading.Thread(target=trigger_job, args=(job_id, job))
    thread.start()
    return jsonify({'success': True, 'message': 'Job started'})

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    data = request.json
    immich_url = data.get('immich_url')
    api_key = data.get('api_key')
    
    if not immich_url or not api_key:
        return jsonify({'success': False, 'error': 'Missing URL or API Key.'})
        
    try:
        assets, corrected_url = fetch_album_assets(immich_url, api_key)
        if assets:
            return jsonify({
                'success': True, 
                'message': f'Connection successful! Found {len(assets)} images in album.',
                'corrected_url': corrected_url
            })
        else:
            return jsonify({'success': False, 'error': 'Connected, but no assets found or invalid album.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=False)
