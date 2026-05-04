import os
from dotenv import load_dotenv
import io
import zipfile
import json
import requests
import isodate 
from flask import Flask, render_template, request
import ijson

load_dotenv()

api_session = requests.Session()



app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['SECRET_KEY'] =os.environ.get('SECRET_KEY')

# Ensure you have your actual YouTube API Key here
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')

# Mapping of YouTube Category IDs to readable names
CATEGORY_MAP = {
    "1": "Film & Animation",
    "2": "Autos & Vehicles",
    "10": "Music",
    "15": "Pets & Animals",
    "17": "Sports",
    "20": "Gaming",
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology"
}

def get_batch_video_info(video_ids):
    """Fetches durations and categories. Returns (video_info, error_message)."""
    if not YOUTUBE_API_KEY:
        return {}, "YouTube API Key is missing. Please check your .env file."
    
    if not video_ids:
        return {}, None
        
    api_url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        'id': ','.join(video_ids),
        'part': 'contentDetails,snippet',
        'key': YOUTUBE_API_KEY
    }
    
    video_info = {}
    try:
        response = api_session.get(api_url, params=params, timeout=10)
        
        # Handle specific API errors
        if response.status_code == 403:
            return {}, "YouTube API quota exceeded or invalid key."
        
        response.raise_for_status()
        data = response.json()
        
        for item in data.get('items', []):
            v_id = item['id']
            iso_dur = item['contentDetails']['duration']
            cat_id = item['snippet'].get('categoryId', "Unknown")
            
            video_info[v_id] = {
                'duration': isodate.parse_duration(iso_dur).total_seconds(),
                'category': CATEGORY_MAP.get(cat_id, "Other")
            }
        return video_info, None
        
    except Exception as e:
        return {}, f"Batch API Error: {str(e)}"

def perform_analysis(history_data):
    """Returns (shorts, videos, categories, error_message)."""
    shorts_count = 0
    videos_count = 0
    category_counts = {}
    master_info = {}
    
    target_data = history_data[:500]
    all_video_ids = []
    
    for entry in target_data:
        url = entry.get('titleUrl', '')
        v_id = None
        if "v=" in url:
            v_id = url.split("v=")[1].split("&")[0][:11]
        elif "/shorts/" in url:
            v_id = url.split("/shorts/")[1][:11]
        if v_id:
            all_video_ids.append(v_id)

    # Process in chunks of 50
    for i in range(0, len(all_video_ids), 50):
        chunk = all_video_ids[i:i + 50]
        chunk_info, error = get_batch_video_info(chunk)
        
        # If an error occurs in any chunk, stop and return the error
        if error:
            return 0, 0, {}, error
            
        master_info.update(chunk_info)

    for entry in target_data:
        url = entry.get('titleUrl', '')
        v_id = None
        if "v=" in url:
            v_id = url.split("v=")[1].split("&")[0][:11]
        elif "/shorts/" in url:
            v_id = url.split("/shorts/")[1][:11]
            
        if v_id in master_info:
            info = master_info[v_id]
            if "/shorts/" in url or info['duration'] <= 60:
                shorts_count += 1
            else:
                videos_count += 1
            
            cat_name = info['category']
            category_counts[cat_name] = category_counts.get(cat_name, 0) + 1
            
    return shorts_count, videos_count, category_counts, None

@app.route('/')
def index():
    """Renders the main upload page."""
    return render_template('index.html')

@app.route('/process-upload', methods=['POST'])
def process_upload():
    if 'file' not in request.files:
        return "No file part"
    file = request.files['file']
    if file.filename == '':
        return "No selected file"
    
    try:
        # Load the 3MB compressed ZIP into memory (This is safe and small)
        zip_data = io.BytesIO(file.read())
        with zipfile.ZipFile(zip_data, 'r') as z:
            target = next((f for f in z.namelist() if 'watch-history.json' in f), None)
            if not target: return "Error: watch-history.json not found in ZIP."
            
            with z.open(target) as f:
                # STREAM THE JSON: 'item' yields objects from the main JSON array one by one
                objects = ijson.items(f, 'item')
                
                # Sip only the first 500 items, then stop reading
                target_data = []
                for i, obj in enumerate(objects):
                    if i >= 500:
                        break
                    target_data.append(obj)
                
                # Pass ONLY the tiny 500-item list to your analysis function
                shorts, videos, categories, error = perform_analysis(target_data)
                
                if error:
                    return render_template('results.html', error=error)
                
                total_watched = shorts + videos
                return render_template('results.html', 
                                     shorts=shorts, 
                                     videos=videos, 
                                     total=total_watched,
                                     categories=categories)
    except Exception as e:
        return f"An error occurred: {str(e)}"
        
if __name__ == '__main__':
    # Threading is essential for multiple batch network calls[cite: 1]
    app.run(debug=True, threaded=True)
