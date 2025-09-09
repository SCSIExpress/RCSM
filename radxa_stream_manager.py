# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# RCSM - RockChip Stream Manager
#
# This Python Flask application provides a web interface to manage
# video streaming with hardware acceleration on Radxa and Raspberry Pi devices.
# Supports both rkmpp (Radxa) and h264_v4l2m2m (Raspberry Pi) encoders.
#
# v8: Added Raspberry Pi Zero 2W support with libcamera and hardware acceleration.
#
# Date: December 9, 2024
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

try:
    import psutil
except ImportError:
    logging.warning("psutil not available, system monitoring will be limited")
    # Create dummy psutil for compatibility
    class DummyPsutil:
        def cpu_percent(self, interval=1): return 0
        def virtual_memory(self): return type('obj', (object,), {'percent': 0})
    psutil = DummyPsutil()

from flask import Flask, render_template, jsonify, request

# --- Configuration ---
APP_PORT = 80

# Platform detection
def detect_platform():
    """Detect if running on Radxa or Raspberry Pi"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read().lower()
        
        if 'rockchip' in cpuinfo or 'rk3566' in cpuinfo:
            return 'radxa'
        elif 'raspberry pi' in cpuinfo or 'bcm' in cpuinfo:
            return 'raspberry_pi'
        else:
            # Try to detect by checking for specific hardware
            if os.path.exists('/dev/rga') or os.path.exists('/dev/mpp_service'):
                return 'radxa'
            elif os.path.exists('/dev/vchiq') or os.path.exists('/opt/vc/bin/vcgencmd'):
                return 'raspberry_pi'
    except:
        pass
    
    return 'unknown'

PLATFORM = detect_platform()

# Platform-specific MediaMTX URLs
if PLATFORM == 'raspberry_pi':
    MEDIAMTX_URL = "https://github.com/bluenviron/mediamtx/releases/download/v1.13.1/mediamtx_v1.13.1_linux_armv7.tar.gz"
else:
    MEDIAMTX_URL = "https://github.com/bluenviron/mediamtx/releases/download/v1.13.1/mediamtx_v1.13.1_linux_arm64.tar.gz"

MEDIAMTX_DIR = "/opt/mediamtx"
MEDIAMTX_BIN = os.path.join(MEDIAMTX_DIR, "mediamtx")
MEDIAMTX_CONFIG = os.path.join(MEDIAMTX_DIR, "mediamtx.yml")
LOG_FILE = "/tmp/radxa_stream_manager.log"

# Update Configuration
UPDATE_REPO = "SCSIExpress/RCSM"
UPDATE_BRANCH = "main"  # Change to "develop" for beta updates

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
    
    # Check for libcamera devices (Raspberry Pi CSI camera)
    if PLATFORM == 'raspberry_pi':
        try:
            libcamera_output = run_command("libcamera-hello --list-cameras")
            if libcamera_output and "Available cameras" in libcamera_output:
                # Parse libcamera output
                for line in libcamera_output.splitlines():
                    if ":" in line and ("imx" in line.lower() or "ov" in line.lower() or "camera" in line.lower()):
                        camera_info = line.strip()
                        devices.append({
                            "name": f"CSI Camera ({camera_info})",
                            "path": "libcamera:0",
                            "type": "libcamera"
                        })
                        break
        except Exception as e:
            logging.debug(f"libcamera not available: {e}")
    
    # Check for V4L2 devices
    try:
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
                         devices.append({
                             "name": current_device_name, 
                             "path": line,
                             "type": "v4l2"
                         })
                         current_device_name = None # Reset for next device block
        else:
            logging.warning("`v4l2-ctl --list-devices` produced no output.")
    except Exception as e:
        logging.error(f"Failed to get video devices: {e}")
    
    return devices

def get_device_capabilities(device_path):
    """Gets supported formats, resolutions and framerates for a video device."""
    try:
        # Handle libcamera devices
        if device_path.startswith("libcamera:"):
            try:
                libcamera_output = run_command("libcamera-hello --list-cameras")
                if libcamera_output:
                    return f"Libcamera device capabilities:\n{libcamera_output}"
                else:
                    return "Libcamera device detected but no detailed capabilities available"
            except Exception as e:
                return f"Error getting libcamera capabilities: {str(e)}"
        
        # Handle V4L2 devices
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

def parse_device_options(device_path):
    """Parse device output to extract available resolutions, framerates, and pixel formats."""
    try:
        # Handle libcamera devices
        if device_path.startswith("libcamera:"):
            # Provide common options for libcamera devices
            return {
                "pixel_formats": ["YUV420", "RGB24"],
                "resolutions": ["1920x1080", "1640x1232", "1280x720", "640x480"],
                "framerates": [30, 25, 15, 10]
            }
        
        # Handle V4L2 devices
        formats_output = run_command(f"v4l2-ctl --device={device_path} --list-formats-ext")
        if not formats_output:
            return {"error": "No format information available"}
        
        options = {
            "pixel_formats": [],
            "resolutions": [],
            "framerates": []
        }
        
        current_format = None
        
        for line in formats_output.split('\n'):
            line = line.strip()
            
            # Parse pixel format lines like "[0]: 'YUYV' (YUYV 4:2:2)"
            if line.startswith('[') and ']:' in line and "'" in line:
                format_match = re.search(r"'([^']+)'", line)
                if format_match:
                    current_format = format_match.group(1)
                    if current_format not in options["pixel_formats"]:
                        options["pixel_formats"].append(current_format)
            
            # Parse resolution and framerate lines like "Size: Discrete 1920x1080"
            elif "Size: Discrete" in line:
                size_match = re.search(r'(\d+)x(\d+)', line)
                if size_match:
                    resolution = f"{size_match.group(1)}x{size_match.group(2)}"
                    if resolution not in options["resolutions"]:
                        options["resolutions"].append(resolution)
            
            # Parse framerate lines like "Interval: Discrete 0.033s (30.000 fps)"
            elif "Interval: Discrete" in line and "fps" in line:
                fps_match = re.search(r'\(([0-9.]+)\s+fps\)', line)
                if fps_match:
                    fps = float(fps_match.group(1))
                    fps_int = int(fps) if fps.is_integer() else fps
                    if fps_int not in options["framerates"]:
                        options["framerates"].append(fps_int)
        
        # Sort options for better UX
        options["resolutions"].sort(key=lambda x: int(x.split('x')[0]), reverse=True)  # Sort by width, largest first
        options["framerates"].sort(reverse=True)  # Sort framerates, highest first
        
        # Common pixel format ordering (preferred formats first)
        format_priority = ['YUYV', 'MJPG', 'H264', 'RGB24', 'BGR24', 'YUV420', 'NV12']
        sorted_formats = []
        for fmt in format_priority:
            if fmt in options["pixel_formats"]:
                sorted_formats.append(fmt)
        # Add any remaining formats
        for fmt in options["pixel_formats"]:
            if fmt not in sorted_formats:
                sorted_formats.append(fmt)
        options["pixel_formats"] = sorted_formats
        
        logging.info(f"Parsed options for {device_path}: {options}")
        return options
        
    except Exception as e:
        logging.error(f"Failed to parse device options for {device_path}: {e}")
        return {"error": str(e)}

def get_camera_controls(device_path):
    """Gets available camera controls for a video device."""
    try:
        # Handle libcamera devices
        if device_path.startswith("libcamera:"):
            return "Libcamera controls available through libcamera-still/libcamera-vid commands"
        
        # Handle V4L2 devices
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
        # Handle libcamera devices
        if device_path.startswith("libcamera:"):
            logging.info(f"Libcamera control setting not implemented for {control_name}={value}")
            return False
        
        # Handle V4L2 devices
        result = run_command(f"v4l2-ctl --device={device_path} --set-ctrl={control_name}={value}")
        logging.info(f"Set {control_name}={value} on {device_path}: {result}")
        return True
    except Exception as e:
        logging.error(f"Failed to set camera control {control_name}={value} on {device_path}: {e}")
        return False

def get_camera_control_value(device_path, control_name):
    """Gets current value of a camera control."""
    try:
        # Handle libcamera devices
        if device_path.startswith("libcamera:"):
            return None
        
        # Handle V4L2 devices
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

def connect_to_wifi(ssid, password=None, security_type=None):
    """Connects to a WiFi network with specified security type."""
    try:
        # Build nmcli command based on security type
        if security_type and security_type.lower() == "wep":
            # WEP networks
            if password:
                result = run_command(f"nmcli dev wifi connect '{ssid}' password '{password}' wep-key-type key")
            else:
                return {"success": False, "message": "WEP networks require a password"}
        elif security_type and "wpa" in security_type.lower():
            # WPA/WPA2 networks (default behavior)
            if password:
                result = run_command(f"nmcli dev wifi connect '{ssid}' password '{password}'")
            else:
                return {"success": False, "message": "WPA networks require a password"}
        elif not password or security_type == "Open":
            # Open networks
            result = run_command(f"nmcli dev wifi connect '{ssid}'")
        else:
            # Default case with password
            result = run_command(f"nmcli dev wifi connect '{ssid}' password '{password}'")
        
        if result and "successfully activated" in result:
            return {"success": True, "message": f"Connected to {ssid}"}
        else:
            return {"success": False, "message": result or "Connection failed"}
    except Exception as e:
        logging.error(f"Failed to connect to WiFi {ssid}: {e}")
        return {"success": False, "message": str(e)}

def add_wifi_network(ssid, password=None, security_type="WPA2"):
    """Manually adds a WiFi network configuration."""
    try:
        # Create connection profile
        if security_type.upper() == "OPEN":
            result = run_command(f"nmcli con add type wifi con-name '{ssid}' ifname '*' ssid '{ssid}'")
        elif security_type.upper() == "WEP":
            if not password:
                return {"success": False, "message": "WEP networks require a password"}
            result = run_command(f"nmcli con add type wifi con-name '{ssid}' ifname '*' ssid '{ssid}' wifi-sec.key-mgmt none wifi-sec.wep-key0 '{password}'")
        else:  # WPA/WPA2/WPA3
            if not password:
                return {"success": False, "message": f"{security_type} networks require a password"}
            result = run_command(f"nmcli con add type wifi con-name '{ssid}' ifname '*' ssid '{ssid}' wifi-sec.key-mgmt wpa-psk wifi-sec.psk '{password}'")
        
        if result and ("successfully added" in result or "Connection" in result):
            # Try to activate the connection
            activate_result = run_command(f"nmcli con up '{ssid}'")
            if activate_result and "successfully activated" in activate_result:
                return {"success": True, "message": f"Added and connected to {ssid}"}
            else:
                return {"success": True, "message": f"Added {ssid} but connection failed: {activate_result}"}
        else:
            return {"success": False, "message": result or "Failed to add network"}
    except Exception as e:
        logging.error(f"Failed to add WiFi network {ssid}: {e}")
        return {"success": False, "message": str(e)}

def get_tailscale_auth_url():
    """Initializes Tailscale and returns the authentication URL."""
    try:
        # Check if tailscale is installed
        version_check = run_command("tailscale version")
        if not version_check:
            return {"success": False, "message": "Tailscale is not installed"}
        
        # Run tailscale up to get auth URL
        result = run_command("sudo tailscale up --auth-key= --timeout=30s")
        
        # Parse the output for the auth URL
        if result and "https://login.tailscale.com" in result:
            # Extract the URL from the output
            import re
            url_match = re.search(r'https://login\.tailscale\.com/[^\s]+', result)
            if url_match:
                auth_url = url_match.group(0)
                return {"success": True, "auth_url": auth_url, "message": "Visit the URL to authenticate"}
            else:
                return {"success": False, "message": "Could not extract auth URL from output"}
        else:
            # Try alternative approach - check if already authenticated
            status = get_tailscale_status()
            if status.get("connected"):
                return {"success": True, "message": "Tailscale is already connected", "already_connected": True}
            else:
                return {"success": False, "message": result or "Failed to initialize Tailscale"}
    except Exception as e:
        logging.error(f"Failed to initialize Tailscale: {e}")
        return {"success": False, "message": str(e)}

def reset_tailscale():
    """Resets Tailscale connection to allow switching tailnets."""
    try:
        # Logout from current tailnet
        logout_result = run_command("sudo tailscale logout")
        
        # Reset the state
        reset_result = run_command("sudo tailscale down")
        
        return {"success": True, "message": "Tailscale has been reset. You can now initialize with a new tailnet."}
    except Exception as e:
        logging.error(f"Failed to reset Tailscale: {e}")
        return {"success": False, "message": str(e)}

def check_tailscale_installed():
    """Checks if Tailscale is installed and configured."""
    try:
        version_result = run_command("tailscale version")
        if version_result:
            status = get_tailscale_status()
            return {
                "installed": True,
                "version": version_result.split('\n')[0] if version_result else "Unknown",
                "configured": status.get("connected", False),
                "status": status
            }
        else:
            return {"installed": False, "configured": False}
    except Exception as e:
        logging.error(f"Failed to check Tailscale installation: {e}")
        return {"installed": False, "configured": False, "error": str(e)}


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
        "platform": PLATFORM
    })

@app.route("/api/platform")
def platform_info():
    """Returns platform-specific information."""
    platform_data = {
        "platform": PLATFORM,
        "supported_encoders": [],
        "libcamera_available": False,
        "hardware_acceleration": False
    }
    
    if PLATFORM == 'raspberry_pi':
        platform_data["supported_encoders"] = ["h264_v4l2m2m", "libx264"]
        platform_data["hardware_acceleration"] = True
        
        # Check if libcamera is available
        try:
            libcamera_check = run_command("libcamera-hello --version")
            platform_data["libcamera_available"] = bool(libcamera_check)
        except:
            platform_data["libcamera_available"] = False
            
    elif PLATFORM == 'radxa':
        platform_data["supported_encoders"] = ["h264_rkmpp", "h264_rkmpp_encoder", "libx264"]
        platform_data["hardware_acceleration"] = True
        
    else:
        platform_data["supported_encoders"] = ["libx264", "libx265"]
        platform_data["hardware_acceleration"] = False
    
    return jsonify(platform_data)

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

@app.route("/api/video/options/<path:device_path>")
def device_options(device_path):
    """Returns parsed options (resolutions, framerates, pixel formats) for a specific video device."""
    # URL decode the device path
    device_path = "/" + device_path
    options = parse_device_options(device_path)
    return jsonify({"device": device_path, "options": options})

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
    """Check if HLS stream is available and analyze latency settings."""
    try:
        import urllib.request
        import re
        hls_url = f"http://localhost:8080/{stream_name}/index.m3u8"
        
        # Try to fetch the HLS playlist
        try:
            with urllib.request.urlopen(hls_url, timeout=5) as response:
                content = response.read().decode('utf-8')
                
                # Analyze HLS playlist for latency info
                segment_duration = None
                segment_count = 0
                
                # Extract target duration
                duration_match = re.search(r'#EXT-X-TARGETDURATION:(\d+)', content)
                if duration_match:
                    segment_duration = int(duration_match.group(1))
                
                # Count segments
                segment_count = len(re.findall(r'#EXTINF:', content))
                
                # Calculate estimated latency
                estimated_latency = None
                if segment_duration and segment_count:
                    estimated_latency = segment_duration * segment_count
                
                # Check for low latency features
                has_ll_hls = '#EXT-X-PART:' in content
                has_preload_hint = '#EXT-X-PRELOAD-HINT:' in content
                
                return jsonify({
                    "available": True,
                    "url": hls_url,
                    "content_preview": content[:200] + "..." if len(content) > 200 else content,
                    "latency_info": {
                        "segment_duration": segment_duration,
                        "segment_count": segment_count,
                        "estimated_latency_seconds": estimated_latency,
                        "low_latency_hls": has_ll_hls,
                        "preload_hints": has_preload_hint
                    }
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
            logging.info(f"Configuration loaded: {config}")
            return jsonify(config)
        else:
            return jsonify({"message": "No saved configuration found"}), 404
    except Exception as e:
        logging.error(f"Error loading configuration: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/config/exists")
def config_exists():
    """Checks if a saved configuration exists."""
    try:
        config_file = os.path.join(os.path.dirname(__file__), "stream_config.json")
        exists = os.path.exists(config_file)
        
        if exists:
            # Also check if auto-start is enabled
            with open(config_file, "r") as f:
                config = json.load(f)
            auto_start_enabled = config.get("auto_start", False)
            return jsonify({
                "exists": True, 
                "auto_start_enabled": auto_start_enabled,
                "config_preview": {
                    "device": config.get("device", "N/A"),
                    "resolution": config.get("resolution", "N/A"),
                    "stream_name": config.get("stream_name", "N/A")
                }
            })
        else:
            return jsonify({"exists": False, "auto_start_enabled": False})
    except Exception as e:
        logging.error(f"Error checking configuration: {e}")
        return jsonify({"exists": False, "auto_start_enabled": False, "error": str(e)})

@app.route("/api/config/test-autostart", methods=["POST"])
def test_autostart():
    """Manually trigger auto-start for testing purposes."""
    try:
        logging.info("Manual auto-start test triggered")
        auto_start_thread = threading.Thread(target=auto_start_stream)
        auto_start_thread.daemon = True
        auto_start_thread.start()
        return jsonify({"status": "ok", "message": "Auto-start test initiated, check logs"})
    except Exception as e:
        logging.error(f"Error triggering auto-start test: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/update/test-connection", methods=["GET"])
def test_github_connection():
    """Test connectivity to GitHub for update functionality."""
    try:
        import urllib.request
        
        # Test basic internet connectivity
        try:
            urllib.request.urlopen("https://8.8.8.8", timeout=5)
            internet_ok = True
        except:
            internet_ok = False
        
        # Test GitHub connectivity
        github_ok = False
        github_error = None
        try:
            req = urllib.request.Request("https://api.github.com")
            req.add_header('User-Agent', 'RCSM-Updater/1.0')
            with urllib.request.urlopen(req, timeout=10) as response:
                github_ok = response.status == 200
        except Exception as e:
            github_error = str(e)
        
        # Test specific repository API
        repo_ok = False
        repo_error = None
        try:
            req = urllib.request.Request("https://api.github.com/repos/SCSIExpress/RCSM")
            req.add_header('User-Agent', 'RCSM-Updater/1.0')
            with urllib.request.urlopen(req, timeout=10) as response:
                repo_ok = response.status == 200
        except Exception as e:
            repo_error = str(e)
        
        # Check write permissions
        current_dir = os.path.dirname(os.path.abspath(__file__))
        write_ok = os.access(current_dir, os.W_OK)
        
        return jsonify({
            "internet_connection": internet_ok,
            "github_api": github_ok,
            "github_error": github_error,
            "repository_access": repo_ok,
            "repository_error": repo_error,
            "write_permission": write_ok,
            "current_directory": current_dir,
            "git_available": bool(run_command("git --version"))
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "internet_connection": False,
            "github_api": False,
            "repository_access": False,
            "write_permission": False
        }), 500

@app.route("/api/mediamtx/test-config", methods=["POST"])
def test_mediamtx_config():
    """Test MediaMTX configuration without applying it."""
    try:
        data = request.json or {}
        srt_port = data.get("srt_port", 8888)
        stream_name = data.get("stream_name", "live")
        
        # Create test configuration
        test_config = {
            "srt": True,
            "srtAddress": f":{srt_port}",
            "hls": True,
            "hlsAddress": ":8080",
            "hlsAllowOrigin": "*",
            "paths": {
                stream_name: {
                    "source": "publisher"
                }
            }
        }
        
        # Test the configuration
        is_valid = validate_mediamtx_config(test_config)
        
        # Get MediaMTX version info
        version = get_mediamtx_version()
        
        return jsonify({
            "config_valid": is_valid,
            "mediamtx_version": version,
            "test_config": test_config,
            "mediamtx_binary": MEDIAMTX_BIN,
            "config_file": MEDIAMTX_CONFIG
        })
        
    except Exception as e:
        logging.error(f"Error testing MediaMTX config: {e}")
        return jsonify({
            "config_valid": False,
            "error": str(e)
        }), 500

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
    security_type = data.get("security_type")
    
    if not ssid:
        return jsonify({"success": False, "message": "SSID is required"}), 400
    
    result = connect_to_wifi(ssid, password, security_type)
    return jsonify(result)

@app.route("/api/wifi/add", methods=["POST"])
def wifi_add_network():
    """Manually adds a WiFi network."""
    data = request.json
    ssid = data.get("ssid")
    password = data.get("password")
    security_type = data.get("security_type", "WPA2")
    
    if not ssid:
        return jsonify({"success": False, "message": "SSID is required"}), 400
    
    result = add_wifi_network(ssid, password, security_type)
    return jsonify(result)

@app.route("/api/tailscale/init", methods=["POST"])
def tailscale_init():
    """Initializes Tailscale and returns authentication URL."""
    result = get_tailscale_auth_url()
    return jsonify(result)

@app.route("/api/tailscale/reset", methods=["POST"])
def tailscale_reset():
    """Resets Tailscale to allow switching tailnets."""
    result = reset_tailscale()
    return jsonify(result)

@app.route("/api/tailscale/check")
def tailscale_check():
    """Checks Tailscale installation and configuration status."""
    result = check_tailscale_installed()
    return jsonify(result)


@app.route("/api/version", methods=["GET"])
def get_version():
    """Get current version information."""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Try to get git commit info
        current_commit = None
        commit_date = None
        commit_message = None
        branch_name = None
        git_available = False
        
        try:
            # Check if git is available and we're in a repo
            git_check = run_command("git rev-parse --is-inside-work-tree")
            if git_check and "true" in git_check.lower():
                git_available = True
                
                # Get commit info
                current_commit = run_command("git rev-parse HEAD")
                if current_commit and len(current_commit) >= 7:
                    current_commit = current_commit[:7]  # Short hash
                
                # Get commit date
                commit_date = run_command("git log -1 --format=%cd --date=short")
                
                # Get commit message
                commit_message = run_command("git log -1 --format=%s")
                
                # Get branch name
                branch_name = run_command("git rev-parse --abbrev-ref HEAD")
                
        except Exception as e:
            logging.debug(f"Git info not available: {e}")
        
        # Get file modification time as fallback
        file_mtime = None
        try:
            script_path = os.path.abspath(__file__)
            mtime = os.path.getmtime(script_path)
            file_mtime = time.strftime('%Y-%m-%d', time.localtime(mtime))
        except:
            pass
        
        return jsonify({
            "commit": current_commit or "Unknown",
            "date": commit_date or file_mtime or "Unknown",
            "message": commit_message or "Unknown",
            "branch": branch_name or "Unknown",
            "git_available": git_available,
            "repository": "https://github.com/SCSIExpress/RCSM",
            "file_modified": file_mtime
        })
        
    except Exception as e:
        return jsonify({
            "commit": "Unknown",
            "date": "Unknown",
            "message": "Unknown",
            "branch": "Unknown", 
            "git_available": False,
            "repository": "https://github.com/SCSIExpress/RCSM",
            "error": str(e)
        })


@app.route("/api/update", methods=["POST"])
def check_and_update():
    """Check for updates from GitHub and update the application."""
    try:
        import tempfile
        import shutil
        import urllib.request
        import zipfile
        import time
        
        # GitHub repository information (using configuration)
        repo_url = f"https://github.com/{UPDATE_REPO}"
        api_url = f"https://api.github.com/repos/{UPDATE_REPO}/commits/{UPDATE_BRANCH}"
        download_url = f"https://github.com/{UPDATE_REPO}/archive/refs/heads/{UPDATE_BRANCH}.zip"
        
        # Get current directory and check write permissions
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if not os.access(current_dir, os.W_OK):
            return jsonify({
                "status": "error",
                "message": f"No write permission to directory: {current_dir}"
            }), 500
        
        # Test internet connectivity
        try:
            urllib.request.urlopen("https://api.github.com", timeout=5)
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"No internet connection or GitHub is unreachable: {str(e)}"
            }), 500
        
        # Check if we're in a git repository to get current commit
        current_commit = None
        git_available = False
        try:
            current_commit = run_command("git rev-parse HEAD")
            if current_commit and len(current_commit) >= 7:
                current_commit = current_commit[:7]  # Short hash
                git_available = True
                logging.info(f"Current git commit: {current_commit}")
        except:
            logging.info("Not in a git repository or git not available, proceeding with update")
        
        # Get latest commit from GitHub API
        try:
            # Add User-Agent header to avoid GitHub API issues
            req = urllib.request.Request(api_url)
            req.add_header('User-Agent', 'RCSM-Updater/1.0')
            
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status != 200:
                    return jsonify({
                        "status": "error",
                        "message": f"GitHub API returned status {response.status}"
                    }), 500
                
                import json
                data = json.loads(response.read().decode())
                latest_commit = data['sha'][:7]  # Short hash
                commit_message = data['commit']['message'].split('\n')[0]  # First line only
                commit_date = data['commit']['author']['date']
                
                logging.info(f"Latest GitHub commit: {latest_commit}")
                
        except urllib.error.HTTPError as e:
            if e.code == 403:
                return jsonify({
                    "status": "error",
                    "message": "GitHub API rate limit exceeded. Please try again later."
                }), 500
            else:
                return jsonify({
                    "status": "error", 
                    "message": f"GitHub API error {e.code}: {str(e)}"
                }), 500
        except Exception as e:
            return jsonify({
                "status": "error", 
                "message": f"Failed to check for updates: {str(e)}"
            }), 500
        
        # Compare commits if we have current commit info
        if git_available and current_commit and current_commit == latest_commit:
            return jsonify({
                "status": "up_to_date",
                "message": "Application is already up to date",
                "current_commit": current_commit,
                "latest_commit": latest_commit,
                "commit_message": commit_message,
                "commit_date": commit_date
            })
        
        # If not in git repo, warn user but proceed
        if not git_available:
            logging.warning("Cannot verify current version - not in git repository")
        
        # Download and extract update
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "update.zip")
            
            # Download the latest version with progress logging
            logging.info(f"Downloading update from {download_url}")
            try:
                req = urllib.request.Request(download_url)
                req.add_header('User-Agent', 'RCSM-Updater/1.0')
                
                with urllib.request.urlopen(req, timeout=60) as response:
                    if response.status != 200:
                        return jsonify({
                            "status": "error",
                            "message": f"Failed to download update: HTTP {response.status}"
                        }), 500
                    
                    # Get file size for progress tracking
                    file_size = response.headers.get('Content-Length')
                    if file_size:
                        file_size = int(file_size)
                        logging.info(f"Downloading {file_size} bytes")
                    
                    with open(zip_path, 'wb') as f:
                        shutil.copyfileobj(response, f)
                        
            except Exception as e:
                return jsonify({
                    "status": "error",
                    "message": f"Failed to download update: {str(e)}"
                }), 500
            
            # Verify and extract the zip file
            if not os.path.exists(zip_path) or os.path.getsize(zip_path) == 0:
                return jsonify({
                    "status": "error",
                    "message": "Downloaded file is empty or corrupted"
                }), 500
            
            extract_dir = os.path.join(temp_dir, "extracted")
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # Test the zip file integrity
                    bad_file = zip_ref.testzip()
                    if bad_file:
                        return jsonify({
                            "status": "error",
                            "message": f"Corrupted file in archive: {bad_file}"
                        }), 500
                    
                    zip_ref.extractall(extract_dir)
                    logging.info(f"Extracted archive to {extract_dir}")
                    
            except zipfile.BadZipFile:
                return jsonify({
                    "status": "error",
                    "message": "Downloaded file is not a valid zip archive"
                }), 500
            
            # Find the extracted folder (should be RCSM-main)
            extracted_folders = [d for d in os.listdir(extract_dir) if os.path.isdir(os.path.join(extract_dir, d))]
            if not extracted_folders:
                return jsonify({
                    "status": "error",
                    "message": "No folders found in downloaded archive"
                }), 500
            
            source_dir = os.path.join(extract_dir, extracted_folders[0])
            logging.info(f"Source directory: {source_dir}")
            
            # Backup current files
            backup_dir = os.path.join(current_dir, f"backup_{int(time.time())}")
            try:
                os.makedirs(backup_dir, exist_ok=True)
                logging.info(f"Created backup directory: {backup_dir}")
            except Exception as e:
                return jsonify({
                    "status": "error",
                    "message": f"Failed to create backup directory: {str(e)}"
                }), 500
            
            # Files to update - check if they exist in source first
            files_to_update = [
                "radxa_stream_manager.py",
                "templates/index.html", 
                "setup.sh",
                "README.md",
                "CHANGELOG.md",
                "API.md",
                "INSTALLATION.md",
                "TROUBLESHOOTING.md",
                "CONTRIBUTING.md"
            ]
            
            # Verify source files exist before starting update
            available_files = []
            for file_path in files_to_update:
                source_file = os.path.join(source_dir, file_path)
                if os.path.exists(source_file):
                    available_files.append(file_path)
                else:
                    logging.warning(f"Source file not found: {file_path}")
            
            if not available_files:
                return jsonify({
                    "status": "error",
                    "message": "No updatable files found in the downloaded archive"
                }), 500
            
            # Perform the update
            updated_files = []
            failed_files = []
            
            for file_path in available_files:
                try:
                    source_file = os.path.join(source_dir, file_path)
                    dest_file = os.path.join(current_dir, file_path)
                    backup_file = os.path.join(backup_dir, file_path)
                    
                    # Create backup directory structure
                    backup_parent = os.path.dirname(backup_file)
                    if backup_parent:
                        os.makedirs(backup_parent, exist_ok=True)
                    
                    # Backup current file if it exists
                    if os.path.exists(dest_file):
                        shutil.copy2(dest_file, backup_file)
                        logging.info(f"Backed up: {file_path}")
                    
                    # Create destination directory if needed
                    dest_parent = os.path.dirname(dest_file)
                    if dest_parent:
                        os.makedirs(dest_parent, exist_ok=True)
                    
                    # Copy new file
                    shutil.copy2(source_file, dest_file)
                    updated_files.append(file_path)
                    logging.info(f"Updated file: {file_path}")
                    
                except Exception as e:
                    failed_files.append(f"{file_path}: {str(e)}")
                    logging.error(f"Failed to update {file_path}: {e}")
            
            if failed_files:
                logging.warning(f"Some files failed to update: {failed_files}")
            
            if not updated_files:
                return jsonify({
                    "status": "error",
                    "message": f"No files were updated. Errors: {'; '.join(failed_files)}"
                }), 500
        
        # Try to restart the service - check multiple possible service names
        restart_attempted = False
        service_names = ["radxa-stream-manager", "rcsm", "radxa_stream_manager"]
        
        for service_name in service_names:
            try:
                service_status = run_command(f"systemctl is-active {service_name}")
                if service_status and "active" in service_status:
                    logging.info(f"Found active service: {service_name}")
                    restart_result = run_command(f"sudo systemctl restart {service_name}")
                    logging.info(f"Service restart result: {restart_result}")
                    restart_attempted = True
                    break
            except Exception as e:
                logging.debug(f"Service {service_name} not found or not active: {e}")
                continue
        
        if not restart_attempted:
            logging.info("No active systemd service found for auto-restart")
        
        # Prepare response
        response_data = {
            "status": "success",
            "message": f"Successfully updated {len(updated_files)} files",
            "updated_files": updated_files,
            "backup_location": backup_dir,
            "latest_commit": latest_commit,
            "commit_message": commit_message,
            "commit_date": commit_date,
            "restart_attempted": restart_attempted,
            "restart_note": "Please manually restart the application if not running as a service"
        }
        
        # Add warnings if any files failed
        if failed_files:
            response_data["warnings"] = failed_files
            response_data["message"] += f" (with {len(failed_files)} warnings)"
        
        # Add current commit info if available
        if git_available and current_commit:
            response_data["previous_commit"] = current_commit
        
        return jsonify(response_data)
        
    except Exception as e:
        logging.error(f"Update failed: {e}")
        return jsonify({
            "status": "error",
            "message": f"Update failed: {str(e)}"
        }), 500


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

    # 2. Platform-specific FFmpeg tests
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        try:
            output = run_command("ffmpeg -encoders")
            
            if PLATFORM == 'radxa':
                if "rkmpp" in output:
                    results.append({"name": "FFmpeg Rockchip Support", "status": "pass", "message": "FFmpeg found with rkmpp encoders."})
                else:
                    results.append({"name": "FFmpeg Rockchip Support", "status": "fail", "message": "FFmpeg found, but rkmpp encoders are missing. Re-run setup.sh."})
            elif PLATFORM == 'raspberry_pi':
                if "h264_v4l2m2m" in output:
                    results.append({"name": "FFmpeg Raspberry Pi Support", "status": "pass", "message": "FFmpeg found with h264_v4l2m2m encoder."})
                else:
                    results.append({"name": "FFmpeg Raspberry Pi Support", "status": "fail", "message": "FFmpeg found, but h264_v4l2m2m encoder is missing."})
            else:
                results.append({"name": "FFmpeg Support", "status": "pass", "message": "FFmpeg found with software encoders."})
                
        except Exception as e:
            results.append({"name": "FFmpeg Support", "status": "fail", "message": f"Error running ffmpeg: {e}"})
    else:
        results.append({"name": "FFmpeg Support", "status": "fail", "message": "ffmpeg command not found in PATH."})

    # 3. Test for video devices
    devices = get_video_devices()
    if devices:
        device_names = [d.get('name', 'Unknown') for d in devices]
        results.append({"name": "Video Device Detection", "status": "pass", "message": f"Found devices: {', '.join(device_names)}"})
    else:
        results.append({"name": "Video Device Detection", "status": "fail", "message": "No video devices found."})

    # 4. Platform-specific device permission tests
    if PLATFORM == 'radxa':
        for dev_path in ["/dev/rga", "/dev/mpp_service"]:
            if os.path.exists(dev_path):
                if os.access(dev_path, os.R_OK | os.W_OK):
                    results.append({"name": f"Permissions for {dev_path}", "status": "pass", "message": "Read/Write access granted."})
                else:
                    results.append({"name": f"Permissions for {dev_path}", "status": "fail", "message": "Access denied. Check udev rules and user groups."})
            else:
                results.append({"name": f"Permissions for {dev_path}", "status": "fail", "message": "Device does not exist."})
    elif PLATFORM == 'raspberry_pi':
        # Test libcamera availability
        try:
            libcamera_output = run_command("libcamera-hello --version")
            if libcamera_output:
                results.append({"name": "Libcamera Support", "status": "pass", "message": "libcamera tools are available."})
            else:
                results.append({"name": "Libcamera Support", "status": "fail", "message": "libcamera tools not found."})
        except Exception as e:
            results.append({"name": "Libcamera Support", "status": "fail", "message": f"Error checking libcamera: {e}"})
        
        # Test GPU memory split
        try:
            gpu_mem = run_command("vcgencmd get_mem gpu")
            if gpu_mem and "gpu=" in gpu_mem:
                mem_value = int(gpu_mem.split("=")[1].replace("M", ""))
                if mem_value >= 64:
                    results.append({"name": "GPU Memory", "status": "pass", "message": f"GPU memory: {mem_value}M (sufficient for hardware encoding)"})
                else:
                    results.append({"name": "GPU Memory", "status": "fail", "message": f"GPU memory: {mem_value}M (recommend 128M+ for hardware encoding)"})
            else:
                results.append({"name": "GPU Memory", "status": "fail", "message": "Could not determine GPU memory allocation"})
        except Exception as e:
            results.append({"name": "GPU Memory", "status": "fail", "message": f"Error checking GPU memory: {e}"})
    
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
                        
                        # Wait for system to be fully ready (longer delay for auto-start)
                        logging.info("Waiting 10 seconds for system to be ready...")
                        time.sleep(10)
                        
                        # Start the stream using the same logic as the API endpoint
                        try:
                            # Prepare stream data
                            stream_data = {
                                "device": config["device"],
                                "pixel_format": config.get("pixel_format", "YUYV"),  # Default to YUYV if not specified
                                "resolution": config["resolution"],
                                "framerate": config["framerate"],
                                "bitrate": config["bitrate"],
                                "encoder": config["encoder"],
                                "srt_port": config["srt_port"],
                                "stream_name": config["stream_name"]
                            }
                            
                            logging.info(f"Auto-start stream data: {stream_data}")
                            
                            # Call the stream start function directly
                            ffmpeg_cmd = start_stream_internal(stream_data)
                            logging.info(f"Auto-start completed successfully with command: {ffmpeg_cmd}")
                            
                        except ValueError as e:
                            logging.error(f"Auto-start failed - invalid configuration: {e}")
                        except RuntimeError as e:
                            logging.error(f"Auto-start failed - runtime error: {e}")
                        except Exception as e:
                            logging.error(f"Auto-start failed - unexpected error: {e}")
                            import traceback
                            logging.error(f"Auto-start traceback: {traceback.format_exc()}")
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

def get_mediamtx_version():
    """Get MediaMTX version to determine supported features."""
    try:
        version_output = run_command(f"{MEDIAMTX_BIN} --version")
        if version_output:
            logging.info(f"MediaMTX version: {version_output}")
            return version_output
        return None
    except Exception as e:
        logging.warning(f"Could not determine MediaMTX version: {e}")
        return None

def validate_mediamtx_config(config_content):
    """Validate MediaMTX configuration by testing it."""
    try:
        # Create a temporary config file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as temp_config:
            yaml.dump(config_content, temp_config)
            temp_config_path = temp_config.name
        
        # Test the configuration
        test_result = run_command(f"{MEDIAMTX_BIN} --conf {temp_config_path} --check")
        
        # Clean up temp file
        os.unlink(temp_config_path)
        
        if test_result is not None:
            logging.info("MediaMTX configuration validation passed")
            return True
        else:
            logging.warning("MediaMTX configuration validation failed")
            return False
            
    except Exception as e:
        logging.error(f"Error validating MediaMTX configuration: {e}")
        return False

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
    pixel_format = data.get("pixel_format", "yuyv422")  # Default to YUYV
    srt_port = data.get("srt_port", 8888)
    stream_name = data.get("stream_name", "live")

    if not all([device, resolution, framerate, bitrate, encoder, srt_port, stream_name]):
        raise ValueError("Missing one or more required parameters for starting the stream.")
    
    # Check MediaMTX version for feature compatibility
    mediamtx_version = get_mediamtx_version()

    # 1. Generate MediaMTX config with version-appropriate settings
    mediamtx_config_content = {
        "srt": True,
        "srtAddress": f":{srt_port}",
        "hls": True,
        "hlsAddress": ":8080",
        "hlsEncryption": False,
        "hlsAllowOrigin": "*",
        "hlsVariant": "mpegts",         # Standard variant for broad compatibility
        "hlsSegmentCount": 3,           # Safe default for compatibility
        "hlsSegmentDuration": "2s",     # Conservative duration to ensure stability
        "paths": {
            stream_name: {
                "source": "publisher",
                "sourceOnDemand": False
            }
        }
    }
    
    # Try to optimize for lower latency if MediaMTX version supports it
    if mediamtx_version:
        try:
            # For newer versions, try shorter segments
            mediamtx_config_content["hlsSegmentCount"] = 2
            mediamtx_config_content["hlsSegmentDuration"] = "1s"
            logging.info("Using optimized HLS settings for detected MediaMTX version")
        except:
            logging.info("Using conservative HLS settings for compatibility")
    else:
        logging.info("MediaMTX version unknown, using conservative HLS settings")
    # Validate configuration before applying
    if not validate_mediamtx_config(mediamtx_config_content):
        logging.warning("Configuration validation failed, using minimal safe config")
        # Fallback to minimal configuration
        mediamtx_config_content = {
            "srt": True,
            "srtAddress": f":{srt_port}",
            "hls": True,
            "hlsAddress": ":8080",
            "hlsAllowOrigin": "*",
            "paths": {
                stream_name: {
                    "source": "publisher"
                }
            }
        }
    
    # Write configuration file with error handling
    try:
        with open(MEDIAMTX_CONFIG, "w") as f:
            yaml.dump(mediamtx_config_content, f)
        logging.info(f"MediaMTX config written to {MEDIAMTX_CONFIG}")
        logging.info(f"Config content: {mediamtx_config_content}")
    except Exception as e:
        raise RuntimeError(f"Failed to write MediaMTX configuration: {e}")
    
    # 2. Restart MediaMTX with better error handling
    logging.info("Restarting MediaMTX service with new configuration.")
    
    # Stop MediaMTX first
    stop_result = run_command("sudo systemctl stop mediamtx")
    logging.info(f"MediaMTX stop result: {stop_result}")
    time.sleep(2)  # Give it time to stop
    
    # Start MediaMTX
    start_result = run_command("sudo systemctl start mediamtx")
    logging.info(f"MediaMTX start result: {start_result}")
    
    # Check for startup errors
    time.sleep(3)  # Give MediaMTX time to start
    status_result = run_command("sudo systemctl is-active mediamtx")
    logging.info(f"MediaMTX status after restart: {status_result}")
    
    if not status_result or "active" not in status_result:
        # Get detailed error information
        error_logs = run_command("sudo journalctl -u mediamtx -n 10 --no-pager")
        logging.error(f"MediaMTX failed to start. Recent logs: {error_logs}")
        raise RuntimeError(f"MediaMTX service failed to start. Status: {status_result}")
    
    # Check if HLS port is available
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

    # 3. Start FFmpeg - Platform-specific command generation
    width, height = resolution.split("x")
    srt_url = f"srt://127.0.0.1:{srt_port}?streamid=publish:{stream_name}"
    
    # Give MediaMTX an extra moment to be fully ready
    time.sleep(1)
    
    # Build FFmpeg command based on platform and device type
    if device.startswith("libcamera:"):
        # Raspberry Pi libcamera input
        camera_index = device.split(":")[1] if ":" in device else "0"
        
        # Use h264_v4l2m2m encoder for Raspberry Pi hardware acceleration
        if encoder in ["h264_rkmpp", "h264_rkmpp_encoder"]:
            encoder = "h264_v4l2m2m"  # Use Pi's hardware encoder
        
        ffmpeg_cmd = (
            f"libcamera-vid --codec yuv420 --width {width} --height {height} "
            f"--framerate {framerate} --timeout 0 --inline --listen -o - | "
            f"ffmpeg -f rawvideo -pix_fmt yuv420p -s {width}x{height} "
            f"-framerate {framerate} -i - "
            f"-c:v {encoder} -b:v {bitrate}k "
            f"-g {int(framerate)} -keyint_min {int(framerate)} "
            f"-preset ultrafast -tune zerolatency "
            f"-bufsize {int(bitrate)*2}k -maxrate {int(bitrate)*1.2}k "
            f"-f mpegts '{srt_url}'"
        )
    else:
        # V4L2 device input (USB cameras, etc.)
        # Map pixel format names to FFmpeg input formats
        pixel_format_map = {
            'YUYV': 'yuyv422',
            'MJPG': 'mjpeg',
            'H264': 'h264',
            'RGB24': 'rgb24',
            'BGR24': 'bgr24',
            'YUV420': 'yuv420p',
            'NV12': 'nv12'
        }
        
        # Get FFmpeg input format, default to yuyv422 if not found
        input_format = pixel_format_map.get(pixel_format.upper(), pixel_format.lower())
        
        # Platform-specific encoder selection
        if PLATFORM == 'raspberry_pi':
            if encoder in ["h264_rkmpp", "h264_rkmpp_encoder"]:
                encoder = "h264_v4l2m2m"  # Use Pi's hardware encoder
        
        # Build FFmpeg command based on pixel format
        if pixel_format.upper() == 'MJPG':
            # For MJPEG input, we don't need input_format parameter
            ffmpeg_cmd = (
                f"ffmpeg -f v4l2 -video_size {width}x{height} "
                f"-framerate {framerate} -i {device} "
                f"-c:v {encoder} -b:v {bitrate}k "
                f"-g {int(framerate)} -keyint_min {int(framerate)} "
                f"-sc_threshold 0 -force_key_frames 'expr:gte(t,n_forced*1)' "
                f"-preset ultrafast -tune zerolatency "
                f"-bufsize {int(bitrate)*2}k -maxrate {int(bitrate)*1.2}k "
                f"-f mpegts '{srt_url}'"
            )
        else:
            # For other formats, specify input format
            ffmpeg_cmd = (
                f"ffmpeg -f v4l2 -input_format {input_format} -video_size {width}x{height} "
                f"-framerate {framerate} -i {device} "
                f"-c:v {encoder} -b:v {bitrate}k "
                f"-g {int(framerate)} -keyint_min {int(framerate)} "
                f"-sc_threshold 0 -force_key_frames 'expr:gte(t,n_forced*1)' "
                f"-preset ultrafast -tune zerolatency "
                f"-bufsize {int(bitrate)*2}k -maxrate {int(bitrate)*1.2}k "
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

    # psutil is now imported at the top of the file

    # Check for auto-start configuration and start stream if enabled
    auto_start_thread = threading.Thread(target=auto_start_stream)
    auto_start_thread.daemon = True
    auto_start_thread.start()

    app.run(host="0.0.0.0", port=APP_PORT, debug=False) # Disable debug mode for production