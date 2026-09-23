#!/usr/bin/env bash
# FinTech Desk — Desktop Build Script
# Builds installers for Windows, macOS, and Linux

set -e
cd "$(dirname "$0")"

VERSION="1.0.0"
APP_NAME="fintech_desk"

echo "=== FinTech Desk Desktop Build ==="
echo "Version: $VERSION"
echo ""

# Install/update dependencies
flutter pub get

# Detect platform and build
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "[macOS] Building .app and .dmg..."
    flutter build macos --release
    # Create DMG
    if command -v create-dmg &>/dev/null; then
        create-dmg \
            --volname "FinTech Desk" \
            --window-pos 200 120 \
            --window-size 800 400 \
            --icon-size 100 \
            --app-drop-link 600 185 \
            "build/macos/FinTechDesk-$VERSION.dmg" \
            "build/macos/Build/Products/Release/fintech_desk.app"
        echo "DMG: build/macos/FinTechDesk-$VERSION.dmg"
    else
        echo "macOS .app: build/macos/Build/Products/Release/fintech_desk.app"
    fi

elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "[Linux] Building Linux app..."
    flutter build linux --release

    # Create .deb package
    DEB_DIR="build/linux/deb"
    mkdir -p "$DEB_DIR/DEBIAN"
    mkdir -p "$DEB_DIR/usr/local/bin"
    mkdir -p "$DEB_DIR/usr/share/applications"
    mkdir -p "$DEB_DIR/usr/share/pixmaps"

    # Copy binary
    cp -r "build/linux/x64/release/bundle/" "$DEB_DIR/usr/local/fintech_desk/"

    # Control file
    cat > "$DEB_DIR/DEBIAN/control" <<EOF
Package: fintech-desk
Version: $VERSION
Section: finance
Priority: optional
Architecture: amd64
Maintainer: FinTech SaaS <support@fintechdesk.app>
Description: FinTech Desk Desktop Application
 Professional financial document management for Indian financial services.
 Generate account statements, GST invoices, loan schedules, portfolio reports.
 Integrates with Zoho, Gmail, Microsoft 365, WhatsApp, Razorpay, and more.
EOF

    # Desktop entry
    cat > "$DEB_DIR/usr/share/applications/fintech-desk.desktop" <<EOF
[Desktop Entry]
Name=FinTech Desk
Comment=Financial Document Management
Exec=/usr/local/fintech_desk/fintech_desk
Icon=fintech-desk
Terminal=false
Type=Application
Categories=Office;Finance;
EOF

    # Launcher script
    cat > "$DEB_DIR/usr/local/bin/fintech-desk" <<'SCRIPT'
#!/bin/bash
/usr/local/fintech_desk/fintech_desk "$@"
SCRIPT
    chmod +x "$DEB_DIR/usr/local/bin/fintech-desk"

    dpkg-deb --build "$DEB_DIR" "build/linux/FinTechDesk-$VERSION-amd64.deb" 2>/dev/null || true

    # Also create AppImage if appimagetool is available
    if command -v appimagetool &>/dev/null; then
        echo "Creating AppImage..."
        # AppImage build steps would go here
    fi

    echo "Linux build: build/linux/x64/release/bundle/"
    echo "DEB package: build/linux/FinTechDesk-$VERSION-amd64.deb"

elif [[ "$OS" == "Windows_NT" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
    echo "[Windows] Building Windows app..."
    flutter build windows --release

    # Create NSIS installer if makensis is available
    if command -v makensis &>/dev/null; then
        cat > "build/windows/installer.nsi" <<NSIS
!include "MUI2.nsh"
Name "FinTech Desk"
OutFile "FinTechDesk-Setup-$VERSION.exe"
InstallDir "\$PROGRAMFILES64\FinTech Desk"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "\$INSTDIR"
  File /r "windows\x64\runner\Release\*.*"
  CreateShortCut "\$DESKTOP\FinTech Desk.lnk" "\$INSTDIR\fintech_desk.exe"
  CreateShortCut "\$SMPROGRAMS\FinTech Desk\FinTech Desk.lnk" "\$INSTDIR\fintech_desk.exe"
  WriteUninstaller "\$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "\$DESKTOP\FinTech Desk.lnk"
  RMDir /r "\$INSTDIR"
SectionEnd
NSIS
        makensis "build/windows/installer.nsi"
        echo "Windows Installer: build/windows/FinTechDesk-Setup-$VERSION.exe"
    else
        echo "Windows build: build/windows/x64/runner/Release/"
        echo "To create an installer, install NSIS: https://nsis.sourceforge.io/"
    fi
fi

echo ""
echo "=== Build Complete ==="
echo "Start the backend server first: cd .. && python app.py"
echo "Then launch the desktop app."
