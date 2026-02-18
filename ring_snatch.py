import os
import time
import sys
import json
import urllib.request
import urllib.error

# Configuration (Passed via Environment or Defaults)
# Note: Inside Docker this usually defaults to localhost
HA_BASE_URL = os.getenv("HA_BASE_URL", "http://127.0.0.1:8123")
TOKEN = os.getenv("HA_TOKEN")
ENTITY_ID = "camera.front_door_live_view"
OUTPUT_FILE = "/config/www/snapshots/ring_last_motion.jpg"

def log(msg):
    print(f"[RingSnatch] {msg}")

def get_real_entity_token():
    """Fetch the internal access_token from the entity state."""
    url = f"{HA_BASE_URL}/api/states/{ENTITY_ID}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    
    log(f"Fetching state for {ENTITY_ID}...")
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read())
                attrs = data.get("attributes", {})
                access_token = attrs.get("access_token")
                if access_token:
                    log("Got internal access_token.")
                    return access_token
                else:
                    log("Error: Entity has no access_token attribute.")
            else:
                log(f"Error fetching state: {response.status}")
    except Exception as e:
        log(f"State fetch failed: {e}")
        
    return None

def grab_frame_from_stream(access_token):
    """Connect to the MJPEG stream and extract the first valid JPEG frame."""
    
    stream_url = f"{HA_BASE_URL}/api/camera_proxy_stream/{ENTITY_ID}?token={access_token}"
    log(f"Connecting to stream: {stream_url}")
    
    # MJPEG stream boundary marker is usually defined in Content-Type header
    # but we can just hunt for JPEG magic numbers: FF D8 ... FF D9
    
    max_retries = 20
    
    for i in range(max_retries):
        try:
            log(f"Attempt {i+1}/{max_retries} connecting to stream...")
            # Impersonate Home Assistant Frontend
            req = urllib.request.Request(stream_url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"{HA_BASE_URL}/lovelace",
                "Accept": "*/*"
            })
            
            # 30 second timeout to allow for buffering once connected
            with urllib.request.urlopen(req, timeout=30) as response:
                log("Stream connected! buffering...")
                
                buffer = b""
                start_time = time.time()
                last_good_frame = None
                
                while (time.time() - start_time) < 15: # Read for up to 15s per connection
                    # Read chunks
                    chunk = response.read(4096)
                    if not chunk:
                        break
                    
                    buffer += chunk
                    
                    # Look for JPEG start
                    start = buffer.find(b'\xff\xd8')
                    if start != -1:
                        # Look for JPEG end
                        end = buffer.find(b'\xff\xd9', start)
                        if end != -1:
                            log("Found a JPEG frame!")
                            jpeg_data = buffer[start:end+2]
                            
                            # Update candidate
                            last_good_frame = jpeg_data
                            
                            # Advance buffer past this frame
                            buffer = buffer[end+2:]
                            
                            # If we have enough data (time > 6s), save and exit
                            if (time.time() - start_time) > 6:
                                log("Duration met. Saving last captured frame.")
                                with open(OUTPUT_FILE, 'wb') as f:
                                    f.write(last_good_frame)
                                log(f"Saved {len(last_good_frame)} bytes to {OUTPUT_FILE}")
                                return True
                                
                            # Otherwise continue to get a fresher frame
                            continue

                    # Keep buffer size manageable (only if no frame found yet)
                    if len(buffer) > 2_000_000:
                         # meaningful start check
                         start = buffer.find(b'\xff\xd8')
                         if start != -1:
                             buffer = buffer[start:]
                         else:
                             buffer = buffer[-2000:]
                
                # If we exit loop but have a frame (e.g. stream closed early), save it
                if last_good_frame:
                    log("Stream ended but we have a frame. Saving it.")
                    with open(OUTPUT_FILE, 'wb') as f:
                        f.write(last_good_frame)
                    log(f"Saved {len(last_good_frame)} bytes to {OUTPUT_FILE}")
                    return True
                
                log("Stream closed or empty without full frame.")
                
        except urllib.error.HTTPError as e:
            if e.code in [500, 502, 503, 504]:
                log(f"Got {e.code} (Camera Sleeping/Busy). Retrying...")
            else:
                log(f"HTTP Error: {e.code} {e.reason}")
        except Exception as e:
            log(f"Stream error: {e}")
            
        time.sleep(2) # Wait before retry
        
    log("Gave up. Stream never started.")
    return False

if __name__ == "__main__":
    if not TOKEN:
        log("Error: HA_TOKEN env var missing.")
        sys.exit(1)

    # 1. Get the ephemeral token
    real_token = get_real_entity_token()
    if not real_token:
        sys.exit(1)

    # 2. Attack!
    success = grab_frame_from_stream(real_token)
    
    if not success:
        sys.exit(1)
