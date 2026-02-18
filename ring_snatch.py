import os
import sys
import json
import urllib.request
import subprocess
import time

# Configuration
HA_BASE_URL = os.getenv("HA_BASE_URL", "http://127.0.0.1:8123")
TOKEN = os.getenv("HA_TOKEN")
# We use the info sensor to get the direct RTSP URL (bypassing HA proxy)
INFO_SENSOR_ID = "sensor.front_door_info"
OUTPUT_FILE = "/config/www/snapshots/ring_last_motion.jpg"

def log(msg):
    print(f"[RingSnatch] {msg}")

def get_rtsp_url():
    """Fetch the RTSP URL from the info sensor attributes."""
    url = f"{HA_BASE_URL}/api/states/{INFO_SENSOR_ID}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    
    log(f"Fetching stream source from {INFO_SENSOR_ID}...")
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read())
                attrs = data.get("attributes", {})
                stream_source = attrs.get("stream_Source")
                if stream_source:
                    log(f"Got RTSP URL: {stream_source}")
                    return stream_source
                else:
                    log("Error: Sensor has no stream_Source attribute.")
            else:
                log(f"Error fetching state: {response.status}")
    except Exception as e:
        log(f"State fetch failed: {e}")
        
    return None

def grab_frame_ffmpeg(rtsp_url):
    """Use ffmpeg to grab a single frame from the RTSP stream."""
    log(f"Starting ffmpeg capture from {rtsp_url}...")
    
    # ffmpeg -y -i "rtsp://..." -vframes 1 "/path/to/output.jpg"
    cmd = [
        "ffmpeg",
        "-y",
        "-i", rtsp_url,
        "-vframes", "1",
        OUTPUT_FILE
    ]
    
    # Retry loop for ffmpeg (stream might take a moment to wake up)
    max_retries = 3
    for i in range(max_retries):
        try:
            # Run ffmpeg with a timeout (e.g. 20 seconds to connect and grab)
            # Capture output to avoid log spam unless error
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                timeout=30
            )
            
            if result.returncode == 0:
                log(f"Success! Frame saved to {OUTPUT_FILE}")
                return True
            else:
                log(f"ffmpeg failed (Attempt {i+1}/{max_retries}): {result.stderr.decode('utf-8')[:200]}...") # Log first 200 chars of error
                
        except subprocess.TimeoutExpired:
            log(f"ffmpeg timed out (Attempt {i+1}/{max_retries})")
        except Exception as e:
            log(f"ffmpeg execution error: {e}")
            
        time.sleep(2) # Wait before retry
        
    return False

if __name__ == "__main__":
    if not TOKEN:
        log("Error: HA_TOKEN env var missing.")
        sys.exit(1)

    # 1. Get the RTSP URL
    rtsp_url = get_rtsp_url()
    if not rtsp_url:
        sys.exit(1)

    # 2. Grab frame
    success = grab_frame_ffmpeg(rtsp_url)
    
    if not success:
        sys.exit(1)
