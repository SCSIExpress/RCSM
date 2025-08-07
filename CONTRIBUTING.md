# Contributing to RCSM

Thank you for your interest in contributing to the Radxa Camera Stream Manager! This document provides guidelines and information for contributors.

## Getting Started

### Prerequisites

- Python 3.6 or higher
- Git
- A Radxa single-board computer for testing (recommended)
- Basic knowledge of Flask and web development

### Development Setup

1. Fork the repository on GitHub
2. Clone your fork locally:
```bash
git clone https://github.com/YOUR_USERNAME/RCSM.git
cd RCSM
```

3. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

4. Install dependencies:
```bash
pip install flask
```

5. Run the application in development mode:
```bash
python3 radxa_stream_manager.py
```

## How to Contribute

### Reporting Bugs

Before creating bug reports, please check the existing issues to avoid duplicates. When creating a bug report, include:

- **Clear description** of the issue
- **Steps to reproduce** the problem
- **Expected behavior** vs actual behavior
- **System information** (Radxa model, OS version, Python version)
- **Error messages** or logs if applicable

### Suggesting Features

Feature requests are welcome! Please provide:

- **Clear description** of the feature
- **Use case** explaining why this feature would be useful
- **Possible implementation** ideas (if you have any)

### Pull Requests

1. **Create a feature branch** from main:
```bash
git checkout -b feature/your-feature-name
```

2. **Make your changes** following the coding standards below

3. **Test your changes** thoroughly:
   - Test on actual Radxa hardware if possible
   - Verify web interface works on different browsers
   - Check that existing functionality still works

4. **Commit your changes** with clear, descriptive messages:
```bash
git commit -m "Add feature: brief description of what you added"
```

5. **Push to your fork**:
```bash
git push origin feature/your-feature-name
```

6. **Create a Pull Request** on GitHub with:
   - Clear title and description
   - Reference to any related issues
   - Screenshots if UI changes are involved

## Coding Standards

### Python Code Style

- Follow PEP 8 style guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and concise
- Handle errors gracefully with appropriate error messages

### HTML/CSS/JavaScript

- Use semantic HTML elements
- Maintain responsive design principles
- Keep JavaScript minimal and functional
- Follow consistent indentation (2 spaces for HTML/CSS/JS)

### Example Code Style

```python
def start_camera_stream():
    """
    Start the camera stream using GStreamer.
    
    Returns:
        dict: Status response with success/error information
    """
    try:
        # Implementation here
        return {"status": "success", "message": "Stream started"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

## Testing

### Manual Testing Checklist

Before submitting a PR, please verify:

- [ ] Web interface loads correctly
- [ ] Start stream button works
- [ ] Stop stream button works
- [ ] Status updates correctly
- [ ] Error handling works properly
- [ ] Mobile/responsive design works
- [ ] No console errors in browser

### Testing on Different Platforms

If possible, test on:
- Different Radxa models (Rock 5B, Rock 4, etc.)
- Different browsers (Chrome, Firefox, Safari)
- Different screen sizes (desktop, tablet, mobile)

## Documentation

When adding new features:

- Update the README.md if needed
- Add inline code comments for complex logic
- Update API documentation for new endpoints
- Include usage examples where helpful

## Community Guidelines

- Be respectful and constructive in discussions
- Help others learn and grow
- Focus on the technical aspects of contributions
- Be patient with new contributors

## Questions?

If you have questions about contributing:

1. Check existing issues and discussions
2. Create a new discussion on GitHub
3. Reach out to maintainers

## Recognition

Contributors will be recognized in:
- GitHub contributors list
- Release notes for significant contributions
- Special thanks in documentation updates

Thank you for helping make RCSM better!