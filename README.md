# RCSM - RockChip Stream Manager

A web-based interface for managing camera streams on Radxa and Raspberry Pi single-board computers. This application provides an intuitive way to start, stop, and monitor camera streams with real-time status updates and hardware acceleration support.

## Features

- 🎥 **Stream Management**: Start and stop camera streams with a single click
- 🔍 **Smart Camera Detection**: Automatically detect available resolutions, framerates, and pixel formats
- 🚀 **Hardware Acceleration**: Platform-specific hardware encoders (rkmpp for Radxa, h264_v4l2m2m for Raspberry Pi)
- 📷 **Multi-Camera Support**: V4L2 USB cameras and libcamera CSI cameras (Raspberry Pi)
- 🌐 **Web Interface**: Clean, responsive web UI accessible from any device
- 📊 **Real-time Status**: Live updates on stream status and system information
- 🔧 **Easy Setup**: Automated installation script for quick deployment
- 📱 **Mobile Friendly**: Responsive design works on desktop and mobile devices
- 🌍 **Multi-Platform**: Supports both Radxa (RK3566) and Raspberry Pi Zero 2W

## Quick Start

### Prerequisites

**Supported Platforms:**
- **Radxa**: Zero 3E, Rock 5B, Rock 4, and other RK3566-based boards
- **Raspberry Pi**: Zero 2W, Pi 4, Pi 5 (with hardware acceleration support)

**Requirements:**
- Python 3.6 or higher
- Camera connected to your device (USB or CSI)
- Internet connection for installation

### Installation

**One-Command Install:**
```bash
curl -fsSL https://raw.githubusercontent.com/SCSIExpress/RCSM/main/setup.sh | sudo bash
```

That's it! The installer will:
- Automatically detect your platform (Radxa or Raspberry Pi)
- Download all required files from GitHub
- Install platform-specific dependencies and hardware acceleration
- Set up and start the services
- Configure everything for you

**For Raspberry Pi users:** A reboot is required after installation to enable camera and GPU memory settings.

**Access the web interface:**
```
http://your-device-ip:80
```

The setup script handles everything automatically - no need to clone the repository or manually start services.

### Platform-Specific Installation Notes

**Raspberry Pi Zero 2W:**
- Ensure you have a compatible camera (CSI or USB)
- The installer will configure GPU memory split to 128MB
- A reboot is required after installation
- CSI cameras will appear as `libcamera:0` in the device list

**Radxa Zero 3E:**
- Hardware acceleration is automatically configured
- Both USB and MIPI CSI cameras are supported
- No reboot required after installation

## Usage

### Web Interface

The web interface provides:

- **Stream Control**: Start/Stop buttons for camera streaming
- **Camera Detection**: Automatic detection of supported resolutions, framerates, and pixel formats
- **Platform Detection**: Automatically detects and optimizes for your hardware
- **Hardware Acceleration**: Uses platform-specific encoders for optimal performance
- **Status Display**: Real-time stream status indicator
- **System Info**: Current system status and configuration
- **Responsive Design**: Works on desktop, tablet, and mobile devices

### Platform-Specific Features

**Radxa (RK3566-based boards):**
- Hardware-accelerated encoding with rkmpp
- RGA hardware scaling support
- V4L2 camera detection and control

**Raspberry Pi:**
- libcamera support for CSI cameras
- h264_v4l2m2m hardware encoding
- GPU memory optimization
- V4L2 USB camera support

### API Endpoints

- `GET /` - Main web interface
- `POST /start_stream` - Start camera stream
- `POST /stop_stream` - Stop camera stream
- `GET /stream_status` - Get current stream status (JSON)

## Configuration

The application automatically detects camera capabilities and generates optimized FFmpeg commands. The web interface allows you to:

1. **Select Video Device**: Choose from detected cameras
2. **Detect Options**: Automatically discover supported resolutions, framerates, and pixel formats
3. **Configure Stream**: Select optimal settings based on detected capabilities
4. **Save Configuration**: Store settings for automatic startup

The system uses FFmpeg with platform-specific hardware acceleration for efficient streaming:
- **Radxa**: rkmpp encoder with RGA scaling
- **Raspberry Pi**: h264_v4l2m2m encoder with libcamera integration

## Troubleshooting

### Common Issues

**Stream won't start:**
- Verify camera is connected and detected: `ls /dev/video*`
- For Raspberry Pi CSI camera: `libcamera-hello --list-cameras`
- Check FFmpeg installation: `ffmpeg -version`
- Ensure no other applications are using the camera

**Web interface not accessible:**
- Check if the application is running: `ps aux | grep python`
- Verify firewall settings allow port 80
- Try accessing via localhost: `http://localhost:80`

**Permission errors:**
- Run setup script with appropriate permissions
- Check camera device permissions: `ls -l /dev/video*`
- For Raspberry Pi: Ensure user is in `video` and `render` groups

## Development

### Project Structure

```
RCSM/
├── radxa_stream_manager.py    # Main Flask application
├── templates/
│   └── index.html            # Web interface template
├── setup.sh                  # Installation script
├── README.md                 # This file
└── .vscode/
    └── settings.json         # VS Code configuration
```

### Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and test thoroughly
4. Commit your changes: `git commit -am 'Add new feature'`
5. Push to the branch: `git push origin feature-name`
6. Submit a pull request

## License

This project is open source and available under the [MIT License](LICENSE).

## Support

- **Issues**: Report bugs and request features via [GitHub Issues](https://github.com/SCSIExpress/RCSM/issues)
- **Discussions**: Join the conversation in [GitHub Discussions](https://github.com/SCSIExpress/RCSM/discussions)

## Acknowledgments

- Built for the Radxa community
- Uses GStreamer for video streaming
- Flask web framework for the interface

---

**Note**: This application is designed for Radxa and Raspberry Pi single-board computers with hardware acceleration support. It may work with other Linux-based systems but without hardware acceleration optimizations.