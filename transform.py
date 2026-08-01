import requests
import random
import os
import shutil
import tempfile
from PIL import Image, ImageFilter, ImageEnhance, ExifTags

def fetch_album_assets(url, api_key):
    if '/albums/' in url and '/api/albums/' not in url:
        url = url.replace('/albums/', '/api/albums/')
        
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json', 'x-api-key': api_key}
    print(f"Fetching album data from {url}...")
    
    album_id = url.split('/albums/')[-1]
    api_base = url.split('/albums/')[0]
    search_url = f"{api_base}/search/metadata"
    
    try:
        found_ids = []
        page = 1
        
        while True:
            payload = {'albumIds': [album_id], 'size': 1000, 'page': page}
            response = requests.post(search_url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                assets = data.get('assets', {}).get('items', [])
                new_ids = [asset.get('id') for asset in assets if asset.get('id')]
                
                if assets and not new_ids and page == 1:
                    sample_asset = assets[0]
                    keys = list(sample_asset.keys()) if isinstance(sample_asset, dict) else type(sample_asset)
                    raise ValueError(f"Found assets, but none have 'id'. Asset keys: {keys}")
                
                found_ids.extend(new_ids)
                
                if len(assets) < 1000:
                    break
                    
                page += 1
            elif response.status_code == 401 or response.status_code == 403:
                raise ValueError("Authentication failed. Please check your API Key.")
            else:
                raise ValueError(f"Failed to retrieve data. Status Code: {response.status_code} - {response.text}")
                
        return (found_ids, url)
    except Exception as e:
        print("Error fetching JSON:", str(e))
        raise e

def download_asset(asset_id, base_url, api_key, output_path):
    api_base = base_url.split('/albums/')[0]
    download_url = f"{api_base}/assets/{asset_id}/original"
    
    headers = {'Accept': 'application/octet-stream', 'x-api-key': api_key}
    response = requests.get(download_url, headers=headers, stream=True)
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(1024 * 1024):
                f.write(chunk)
    else:
        raise ValueError(f"Failed to download asset {asset_id}. Status Code: {response.status_code}")

def clear_directory(directory_path):
    abs_dir = os.path.abspath(directory_path)
    abs_cwd = os.path.abspath(os.getcwd())
    
    # SAFETY MEASURE
    if abs_dir in ['/', '/tmp', '/Users', os.path.expanduser('~')]:
        raise ValueError(f"CRITICAL ERROR: Attempted to delete system directory {directory_path}")
        
    if abs_cwd.startswith(abs_dir):
        raise ValueError(f"CRITICAL ERROR: Attempted to delete workspace parent or current directory {directory_path}")
    
    if not os.path.exists(directory_path):
        os.makedirs(directory_path, exist_ok=True)
        return

    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")

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
                if exif[orientation] == 3:
                    image = image.rotate(180, expand=True)
                elif exif[orientation] == 6:
                    image = image.rotate(270, expand=True)
                elif exif[orientation] == 8:
                    image = image.rotate(90, expand=True)

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
        print(f"Error processing {source_path}: {e}")
        raise e

def process_job(job):
    immich_url = job.get('immich_url')
    api_key = job.get('api_key')
    dest_dir = job.get('dest_dir')
    
    try:
        num_images = int(job.get('num_images', 30))
    except ValueError:
        num_images = 30
        
    if not all([immich_url, api_key, dest_dir]):
        safe_job = job.copy()
        if 'api_key' in safe_job and safe_job['api_key']:
            safe_job['api_key'] = '*******************'
        raise ValueError(f"Job is missing required fields. Job data: {safe_job}")

    target_w = 16
    target_h = 10
    blur_f = 5
    bg_bright = 0.75

    all_ids, corrected_url = fetch_album_assets(immich_url, api_key)
    
    if not all_ids:
        raise RuntimeError("No assets found or failed to fetch album data.")
        
    if len(all_ids) > num_images:
        selected_ids = random.sample(all_ids, num_images)
    else:
        selected_ids = all_ids
        
    clear_directory(dest_dir)
    
    temp_dir = tempfile.mkdtemp()
    processed_count = 0
    try:
        for i, asset_id in enumerate(selected_ids, start=1):
            temp_path = os.path.join(temp_dir, f"{asset_id}.jpg")
            
            try:
                download_asset(asset_id, corrected_url, api_key, temp_path)
            except Exception as e:
                print(f"Failed to download {asset_id}: {e}")
                continue
                
            output_filename = f"{i:02d}.jpg"
            full_output_path = os.path.join(dest_dir, output_filename)
            
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
                print(f"Failed processing {asset_id}: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return processed_count
