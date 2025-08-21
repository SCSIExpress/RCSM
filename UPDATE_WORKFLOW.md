# Update Publishing Workflow for RCSM

## Quick Updates (Hotfixes)

For small fixes and improvements:

```bash
# 1. Make your changes
git add .
git commit -m "Fix: Camera detection for MJPEG formats"
git push origin main
```

## Major Updates (Features)

For significant changes:

```bash
# 1. Create a feature branch
git checkout -b feature/camera-detection-v2

# 2. Make your changes and test thoroughly
# ... development work ...

# 3. Commit your changes
git add .
git commit -m "Add: Advanced camera detection with v4l2-ctl integration"

# 4. Push feature branch
git push origin feature/camera-detection-v2

# 5. Create Pull Request on GitHub (optional for review)
# 6. Merge to main when ready
git checkout main
git merge feature/camera-detection-v2
git push origin main

# 7. Clean up
git branch -d feature/camera-detection-v2
git push origin --delete feature/camera-detection-v2
```

## Release Process

### 1. Update Version Information

Before releasing, update the CHANGELOG.md:

```markdown
## [1.1.0] - 2025-01-XX

### Added
- Smart camera detection using v4l2-ctl
- Automatic resolution and framerate detection
- Pixel format selection (YUYV, MJPEG, H264)

### Changed
- Replaced "Check Caps" with "Detect Options" button
- Improved FFmpeg command generation

### Fixed
- Better error handling for unsupported cameras
```

### 2. Tag Releases (Optional but Recommended)

```bash
# Create and push a tag for major releases
git tag -a v1.1.0 -m "Version 1.1.0 - Camera Detection Improvements"
git push origin v1.1.0
```

### 3. GitHub Release (Optional)

Create a GitHub release for major versions:
1. Go to your repository on GitHub
2. Click "Releases" → "Create a new release"
3. Choose your tag (v1.1.0)
4. Add release notes
5. Publish release

## Testing Updates

Before publishing:

```bash
# Test the update system locally
curl -X POST http://localhost/api/update

# Or use the web interface:
# 1. Click "Test Update Connection"
# 2. Click "Check for Updates"
```

## Emergency Rollback

If an update causes issues:

```bash
# Revert the last commit
git revert HEAD
git push origin main

# Or reset to a previous commit (destructive)
git reset --hard <previous-commit-hash>
git push --force origin main
```

## Update System Configuration

The update system is configured in `radxa_stream_manager.py`:

```python
# Repository settings
repo_url = "https://github.com/SCSIExpress/RCSM"
api_url = "https://api.github.com/repos/SCSIExpress/RCSM/commits/main"
download_url = "https://github.com/SCSIExpress/RCSM/archive/refs/heads/main.zip"

# Files that get updated
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
```

## User Experience

When users click "Check for Updates":
1. System compares local commit with GitHub
2. If newer version available, downloads and installs
3. Creates backup of old files
4. Attempts to restart service
5. Shows success/failure message

## Security Considerations

- Updates only download from your official GitHub repository
- Files are verified before installation
- Backups are created automatically
- Only specific files are updated (not user data)