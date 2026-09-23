# FinTech Desk — Desktop App

A Flutter desktop application for the FinTech SaaS platform, installable on **Windows**, **macOS**, and **Linux**.

## Features

### Core Financial Documents
- **Account Statements** — Upload Excel, generate branded PDF statements per client
- **GST Invoices** — CGST/SGST (intrastate) or IGST (interstate) with HSN codes
- **Loan / EMI Schedules** — Full amortisation schedule with per-instalment breakdown
- **Portfolio Reports** — Investment portfolio with returns calculation

### Multi-Channel Delivery
- **SMTP Email** — Custom host, Gmail, Outlook, Zoho Mail
- **Gmail API** — OAuth 2.0, send via Google Workspace
- **Microsoft 365 / Outlook** — OAuth 2.0, full Teams notifications
- **WhatsApp Business** — Meta Cloud API, bulk document delivery
- **Twilio SMS/WhatsApp** — SMS alerts + WhatsApp delivery

### Integrations Hub
| Integration | Features |
|---|---|
| **Zoho CRM** | Sync contacts, push clients, OAuth 2.0 |
| **Zoho Books** | Create invoices, send via Zoho |
| **Zoho Mail** | Send emails via Zoho Mail |
| **Gmail** | OAuth, send as alias, bulk send |
| **Microsoft 365** | Outlook email, Teams notifications |
| **WhatsApp Business** | Document delivery, templates |
| **Twilio** | SMS alerts, WhatsApp |
| **Razorpay** | Payment links in invoices |
| **Stripe** | International payment processing |
| **Telegram Bot** | Document delivery, notifications |
| **Slack** | Internal team notifications |

## Installation

### Prerequisites
1. Install [Flutter](https://docs.flutter.dev/get-started/install) (3.16+)
2. Set up the backend server (see root README)

### Build & Run

```bash
cd flutter_desktop

# Install dependencies
flutter pub get

# Run in debug mode (connects to localhost:8000)
flutter run -d windows   # Windows
flutter run -d macos     # macOS
flutter run -d linux     # Linux

# Build release binary
./build_desktop.sh
```

### Backend Setup
The desktop app connects to the Python Flask backend via REST API.

```bash
# Start the backend (from project root)
pip install -r requirements.txt
python app.py

# Or with Docker
docker-compose up
```

The default backend URL is `http://localhost:8000/api/v1`. You can change it in **Settings → App / Backend**.

### For Remote / Hosted Backend
Change the backend URL in Settings to your server URL, e.g.:
```
https://your-company.example.com/api/v1
```

## Configuration

### SMTP Email
Settings → SMTP Email → Enter host, port, username, and password.

### Gmail OAuth
1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Gmail API
3. Create OAuth 2.0 credentials
4. Go to Integrations → Gmail → Enter Client ID, Secret, Redirect URI
5. Click "Save & Authorize" to open the OAuth flow in your browser

### Zoho Integration
1. Create an app at [Zoho API Console](https://api-console.zoho.com/)
2. Go to Integrations → Zoho Suite → Enter credentials
3. Click "Save & Authorize"

### WhatsApp Business
1. Set up a [Meta Business App](https://developers.facebook.com/)
2. Go to Integrations → WhatsApp Business → Enter Phone Number ID + Access Token

### Razorpay
1. Get API keys from [Razorpay Dashboard](https://dashboard.razorpay.com/)
2. Go to Integrations → Razorpay → Enter Key ID + Key Secret

## Distribution

### Windows Installer
```bash
# Install NSIS first, then:
./build_desktop.sh
# Output: build/windows/FinTechDesk-Setup-1.0.0.exe
```

### macOS DMG
```bash
brew install create-dmg
./build_desktop.sh
# Output: build/macos/FinTechDesk-1.0.0.dmg
```

### Linux DEB Package
```bash
./build_desktop.sh
# Output: build/linux/FinTechDesk-1.0.0-amd64.deb
# Install: sudo dpkg -i FinTechDesk-1.0.0-amd64.deb
```

## Architecture

```
flutter_desktop/
├── lib/
│   ├── main.dart              # Entry point + window config
│   ├── app.dart               # Root app widget + routing
│   ├── core/
│   │   ├── api_client.dart    # Dio HTTP client + auth interceptor
│   │   ├── constants.dart     # App constants + integration names
│   │   └── theme.dart         # Light/dark theme
│   ├── models/                # Data models
│   ├── services/              # Business logic + API calls
│   ├── screens/               # All UI screens
│   └── widgets/               # Reusable widgets (sidebar, etc.)
├── windows/                   # Windows runner
├── macos/                     # macOS runner
├── linux/                     # Linux runner
└── build_desktop.sh           # Cross-platform build script
```
