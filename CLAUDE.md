# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## WhatsApp Server Overview

This is the **Node.js WhatsApp server component** of the larger Spring Boot notification service. It provides a local WhatsApp Web integration using `whatsapp-web.js` that allows the main Spring Boot application to send WhatsApp messages without relying on the Facebook Graph API during development.

## Common Development Commands

### Running the WhatsApp Server
- `npm start` - Start the WhatsApp server on port 3000
- `node whatsapp-server.js` - Alternative start command
- `start-whatsapp.bat` - Windows batch script to start server with proper directory navigation

### Package Management
- `npm install` - Install dependencies after cloning
- `npm list` - View installed packages
- `npm update` - Update dependencies
- `npm audit` - Check for security vulnerabilities

### Testing and Monitoring
- `node test-whatsapp.js --test` - Run comprehensive connection and message tests
- `node test-whatsapp.js --monitor` - Start continuous monitoring (30s intervals)
- `node test-whatsapp.js --monitor --interval 60` - Custom monitoring interval
- `health-check.bat` - Windows script for daily health verification
- `monitor.bat` - Interactive monitoring menu for Windows

### Maintenance Commands
- `npx kill-port 3000` - Stop server running on port 3000
- `cleanup.bat` - Clean WhatsApp sessions and restart server
- Remove sessions manually: `rmdir /s /q .wwebjs_auth .wwebjs_cache` (Windows)

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
- `GET /qr-page` - Web interface for QR code scanning with visual interface
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
# Manual API test
curl -X POST http://localhost:3000/send-message \
  -H "Content-Type: application/json" \
  -d '{"number": "22544210112", "message": "Test message"}'

# Automated test with monitoring
node test-whatsapp.js --test
```

### Troubleshooting Common Issues
- **QR code doesn't appear**: Delete `.wwebjs_auth/` and `.wwebjs_cache/` directories, restart server
- **Port already in use**: Run `npx kill-port 3000` or use `cleanup.bat`
- **Connection lost**: Server auto-reconnects after 5 seconds; check logs for errors
- **Session expires**: WhatsApp sessions expire after ~2 weeks of inactivity - re-scan QR code
- **Protocol errors**: Clean sessions with `cleanup.bat` and restart
- **QR code access**: Use http://localhost:3000/qr-page for visual QR interface

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

## Important Configuration

### Key Files and Scripts
- **Main server**: `whatsapp-server.js` - Core Express server with WhatsApp integration
- **Test suite**: `test-whatsapp.js` - Comprehensive testing and monitoring utilities
- **Windows utilities**: `*.bat` files for automated maintenance (cleanup, monitoring, health checks)
- **Session storage**: `.wwebjs_auth/ecole-notification/` - Persistent WhatsApp sessions
- **Comprehensive guide**: `GUIDE-COMPLET.md` - Detailed French documentation for setup/maintenance

### Environment Configuration
- **Default port**: 3000 (configurable in `whatsapp-server.js` line 7)
- **Session name**: "ecole-notification" (configurable in LocalAuth strategy)
- **Test number**: 22544210112 (configurable in `test-whatsapp.js` line 64)
- **Puppeteer args**: Optimized for headless operation with performance flags

### Operational URLs
- **QR Code Interface**: http://localhost:3000/qr-page (visual QR scanning)
- **Status API**: http://localhost:3000/status
- **QR Data API**: http://localhost:3000/qr

## Important Notes

### Documentation Consistency
- The actual implemented endpoints are `/status`, `/qr`, `/qr-page`, and `/send-message`
- The README.md mentions different endpoints that may be from an earlier design
- Always refer to the actual code implementation in `whatsapp-server.js` for current API endpoints
- For comprehensive operational procedures, reference `GUIDE-COMPLET.md`

### WhatsApp Web Version Management
- Server uses remote web version cache for stability
- Version URL: https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.2412.54.html
- Automatic reconnection logic handles temporary disconnections