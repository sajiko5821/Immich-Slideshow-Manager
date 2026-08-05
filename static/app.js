let currentJobs = [];
let pollInterval;
let envSettings = { env_api_key: false };

async function init() {
    await loadSettings();
    loadJobs();
    pollInterval = setInterval(loadJobs, 5000);

    document.getElementById('btn-new-config').addEventListener('click', openModal);
    document.getElementById('btn-close-modal').addEventListener('click', closeModal);
    document.getElementById('btn-cancel').addEventListener('click', closeModal);
    document.getElementById('config-form').addEventListener('submit', saveJob);
    document.getElementById('btn-test-conn').addEventListener('click', testConnection);
}

async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        envSettings = await response.json();
    } catch (e) {
        console.error('Failed to load settings', e);
    }
}

async function loadJobs() {
    try {
        const response = await fetch('/api/jobs');
        currentJobs = await response.json();
        renderJobs();
    } catch (e) {
        console.error('Failed to load jobs', e);
    }
}

function renderJobs() {
    const container = document.getElementById('jobs-container');
    container.innerHTML = '';

    currentJobs.forEach(job => {
        const card = document.createElement('div');
        card.className = 'job-card glass-container';
        
        let statusClass = 'status-idle';
        let statusIcon = 'fa-circle-pause';
        let statusText = 'Idle';
        
        if (job.last_status === 'running') {
            statusClass = 'status-running';
            statusIcon = 'fa-circle-notch fa-spin';
            statusText = 'Running';
        } else if (job.last_status === 'success') {
            statusClass = 'status-success';
            statusIcon = 'fa-check';
            statusText = 'Success';
        } else if (job.last_status === 'error') {
            statusClass = 'status-error';
            statusIcon = 'fa-triangle-exclamation';
            statusText = 'Failed';
        }

        card.innerHTML = `
            <div class="job-header">
                <div>
                    <h3>${job.name}</h3>
                    <div class="job-status ${statusClass}">
                        <i class="fa-solid ${statusIcon}"></i> ${statusText}
                    </div>
                </div>
                <div class="job-actions">
                    <button class="icon-btn" onclick="triggerJob(${job.id})" title="Sync Now"><i class="fa-solid fa-play"></i></button>
                    <button class="icon-btn" onclick="editJob(${job.id})" title="Edit"><i class="fa-solid fa-pen"></i></button>
                    <button class="icon-btn" onclick="deleteJob(${job.id})" title="Delete"><i class="fa-solid fa-trash"></i></button>
                </div>
            </div>
            
            <div class="job-details">
                <div class="detail-item">
                    <i class="fa-solid fa-link"></i>
                    <span>${job.immich_url}</span>
                </div>
                <div class="detail-item">
                    <i class="fa-solid fa-image"></i>
                    <span>${job.num_images} images</span>
                </div>
                <div class="detail-item">
                    <i class="fa-solid fa-clock"></i>
                    <span>Daily at ${job.sync_time || '02:00'}</span>
                </div>
                <div class="detail-item">
                    <i class="fa-solid fa-display"></i>
                    <span>Dest: ${job.dest_dir}</span>
                </div>
            </div>
            
            ${job.last_message ? `
            <div class="detail-item" style="font-size: 0.8rem; margin-top: 1rem; color: #94a3b8;">
                <i class="fa-solid fa-info-circle"></i>
                <span>${job.last_message}</span>
            </div>
            ` : ''}
        `;
        
        container.appendChild(card);
    });
}

function openModal() {
    document.getElementById('config-form').reset();
    document.getElementById('job-id').value = '';
    document.getElementById('modal-title').textContent = 'New Configuration';
    document.getElementById('test-result').style.display = 'none';
    
    const apiGroup = document.getElementById('api-key-group');
    const apiKeyInput = document.getElementById('job-api-key');
    if (apiGroup) apiGroup.style.display = 'none';
    if (apiKeyInput) apiKeyInput.removeAttribute('required');
    
    document.getElementById('config-modal').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('config-modal').classList.add('hidden');
}

function editJob(id) {
    const job = currentJobs.find(j => j.id === id);
    if (!job) return;
    
    document.getElementById('job-id').value = job.id;
    document.getElementById('job-name').value = job.name;
    document.getElementById('job-immich-url').value = job.immich_url;
    document.getElementById('job-api-key').value = job.api_key || '';
    document.getElementById('job-dest').value = job.dest_dir;
    document.getElementById('job-num').value = job.num_images;
    document.getElementById('job-time').value = job.sync_time || '02:00';
    document.getElementById('test-result').style.display = 'none';
    
    const apiGroup = document.getElementById('api-key-group');
    const apiKeyInput = document.getElementById('job-api-key');
    if (apiGroup) apiGroup.style.display = 'none';
    if (apiKeyInput) apiKeyInput.removeAttribute('required');

    document.getElementById('modal-title').textContent = 'Edit Configuration';
    document.getElementById('config-modal').classList.remove('hidden');
}

async function saveJob(e) {
    e.preventDefault();
    
    const id = document.getElementById('job-id').value;
    const jobData = {
        name: document.getElementById('job-name').value,
        immich_url: document.getElementById('job-immich-url').value,
        api_key: document.getElementById('job-api-key').value,
        dest_dir: document.getElementById('job-dest').value,
        num_images: parseInt(document.getElementById('job-num').value),
        sync_time: document.getElementById('job-time').value
    };
    
    try {
        const url = id ? `/api/jobs/${id}` : '/api/jobs';
        const method = id ? 'PUT' : 'POST';
        
        const res = await fetch(url, {
            method: method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(jobData)
        });
        
        if (res.ok) {
            closeModal();
            loadJobs();
        }
    } catch (e) {
        console.error('Failed to save job', e);
    }
}

async function deleteJob(id) {
    if (!confirm('Are you sure you want to delete this configuration?')) return;
    
    try {
        const res = await fetch(`/api/jobs/${id}`, { method: 'DELETE' });
        if (res.ok) loadJobs();
    } catch (e) {
        console.error('Failed to delete job', e);
    }
}

async function triggerJob(id) {
    try {
        const res = await fetch(`/api/jobs/${id}/trigger`, { method: 'POST' });
        if (res.ok) {
            loadJobs();
        }
    } catch (e) {
        console.error('Failed to trigger job', e);
    }
}

async function testConnection() {
    const url = document.getElementById('job-immich-url').value;
    const apiKey = document.getElementById('job-api-key').value;
    const resultDiv = document.getElementById('test-result');
    const btn = document.getElementById('btn-test-conn');
    
    if (!url) {
        resultDiv.style.display = 'block';
        resultDiv.style.backgroundColor = 'rgba(239, 68, 68, 0.2)';
        resultDiv.style.color = '#fca5a5';
        resultDiv.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Please enter the Album URL';
        return;
    }
    
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Testing...';
    
    try {
        const res = await fetch('/api/test-connection', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ immich_url: url, api_key: apiKey })
        });
        
        const data = await res.json();
        
        resultDiv.style.display = 'block';
        if (data.success) {
            if (data.corrected_url && data.corrected_url !== url) {
                document.getElementById('job-immich-url').value = data.corrected_url;
            }
            resultDiv.style.backgroundColor = 'rgba(16, 185, 129, 0.2)';
            resultDiv.style.color = '#34d399';
            resultDiv.innerHTML = `<i class="fa-solid fa-check"></i> ${data.message}`;
        } else {
            resultDiv.style.backgroundColor = 'rgba(239, 68, 68, 0.2)';
            resultDiv.style.color = '#fca5a5';
            resultDiv.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Connection failed: ${data.error}`;
        }
    } catch (e) {
        resultDiv.style.display = 'block';
        resultDiv.style.backgroundColor = 'rgba(239, 68, 68, 0.2)';
        resultDiv.style.color = '#fca5a5';
        resultDiv.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Network error occurred`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Test Connection';
    }
}

document.addEventListener('DOMContentLoaded', init);
