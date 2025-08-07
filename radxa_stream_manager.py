# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Radxa Zero 3E Streaming Manager
#
# This Python Flask application provides a web interface to manage
# video streaming with ffmpeg-rockchip and MediaMTX on a Radxa Zero 3E.
#
# v7: Fixes broken JS/CSS links and improves logging reliability.
#
# Date: August 4, 2025
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

import os
import subprocess
import json
import threading
import re
import yaml
import time
import logging
import shutil
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, jsonify, request

# --- Configuration ---
APP_PORT = 5000
MEDIAMTX_URL = "https://github.com/bluenviron/mediamtx/releases/download/v1.13.1/mediamtx_v1.13.1_linux_arm64.tar.gz"
MEDIAMTX_DIR = "/opt/mediamtx"
MEDIAMTX_BIN = os.path.join(MEDIAMTX_DIR, "mediamtx")
MEDIAMTX_CONFIG = os.path.join(MEDIAMTX_DIR, "mediamtx.yml")
LOG_FILE = "/tmp/radxa_stream_manager.log"

# --- Globals for Stream Monitoring ---
ffmpeg_process = None
stream_stats = {}
stats_lock = threading.Lock()

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Helper Functions ---

def run_command(command, capture_output=True):
    """Runs a shell command and returns its output."""
    try:
        # Using list format for commands is safer than shell=True
        if isinstance(command, str) and not capture_output:
             process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             stdout, stderr = process.communicate()
             if process.returncode != 0:
                 logging.error(f"Error running command: {command}\nStderr: {stderr.decode('utf-8')}")
                 return None
             return stdout.decode('utf-8').strip()
        
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=capture_output,
            text=True
        )
        return result.stdout.strip() if capture_output else ""
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running command: {command}\nStderr: {e.stderr}")
        return None

def get_video_devices():
    """Gets a list of available video devices."""
    devices = []
    try:
        # Ensure v4l-utils is installed and the command runs
        output = run_command("v4l2-ctl --list-devices")
        if output:
            logging.info(f"v4l2-ctl output:\n{output}")
            current_device_name = None
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                if not line.startswith('/dev/video'):
                    # This line is a device name, like "USB Camera: (usb-....)"
                    current_device_name = line
                else:
                    # This line is a device path
                    if current_device_name:
                         devices.append({"name": current_device_name, "path": line})
                         current_device_name = None # Reset for next device block
        else:
            logging.warning("`v4l2-ctl --list-devices` produced no output.")
    except Exception as e:
        logging.error(f"Failed to get video devices: {e}")
    return devices

def get_device_capabilities(device_path):
    """Gets supported formats, resolutions and framerates for a video device."""
    try:
        # Get supported formats
        formats_output = run_command(f"v4l2-ctl --device={device_path} --list-formats-ext")
        if formats_output:
            logging.info(f"Device {device_path} capabilities:\n{formats_output}")
            return formats_output
        else:
            logging.warning(f"No format information available for {device_path}")
            return "No format information available"
    except Exception as e:
        logging.error(f"Failed to get device capabilities for {device_path}: {e}")
        return f"Error: {str(e)}"

def get_camera_controls(device_path):
    """Gets available camera controls for a video device."""
    try:
        controls_output = run_command(f"v4l2-ctl --device={device_path} --list-ctrls")
        if controls_output:
            logging.info(f"Device {device_path} controls:\n{controls_output}")
            return controls_output
        else:
            return "No controls available"
    except Exception as e:
        logging.error(f"Failed to get camera controls for {device_path}: {e}")
        return f"Error: {str(e)}"

def set_camera_control(device_path, control_name, value):
    """Sets a camera control value."""
    try:
        result = run_command(f"v4l2-ctl --device={device_path} --set-ctrl={control_name}={value}")
        logging.info(f"Set {control_name}={value} on {device_path}: {result}")
        return True
    except Exception as e:
        logging.error(f"Failed to set camera control {control_name}={value} on {device_path}: {e}")
        return False

def get_camera_control_value(device_path, control_name):
    """Gets current value of a camera control."""
    try:
        result = run_command(f"v4l2-ctl --device={device_path} --get-ctrl={control_name}")
        if result and ":" in result:
            value = result.split(":")[1].strip()
            return value
        return None
    except Exception as e:
        logging.error(f"Failed to get camera control {control_name} from {device_path}: {e}")
        return None

def get_tailscale_status():
    """Gets Tailscale connection status."""
    try:
        status_result = run_command("tailscale status --json")
        if status_result:
            import json
            status_data = json.loads(status_result)
            return {
                "connected": status_data.get("BackendState") == "Running",
                "ip": status_data.get("TailscaleIPs", [None])[0],
                "hostname": status_data.get("Self", {}).get("HostName", "Unknown"),
                "raw_status": status_result
            }
        else:
            return {"connected": False, "error": "Tailscale not responding"}
    except Exception as e:
        logging.error(f"Failed to get Tailscale status: {e}")
        return {"connected": False, "error": str(e)}

def scan_wifi_networks():
    """Scans for available WiFi networks."""
    try:
        # Use nmcli to scan for networks
        scan_result = run_command("nmcli dev wifi rescan")
        networks_result = run_command("nmcli -f SSID,SIGNAL,SECURITY dev wifi list")
        
        if networks_result:
            networks = []
            lines = networks_result.strip().split('\n')[1:]  # Skip header
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    ssid = parts[0]
                    signal = parts[1] if len(parts) > 1 else "0"
                    security = " ".join(parts[2:]) if len(parts) > 2 else "Open"
                    if ssid and ssid != "--":
                        networks.append({
                            "ssid": ssid,
                            "signal": signal,
                            "security": security
                        })
            return networks
        return []
    except Exception as e:
        logging.error(f"Failed to scan WiFi networks: {e}")
        return []

def get_wifi_status():
    """Gets current WiFi connection status."""
    try:
        result = run_command("nmcli -f NAME,TYPE,DEVICE connection show --active")
        wifi_connections = []
        if result:
            lines = result.strip().split('\n')[1:]  # Skip header
            for line in lines:
                if "wifi" in line.lower():
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        wifi_connections.append({
                            "name": parts[0],
                            "device": parts[-1]
                        })
        
        # Get IP info
        ip_result = run_command("ip route get 1.1.1.1 | grep -oP 'src \\K\\S+'")
        current_ip = ip_result.strip() if ip_result else "Unknown"
        
        return {
            "connected": len(wifi_connections) > 0,
            "connections": wifi_connections,
            "ip": current_ip
        }
    except Exception as e:
        logging.error(f"Failed to get WiFi status: {e}")
        return {"connected": False, "error": str(e)}

def connect_to_wifi(ssid, password=None):
    """Connects to a WiFi network."""
    try:
        if password:
            result = run_command(f"nmcli dev wifi connect '{ssid}' password '{password}'")
        else:
            result = run_command(f"nmcli dev wifi connect '{ssid}'")
        
        if result and "successfully activated" in result:
            return {"success": True, "message": f"Connected to {ssid}"}
        else:
            return {"success": False, "message": result or "Connection failed"}
    except Exception as e:
        logging.error(f"Failed to connect to WiFi {ssid}: {e}")
        return {"success": False, "message": str(e)}


def get_device_temperature():
    """Gets the CPU temperature."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read().strip()) / 1000
            return f"{temp:.2f}°C"
    except FileNotFoundError:
        logging.warning("Temperature sensor not found at /sys/class/thermal/thermal_zone0/temp")
        return "N/A"
    except Exception as e:
        logging.error(f"Error reading temperature: {e}")
        return "N/A"

def get_cpu_usage():
    """Gets CPU usage."""
    try:
        return f"{psutil.cpu_percent(interval=1)}%"
    except Exception as e:
        logging.error(f"Error getting CPU usage: {e}")
        return "N/A"

def get_memory_usage():
    """Gets memory usage."""
    try:
        mem = psutil.virtual_memory()
        return f"{mem.percent}%"
    except Exception as e:
        logging.error(f"Error getting memory usage: {e}")
        return "N/A"

def monitor_ffmpeg_output(process):
    """Reads ffmpeg's stderr in a separate thread and parses for stats."""
    global stream_stats
    # FFmpeg outputs progress to stderr
    for line in iter(process.stderr.readline, ''):
        logging.info(f"FFMPEG: {line.strip()}")
        if 'bitrate=' in line:
            bitrate_match = re.search(r'bitrate=\s*(\S+)', line)
            speed_match = re.search(r'speed=\s*(\S+)', line)
            with stats_lock:
                if bitrate_match:
                    stream_stats['bitrate'] = bitrate_match.group(1)
                if speed_match:
                    stream_stats['speed'] = speed_match.group(1)
    process.stderr.close()


# --- Flask Routes ---

@app.route("/")
def index():
    """Renders the main dashboard."""
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    """Returns system status as JSON."""
    global ffmpeg_process
    mediamtx_status = "Running" if run_command(f"pgrep -f {MEDIAMTX_BIN}") else "Stopped"
    
    ffmpeg_running = False
    if ffmpeg_process and ffmpeg_process.poll() is None:
        ffmpeg_running = True
    else:
        with stats_lock:
            stream_stats.clear()

    return jsonify({
        "mediamtx_status": mediamtx_status,
        "ffmpeg_status": "Running" if ffmpeg_running else "Stopped",
        "temperature": get_device_temperature(),
        "cpu_usage": get_cpu_usage(),
        "memory_usage": get_memory_usage(),
    })

@app.route("/api/video/devices")
def video_devices():
    """Returns a list of video devices."""
    return jsonify(get_video_devices())

@app.route("/api/video/capabilities/<path:device_path>")
def device_capabilities(device_path):
    """Returns capabilities for a specific video device."""
    # URL decode the device path
    device_path = "/" + device_path
    capabilities = get_device_capabilities(device_path)
    return jsonify({"device": device_path, "capabilities": capabilities})

@app.route("/api/video/controls/<path:device_path>")
def camera_controls(device_path):
    """Returns available camera controls for a video device."""
    device_path = "/" + device_path
    controls = get_camera_controls(device_path)
    return jsonify({"device": device_path, "controls": controls})

@app.route("/api/video/control/<path:device_path>", methods=["POST"])
def set_camera_control_api(device_path):
    """Sets a camera control value."""
    device_path = "/" + device_path
    data = request.json
    control_name = data.get("control")
    value = data.get("value")
    
    if not control_name or value is None:
        return jsonify({"status": "error", "message": "Missing control name or value"}), 400
    
    success = set_camera_control(device_path, control_name, value)
    if success:
        return jsonify({"status": "ok", "message": f"Set {control_name}={value}"})
    else:
        return jsonify({"status": "error", "message": "Failed to set control"}), 500

@app.route("/api/video/control/<path:device_path>/<control_name>")
def get_camera_control_api(device_path, control_name):
    """Gets current value of a camera control."""
    device_path = "/" + device_path
    value = get_camera_control_value(device_path, control_name)
    if value is not None:
        return jsonify({"control": control_name, "value": value})
    else:
        return jsonify({"status": "error", "message": "Failed to get control value"}), 500

@app.route("/api/stream/start", methods=["POST"])
def stream_start():
    """Generates config, restarts MediaMTX, starts ffmpeg stream."""
    data = request.json
    
    try:
        ffmpeg_cmd = start_stream_internal(data)
        return jsonify({"status": "ok", "command": ffmpeg_cmd})
    except ValueError as e:
        message = str(e)
        logging.error(message)
        return jsonify({"status": "error", "message": message}), 400
    except RuntimeError as e:
        message = str(e)
        logging.error(message)
        return jsonify({"status": "error", "message": message}), 500
    except Exception as e:
        message = f"Unexpected error: {str(e)}"
        logging.error(message)
        return jsonify({"status": "error", "message": message}), 500

@app.route("/api/stream/stop", methods=["POST"])
def stream_stop():
    """Stops the ffmpeg stream."""
    global ffmpeg_process
    if ffmpeg_process and ffmpeg_process.poll() is None:
        logging.info("Stopping ffmpeg process.")
        ffmpeg_process.terminate()
        ffmpeg_process.wait()
        ffmpeg_process = None
        with stats_lock:
            stream_stats.clear()
    else:
        logging.warning("Stop stream called, but no ffmpeg process was running.")
    return jsonify({"status": "ok"})

@app.route("/api/stream/stats")
def stream_stats_api():
    """Returns the latest stream statistics."""
    with stats_lock:
        return jsonify(stream_stats)

@app.route("/api/stream/hls/<stream_name>")
def check_hls_stream(stream_name):
    """Check if HLS stream is available."""
    try:
        import urllib.request
        hls_url = f"http://localhost:8080/{stream_name}/index.m3u8"
        
        # Try to fetch the HLS playlist
        try:
            with urllib.request.urlopen(hls_url, timeout=5) as response:
                content = response.read().decode('utf-8')
                return jsonify({
                    "available": True,
                    "url": hls_url,
                    "content_preview": content[:200] + "..." if len(content) > 200 else content
                })
        except urllib.error.URLError as e:
            return jsonify({
                "available": False,
                "url": hls_url,
                "error": str(e)
            })
    except Exception as e:
        return jsonify({
            "available": False,
            "error": f"Unexpected error: {str(e)}"
        })

@app.route("/api/logs")
def get_logs():
    """Returns the last 100 lines of the log file."""
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            return jsonify({"log": "".join(lines[-100:])})
    except FileNotFoundError:
        return jsonify({"log": "Log file not found."})

@app.route("/api/mediamtx/logs")
def get_mediamtx_logs():
    """Returns MediaMTX service logs."""
    try:
        # Get last 50 lines of MediaMTX logs
        result = run_command("journalctl -u mediamtx -n 50 --no-pager")
        if result:
            return jsonify({"log": result})
        else:
            return jsonify({"log": "No MediaMTX logs found or service not running."})
    except Exception as e:
        return jsonify({"log": f"Error getting MediaMTX logs: {str(e)}"})

@app.route("/api/config/save", methods=["POST"])
def save_config():
    """Saves stream configuration to file."""
    try:
        config = request.json
        config_file = os.path.join(os.path.dirname(__file__), "stream_config.json")
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        logging.info(f"Configuration saved: {config}")
        return jsonify({"status": "ok", "message": "Configuration saved"})
    except Exception as e:
        logging.error(f"Error saving configuration: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/config/load")
def load_config():
    """Loads stream configuration from file."""
    try:
        config_file = os.path.join(os.path.dirname(__file__), "stream_config.json")
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                config = json.load(f)
            return jsonify(config)
        else:
            return jsonify({"message": "No saved configuration found"}), 404
    except Exception as e:
        logging.error(f"Error loading configuration: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/tailscale/status")
def tailscale_status():
    """Returns Tailscale connection status."""
    return jsonify(get_tailscale_status())

@app.route("/api/wifi/status")
def wifi_status():
    """Returns WiFi connection status."""
    return jsonify(get_wifi_status())

@app.route("/api/wifi/scan")
def wifi_scan():
    """Scans for available WiFi networks."""
    networks = scan_wifi_networks()
    return jsonify({"networks": networks})

@app.route("/api/wifi/connect", methods=["POST"])
def wifi_connect():
    """Connects to a WiFi network."""
    data = request.json
    ssid = data.get("ssid")
    password = data.get("password")
    
    if not ssid:
        return jsonify({"success": False, "message": "SSID is required"}), 400
    
    result = connect_to_wifi(ssid, password)
    return jsonify(result)

@app.route("/api/test", methods=["POST"])
def run_tests():
    """Runs a series of system tests."""
    logging.info("--- Starting System Test ---")
    results = []

    # 1. Test MediaMTX executable
    if os.path.isfile(MEDIAMTX_BIN) and os.access(MEDIAMTX_BIN, os.X_OK):
        results.append({"name": "MediaMTX Executable", "status": "pass", "message": f"Found and executable at {MEDIAMTX_BIN}"})
    else:
        results.append({"name": "MediaMTX Executable", "status": "fail", "message": f"Not found or not executable at {MEDIAMTX_BIN}"})

    # 2. Test FFmpeg installation and rkmpp support
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        try:
            output = run_command("ffmpeg -encoders")
            if "rkmpp" in output:
                results.append({"name": "FFmpeg Rockchip Support", "status": "pass", "message": "FFmpeg found with rkmpp encoders."})
            else:
                results.append({"name": "FFmpeg Rockchip Support", "status": "fail", "message": "FFmpeg found, but rkmpp encoders are missing. Re-run setup.sh."})
        except Exception as e:
            results.append({"name": "FFmpeg Rockchip Support", "status": "fail", "message": f"Error running ffmpeg: {e}"})
    else:
        results.append({"name": "FFmpeg Rockchip Support", "status": "fail", "message": "ffmpeg command not found in PATH."})

    # 3. Test for video devices
    if get_video_devices():
        results.append({"name": "Video Device Detection", "status": "pass", "message": "At least one video device was found."})
    else:
        results.append({"name": "Video Device Detection", "status": "fail", "message": "No video devices found by v4l2-ctl."})

    # 4. Test device permissions
    for dev_path in ["/dev/rga", "/dev/mpp_service"]:
        if os.path.exists(dev_path):
            if os.access(dev_path, os.R_OK | os.W_OK):
                results.append({"name": f"Permissions for {dev_path}", "status": "pass", "message": "Read/Write access granted."})
            else:
                results.append({"name": f"Permissions for {dev_path}", "status": "fail", "message": "Access denied. Check udev rules and user groups."})
        else:
            results.append({"name": f"Permissions for {dev_path}", "status": "fail", "message": "Device does not exist."})
    
    logging.info("--- System Test Finished ---")
    return jsonify(results)


def auto_start_stream():
    """Check for saved configuration and auto-start stream if enabled."""
    try:
        config_file = os.path.join(os.path.dirname(__file__), "stream_config.json")
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                config = json.load(f)
            
            # Check if auto-start is enabled
            if config.get("auto_start", False):
                logging.info("Auto-start is enabled, checking configuration...")
                
                # Validate required fields
                required_fields = ["device", "resolution", "framerate", "bitrate", "encoder", "srt_port", "stream_name"]
                if all(config.get(field) for field in required_fields):
                    # Check if the video device still exists
                    device_path = config["device"]
                    if os.path.exists(device_path):
                        logging.info(f"Auto-starting stream with device: {device_path}")
                        
                        # Wait a bit for system to be fully ready
                        time.sleep(5)
                        
                        # Start the stream using the same logic as the API endpoint
                        try:
                            # Prepare stream data
                            stream_data = {
                                "device": config["device"],
                                "resolution": config["resolution"],
                                "framerate": config["framerate"],
                                "bitrate": config["bitrate"],
                                "encoder": config["encoder"],
                                "srt_port": config["srt_port"],
                                "stream_name": config["stream_name"]
                            }
                            
                            # Call the stream start function directly
                            start_stream_internal(stream_data)
                            logging.info("Auto-start completed successfully")
                            
                        except Exception as e:
                            logging.error(f"Auto-start failed: {e}")
                    else:
                        logging.warning(f"Auto-start skipped: saved device {device_path} not found")
                else:
                    logging.warning("Auto-start skipped: incomplete configuration")
            else:
                logging.info("Auto-start is disabled")
        else:
            logging.info("No saved configuration found, skipping auto-start")
    except Exception as e:
        logging.error(f"Error during auto-start check: {e}")

def start_stream_internal(data):
    """Internal function to start stream (used by both API and auto-start)."""
    global ffmpeg_process
    
    if ffmpeg_process and ffmpeg_process.poll() is None:
        logging.warning("An existing ffmpeg process was found and will be terminated.")
        ffmpeg_process.terminate()
        ffmpeg_process.wait()

    device = data.get("device")
    resolution = data.get("resolution")
    framerate = data.get("framerate")
    bitrate = data.get("bitrate")
    encoder = data.get("encoder")
    srt_port = data.get("srt_port", 8888)
    stream_name = data.get("stream_name", "live")

    if not all([device, resolution, framerate, bitrate, encoder, srt_port, stream_name]):
        raise ValueError("Missing one or more required parameters for starting the stream.")

    # 1. Generate MediaMTX config
    mediamtx_config_content = {
        "srt": True,
        "srtAddress": f":{srt_port}",
        "hls": True,
        "hlsAddress": ":8080",
        "hlsEncryption": False,
        "hlsAllowOrigin": "*",
        "hlsVariant": "mpegts",
        "hlsSegmentCount": 3,
        "hlsSegmentDuration": "1s",
        "hlsPartDuration": "200ms",
        "paths": {
            stream_name: {
                "source": "publisher",
                "sourceOnDemand": False
            }
        }
    }
    with open(MEDIAMTX_CONFIG, "w") as f:
        yaml.dump(mediamtx_config_content, f)
    
    # 2. Restart MediaMTX
    logging.info("Restarting MediaMTX service with new configuration.")
    logging.info(f"Generated MediaMTX config: {mediamtx_config_content}")
    restart_result = run_command("sudo systemctl restart mediamtx")
    logging.info(f"MediaMTX restart command result: {restart_result}")
    
    # Check MediaMTX status immediately after restart
    status_result = run_command("sudo systemctl is-active mediamtx")
    logging.info(f"MediaMTX status after restart: {status_result}")
    
    # Also check if HLS port is available
    hls_port_check = run_command("netstat -ln | grep :8080")
    logging.info(f"HLS port 8080 status: {hls_port_check}")
    
    # Wait for MediaMTX to fully start and initialize SRT server
    max_retries = 15
    for i in range(max_retries):
        time.sleep(1)
        
        # Check if MediaMTX process is running
        process_check = run_command(f"pgrep -f {MEDIAMTX_BIN}")
        if process_check:
            logging.info(f"MediaMTX process found: PID {process_check}")
            
            # Check if SRT port is listening
            port_check = run_command(f"netstat -ln | grep :{srt_port}")
            if port_check:
                logging.info(f"MediaMTX SRT server is ready on port {srt_port}")
                break
            else:
                logging.info(f"Waiting for SRT server to bind to port {srt_port}... (attempt {i+1}/{max_retries})")
        else:
            logging.warning(f"MediaMTX process not found, attempt {i+1}/{max_retries}")
            # Get service status for debugging
            service_status = run_command("sudo systemctl status mediamtx --no-pager -l")
            logging.error(f"MediaMTX service status: {service_status}")
    else:
        # Get final logs for debugging
        final_logs = run_command("journalctl -u mediamtx -n 20 --no-pager")
        logging.error(f"MediaMTX failed to start. Recent logs: {final_logs}")
        raise RuntimeError(f"MediaMTX failed to start or SRT server not ready on port {srt_port}")

    # 3. Start FFmpeg
    width, height = resolution.split("x")
    srt_url = f"srt://127.0.0.1:{srt_port}?streamid=publish:{stream_name}"
    
    # Give MediaMTX an extra moment to be fully ready
    time.sleep(1)
    
    # Use camera's native framerate instead of forcing it
    ffmpeg_cmd = (
        f"ffmpeg -f v4l2 -input_format yuyv422 -video_size {width}x{height} "
        f"-i {device} -c:v {encoder} -b:v {bitrate}k -g 20 "
        f"-f mpegts '{srt_url}'"
    )
    logging.info(f"Starting FFmpeg with command: {ffmpeg_cmd}")

    ffmpeg_process = subprocess.Popen(ffmpeg_cmd, shell=True, stderr=subprocess.PIPE, text=True, bufsize=1)
    
    monitor_thread = threading.Thread(target=monitor_ffmpeg_output, args=(ffmpeg_process,))
    monitor_thread.daemon = True
    monitor_thread.start()

    # Wait a moment and check if HLS stream becomes available
    def check_hls_availability():
        time.sleep(3)  # Wait for stream to start
        try:
            import urllib.request
            hls_url = f"http://localhost:8080/{stream_name}/index.m3u8"
            with urllib.request.urlopen(hls_url, timeout=5) as response:
                if response.status == 200:
                    logging.info(f"HLS stream is available at {hls_url}")
                else:
                    logging.warning(f"HLS stream returned status {response.status}")
        except Exception as e:
            logging.warning(f"HLS stream not yet available: {e}")
    
    hls_check_thread = threading.Thread(target=check_hls_availability)
    hls_check_thread.daemon = True
    hls_check_thread.start()

    return ffmpeg_cmd

if __name__ == "__main__":
    # Configure robust logging
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    # Configure file handler with rotation
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10240, backupCount=5)
    file_handler.setLevel(logging.INFO)
    
    # Configure stream handler (for journalctl visibility)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    
    # Create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    
    # Add handlers to the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    
    # Remove Flask's default handlers to avoid duplicate logs in the file
    app.logger.handlers = []
    
    logging.info("Logger configured successfully.")

    try:
        import psutil
    except ImportError:
        logging.critical("psutil is not installed! CPU and Memory usage will not be available.")
        logging.critical("Please run the setup script or install with: pip install psutil")
        # Create dummy functions if psutil is not available
        class DummyPsutil:
            def cpu_percent(self, interval): return "N/A"
            def virtual_memory(self): return type('obj', (object,), {'percent': "N/A"})
        psutil = DummyPsutil()

    # Check for auto-start configuration and start stream if enabled
    auto_start_thread = threading.Thread(target=auto_start_stream)
    auto_start_thread.daemon = True
    auto_start_thread.start()

    app.run(host="0.0.0.0", port=APP_PORT, debug=False) # Disable debug mode for production