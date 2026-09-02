#!/usr/bin/env bash
# ==============================================================================
# Video Converter Installer for Linux (Ubuntu/Debian) & macOS
# Sets up Python venv, command-line symlinks, and Desktop/Launchpad integration
# ==============================================================================
set -e

OS="$(uname -s)"
REPO_DIR="$(cd -P "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" >/dev/null 2>&1 && pwd)"
BIN_DIR="$HOME/.local/bin"

echo "======================================================"
echo "🎬 Cài đặt Video Converter ($OS)"
echo "======================================================"
echo "[*] Thư mục nguồn: $REPO_DIR"

# 1. Kiểm tra & cài đặt các gói phụ thuộc
if [ "$OS" = "Darwin" ]; then
    echo "[*] Kiểm tra môi trường macOS..."
    if ! command -v brew >/dev/null 2>&1; then
        echo "[!] Khuyên dùng Homebrew (https://brew.sh) để cài FFmpeg trên macOS."
    fi
    if ! command -v ffmpeg >/dev/null 2>&1; then
        echo "[*] Đang cài đặt FFmpeg qua Homebrew..."
        brew install ffmpeg || echo "[!] Vui lòng cài ffmpeg thủ công: brew install ffmpeg"
    fi
else
    # Linux (Ubuntu, Debian, Fedora, Arch)
    MISSING_PKGS=""
    command -v ffmpeg >/dev/null 2>&1 || MISSING_PKGS="$MISSING_PKGS ffmpeg"
    command -v python3 >/dev/null 2>&1 || MISSING_PKGS="$MISSING_PKGS python3 python3-venv"
    command -v zenity >/dev/null 2>&1 || MISSING_PKGS="$MISSING_PKGS zenity"

    if [ -n "$MISSING_PKGS" ]; then
        echo "[!] Phát hiện thiếu gói hệ thống: $MISSING_PKGS"
        if command -v apt >/dev/null 2>&1; then
            echo "[*] Đang cài đặt qua apt (sudo)..."
            sudo apt update && sudo apt install -y $MISSING_PKGS
        elif command -v dnf >/dev/null 2>&1; then
            sudo dnf install -y $MISSING_PKGS
        elif command -v pacman >/dev/null 2>&1; then
            sudo pacman -S --noconfirm $MISSING_PKGS
        fi
    fi
fi

# 2. Thiết lập môi trường ảo Python venv và cài thư viện
echo "[*] Đang thiết lập môi trường Python venv..."
if [ ! -d "$REPO_DIR/venv" ]; then
    python3 -m venv "$REPO_DIR/venv"
fi
"$REPO_DIR/venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

# 3. Cấp quyền thực thi cho các script
chmod +x "$REPO_DIR/vid" "$REPO_DIR/vid-gui" "$REPO_DIR/install.sh"

# 4. Tạo thư mục bin nếu chưa có và liên kết symlinks
mkdir -p "$BIN_DIR"
ln -sf "$REPO_DIR/vid" "$BIN_DIR/vid"
ln -sf "$REPO_DIR/vid-gui" "$BIN_DIR/vid-gui"
ln -sf "$BIN_DIR/vid" "$BIN_DIR/vid2" 2>/dev/null || true
ln -sf "$BIN_DIR/vid-gui" "$BIN_DIR/vid2-gui" 2>/dev/null || true

# 5. Tích hợp giao diện Desktop / Spotlight
if [ "$OS" = "Darwin" ]; then
    # Tạo macOS App Bundle trong ~/Applications
    MAC_APPS="$HOME/Applications"
    mkdir -p "$MAC_APPS"
    APP_BUNDLE="$MAC_APPS/Video Converter.app"
    mkdir -p "$APP_BUNDLE/Contents/MacOS"
    mkdir -p "$APP_BUNDLE/Contents/Resources"
    cat > "$APP_BUNDLE/Contents/MacOS/Video Converter" << MACOSEOF
#!/bin/bash
exec "$REPO_DIR/vid-gui"
MACOSEOF
    chmod +x "$APP_BUNDLE/Contents/MacOS/Video Converter"
    if [ -f "$REPO_DIR/assets/icon.png" ]; then
        cp "$REPO_DIR/assets/icon.png" "$APP_BUNDLE/Contents/Resources/app.png"
    fi
    echo "[*] Đã tạo ứng dụng macOS: $APP_BUNDLE (tìm trong Spotlight/Launchpad)"
else
    # Linux Desktop Entry
    APP_DIR="$HOME/.local/share/applications"
    ICON_DIR="$HOME/.local/share/icons"
    mkdir -p "$ICON_DIR" "$ICON_DIR/hicolor/512x512/apps"
    if [ -f "$REPO_DIR/assets/icon.png" ]; then
        cp "$REPO_DIR/assets/icon.png" "$ICON_DIR/vid.png"
        cp "$REPO_DIR/assets/icon.png" "$ICON_DIR/hicolor/512x512/apps/vid.png"
    fi

    mkdir -p "$APP_DIR"
    cat > "$APP_DIR/vid.desktop" << DESKTOPEOF
[Desktop Entry]
Name=Video Converter
Comment=Chuyển đổi video WebM, MP4, MOV chất lượng cao
Exec=$BIN_DIR/vid-gui
Icon=$REPO_DIR/assets/icon.png
Terminal=false
Type=Application
Categories=AudioVideo;Video;AudioVideoEditing;
Keywords=vid;video;converter;convert;webm;mp4;mov;transcode;
StartupNotify=true
DESKTOPEOF
    chmod +x "$APP_DIR/vid.desktop"

    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APP_DIR" 2>/dev/null || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f "$ICON_DIR/hicolor" 2>/dev/null || true
    fi
fi

echo ""
echo "======================================================"
echo "✔ Cài đặt thành công 100% trên $OS!"
echo "======================================================"
echo "👉 Từ bây giờ bạn có thể:"
echo "   1. Mở ứng dụng từ Menu/Spotlight/Launchpad: 'Video Converter'"
echo "   2. Mở giao diện từ terminal: vid-gui"
echo "   3. Dùng lệnh dòng lệnh: vid input.webm"
echo "======================================================"
