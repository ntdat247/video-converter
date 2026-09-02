# vid - Universal Video Converter (WebM ⇄ MP4 ⇄ MOV) on Ubuntu

[![Ubuntu](https://img.shields.io/badge/Platform-Ubuntu%20Linux-orange.svg)](https://ubuntu.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Enabled-green.svg)](https://ffmpeg.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*Read this in: [English](#english) | [Tiếng Việt](#tiếng-việt)*

---

<a name="english"></a>
## English

A versatile, lightweight, and high-performance video converter designed for Ubuntu Linux. Seamlessly transcode between popular web and desktop formats: **WebM**, **MP4**, **MOV** (and **MKV**). Supports both an ultra-fast **Command-Line Interface (CLI)** and a modern **Graphical User Interface (Web GUI)**.

---

### 🌟 Key Features

- 🖥️ **Dual Modes (CLI & GUI):**
  - **CLI:** Fast, scriptable, and pipeline-friendly with intuitive arguments.
  - **Web GUI:** Modern dark-themed dashboard, native GNOME file/directory picker dialogs (`zenity`), live video metadata inspection, CRF slider, preset selectors, and real-time terminal output.
- 🔄 **Multi-Format Transcoding:**
  - **WebM ➜ MP4 / MOV:** Standardized H.264 (`libx264`, `yuv420p`), pristine AAC `320k` audio, and `+faststart` web optimization flags.
  - **MP4 ➜ WebM:** WebM VP9 (`libvpx-vp9`, `yuv420p`) with Opus `192k` audio.
  - **MP4 ⇄ MOV:** Bi-directional lossless/near-lossless transcoding.
  - ⚡ **Stream Copy (Instant Remuxing):** Use `--copy` (or `-c`) to switch containers between MP4 and MOV in under 1 second without re-encoding!
- 💎 **Visually Lossless by Default:**
  - Defaults to **CRF 14**, preset **slow**, and audio **320k**, perfectly preserving UI screen recordings, small fonts, and delicate lines.
- ⏱️ **Chrome Recorder WebM Duration Auto-Repair:**
  - Built-in EBML Cluster Reverse Parser inspects video tail in `< 0.01s`, resolving the common bug where Chrome/Chromium recordings report `0.0s` duration or jump straight to 100%.
- ⏸️ **Two-Stage Process Controls (Pause / Resume / Stop):**
  - **Pause / Resume:** Powered by native Linux `SIGSTOP` / `SIGCONT` signals. Freezes FFmpeg instantly with 0% CPU consumption and resumes flawlessly.
  - **Stop Conversion:** Cleanly terminates the active worker (`SIGKILL`), deletes partial files, and resets the interface.
- 📊 **Realtime Progress & Audio Notifications:**
  - Displays elapsed time, total time, speed factor, FPS, and ETA.
  - Interactive popup modal with subtle Web Audio chime upon 100% completion.
- 🌐 **Smart Process & Port Lifecycle:**
  - Automatic detection of running instances, fallback ports, and safe confirmation on tab close to prevent orphaned processes.

---

### 📥 Installation & Setup (One-Click)

On any Ubuntu / Linux machine, clone the repository and run the setup script:
```bash
git clone https://github.com/ntdat247/video-converter.git
cd video-converter
./install.sh
```
This automatically sets up the Python virtual environment, installs dependencies (`ffmpeg`, `zenity`, `flask`), creates symlinks for `vid` & `vid-gui` in `~/.local/bin`, and registers the app icon in the GNOME Application Menu.

---

### 🚀 Launching the GUI

You have three convenient ways to open the GUI:

1. **From the Terminal:**
   ```bash
   vid-gui
   # or:
   vid --gui
   ```
2. **From Ubuntu App Launcher (GNOME):**
   - Press the **Super** key (Windows key).
   - Search for **`vid`** or **`Video Converter`** and hit Enter!
3. **From Browser:**
   - Open [http://127.0.0.1:5050](http://127.0.0.1:5050) once the service is started.

---

### 📖 CLI Cheat Sheet

#### 1. Convert WebM ➜ MP4
```bash
# Automatically creates an MP4 file with the same base name:
vid "meeting_recording.webm"

# Specify a custom output file:
vid "meeting_recording.webm" -o "output.mp4"
```

#### 2. Convert MP4 ➜ WebM
```bash
# Auto-detects target format based on extension:
vid "screen_capture.mp4" -t webm
```

#### 3. Convert Between MP4 ⇄ MOV
```bash
# High quality re-encode (CRF 14):
vid "presentation.mp4" -t mov

# MOV to MP4:
vid "sample.mov" -t mp4

# ⚡ Stream Copy (Instant remux without re-encoding in ~0.5s):
vid "input.mp4" -t mov --copy
vid "input.mov" -t mp4 --copy
```

#### 4. Batch Processing Directories
```bash
# Convert all supported videos in the current folder to MP4:
vid -d . -t mp4

# Convert all MP4 files in a folder to WebM:
vid -d /path/to/source --from mp4 --to webm

# Convert all MOV files to MP4 and output to another directory:
vid -d /path/to/mov_dir --from mov --to mp4 -o /path/to/mp4_dir

# Recursively scan all subdirectories (-r):
vid -d /path/to/parent_folder -t mp4 -r
```

#### 5. Useful Automation Flags
```bash
# Auto-overwrite (-y) and delete source file after success (--delete-original):
vid "recording.webm" -y --delete-original

# Fast compression for lightweight drafts:
vid "demo.mp4" -t webm -q 22 --preset fast

# Run in background for long videos (2-4 hours):
nohup vid -d . -t mp4 > convert.log 2>&1 &
tail -f convert.log
```

---

### 🎛️ CLI Options Reference

| Option | Description | Default |
|---|---|---|
| `-g, --gui` | Launch the Web-based Graphical User Interface | `False` |
| `input` | Path to input video file or folder | *(Optional)* |
| `-o, --output` | Output file path or destination directory | Same base name |
| `-t, --to` | Target output format (`mp4`, `webm`, `mov`, `mkv`) | Auto-inferred |
| `--from` | Source format filter when scanning directories | All supported |
| `-c, --copy` | Stream copy mode (remux without re-encoding) | `False` |
| `-d, --dir` | Directory path containing video files | `None` |
| `-r, --recursive`| Recursively search subdirectories | `False` |
| `-q, --crf` | Constant Rate Factor (0–51, lower = higher quality) | **`14`** *(Visually Lossless)* |
| `-p, --preset` | FFmpeg encoding preset (`ultrafast`, `fast`, `slow`, ...) | **`slow`** |
| `-b, --audio-bitrate` | Audio bitrate (`320k` for MP4/MOV, `192k` for WebM) | **`320k`** |
| `-y, --yes` | Overwrite destination file without prompting | `False` |
| `--delete-original` | Automatically delete original file after successful conversion | `False` |

---

### 🧪 Automated Tests

Run the test suite directly from the project directory:
```bash
./venv/bin/python test_converter.py -v
```
All 9 automated test cases verify container parsing, stream copying, re-encoding, and error handling.

---
---

<a name="tiếng-việt"></a>
## Tiếng Việt

Ứng dụng chuyển đổi video đa năng, gọn nhẹ và chất lượng cao chuyên biệt cho hệ điều hành Ubuntu Linux. Hỗ trợ chuyển đổi mượt mà giữa các định dạng phổ biến: **WebM**, **MP4**, **MOV** (và **MKV**), tích hợp cả **Giao diện dòng lệnh (CLI)** và **Giao diện đồ họa trực quan (Web GUI)**.

---

### 🌟 Tính năng nổi bật

- 🖥️ **Đầy đủ 2 chế độ (CLI & GUI):**
  - **Giao diện dòng lệnh (CLI):** Cực nhanh, hỗ trợ viết script tự động hóa trong bash/terminal.
  - **Giao diện đồ họa (Web GUI):** Hiện đại, tích hợp hộp thoại chọn file/thư mục chuẩn GNOME Ubuntu (`zenity`), tự động đọc thông số video nguồn, thanh trượt CRF, chọn preset và khung terminal logs trực tiếp.
- 🔄 **Hỗ trợ chuyển đổi đa định dạng:**
  - **WebM ➜ MP4 / MOV:** Chuẩn hóa H.264 (`libx264`, `yuv420p`), âm thanh chất lượng cao AAC `320k`, cờ tối ưu hóa web `+faststart`.
  - **MP4 ➜ WebM:** Mã hóa VP9 (`libvpx-vp9`, `yuv420p`), âm thanh Opus `192k`.
  - **MP4 ⇄ MOV:** Chuyển đổi linh hoạt 2 chiều giữa MP4 và QuickTime MOV.
  - ⚡ **Stream Copy (Remux siêu tốc):** Hỗ trợ cờ `--copy` (hoặc `-c`) để chuyển đổi MP4 ⇄ MOV trong vòng chưa đầy 1 giây mà không cần nén lại.
- 💎 **Độ nét tối đa (Visually Lossless mặc định):**
  - Mặc định sử dụng **CRF 14**, preset **slow**, audio **320k** bảo toàn 100% độ sắc nét của chữ, giao diện phần mềm và bài giảng đào tạo.
- ⏱️ **Tự động sửa thời lượng WebM (Chrome Recorder):**
  - Tích hợp bộ quét EBML Cluster quét ngược đuôi file (< 0.01s), khắc phục triệt để lỗi video WebM quay từ Chrome bị báo `0.0s` hoặc nhảy 100% tiến độ ảo.
- ⏸️ **Bộ điều khiển tiến trình 2 trạng thái (Tạm dừng / Tiếp tục / Dừng hẳn):**
  - **Tạm dừng / Tiếp tục:** Hoạt động dựa trên tín hiệu chuẩn Linux `SIGSTOP` / `SIGCONT`. Đóng băng tiến trình với 0% CPU và tiếp tục ngay khung hình đang dừng.
  - **Dừng hoàn toàn:** Hủy tác vụ an toàn (`SIGKILL`), dọn dẹp file tạm và đưa giao diện về trạng thái sẵn sàng.
- 📊 **Tiến độ trực quan & Chuông báo hoàn tất:**
  - Hiển thị đầy đủ thời gian HH:MM:SS, tốc độ nén, FPS và thời gian còn lại (ETA).
  - Tự động bật Popup chúc mừng kèm âm thanh chuông nhẹ qua Web Audio API khi hoàn tất 100%.
- 🌐 **Quản lý tiến trình & Cổng thông minh:**
  - Tự động phát hiện phiên bản đang chạy, tự đổi cổng khi trùng lặp và hỏi xác nhận khi đóng tab trình duyệt để giải phóng tài nguyên.

---

### 📥 Cài đặt nhanh trên máy mới (1 Lệnh duy nhất)

Khi clone mã nguồn về bất kỳ máy Ubuntu nào khác, bạn chỉ cần chạy script cài đặt tự động:
```bash
git clone https://github.com/ntdat247/video-converter.git
cd video-converter
./install.sh
```
Lệnh này sẽ tự động: kiểm tra `ffmpeg`/`zenity`, tạo môi trường ảo Python `venv`, cài đặt thư viện, gắn lệnh `vid` & `vid-gui` vào terminal (`~/.local/bin`), và đăng ký biểu tượng icon vào danh sách ứng dụng Ubuntu (App Launcher).

---

### 🚀 Khởi chạy Giao diện đồ họa (GUI)

Bạn có 3 cách rất thuận tiện để mở giao diện:

1. **Từ terminal:**
   ```bash
   vid-gui
   # hoặc:
   vid --gui
   ```
2. **Từ danh sách ứng dụng Ubuntu (App Launcher):**
   - Nhấn phím **Super** (phím Windows) trên bàn phím.
   - Gõ tìm kiếm: **`vid`** hoặc **`Video Converter`** rồi nhấn Enter!
3. **Từ trình duyệt:**
   - Truy cập [http://127.0.0.1:5050](http://127.0.0.1:5050) sau khi khởi động ứng dụng.

---

### 📖 Bảng tổng hợp các lệnh dòng lệnh (CLI Cheat Sheet)

#### 1. Chuyển đổi WebM ➜ MP4
```bash
# Mặc định tự động xuất file MP4 cùng tên:
vid "video_training.webm"

# Chỉ định tên file kết quả:
vid "video_training.webm" -o "output.mp4"
```

#### 2. Chuyển đổi MP4 ➜ WebM
```bash
# Tự động xuất sang file WebM theo đuôi mở rộng:
vid "demo.mp4" -t webm
```

#### 3. Chuyển đổi qua lại giữa MP4 ⇄ MOV
```bash
# MP4 sang MOV (mã hóa chất lượng cao CRF 14):
vid "presentation.mp4" -t mov

# MOV sang MP4:
vid "presentation.mov" -t mp4

# ⚡ Chuyển đổi siêu tốc không nén lại (Stream Copy trong 0.5 giây):
vid "video.mp4" -t mov --copy
vid "video.mov" -t mp4 --copy
```

#### 4. Chuyển đổi hàng loạt trong thư mục
```bash
# Chuyển đổi toàn bộ video trong thư mục hiện tại sang MP4:
vid -d . -t mp4

# Chuyển đổi tất cả file MP4 sang WebM:
vid -d /path/to/folder --from mp4 --to webm

# Chuyển đổi tất cả file MOV sang MP4 và lưu sang thư mục khác:
vid -d /path/to/mov_folder --from mov --to mp4 -o /path/to/mp4_folder

# Quét đệ quy tất cả các thư mục con bên trong (-r):
vid -d /path/to/folder -t mp4 -r
```

#### 5. Tùy chọn tiện ích tự động hóa
```bash
# Tự động ghi đè (-y) và xóa file gốc sau khi convert thành công (--delete-original):
vid "video.webm" -y --delete-original

# Xuất nhanh file nhẹ hơn cho video nháp:
vid "video.mp4" -t webm -q 22 --preset fast

# Chạy ngầm trong nền cho video dài (2-4 tiếng):
nohup vid -d . -t mp4 > convert.log 2>&1 &
tail -f convert.log
```

---

### 🎛️ Bảng giải thích toàn bộ tham số (CLI Options)

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `-g, --gui` | Khởi chạy giao diện đồ họa Web GUI trực quan | `False` |
| `input` | File video hoặc thư mục cần chuyển đổi | *(Tùy chọn)* |
| `-o, --output` | Đường dẫn file kết quả hoặc thư mục kết quả | Tự động đặt cùng tên gốc |
| `-t, --to` | Định dạng đích mong muốn (`mp4`, `webm`, `mov`, `mkv`) | Tự suy đoán từ nguồn / đích |
| `--from` | Lọc định dạng nguồn khi quét thư mục | Tất cả video hợp lệ |
| `-c, --copy` | Sao chép luồng trực tiếp không nén lại (cực nhanh cho MP4 ⇄ MOV) | `False` |
| `-d, --dir` | Chỉ định thư mục chứa các file video | `None` |
| `-r, --recursive` | Tìm kiếm video trong cả các thư mục con | `False` |
| `-q, --crf` | Chỉ số chất lượng video (0 - 51, càng nhỏ càng nét) | **`14`** *(Visually Lossless)* |
| `-p, --preset` | Tốc độ mã hóa (`ultrafast`, `fast`, `medium`, `slow`,...) | **`slow`** |
| `-b, --audio-bitrate` | Bitrate âm thanh (`320k` cho MP4/MOV, `192k` cho WebM Opus) | **`320k`** |
| `-y, --yes` | Tự động ghi đè nếu file kết quả đã có sẵn | `False` |
| `--delete-original` | Xóa file video gốc sau khi convert thành công | `False` |

---

### 🧪 Kiểm thử tự động (Unit Tests)

Chạy bộ kiểm thử tự động ngay tại thư mục dự án:
```bash
./venv/bin/python test_converter.py -v
```
Toàn bộ 9/9 bài kiểm thử đều được xác minh tự động và đạt chuẩn (PASS).
