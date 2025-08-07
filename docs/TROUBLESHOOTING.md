# Troubleshooting Guide

This guide helps you resolve common issues with RCSM (Radxa Camera Stream Manager).

## Quick Diagnostics

Run these commands to gather system information:

```bash
# System info
uname -a
python3 --version
gst-launch-1.0 --version

# Camera detection
ls -l /dev/video*
v4l2-ctl --list-devices

# Network
ip addr show
netstat -tlnp | grep :5000

# Process check
ps aux | grep python
```

## Common Issues and Solutions

### 1. Application Won't Start

#### Symptom
```
python3 radxa_stream_manager.py
ModuleNotFoundError: No module named 'flask'
```

#### Solution
```bash
# Install Flask
pip3 install flask

# Or use system package manager
sudo apt install python3-flask -y
```

#### Alternative Solutions
- Check Python version: `python3 --version` (needs 3.6+)
- Use virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install flask
```

### 2. Camera Not Detected

#### Symptom
- No `/dev/video*` devices
- "Camera not found" error in web interface

#### Diagnosis
```bash
# Check USB devices
lsusb

# Check video devices
ls -l /dev/video*

# Check kernel modules
lsmod | grep uvc
```

#### Solutions

**For USB Cameras:**
```bash
# Load USB video driver
sudo modprobe uvcvideo

# Make permanent
echo 'uvcvideo' | sudo tee -a /etc/modules
```

**For CSI Cameras:**
```bash
# Enable camera interface (Raspberry Pi style)
sudo raspi-config
# Navigate to Interface Options > Camera > Enable

# Or edit config directly
sudo nano /boot/config.txt
# Add: start_x=1
# Add: gpu_mem=128
```

**Permission Issues:**
```bash
# Add user to video group
sudo usermod -a -G video $USER

# Fix device permissions
sudo chmod 666 /dev/video*

# Logout and login again
```

### 3. Stream Won't Start

#### Symptom
- "Failed to start stream" error
- Stream status shows "error"

#### Diagnosis
```bash
# Test GStreamer directly
gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! autovideosink

# Check if camera is in use
sudo lsof /dev/video0
```

#### Solutions

**Camera in Use:**
```bash
# Find and kill processes using camera
sudo lsof /dev/video0
sudo kill -9 <PID>
```

**GStreamer Issues:**
```bash
# Reinstall GStreamer
sudo apt remove --purge gstreamer1.0-*
sudo apt update
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav -y
```

**Wrong Camera Device:**
```bash
# List all video devices
v4l2-ctl --list-devices

# Test different devices
gst-launch-1.0 v4l2src device=/dev/video1 ! videoconvert ! autovideosink
```

### 4. Web Interface Not Accessible

#### Symptom
- Browser shows "This site can't be reached"
- Connection timeout errors

#### Diagnosis
```bash
# Check if application is running
ps aux | grep python

# Check if port is listening
netstat -tlnp | grep :5000

# Check firewall
sudo ufw status
```

#### Solutions

**Application Not Running:**
```bash
# Start application
cd RCSM
python3 radxa_stream_manager.py

# Check for errors in output
```

**Firewall Blocking:**
```bash
# Allow port 5000
sudo ufw allow 5000

# Or disable firewall temporarily
sudo ufw disable
```

**Network Issues:**
```bash
# Find your IP address
ip addr show

# Try localhost first
curl http://localhost:5000

# Then try network IP
curl http://192.168.1.100:5000
```

### 5. Poor Stream Quality

#### Symptom
- Choppy video
- Low frame rate
- High latency

#### Solutions

**Optimize GStreamer Pipeline:**
Edit `radxa_stream_manager.py` and modify the stream command:

```python
# For better performance
stream_command = [
    'gst-launch-1.0',
    'v4l2src', 'device=/dev/video0',
    '!', 'video/x-raw,width=1280,height=720,framerate=30/1',
    '!', 'videoconvert',
    '!', 'x264enc', 'tune=zerolatency', 'bitrate=2000',
    '!', 'rtph264pay',
    '!', 'udpsink', 'host=0.0.0.0', 'port=5000'
]
```

**System Optimization:**
```bash
# Increase GPU memory
sudo nano /boot/config.txt
# Add: gpu_mem=128

# Reduce system load
sudo systemctl stop unnecessary-service
```

### 6. Permission Errors

#### Symptom
```
PermissionError: [Errno 13] Permission denied: '/dev/video0'
```

#### Solutions
```bash
# Add user to video group
sudo usermod -a -G video $USER

# Change device permissions
sudo chmod 666 /dev/video*

# Create udev rule for permanent fix
sudo nano /etc/udev/rules.d/99-camera.rules
# Add: SUBSYSTEM=="video4linux", GROUP="video", MODE="0664"

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 7. High CPU Usage

#### Symptom
- System becomes slow
- High CPU usage from GStreamer process

#### Solutions

**Reduce Stream Quality:**
```python
# Lower resolution and frame rate
'!', 'video/x-raw,width=640,height=480,framerate=15/1',
```

**Use Hardware Acceleration:**
```python
# If available on your Radxa device
'!', 'v4l2h264enc',  # Instead of x264enc
```

**Optimize System:**
```bash
# Set CPU governor to performance
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

### 8. Memory Issues

#### Symptom
- "Out of memory" errors
- System freezing

#### Solutions
```bash
# Increase swap space
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Increase GPU memory split
sudo nano /boot/config.txt
# Add: gpu_mem=64
```

## Advanced Troubleshooting

### Enable Debug Logging

Add debug logging to `radxa_stream_manager.py`:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Add to Flask app
app.logger.setLevel(logging.DEBUG)
```

### GStreamer Debug

```bash
# Set debug level
export GST_DEBUG=3

# Run with debug output
GST_DEBUG=3 python3 radxa_stream_manager.py
```

### Network Debugging

```bash
# Check network connectivity
ping 8.8.8.8

# Check DNS resolution
nslookup google.com

# Monitor network traffic
sudo tcpdump -i any port 5000
```

## System-Specific Issues

### Radxa Rock 5B

**Issue:** Camera not detected after boot
**Solution:**
```bash
# Add to /etc/rc.local
modprobe uvcvideo
chmod 666 /dev/video*
```

### Radxa Rock 4

**Issue:** GStreamer crashes with hardware acceleration
**Solution:**
```bash
# Disable hardware acceleration
# Use software encoding only
```

### Ubuntu/Debian Issues

**Issue:** Snap version conflicts
**Solution:**
```bash
# Remove snap packages
sudo snap remove gstreamer

# Install from apt
sudo apt install gstreamer1.0-tools
```

## Getting More Help

### Log Collection

When reporting issues, include:

```bash
# System logs
sudo journalctl -u rcsm -n 50

# Application logs
tail -f /var/log/rcsm.log

# System information
uname -a > system_info.txt
lsusb >> system_info.txt
v4l2-ctl --list-devices >> system_info.txt
```

### Creating Bug Reports

Include this information:

1. **System Details:**
   - Radxa model
   - OS version
   - Python version
   - GStreamer version

2. **Error Messages:**
   - Complete error output
   - Browser console errors
   - System logs

3. **Steps to Reproduce:**
   - What you were trying to do
   - What happened instead
   - What you expected to happen

4. **Configuration:**
   - Camera model
   - Network setup
   - Any modifications made

### Community Resources

- [GitHub Issues](https://github.com/SCSIExpress/RCSM/issues)
- [Radxa Community Forum](https://forum.radxa.com)
- [GStreamer Documentation](https://gstreamer.freedesktop.org/documentation/)

## Prevention Tips

1. **Regular Updates:**
```bash
sudo apt update && sudo apt upgrade -y
```

2. **Monitor Resources:**
```bash
htop  # Monitor CPU/memory usage
```

3. **Backup Configuration:**
```bash
cp radxa_stream_manager.py radxa_stream_manager.py.backup
```

4. **Test After Changes:**
Always test the web interface after making system changes.

5. **Use Version Control:**
```bash
git status  # Check for uncommitted changes
git commit -am "Working configuration"
```