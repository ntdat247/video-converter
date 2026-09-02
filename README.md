# vid2 - Universal Video Converter (WebM ⇄ MP4 ⇄ MOV) on Ubuntu

Ứng dụng chuyển đổi video đa năng, gọn nhẹ và chất lượng cao giữa các định dạng phổ biến nhất: **WebM**, **MP4**, **MOV** (và **MKV**), hỗ trợ cả **Giao diện dòng lệnh (CLI)** và **Giao diện đồ họa trực quan (GUI)** trên Ubuntu Linux.

---

## 🌟 Tính năng nổi bật

- 🖥️ **Đầy đủ 2 chế độ:** 
  - **Giao diện dòng lệnh (CLI):** Cực nhanh, hỗ trợ kịch bản bash/terminal.
  - **Giao diện đồ họa (GUI):** Hiện đại, tích hợp hộp thoại chọn file/thư mục chuẩn GNOME Ubuntu (Zenity), xem trước thông số video, thanh trượt CRF, chọn preset và thanh tiến trình thời gian thực.
- 🔄 **Hỗ trợ chuyển đổi đa định dạng:**
  - **WebM ➜ MP4 / MOV:** Chuẩn hóa H.264 (`libx264`, `yuv420p`), AAC `320k`, cờ `+faststart`.
  - **MP4 ➜ WebM:** Mã hóa VP9 (`libvpx-vp9`, `yuv420p`), Opus `192k`.
  - **MP4 ⇄ MOV:** Chuyển đổi linh hoạt 2 chiều giữa MP4 và QuickTime MOV.
  - ⚡ **Stream Copy (Remux cực nhanh):** Hỗ trợ cờ `--copy` (hoặc `-c`) để chuyển đổi MP4 ⇄ MOV trong vòng chưa đầy 1 giây mà không cần nén lại video.
- 💎 **Độ nét tối đa (Visually Lossless mặc định):** Mặc định sử dụng **CRF 14**, preset **slow**, audio **320k** bảo toàn 100% độ sắc nét của chữ và giao diện ứng dụng.
- ⏱️ **Tự động sửa thời lượng WebM (Chrome Recorder):** Tích hợp EBML Cluster Parser quét ngược đuôi file (< 0.01s), khắc phục lỗi WebM Chrome bị báo `0.0s` hoặc nhảy 100% tiến độ sớm.
- 📊 **Tiến độ trực quan (Realtime HH:MM:SS):** Hiển thị thời gian `Đang xử lý 00:25:06 / 03:05:57 (13.5%)`, tốc độ xử lý (speed, fps) và thời gian còn lại (ETA).

---

## 🚀 Khởi chạy Giao diện đồ họa (GUI)

Bạn có 3 cách rất thuận tiện để mở giao diện đồ họa:

1. **Từ terminal:**
   ```bash
   vid2-gui
   # hoặc:
   vid2 --gui
   ```
2. **Từ danh sách ứng dụng Ubuntu (App Launcher):**
   - Nhấn phím **Super** (phím Windows) trên bàn phím.
   - Gõ tìm kiếm: **`vid2`** hoặc **`Video Converter`** rồi nhấn Enter!

---

## 📖 Bảng tổng hợp các lệnh dòng lệnh (CLI Cheat Sheet)

### 1. Chuyển đổi WebM ➜ MP4
```bash
# Mặc định tự động xuất file MP4 cùng tên:
vid2 "video.webm"

# Chỉ định tên file kết quả:
vid2 "video.webm" -o "output.mp4"
```

### 2. Chuyển đổi MP4 ➜ WebM
```bash
# Tự động xuất sang file WebM (do file nguồn là MP4):
vid2 "video.mp4"

# Hoặc chỉ định rõ định dạng đích bằng -t:
vid2 "video.mp4" -t webm
```

### 3. Chuyển đổi qua lại giữa MP4 ⇄ MOV
```bash
# MP4 sang MOV (mã hóa chất lượng cao CRF 14):
vid2 "video.mp4" -t mov

# MOV sang MP4:
vid2 "video.mov" -t mp4

# ⚡ Chuyển đổi siêu tốc không nén lại (Stream Copy trong 0.5 giây):
vid2 "video.mp4" -t mov --copy
vid2 "video.mov" -t mp4 --copy
```

### 4. Chuyển đổi hàng loạt trong thư mục
```bash
# Chuyển đổi toàn bộ video trong thư mục hiện tại sang MP4:
vid2 -d . -t mp4

# Chuyển đổi tất cả file MP4 sang WebM:
vid2 -d /path/to/folder --from mp4 --to webm

# Chuyển đổi tất cả file MOV sang MP4 và lưu sang thư mục khác:
vid2 -d /path/to/mov_folder --from mov --to mp4 -o /path/to/mp4_folder

# Quét đệ quy tất cả các thư mục con bên trong (-r):
vid2 -d /path/to/folder -t mp4 -r
```

### 5. Tùy chọn tiện ích khác
```bash
# Tự động ghi đè (-y) và xóa file gốc sau khi convert thành công (--delete-original):
vid2 "video.webm" -y --delete-original

# Xuất nhanh file nhẹ hơn cho video thông thường:
vid2 "video.mp4" -t webm -q 22 --preset fast

# Chạy ngầm trong nền cho video dài (2-4 tiếng):
nohup vid2 -d . -t mp4 > convert.log 2>&1 &
tail -f convert.log
```

---

## 🎛️ Bảng giải thích toàn bộ tham số (CLI Options)

| Tham số | Ý nghĩa | Mặc định |
|---|---|---|
| `-g, --gui` | Khởi chạy giao diện đồ họa Web GUI trực quan | `False` |
| `input` | File video hoặc thư mục cần chuyển đổi | (Tùy chọn) |
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

## 🧪 Kiểm thử tự động (Unit Tests)

Trong thư mục `/home/dat/Applications/vid2`:
```bash
./venv/bin/python test_converter.py -v
```
Toàn bộ 9/9 bài kiểm thử đều được tự động xác minh.
