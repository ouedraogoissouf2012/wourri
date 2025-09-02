# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## WhatsApp Server Overview

This is the **Node.js WhatsApp server component** of the larger Spring Boot notification service. It provides a local WhatsApp Web integration using `whatsapp-web.js` that allows the main Spring Boot application to send WhatsApp messages without relying on the Facebook Graph API during development.

## Common Development Commands

### Running the WhatsApp Server
- `npm start` - Start the WhatsApp server on port 3000
- `node whatsapp-server.js` - Alternative start command

### Package Management
- `npm install` - Install dependencies after cloning
- `npm list` - View installed packages

## Architecture

### Core Dependencies
- **express** (^4.18.2) - REST API server framework
- **whatsapp-web.js** (^1.22.2) - WhatsApp Web integration library
- **qrcode-terminal** (^0.12.0) - QR code display in terminal
- **cors** (^2.8.5) - Cross-origin resource sharing support

### Authentication Flow
The server uses WhatsApp Web's session-based authentication:
1. On first run, generates QR code displayed in terminal
2. User scans QR code with WhatsApp mobile app
3. Creates persistent session in `.wwebjs_auth/` directory
4. Subsequent runs reuse saved session (no QR scan needed)

### API Endpoints
- `GET /status` - Returns connection status and QR code requirement
- `GET /qr` - Returns current QR code data if authentication needed  
- `POST /send-message` - Send WhatsApp message (requires `number` and `message` in body)

### Session Management
- **Session Storage**: `.wwebjs_auth/ecole-notification/` - Persistent WhatsApp session data (configurable via LocalAuth name parameter)
- **Cache Directory**: `.wwebjs_cache/` - Temporary browser cache files
- **Session Name**: "ecole-notification" - Configured in LocalAuth strategy

## Integration with Main Application

This WhatsApp server is designed to work alongside the Spring Boot notification service:

### Communication Pattern
- Spring Boot app (`http://localhost:8080`) makes HTTP requests to this server (`http://localhost:3000`)
- WhatsAppService in Spring Boot uses WebClient to call `/send-message` endpoint
- Async processing in Spring Boot handles message queuing and retry logic

### Message Flow
1. Spring Boot receives notification request via REST API
2. WhatsAppService formats message and calls `POST /send-message`
3. WhatsApp server validates connection status
4. If connected, sends message via WhatsApp Web protocol
5. Returns success/failure response to Spring Boot
6. Spring Boot updates notification delivery status in database

## Development Workflow

### Initial Setup
1. Run `npm install` to install dependencies
2. Start server with `npm start`
3. Scan displayed QR code with WhatsApp mobile app
4. Server will show "✅ WhatsApp connecté et prêt !" when ready

### Testing Message Sending
```bash
curl -X POST http://localhost:3000/send-message \
  -H "Content-Type: application/json" \
  -d '{"number": "+1234567890", "message": "Test message"}'
```

### Troubleshooting
- If QR code doesn't appear, delete `.wwebjs_auth/` and `.wwebjs_cache/` directories
- Check `GET /status` endpoint to verify connection state
- WhatsApp session expires after ~2 weeks of inactivity

## Key Design Considerations

### Error Handling
- Returns appropriate HTTP status codes (400, 503, 500)
- Includes detailed error messages for debugging
- Validates required request parameters before processing

### Number Formatting
- Accepts numbers with or without WhatsApp chat ID suffix
- Automatically formats phone numbers to `number@c.us` format
- Supports international number formats

### Logging
- Console logging for all major events (connection, messages, errors)
- Message preview logging (first 50 characters) for debugging
- Emojis used for visual status indication in logs

## Security Notes

### Port Exposure
- Server runs on localhost:3000 (not exposed externally by default)
- Only accepts requests from same machine (suitable for development)
- CORS enabled for local Spring Boot integration

### Session Security
- WhatsApp session data stored locally in `.wwebjs_auth/`
- No sensitive credentials stored in code
- Relies on WhatsApp Web's built-in security model

## Important Notes

### Documentation Consistency
- The actual implemented endpoints are `/status`, `/qr`, and `/send-message`
- The README.md mentions different endpoints that may be from an earlier design
- Always refer to the actual code implementation in `whatsapp-server.js` for current API endpoints