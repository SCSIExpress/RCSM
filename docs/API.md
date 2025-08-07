# API Documentation

RCSM provides a RESTful API for programmatic control of camera streams. All endpoints return JSON responses.

## Base URL

```
http://your-radxa-ip:5000
```

## Endpoints

### GET /

Returns the main web interface.

**Response:**
- Content-Type: `text/html`
- Returns the main HTML interface

---

### POST /start_stream

Starts the camera stream.

**Request:**
- Method: `POST`
- Content-Type: `application/json` (optional)
- Body: None required

**Response:**
```json
{
  "status": "success",
  "message": "Stream started successfully"
}
```

**Error Response:**
```json
{
  "status": "error",
  "message": "Error description"
}
```

**Status Codes:**
- `200` - Success
- `500` - Internal server error (stream already running, camera not available, etc.)

---

### POST /stop_stream

Stops the camera stream.

**Request:**
- Method: `POST`
- Content-Type: `application/json` (optional)
- Body: None required

**Response:**
```json
{
  "status": "success",
  "message": "Stream stopped successfully"
}
```

**Error Response:**
```json
{
  "status": "error",
  "message": "Error description"
}
```

**Status Codes:**
- `200` - Success
- `500` - Internal server error

---

### GET /stream_status

Returns the current status of the camera stream.

**Request:**
- Method: `GET`

**Response:**
```json
{
  "status": "running",
  "message": "Stream is active",
  "timestamp": "2025-01-08T10:30:00Z"
}
```

**Possible Status Values:**
- `"running"` - Stream is currently active
- `"stopped"` - Stream is not running
- `"error"` - Stream encountered an error

**Status Codes:**
- `200` - Success

## Usage Examples

### cURL Examples

**Start Stream:**
```bash
curl -X POST http://192.168.1.100:5000/start_stream
```

**Stop Stream:**
```bash
curl -X POST http://192.168.1.100:5000/stop_stream
```

**Check Status:**
```bash
curl http://192.168.1.100:5000/stream_status
```

### Python Examples

```python
import requests

base_url = "http://192.168.1.100:5000"

# Start stream
response = requests.post(f"{base_url}/start_stream")
print(response.json())

# Check status
status = requests.get(f"{base_url}/stream_status")
print(status.json())

# Stop stream
response = requests.post(f"{base_url}/stop_stream")
print(response.json())
```

### JavaScript Examples

```javascript
const baseUrl = 'http://192.168.1.100:5000';

// Start stream
fetch(`${baseUrl}/start_stream`, {
    method: 'POST'
})
.then(response => response.json())
.then(data => console.log(data));

// Check status
fetch(`${baseUrl}/stream_status`)
.then(response => response.json())
.then(data => console.log(data));

// Stop stream
fetch(`${baseUrl}/stop_stream`, {
    method: 'POST'
})
.then(response => response.json())
.then(data => console.log(data));
```

## Error Handling

All endpoints return consistent error responses:

```json
{
  "status": "error",
  "message": "Detailed error description",
  "code": "ERROR_CODE" // Optional error code
}
```

### Common Error Codes

- `CAMERA_NOT_FOUND` - Camera device not detected
- `STREAM_ALREADY_RUNNING` - Attempt to start stream when already running
- `STREAM_NOT_RUNNING` - Attempt to stop stream when not running
- `GSTREAMER_ERROR` - GStreamer pipeline error
- `PERMISSION_DENIED` - Insufficient permissions to access camera

## Rate Limiting

Currently, no rate limiting is implemented. However, it's recommended to:
- Wait for previous requests to complete before sending new ones
- Check stream status before attempting to start/stop
- Implement client-side debouncing for user interactions

## CORS

Cross-Origin Resource Sharing (CORS) is not currently configured. If you need to access the API from a web application on a different domain, you may need to:

1. Configure CORS headers in the Flask application
2. Use a proxy server
3. Access the API from the same origin as the web interface

## WebSocket Support

The current API uses HTTP requests. For real-time updates, the web interface uses periodic polling. Future versions may include WebSocket support for real-time bidirectional communication.

## Authentication

The current version does not implement authentication. All endpoints are publicly accessible. For production deployments, consider:

- Adding API key authentication
- Implementing user authentication
- Using HTTPS for secure communication
- Restricting access by IP address or network