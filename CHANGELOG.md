# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure and documentation

## [1.0.0] - 2025-01-08

### Added
- Initial release of Radxa Camera Stream Manager
- Web-based interface for camera stream management
- Real-time stream status monitoring
- Start/stop stream functionality via web UI
- RESTful API endpoints for stream control
- Responsive web design for mobile and desktop
- Automated setup script for easy installation
- GStreamer integration for camera streaming
- Flask web framework implementation
- Cross-platform compatibility (Linux focus)

### Features
- **Web Interface**: Clean, intuitive web UI accessible from any browser
- **Stream Control**: One-click start/stop camera streaming
- **Status Monitoring**: Real-time updates on stream status
- **API Endpoints**: RESTful API for programmatic control
- **Mobile Support**: Responsive design works on all devices
- **Easy Setup**: Automated installation with setup.sh script

### Technical Details
- Python 3.6+ compatibility
- Flask web framework
- GStreamer for video processing
- HTML5/CSS3/JavaScript frontend
- JSON API responses
- Process management for stream control

### Documentation
- Comprehensive README with setup instructions
- Contributing guidelines for developers
- MIT License for open source usage
- Installation and troubleshooting guides

---

## Release Notes

### Version 1.0.0 - Initial Release

This is the first stable release of RCSM (Radxa Camera Stream Manager). The application provides a complete solution for managing camera streams on Radxa single-board computers through a web interface.

**Key Highlights:**
- Zero-configuration setup for most Radxa devices
- Web-based control accessible from any device on the network
- Real-time status updates without page refresh
- Mobile-friendly responsive design
- Comprehensive error handling and user feedback

**Tested On:**
- Radxa Rock 5B
- Various camera modules
- Multiple browsers (Chrome, Firefox, Safari)
- Desktop and mobile devices

**Known Limitations:**
- Requires GStreamer to be installed on the system
- Currently supports single camera stream at a time
- Network streaming configuration may need adjustment for specific setups

**Future Roadmap:**
- Multiple camera support
- Stream recording functionality
- Advanced configuration options
- Performance monitoring
- Plugin system for custom stream processors