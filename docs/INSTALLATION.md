# Installation Guide

This guide provides detailed installation instructions for RCSM on various Radxa devices and Linux distributions.

## System Requirements

### Hardware Requirements
- Radxa single-board computer (Rock 5B, Rock 4, Rock 3, etc.)
- USB camera or CSI camera module
- MicroSD card (16GB+ recommended)
- Network connection (Ethernet or WiFi)

### Software Requirements
- Linux-based OS (Ubuntu, Debian, Armbian, etc.)
- Python 3.6 or higher
- GStreamer 1.0 or higher
- Internet connection for initial setup

## Quick Installation

### Method 1: One-Command Install (Recommended)

Install RCSM with a single command that downloads everything automatically:

```bash
curl -fsSL https://raw.githubusercontent.com/SCSIExpress/RCSM/main/setup.sh | sudo bash
```

Or using wget:
```bash
wget -qO- https://raw.githubusercontent.com/SCSIExpress/RCSM/main/setup.sh | sudo bash
```

That's it! The script will:
- Install all dependencies
- Download the latest application files from GitHub
- Set up services automatically
- Start the web interface

### Method 2: Manual Repository Clone

If you prefer to clone the repository first:

```bash
git clone https://github.com/SCSIExpress/RCSM.git
cd RCSM
chmod +x setup.sh
sudo ./setup.sh
```

### Method 2: Manual Installation

If the automated setup doesn't work for your system, follow these manual steps:

1. **Update system packages:**
```bash
sudo apt update && sudo apt upgrade -y
```

2. **Install Python and pip:**
```bash
sudo apt install python3 python3-pip -y
```

3. **Install GStreamer:**
```bash
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav -y
```

4. **Install Flask:**
```bash
pip3 install flask
```

5. **Clone and run:**
```bash
git clone https://github.com/SCSIExpress/RCSM.git
cd RCSM
python3 radxa_stream_manager.py
```

## Platform-Specific Instructions

### Radxa Rock 5B

The Rock 5B has excellent camera support. For best results:

1. **Enable camera interface:**
```bash
sudo nano /boot/config.txt
# Add: camera_auto_detect=1
```

2. **Install additional packages:**
```bash
sudo apt install v4l-utils -y
```

3. **Verify camera detection:**
```bash
v4l2-ctl --list-devices
```

### Radxa Rock 4

For Rock 4 devices:

1. **Install kernel headers:**
```bash
sudo apt install linux-headers-$(uname -r) -y
```

2. **Load camera modules:**
```bash
sudo modprobe uvcvideo
```

### Radxa Rock 3

Rock 3 setup is similar to Rock 4:

1. **Check camera compatibility:**
```bash
lsusb  # For USB cameras
ls /dev/video*  # Should show video devices
```

## Camera Setup

### USB Cameras

Most USB cameras work out of the box:

1. **Connect camera and verify:**
```bash
ls /dev/video*
# Should show /dev/video0 or similar
```

2. **Test camera:**
```bash
gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! autovideosink
```

### CSI Cameras

For CSI camera modules:

1. **Enable CSI interface in device tree**
2. **Install camera-specific drivers**
3. **Configure camera parameters**

Specific instructions vary by camera model. Consult your camera documentation.

## Network Configuration

### Firewall Setup

Allow access to port 80:

```bash
# UFW (Ubuntu/Debian)
sudo ufw allow 80

# iptables
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
```

### Static IP (Optional)

For consistent access, set a static IP:

```bash
sudo nano /etc/netplan/01-netcfg.yaml
```

Example configuration:
```yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses: [192.168.1.100/24]
      gateway4: 192.168.1.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

Apply changes:
```bash
sudo netplan apply
```

## Service Installation (Optional)

To run RCSM as a system service:

1. **Create service file:**
```bash
sudo nano /etc/systemd/system/rcsm.service
```

2. **Add service configuration:**
```ini
[Unit]
Description=Radxa Camera Stream Manager
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/RCSM
ExecStart=/usr/bin/python3 radxa_stream_manager.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. **Enable and start service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable rcsm
sudo systemctl start rcsm
```

4. **Check service status:**
```bash
sudo systemctl status rcsm
```

## Troubleshooting Installation

### Common Issues

**Python not found:**
```bash
# Install Python 3
sudo apt install python3 python3-pip -y
```

**GStreamer not working:**
```bash
# Reinstall GStreamer
sudo apt remove --purge gstreamer1.0-*
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav -y
```

**Camera not detected:**
```bash
# Check USB devices
lsusb

# Check video devices
ls -l /dev/video*

# Check permissions
sudo usermod -a -G video $USER
# Logout and login again
```

**Permission denied errors:**
```bash
# Add user to video group
sudo usermod -a -G video $USER

# Fix camera permissions
sudo chmod 666 /dev/video*
```

**Flask import error:**
```bash
# Install Flask
pip3 install flask

# Or use system package
sudo apt install python3-flask -y
```

### Verification Steps

After installation, verify everything works:

1. **Check Python version:**
```bash
python3 --version
# Should be 3.6 or higher
```

2. **Check GStreamer:**
```bash
gst-launch-1.0 --version
```

3. **Check camera:**
```bash
v4l2-ctl --list-devices
```

4. **Test application:**
```bash
cd RCSM
python3 radxa_stream_manager.py
# Should start without errors
```

5. **Test web interface:**
Open browser to `http://localhost:80`

## Performance Optimization

### For better performance:

1. **Increase GPU memory split:**
```bash
sudo nano /boot/config.txt
# Add: gpu_mem=128
```

2. **Optimize GStreamer:**
```bash
export GST_DEBUG=2  # Reduce debug output
```

3. **Use hardware acceleration when available:**
Modify stream command in `radxa_stream_manager.py` to use hardware encoders.

## Uninstallation

To remove RCSM:

1. **Stop service (if installed):**
```bash
sudo systemctl stop rcsm
sudo systemctl disable rcsm
sudo rm /etc/systemd/system/rcsm.service
```

2. **Remove files:**
```bash
rm -rf ~/RCSM
```

3. **Remove packages (optional):**
```bash
pip3 uninstall flask
# GStreamer and Python can be kept for other applications
```

## Getting Help

If you encounter issues:

1. Check the [Troubleshooting Guide](TROUBLESHOOTING.md)
2. Review [GitHub Issues](https://github.com/SCSIExpress/RCSM/issues)
3. Create a new issue with:
   - Your Radxa model
   - OS version
   - Error messages
   - Steps you've tried