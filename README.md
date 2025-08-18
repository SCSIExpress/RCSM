# RCSM - RockChip Stream Manager

A web-based interface for managing camera streams on Radxa single-board computers. This application provides an intuitive way to start, stop, and monitor camera streams with real-time status updates.

## Features

- 🎥 **Stream Management**: Start and stop camera streams with a single click
- 🌐 **Web Interface**: Clean, responsive web UI accessible from any device
- 📊 **Real-time Status**: Live updates on stream status and system information
- 🔧 **Easy Setup**: Automated installation script for quick deployment
- 📱 **Mobile Friendly**: Responsive design works on desktop and mobile devices

## Quick Start

### Prerequisites

- RockChip single-board computer (Rock 5B, Rock 4, etc.)
- Python 3.6 or higher
- Camera connected to your Radxa device

### Installation

**One-Command Install:**
```bash
curl -fsSL https://raw.githubusercontent.com/SCSIExpress/RCSM/main/setup.sh | sudo bash
```

That's it! The installer will:
- Download all required files from GitHub
- Install dependencies automatically  
- Set up and start the services
- Configure everything for you

**Access the web interface:**
```
http://your-radxa-ip:80
```

The setup script handles everything automatically - no need to clone the repository or manually start services.

## Usage

### Web Interface

The web interface provides:

- **Stream Control**: Start/Stop buttons for camera streaming
- **Status Display**: Real-time stream status indicator
- **System Info**: Current system status and configuration
- **Responsive Design**: Works on desktop, tablet, and mobile devices

### API Endpoints

- `GET /` - Main web interface
- `POST /start_stream` - Start camera stream
- `POST /stop_stream` - Stop camera stream
- `GET /stream_status` - Get current stream status (JSON)

## Configuration

The application uses default settings that work with most RockChip setups. For custom configurations, modify the stream parameters in `radxa_stream_manager.py`:

```python
# Example stream command customization
stream_command = [
    'gst-launch-1.0',
    'v4l2src', 'device=/dev/video0',
    '!', 'video/x-raw,width=1920,height=1080,framerate=30/1',
    '!', 'videoconvert',
    '!', 'x264enc', 'tune=zerolatency',
    '!', 'rtph264pay',
    '!', 'udpsink', 'host=0.0.0.0', 'port=80'
]
```

## Troubleshooting

### Common Issues

**Stream won't start:**
- Verify camera is connected and detected: `ls /dev/video*`
- Check GStreamer installation: `gst-launch-1.0 --version`
- Ensure no other applications are using the camera

**Web interface not accessible:**
- Check if the application is running: `ps aux | grep python`
- Verify firewall settings allow port 80
- Try accessing via localhost: `http://localhost:80`

**Permission errors:**
- Run setup script with appropriate permissions
- Check camera device permissions: `ls -l /dev/video*`

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

**Note**: This application is designed specifically for Radxa single-board computers but may work with other Linux-based systems with camera support.