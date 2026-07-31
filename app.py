import os
import json
import threading
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from transform import process_job, fetch_album_assets

app = Flask(__name__)
CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {'jobs': []}
    return {'jobs': []}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

config = load_config()

job_status = {}

def trigger_job(job_id, job_data):
    job_status[job_id] = {'status': 'running', 'message': 'Processing images...'}
    try:
        count = process_job(job_data)
        job_status[job_id] = {'status': 'success', 'message': f'Processed {count} images.'}
    except Exception as e:
        job_status[job_id] = {'status': 'error', 'message': str(e)}

def run_scheduled_jobs():
    print("Running scheduled jobs...")
    for job in config.get('jobs', []):
        try:
            process_job(job)
        except Exception as e:
            print(f"Scheduled job {job.get('name')} failed: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=run_scheduled_jobs, trigger="cron", hour=2, minute=0)
scheduler.start()

@app.route('/')
def index():
    return render_template('index.html')

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
            'num_images': int(job_data.get('num_images', 30))
        }
        config['jobs'].append(new_job)
        save_config(config)
        return jsonify({'success': True, 'job': new_job})

@app.route('/api/jobs/<int:job_id>', methods=['PUT', 'DELETE'])
def manage_job(job_id):
    global config
    if request.method == 'DELETE':
        config['jobs'] = [j for j in config['jobs'] if j['id'] != job_id]
        save_config(config)
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
                    'num_images': int(job_data.get('num_images', job['num_images']))
                })
                save_config(config)
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
