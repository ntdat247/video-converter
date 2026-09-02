#!/usr/bin/env bash
# ==============================================================================
# vid - Video Converter Installer for Ubuntu / Linux
# Sets up Python venv, command-line symlinks, and GNOME Desktop integration
# ==============================================================================
set -e

REPO_DIR="$(cd -P "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" >/dev/null 2>&1 && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons"

echo "======================================================"
echo "🎬 Cài đặt vid Video Converter trên Ubuntu Linux"
echo "======================================================"
echo "[*] Thư mục nguồn: $REPO_DIR"

# 1. Kiểm tra các gói phụ thuộc hệ thống
MISSING_PKGS=""
command -v ffmpeg >/dev/null 2>&1 || MISSING_PKGS="$MISSING_PKGS ffmpeg"
command -v python3 >/dev/null 2>&1 || MISSING_PKGS="$MISSING_PKGS python3 python3-venv"
command -v zenity >/dev/null 2>&1 || MISSING_PKGS="$MISSING_PKGS zenity"

if [ -n "$MISSING_PKGS" ]; then
    echo "[!] Phát hiện thiếu một số gói hệ thống: $MISSING_PKGS"
    echo "[*] Đang cài đặt qua apt (yêu cầu quyền sudo)..."
    sudo apt update && sudo apt install -y $MISSING_PKGS
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

# 5. Cài đặt icon vào hệ thống
mkdir -p "$ICON_DIR"
mkdir -p "$ICON_DIR/hicolor/512x512/apps"
if [ -f "$REPO_DIR/assets/icon.png" ]; then
    cp "$REPO_DIR/assets/icon.png" "$ICON_DIR/vid.png"
    cp "$REPO_DIR/assets/icon.png" "$ICON_DIR/hicolor/512x512/apps/vid.png"
fi

# 6. Tạo file .desktop động theo đường dẫn thực tế của máy này
mkdir -p "$APP_DIR"
cat > "$APP_DIR/vid.desktop" << DESKTOPEOF
[Desktop Entry]
Name=vid - Video Converter
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

# 7. Cập nhật cache ứng dụng GNOME
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f "$ICON_DIR/hicolor" 2>/dev/null || true
fi

echo ""
echo "======================================================"
echo "✔ Cài đặt thành công 100%!"
echo "======================================================"
echo "👉 Từ bây giờ trên máy này bạn có thể:"
echo "   1. Nhấn phím Super (Windows) và tìm 'vid' hoặc 'video' để mở app."
echo "   2. Mở giao diện đồ họa từ terminal: vid-gui"
echo "   3. Chuyển đổi video bằng lệnh CLI: vid input.webm"
echo "======================================================"
