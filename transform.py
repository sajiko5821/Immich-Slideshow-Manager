import requests
import random
import os
import shutil
import tempfile
import time
import logging
from PIL import Image, ImageFilter, ImageEnhance, ExifTags

logger = logging.getLogger('immich_slideshow.transform')

def fetch_album_assets(url, api_key):
    if api_key:
        api_key = api_key.strip().strip('"').strip("'")

    if '/albums/' in url and '/api/albums/' not in url:
        url = url.replace('/albums/', '/api/albums/')
        
    album_id = url.split('/albums/')[-1].split('?')[0].rstrip('/')
    raw_base = url.split('/albums/')[0].rstrip('/')
    if not raw_base.endswith('/api'):
        api_base_url = f"{raw_base}/api"
    else:
        api_base_url = raw_base

    headers = {
        'Accept': 'application/json', 
        'Content-Type': 'application/json', 
        'x-api-key': api_key
    }

    logger.info(f"Fetching album '{album_id}' from Immich endpoint: {api_base_url}")
    search_url = f"{api_base_url}/search/metadata"
    
    try:
        found_ids = []
        page = 1
        
        while True:
            logger.debug(f"Querying Immich API search metadata page {page} for album '{album_id}'...")
            payload = {'albumIds': [album_id], 'size': 1000, 'page': page}
            response = requests.post(search_url, headers=headers, json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                assets = data.get('assets', {}).get('items', [])
                new_ids = [asset.get('id') for asset in assets if asset.get('id')]
                
                if assets and not new_ids and page == 1:
                    sample_asset = assets[0]
                    keys = list(sample_asset.keys()) if isinstance(sample_asset, dict) else type(sample_asset)
                    raise ValueError(f"Found assets, but none have 'id'. Asset keys: {keys}")
                
                found_ids.extend(new_ids)
                logger.debug(f"Page {page}: Retrieved {len(new_ids)} asset IDs (Total so far: {len(found_ids)})")
                
                if len(assets) < 1000:
                    break
                    
                page += 1
            elif response.status_code in (401, 403):
                raise ValueError(f"Authentication failed (HTTP {response.status_code}). Please verify your Immich API Key and permissions.")
            else:
                raise ValueError(f"Failed to retrieve album data. Status Code: {response.status_code} - {response.text}")
                
        logger.info(f"Successfully retrieved metadata for {len(found_ids)} total assets from album.")
        return (found_ids, url)
    except Exception as e:
        logger.error(f"Error fetching album assets from Immich: {e}")
        raise e

def download_asset(asset_id, base_url, api_key, output_path):
    if api_key:
        api_key = api_key.strip().strip('"').strip("'")

    raw_base = base_url.split('/albums/')[0].rstrip('/')
    if not raw_base.endswith('/api'):
        raw_base = f"{raw_base}/api"
        
    download_url = f"{raw_base}/assets/{asset_id}/original"
    
    logger.debug(f"Downloading original asset {asset_id} from {download_url}...")
    headers = {
        'Accept': 'application/octet-stream', 
        'x-api-key': api_key
    }
    response = requests.get(download_url, headers=headers, stream=True)
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(1024 * 1024):
                f.write(chunk)
        logger.debug(f"Successfully downloaded asset {asset_id} to temporary file.")
    else:
        raise ValueError(f"Failed to download asset {asset_id}. HTTP Status Code: {response.status_code}")

def clear_directory(directory_path):
    abs_dir = os.path.abspath(directory_path)
    abs_cwd = os.path.abspath(os.getcwd())
    
    # SAFETY MEASURE
    if abs_dir in ['/', '/tmp', '/Users', os.path.expanduser('~')]:
        raise ValueError(f"CRITICAL ERROR: Attempted to delete system directory {directory_path}")
        
    if abs_cwd.startswith(abs_dir):
        raise ValueError(f"CRITICAL ERROR: Attempted to delete workspace parent or current directory {directory_path}")
    
    if not os.path.exists(directory_path):
        logger.info(f"Creating destination directory: {directory_path}")
        os.makedirs(directory_path, exist_ok=True)
        return

    logger.info(f"Clearing old images in destination directory: {directory_path}")
    removed_count = 0
    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
                removed_count += 1
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
                removed_count += 1
        except Exception as e:
            logger.warning(f"Failed to delete {file_path}: {e}")
    logger.debug(f"Removed {removed_count} existing files from {directory_path}.")

def process_image(source_path, output_path, target_width=16, target_height=10, blur_factor=5, background_brightness=0.75):
    try:
        image = Image.open(source_path)

        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        exif = image._getexif()
        if exif is not None:
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break
            
            if orientation in exif:
                orientation_val = exif[orientation]
                if orientation_val == 3:
                    image = image.rotate(180, expand=True)
                elif orientation_val == 6:
                    image = image.rotate(270, expand=True)
                elif orientation_val == 8:
                    image = image.rotate(90, expand=True)
                logger.debug(f"Applied EXIF orientation rotation ({orientation_val}) for image.")

        width, height = image.size
        
        if width > height:
            target_ratio = target_width / target_height
            current_ratio = width / height

            if current_ratio > target_ratio:
                new_width = int(height * target_ratio)
                left_margin = (width - new_width) // 2
                right_margin = width - left_margin
                image = image.crop((left_margin, 0, right_margin, height))

        if width <= height:
            canvas_width = int(height * target_width / target_height)
            canvas_height = height
            bg_width = canvas_width
            bg_height = int(canvas_width * height / width)

            background_image = image.resize((bg_width, bg_height))
            blurred_image = background_image.filter(ImageFilter.GaussianBlur(blur_factor))

            enhancer = ImageEnhance.Brightness(blurred_image)
            darkened_background = enhancer.enhance(background_brightness)

            canvas = Image.new("RGB", (canvas_width, canvas_height))
            canvas.paste(darkened_background, (0, (canvas_height - bg_height) // 2))

            offset = ((canvas_width - width) // 2, 0)
            canvas.paste(image, offset)

            canvas.save(output_path, 'JPEG', quality=95)
        else:
            image.save(output_path, 'JPEG', quality=95)
            
    except Exception as e:
        logger.error(f"Error processing image {source_path}: {e}")
        raise e

def process_job(job):
    job_name = job.get('name', 'Unnamed Job')
    immich_url = job.get('immich_url')
    api_key = job.get('api_key')
    dest_dir = job.get('dest_dir')
    
    start_time = time.time()
    logger.info(f"========== Starting Job: '{job_name}' ==========")
    logger.info(f"Target URL: {immich_url}")
    logger.info(f"Destination Directory: {dest_dir}")
    
    try:
        num_images = int(job.get('num_images', 30))
    except ValueError:
        num_images = 30
    logger.info(f"Max images requested: {num_images}")
        
    if not all([immich_url, api_key, dest_dir]):
        safe_job = job.copy()
        if 'api_key' in safe_job and safe_job['api_key']:
            safe_job['api_key'] = '*******************'
        err_msg = f"Job is missing required fields. Job configuration: {safe_job}"
        logger.error(err_msg)
        raise ValueError(err_msg)

    target_w = 16
    target_h = 10
    blur_f = 5
    bg_bright = 0.75

    all_ids, corrected_url = fetch_album_assets(immich_url, api_key)
    
    if not all_ids:
        err_msg = f"No assets found or failed to fetch album data from '{immich_url}'."
        logger.error(err_msg)
        raise RuntimeError(err_msg)
        
    if len(all_ids) > num_images:
        selected_ids = random.sample(all_ids, num_images)
        logger.info(f"Album contains {len(all_ids)} total photos. Randomly selected {len(selected_ids)} photos.")
    else:
        selected_ids = all_ids
        logger.info(f"Album contains {len(all_ids)} total photos. Processing all {len(selected_ids)} photos.")
        
    clear_directory(dest_dir)
    
    temp_dir = tempfile.mkdtemp()
    processed_count = 0
    failed_count = 0
    total_to_process = len(selected_ids)
    
    try:
        for i, asset_id in enumerate(selected_ids, start=1):
            temp_path = os.path.join(temp_dir, f"{asset_id}.jpg")
            output_filename = f"{i:02d}.jpg"
            full_output_path = os.path.join(dest_dir, output_filename)
            
            logger.info(f"[{i}/{total_to_process}] Downloading asset {asset_id}...")
            try:
                download_asset(asset_id, corrected_url, api_key, temp_path)
            except Exception as e:
                logger.error(f"[{i}/{total_to_process}] Failed to download asset {asset_id}: {e}")
                failed_count += 1
                continue
                
            logger.info(f"[{i}/{total_to_process}] Processing photo -> {output_filename}...")
            try:
                process_image(
                    temp_path, 
                    full_output_path, 
                    target_width=target_w, 
                    target_height=target_h, 
                    blur_factor=blur_f, 
                    background_brightness=bg_bright
                )
                processed_count += 1
            except Exception as e:
                logger.error(f"[{i}/{total_to_process}] Failed processing asset {asset_id}: {e}")
                failed_count += 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    elapsed = time.time() - start_time
    logger.info(f"========== Finished Job: '{job_name}' in {elapsed:.2f} seconds ==========")
    logger.info(f"Summary: {processed_count} succeeded, {failed_count} failed out of {total_to_process} requested.")
    return processed_count
