# Ring Integration Adventure 💍

**Status:** Superseded by [ring-mqtt](https://github.com/tsightler/ring-mqtt).

## The Goal
We wanted to integrate Ring cameras into Home Assistant (running as a Docker Container) to:
1.  Get snapshots and live streams.
2.  Force-wake cameras for on-demand updates.
3.  Manage authentication tokens.

## The Journey
We initially explored `ring_snatch.py` as a lightweight tool to extract tokens and force-wake cameras. However, we discovered that `ring-mqtt` offers a far more robust, "all-in-one" solution that handles token refreshing, device discovery, and state management automatically.

### The Challenge: "The Loop of Death" 🔄
After deploying `ring-mqtt` in Docker, we hit a connection loop:
```
ring-mqtt Attempting to reconnect to MQTT broker...
ring-mqtt Unable to connect to MQTT broker
```

The root causes were:
1.  **Missing Broker:** Home Assistant "Container" edition does not include an MQTT broker (unlike HA OS).
2.  **Network Isolation:** `ring-mqtt` (in Docker) was trying to connect to `localhost`, which meant *inside its own container*, not the host machine.
3.  **Access Control:** When we installed Mosquitto on the host, it defaulted to listening only on `127.0.0.1`, rejecting external connections (including those from Docker).

## The Solution 🛠️

### 1. Install Mosquitto on Host
Instead of running Mosquitto in Docker, we installed it directly on the Ubuntu host to act as the central message bus.

```bash
sudo apt install mosquitto mosquitto-clients
```

### 2. Configure Mosquitto to Listen
We had to explicitly tell Mosquitto to listen on all interfaces so the Docker container could reach it.

`/etc/mosquitto/conf.d/default.conf`:
```text
listener 1883
allow_anonymous true
```

### 3. Connect Home Assistant (Container)
Since HA Container has no "Add-on Store," we added the MQTT Integration manually:
*   **Host:** `192.168.68.119` (The host machine's LAN IP)
*   **Port:** `1883`

### 4. Configure ring-mqtt
We updated the `ring-mqtt` config to point to the host IP, **not** localhost.

`/opt/ring-mqtt/config.json`:
```json
"mqtt_url": "mqtt://user:pass@192.168.68.119:1883",
"local_stream_ip": "192.168.68.119"
```

### 5. Patch ring-mqtt for RTSP Streaming
Even with `local_stream_ip` set, `ring-mqtt` (v5.x) defaults to advertising its internal Docker IP (`172.x.x.x`) when running in Docker mode. This causes Home Assistant (running on host network) to fail with `502 Bad Gateway` when trying to access the stream.

To fix this, we patched `/app/ring-mqtt/devices/camera.js` inside the container to prioritize the configured `local_stream_ip`:

```javascript
// Before
streamSourceUrlBase = await utils.getHostIp()

// After
streamSourceUrlBase = utils.config().local_stream_ip || await utils.getHostIp()
```

This forces `ring-mqtt` to advertise the host IP (`192.168.68.119`), which maps port 8554 correctly to the container.

## Outcome
*   ✅ **Snapshots:** Working perfectly in Home Assistant.
*   ✅ **Live Stream:** Accessible via RTSP on host IP.
*   ✅ **Token Refresh:** Handled automatically by `ring-mqtt`.
*   ✅ **Force Wake:** Supported via the snapshot button/switch in HA.

## References
*   [ring-mqtt Wiki](https://github.com/tsightler/ring-mqtt/wiki) - The ultimate guide.
*   [Mosquitto](https://mosquitto.org/) - The broker we used.
