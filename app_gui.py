"""
app_gui.py - Giao diện Web GUI hiện đại cho ứng dụng vid2
Cung cấp đầy đủ tính năng tương đương CLI: Đơn file, hàng loạt, tùy biến codec, realtime progress SSE.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, Response, jsonify, render_template_string, request

from converter import (
    ConversionProgress,
    ConversionResult,
    SUPPORTED_FORMATS,
    check_dependencies,
    convert_file,
    format_duration,
    get_default_target_ext,
    get_media_info,
)

app = Flask(__name__)

# State quản lý tiến trình chuyển đổi toàn cục (dùng RLock tránh deadlock lồng nhau)
state_lock = threading.RLock()
current_task = {
    "is_running": False,
    "is_paused": False,
    "should_cancel": False,
    "total_files": 0,
    "current_file_idx": 0,
    "current_filename": "",
    "percentage": 0.0,
    "current_time_str": "00:00",
    "total_time_str": "00:00",
    "speed": "--",
    "fps": 0.0,
    "eta_str": "--:--",
    "status": "idle",  # idle, running, completed, cancelled, error
    "message": "",
    "history": [],
    "logs": [],
}

event_listeners: List[queue.Queue] = []
cancel_event = threading.Event()


def broadcast_state():
    """Gửi trạng thái mới nhất tới tất cả client SSE đang mở."""
    with state_lock:
        data = json.dumps(current_task)
    for q in list(event_listeners):
        try:
            q.put_nowait(data)
        except Exception:
            pass


def add_log(level: str, msg: str):
    """Ghi một dòng log có timestamp và broadcast ngay tới web UI."""
    now_str = time.strftime("%H:%M:%S")
    entry = {"time": now_str, "level": level, "msg": msg}
    with state_lock:
        current_task["logs"].append(entry)
        if len(current_task["logs"]) > 500:
            current_task["logs"].pop(0)
    broadcast_state()


def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>vid2 - Video Converter</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-border: #334155;
      --primary: #38bdf8;
      --primary-hover: #0ea5e9;
      --success: #10b981;
      --danger: #ef4444;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px 16px;
    }
    .container {
      max-width: 960px;
      margin: 0 auto;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
    }
    h1 {
      font-size: 1.75rem;
      font-weight: 700;
      color: var(--primary);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .tag {
      font-size: 0.8rem;
      background: #0369a1;
      color: #e0f2fe;
      padding: 2px 8px;
      border-radius: 9999px;
      font-weight: 600;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .card-title {
      font-size: 1.1rem;
      font-weight: 600;
      margin-bottom: 16px;
      color: #cbd5e1;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      background: #0f172a;
      padding: 4px;
      border-radius: 8px;
    }
    .tab-btn {
      flex: 1;
      padding: 8px 16px;
      border: none;
      background: transparent;
      color: var(--text-muted);
      font-weight: 600;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .tab-btn.active {
      background: var(--card-bg);
      color: var(--primary);
      box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    .input-group {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }
    input[type="text"], select {
      flex: 1;
      background: #0f172a;
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 0.95rem;
      outline: none;
    }
    input[type="text"]:focus, select:focus {
      border-color: var(--primary);
    }
    button {
      padding: 10px 18px;
      border-radius: 8px;
      border: none;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .btn-primary { background: var(--primary); color: #0f172a; }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-secondary { background: #334155; color: var(--text); }
    .btn-secondary:hover { background: #475569; }
    .btn-danger { background: var(--danger); color: white; }
    .btn-danger:hover { background: #dc2626; }
    .btn-warning { background: #f59e0b; color: #0f172a; }
    .btn-warning:hover { background: #d97706; }
    .btn-success { background: #10b981; color: white; }
    .btn-success:hover { background: #059669; }

    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    @media (max-width: 640px) {
      .grid-2 { grid-template-columns: 1fr; }
    }
    .form-group {
      margin-bottom: 14px;
    }
    label {
      display: block;
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    .range-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    input[type="range"] {
      flex: 1;
      accent-color: var(--primary);
    }
    .checkbox-group {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 10px;
    }
    .checkbox-label {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.9rem;
      color: #cbd5e1;
      cursor: pointer;
    }
    .checkbox-label input {
      accent-color: var(--primary);
      width: 16px;
      height: 16px;
    }

    /* Media Info Box */
    .media-info-box {
      background: #0f172a;
      border: 1px dashed var(--card-border);
      border-radius: 8px;
      padding: 12px 16px;
      margin-bottom: 16px;
      display: none;
    }
    .media-info-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 8px 16px;
      font-size: 0.85rem;
    }
    .media-info-item span:first-child { color: var(--text-muted); }
    .media-info-item span:last-child { color: var(--primary); font-weight: 600; }

    /* Progress Section */
    .progress-bar-bg {
      background: #0f172a;
      border-radius: 9999px;
      height: 18px;
      overflow: hidden;
      margin: 12px 0 8px 0;
      position: relative;
    }
    .progress-bar-fill {
      background: linear-gradient(90deg, #0ea5e9, #10b981);
      height: 100%;
      width: 0%;
      border-radius: 9999px;
      transition: width 0.3s ease;
    }
    .progress-meta {
      display: flex;
      justify-content: space-between;
      font-size: 0.85rem;
      color: var(--text-muted);
    }

    /* Table */
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      margin-top: 12px;
    }
    th, td {
      padding: 8px 12px;
      text-align: left;
      border-bottom: 1px solid var(--card-border);
    }
    th { color: var(--text-muted); font-weight: 600; }
    .badge-success { color: var(--success); font-weight: 600; }
    .badge-error { color: var(--danger); font-weight: 600; }

    /* Ubuntu Terminal Log Box */
    .terminal-card {
      background: #0c1017;
      border: 1px solid #30363d;
      border-radius: 10px;
      overflow: hidden;
      margin-bottom: 20px;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
    }
    .terminal-header {
      background: #161b22;
      padding: 8px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid #30363d;
    }
    .terminal-dots {
      display: flex;
      align-items: center;
      gap: 7px;
    }
    .terminal-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      display: inline-block;
    }
    .dot-red { background: #ff5f56; }
    .dot-yellow { background: #ffbd2e; }
    .dot-green { background: #27c93f; }
    .terminal-body {
      height: 220px;
      overflow-y: auto;
      padding: 12px 14px;
      font-family: 'Ubuntu Mono', 'JetBrains Mono', 'Consolas', 'Courier New', monospace;
      font-size: 0.83rem;
      line-height: 1.55;
      color: #e6edf3;
      background: #0d1117;
      word-break: break-word;
    }
    .terminal-body::-webkit-scrollbar {
      width: 8px;
    }
    .terminal-body::-webkit-scrollbar-track {
      background: #0d1117;
    }
    .terminal-body::-webkit-scrollbar-thumb {
      background: #30363d;
      border-radius: 4px;
    }
    .terminal-body::-webkit-scrollbar-thumb:hover {
      background: #484f58;
    }
    .log-line {
      margin-bottom: 4px;
    }
    .log-time {
      color: #6e7681;
      margin-right: 6px;
    }
    .log-info { color: #38bdf8; font-weight: 600; }
    .log-debug { color: #8b949e; }
    .log-warn { color: #e3b341; font-weight: 600; }
    .log-error { color: #f85149; font-weight: 600; }

    /* Modal thông báo hoàn thành */
    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(6px);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 9999;
      animation: fadeIn 0.25s ease-out;
    }
    .modal-card {
      background: #1e293b;
      border: 1px solid #38bdf8;
      border-radius: 16px;
      padding: 32px 28px;
      max-width: 480px;
      width: 90%;
      text-align: center;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6), 0 0 30px rgba(56, 189, 248, 0.2);
      animation: scaleUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    @keyframes scaleUp { from { transform: scale(0.9); opacity: 0; } to { transform: scale(1); opacity: 1; } }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>vid2 Video Converter <span class="tag">Ubuntu</span></h1>
        <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 2px;">
          Chuyển đổi WebM ⇄ MP4 ⇄ MOV chất lượng cao &amp; Stream Copy siêu tốc
        </p>
      </div>
      <div style="display: flex; align-items: center; gap: 12px;">
        <span style="color: var(--text-muted); font-size: 0.85rem;">v2.0</span>
      </div>
    </header>

    <!-- Source Selection -->
    <div class="card">
      <div class="tabs">
        <button class="tab-btn active" id="tabSingle" onclick="setMode('single')">🎬 Chuyển đổi 1 File</button>
        <button class="tab-btn" id="tabBatch" onclick="setMode('batch')">📁 Chuyển đổi Thư mục (Hàng loạt)</button>
      </div>

      <!-- Single file input -->
      <div id="singleSection">
        <label for="inputPath">Đường dẫn file video nguồn (.webm, .mp4, .mov, .mkv):</label>
        <div class="input-group">
          <input type="text" id="inputPath" placeholder="/home/.../video.webm" oninput="onInputChanged()">
          <button type="button" class="btn-secondary" onclick="browseFile(this)">Duyệt file...</button>
        </div>
        <div id="mediaInfoBox" class="media-info-box">
          <div class="media-info-grid" id="mediaInfoGrid"></div>
        </div>
      </div>

      <!-- Batch folder input -->
      <div id="batchSection" style="display: none;">
        <label for="inputDir">Thư mục chứa video nguồn:</label>
        <div class="input-group">
          <input type="text" id="inputDir" placeholder="/home/.../videos_folder" oninput="onDirChanged()">
          <button type="button" class="btn-secondary" onclick="browseDir('inputDir', this)">Duyệt thư mục...</button>
        </div>
        <label for="outputDir">Thư mục lưu kết quả (để trống = lưu cùng thư mục nguồn):</label>
        <div class="input-group">
          <input type="text" id="outputDir" placeholder="Tùy chọn: thư mục xuất kết quả...">
          <button type="button" class="btn-secondary" onclick="browseDir('outputDir', this)">Duyệt thư mục...</button>
        </div>
      </div>
    </div>

    <!-- Output & Quality Settings -->
    <div class="card">
      <div class="card-title">⚙️ Cài đặt đầu ra &amp; Chất lượng</div>
      
      <div class="grid-2">
        <div class="form-group">
          <label for="targetFormat">Định dạng đích (Target Format):</label>
          <select id="targetFormat" onchange="onFormatChanged()">
            <option value="mp4" selected>MP4 (Chuẩn H.264 + AAC, tương thích 100%)</option>
            <option value="webm">WebM (VP9 + Opus, chuẩn web Google/Chrome)</option>
            <option value="mov">MOV (QuickTime Apple / Video Editor)</option>
            <option value="mkv">MKV (Matroska)</option>
          </select>
        </div>

        <div class="form-group">
          <label for="preset">Tốc độ nén (Preset):</label>
          <select id="preset">
            <option value="slow" selected>slow (Chất lượng cao nhất, tối ưu viền chữ)</option>
            <option value="medium">medium (Cân bằng tiêu chuẩn)</option>
            <option value="fast">fast (Nhanh hơn)</option>
            <option value="ultrafast">ultrafast (Siêu tốc độ)</option>
          </select>
        </div>
      </div>

      <div class="grid-2">
        <div class="form-group">
          <label for="crfRange">Độ nét / Chất lượng (CRF): <span id="crfValue" style="color: var(--primary); font-weight: bold;">14</span> (<span id="crfLabel">Visually Lossless / Cực nét</span>)</label>
          <div class="range-wrap">
            <input type="range" id="crfRange" min="0" max="51" value="14" oninput="updateCRF(this.value)">
          </div>
        </div>

        <div class="form-group">
          <label for="audioBitrate">Chất lượng âm thanh (Audio Bitrate):</label>
          <select id="audioBitrate">
            <option value="320k" selected>320 kbps (Cao cấp / Giọng nói trong trẻo)</option>
            <option value="256k">256 kbps</option>
            <option value="192k">192 kbps (Chuẩn phòng thu)</option>
            <option value="128k">128 kbps (Tiêu chuẩn nhẹ)</option>
          </select>
        </div>
      </div>

      <div class="checkbox-group">
        <label class="checkbox-label" id="copyStreamsLabel">
          <input type="checkbox" id="copyStreams">
          <span>⚡ <strong>Stream Copy (--copy):</strong> Chuyển đổi định dạng siêu tốc không nén lại (<1s cho MP4 ⇄ MOV)</span>
        </label>
        <label class="checkbox-label">
          <input type="checkbox" id="overwrite" checked>
          <span>Ghi đè file nếu đã tồn tại (-y)</span>
        </label>
        <label class="checkbox-label">
          <input type="checkbox" id="deleteOriginal">
          <span>Xóa file gốc sau khi chuyển đổi thành công (--delete-original)</span>
        </label>
        <label class="checkbox-label" id="recursiveLabel" style="display: none;">
          <input type="checkbox" id="recursive">
          <span>Quét đệ quy tất cả thư mục con (-r)</span>
        </label>
      </div>
    </div>

    <!-- Actions & Live Progress -->
    <div class="card">
      <div style="display: flex; gap: 12px; align-items: center; justify-content: space-between; flex-wrap: wrap;">
        <div style="display: flex; gap: 10px; align-items: center;">
          <button class="btn-primary" id="startBtn" onclick="startConvert()">▶ Bắt đầu chuyển đổi</button>
          <div id="runningControls" style="display: none; gap: 10px; align-items: center;">
            <button class="btn-warning" id="pauseResumeBtn" onclick="togglePauseResume()">
              <span id="pauseResumeIcon">■</span> <span id="pauseResumeText">Tạm dừng</span>
            </button>
            <button class="btn-danger" id="stopBtn" onclick="stopConvert()">
              ⏻ Dừng hoàn toàn
            </button>
          </div>
        </div>
        <div id="statusBadge" style="font-weight: 600; font-size: 0.9rem; color: var(--text-muted);">Sẵn sàng</div>
      </div>

      <div id="progressArea" style="display: none; margin-top: 16px;">
        <div style="display: flex; justify-content: space-between; font-size: 0.9rem; font-weight: 600;">
          <span id="progressFile">Đang xử lý...</span>
          <span id="progressPercent" style="color: var(--primary);">0%</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" id="progressBar"></div>
        </div>
        <div class="progress-meta">
          <span id="progressTime">00:00 / 00:00</span>
          <span id="progressSpeed">--</span>
          <span id="progressEta">ETA: --:--</span>
        </div>
      </div>
    </div>

    <!-- Ubuntu Terminal Logs Box -->
    <div class="terminal-card" id="terminalCard">
      <div class="terminal-header">
        <div class="terminal-dots">
          <span class="terminal-dot dot-red"></span>
          <span class="terminal-dot dot-yellow"></span>
          <span class="terminal-dot dot-green"></span>
          <span style="font-family: 'Ubuntu Mono', monospace; font-size: 0.85rem; font-weight: 600; color: #c9d1d9; margin-left: 6px;">
            terminal@ubuntu: vid2 process logs
          </span>
        </div>
        <div style="display: flex; align-items: center; gap: 10px; font-size: 0.8rem;">
          <label style="display: flex; align-items: center; gap: 5px; color: #8b949e; cursor: pointer; margin: 0;">
            <input type="checkbox" id="autoScrollLog" checked style="accent-color: var(--primary); width: 14px; height: 14px;"> Tự cuộn
          </label>
          <button class="btn-secondary" style="padding: 3px 8px; font-size: 0.75rem;" onclick="copyLogs()">📋 Sao chép</button>
          <button class="btn-secondary" style="padding: 3px 8px; font-size: 0.75rem;" onclick="clearLogs()">🧹 Xóa</button>
        </div>
      </div>
      <div class="terminal-body" id="terminalBody">
        <div style="color: #8b949e;">[Sẵn sàng] Chờ lệnh chuyển đổi...</div>
      </div>
    </div>

    <!-- History / Results Table -->
    <div class="card" id="historyCard" style="display: none;">
      <div class="card-title">📋 Lịch sử / Báo cáo kết quả</div>
      <div style="overflow-x: auto;">
        <table id="historyTable">
          <thead>
            <tr>
              <th>File nguồn</th>
              <th>File kết quả</th>
              <th>Dung lượng</th>
              <th>Thời gian</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody id="historyBody"></tbody>
        </table>
    </div>
  </div>

  <!-- Modal thông báo hoàn tất chuyển đổi -->
  <div id="completionModal" class="modal-overlay" style="display: none;">
    <div class="modal-card">
      <div style="font-size: 3.5rem; margin-bottom: 8px;">🎉</div>
      <h2 style="color: #10b981; font-size: 1.6rem; margin-bottom: 8px;">Chuyển đổi hoàn tất 100%!</h2>
      <p style="color: #94a3b8; font-size: 0.95rem; margin-bottom: 18px;">
        File video đã được xử lý xong với chất lượng cao và sẵn sàng sử dụng.
      </p>
      <div id="completionDetails" style="background: #0f172a; padding: 14px; border-radius: 10px; text-align: left; font-size: 0.9rem; color: #cbd5e1; margin-bottom: 22px; border: 1px solid #334155; line-height: 1.6;">
      </div>
      <div style="display: flex; justify-content: center; gap: 12px;">
        <button type="button" class="btn-primary" style="padding: 10px 24px; font-size: 1rem;" onclick="closeCompletionModal()">✔ Tuyệt vời / Đóng</button>
      </div>
    </div>
  </div>

  <script>
    let currentMode = 'single';

    function setMode(mode) {
      currentMode = mode;
      document.getElementById('tabSingle').classList.toggle('active', mode === 'single');
      document.getElementById('tabBatch').classList.toggle('active', mode === 'batch');
      document.getElementById('singleSection').style.display = mode === 'single' ? 'block' : 'none';
      document.getElementById('batchSection').style.display = mode === 'batch' ? 'block' : 'none';
      document.getElementById('recursiveLabel').style.display = mode === 'batch' ? 'flex' : 'none';
    }

    function updateCRF(val) {
      document.getElementById('crfValue').textContent = val;
      const lbl = document.getElementById('crfLabel');
      const n = parseInt(val);
      if (n === 0) lbl.textContent = "Lossless tuyệt đối";
      else if (n <= 16) lbl.textContent = "Visually Lossless / Cực nét";
      else if (n <= 22) lbl.textContent = "Chất lượng cao cân bằng";
      else if (n <= 28) lbl.textContent = "File nhẹ";
      else lbl.textContent = "Rất nhẹ / Giảm chi tiết";
    }

    async function browseFile(btn) {
      const origText = btn ? btn.textContent : "Duyệt file...";
      if (btn) {
        btn.textContent = "⏳ Đang mở...";
        btn.disabled = true;
      }
      try {
        const res = await fetch('/api/browse-file', { method: 'POST' });
        const data = await res.json();
        if (data.path) {
          document.getElementById('inputPath').value = data.path;
          onInputChanged();
        } else if (data.error) {
          alert("Không thể mở hộp chọn file: " + data.error);
        }
      } catch (err) {
        alert("Lỗi kết nối khi mở hộp chọn file: " + err);
      } finally {
        if (btn) {
          btn.textContent = origText;
          btn.disabled = false;
        }
      }
    }

    async function browseDir(fieldId, btn) {
      const origText = btn ? btn.textContent : "Duyệt thư mục...";
      if (btn) {
        btn.textContent = "⏳ Đang mở...";
        btn.disabled = true;
      }
      try {
        const res = await fetch('/api/browse-dir', { method: 'POST' });
        const data = await res.json();
        if (data.path) {
          document.getElementById(fieldId).value = data.path;
        } else if (data.error) {
          alert("Không thể mở hộp chọn thư mục: " + data.error);
        }
      } catch (err) {
        alert("Lỗi kết nối khi mở hộp chọn thư mục: " + err);
      } finally {
        if (btn) {
          btn.textContent = origText;
          btn.disabled = false;
        }
      }
    }

    let inputTimeout = null;
    function onInputChanged() {
      clearTimeout(inputTimeout);
      inputTimeout = setTimeout(fetchMediaInfo, 300);
    }

    async function fetchMediaInfo() {
      const path = document.getElementById('inputPath').value.trim();
      const box = document.getElementById('mediaInfoBox');
      const grid = document.getElementById('mediaInfoGrid');
      if (!path) {
        box.style.display = 'none';
        return;
      }
      try {
        const res = await fetch('/api/media-info', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: path })
        });
        const data = await res.json();
        if (data.success) {
          grid.innerHTML = `
            <div class="media-info-item"><span>Dung lượng:</span> <span>${data.size}</span></div>
            <div class="media-info-item"><span>Thời lượng:</span> <span>${data.duration_formatted} (${data.duration}s)</span></div>
            <div class="media-info-item"><span>Độ phân giải:</span> <span>${data.resolution}</span></div>
            <div class="media-info-item"><span>Video Codec:</span> <span>${data.video_codec}</span></div>
            <div class="media-info-item"><span>Audio Codec:</span> <span>${data.audio_codec || 'Không có'}</span></div>
          `;
          box.style.display = 'block';

          // Gợi ý định dạng đích thông minh
          const ext = path.split('.').pop().toLowerCase();
          const targetSelect = document.getElementById('targetFormat');
          if (ext === 'webm' || ext === 'mov') targetSelect.value = 'mp4';
          else if (ext === 'mp4') targetSelect.value = 'webm';
        } else {
          box.style.display = 'none';
        }
      } catch {
        box.style.display = 'none';
      }
    }

    function onDirChanged() {}
    function onFormatChanged() {}

    async function startConvert() {
      const mode = currentMode;
      const payload = {
        mode: mode,
        input_path: document.getElementById('inputPath').value.trim(),
        input_dir: document.getElementById('inputDir').value.trim(),
        output_dir: document.getElementById('outputDir').value.trim(),
        target_format: document.getElementById('targetFormat').value,
        crf: parseInt(document.getElementById('crfRange').value),
        preset: document.getElementById('preset').value,
        audio_bitrate: document.getElementById('audioBitrate').value,
        copy_streams: document.getElementById('copyStreams').checked,
        overwrite: document.getElementById('overwrite').checked,
        delete_original: document.getElementById('deleteOriginal').checked,
        recursive: document.getElementById('recursive').checked,
      };

      if (mode === 'single' && !payload.input_path) {
        alert("Vui lòng chọn file video cần chuyển đổi!");
        return;
      }
      if (mode === 'batch' && !payload.input_dir) {
        alert("Vui lòng chọn thư mục chứa video!");
        return;
      }

      try {
        const res = await fetch('/api/convert', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!data.success) {
          alert("Lỗi: " + data.error);
        }
      } catch (err) {
        alert("Không thể kết nối đến server: " + err);
      }
    }

    async function togglePauseResume() {
      if (!window.lastState) return;
      if (window.lastState.is_paused) {
        try {
          await fetch('/api/resume', { method: 'POST' });
        } catch (err) {
          alert("Lỗi khi tiếp tục: " + err);
        }
      } else {
        try {
          await fetch('/api/pause', { method: 'POST' });
        } catch (err) {
          alert("Lỗi khi tạm dừng: " + err);
        }
      }
    }

    async function stopConvert() {
      if (confirm("Bạn có chắc chắn muốn dừng hoàn toàn việc convert không? File đang chuyển đổi dở sẽ bị hủy.")) {
        try {
          await fetch('/api/stop', { method: 'POST' });
        } catch (err) {
          alert("Lỗi khi dừng: " + err);
        }
      }
    }

    // Kết nối SSE nhận tiến trình realtime
    function initSSE() {
      const evtSource = new EventSource('/api/events');
      evtSource.onmessage = function(e) {
        try {
          const state = JSON.parse(e.data);
          updateUIWithState(state);
        } catch {}
      };
    }

    function closeCompletionModal() {
      document.getElementById('completionModal').style.display = 'none';
    }

    function playSuccessChime() {
      try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return;
        const ctx = new AudioContext();
        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(523.25, now);
        osc.frequency.setValueAtTime(659.25, now + 0.12);
        osc.frequency.setValueAtTime(783.99, now + 0.24);
        osc.frequency.setValueAtTime(1046.50, now + 0.36);
        gain.gain.setValueAtTime(0.15, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.7);
        osc.start(now);
        osc.stop(now + 0.7);
      } catch {}
    }

    let hasShownCompletionModal = false;

    function updateUIWithState(state) {
      const startBtn = document.getElementById('startBtn');
      const runningControls = document.getElementById('runningControls');
      const pauseResumeBtn = document.getElementById('pauseResumeBtn');
      const pauseResumeIcon = document.getElementById('pauseResumeIcon');
      const pauseResumeText = document.getElementById('pauseResumeText');
      const progressArea = document.getElementById('progressArea');
      const statusBadge = document.getElementById('statusBadge');
      const historyCard = document.getElementById('historyCard');

      if (state.is_running) {
        hasShownCompletionModal = false;
        startBtn.style.display = 'none';
        runningControls.style.display = 'inline-flex';
        progressArea.style.display = 'block';

        if (state.is_paused) {
          statusBadge.textContent = '⏸ Đang tạm dừng';
          statusBadge.style.color = '#f59e0b';
          pauseResumeBtn.className = 'btn-success';
          pauseResumeIcon.textContent = '▶';
          pauseResumeText.textContent = 'Tiếp tục (Resume)';
        } else {
          statusBadge.textContent = state.total_files > 1 ? `Đang xử lý ${state.current_file_idx}/${state.total_files}...` : 'Đang chuyển đổi...';
          statusBadge.style.color = 'var(--primary)';
          pauseResumeBtn.className = 'btn-warning';
          pauseResumeIcon.textContent = '■';
          pauseResumeText.textContent = 'Tạm dừng';
        }

        document.getElementById('progressFile').textContent = state.current_filename;
        document.getElementById('progressPercent').textContent = state.percentage.toFixed(1) + '%';
        document.getElementById('progressBar').style.width = state.percentage + '%';
        document.getElementById('progressTime').textContent = `${state.current_time_str} / ${state.total_time_str}`;
        document.getElementById('progressSpeed').textContent = state.is_paused ? '0x (Tạm dừng)' : `${state.speed} (${state.fps.toFixed(0)} fps)`;
        document.getElementById('progressEta').textContent = state.is_paused ? 'ETA: Tạm dừng' : (state.eta_str ? `ETA: ${state.eta_str}` : 'ETA: --:--');
      } else {
        startBtn.style.display = 'inline-flex';
        runningControls.style.display = 'none';

        if (state.status === 'completed') {
          statusBadge.textContent = '✔ Hoàn tất thành công!';
          statusBadge.style.color = 'var(--success)';
          document.getElementById('progressBar').style.width = '100%';
          document.getElementById('progressPercent').textContent = '100%';

          if (!hasShownCompletionModal) {
            hasShownCompletionModal = true;
            playSuccessChime();
            const lastItem = (state.history && state.history.length > 0) ? state.history[0] : null;
            if (lastItem) {
              document.getElementById('completionDetails').innerHTML = `
                <div><strong>📁 File kết quả:</strong> <span style="color: #38bdf8; word-break: break-all;">${lastItem.output || state.current_filename}</span></div>
                <div><strong>📦 Dung lượng:</strong> <span style="color: #10b981; font-weight: bold;">${lastItem.size || '--'}</span></div>
                <div><strong>⏱️ Thời gian xử lý:</strong> <span>${lastItem.elapsed ? lastItem.elapsed.toFixed(1) + 's' : '--'}</span></div>
              `;
            } else {
              document.getElementById('completionDetails').innerHTML = `
                <div><strong>📁 File:</strong> <span style="color: #38bdf8;">${state.current_filename}</span></div>
                <div><strong>✔ Trạng thái:</strong> <span>Hoàn tất 100%</span></div>
              `;
            }
            document.getElementById('completionModal').style.display = 'flex';
          }
        } else if (state.status === 'cancelled') {
          statusBadge.textContent = '⏹ Đã dừng lại';
          statusBadge.style.color = 'var(--danger)';
        } else if (state.status === 'error') {
          statusBadge.textContent = '✘ Có lỗi xảy ra: ' + state.message;
          statusBadge.style.color = 'var(--danger)';
        } else {
          statusBadge.textContent = 'Sẵn sàng';
          statusBadge.style.color = 'var(--text-muted)';
        }
      }

      // Cập nhật bảng lịch sử
      if (state.history && state.history.length > 0) {
        historyCard.style.display = 'block';
        const tbody = document.getElementById('historyBody');
        tbody.innerHTML = state.history.map(item => `
          <tr>
            <td style="font-weight: 500;">${item.input}</td>
            <td style="color: var(--primary);">${item.output || '--'}</td>
            <td>${item.size || '--'}</td>
            <td>${item.elapsed ? item.elapsed + 's' : '--'}</td>
            <td><span class="${item.success ? 'badge-success' : 'badge-error'}">${item.success ? 'Thành công' : 'Lỗi'}</span></td>
          </tr>
        `).join('');
      }

      // Cập nhật Ubuntu Terminal Logs
      window.lastState = state;
      if (state.logs) {
        renderLogs(state.logs);
      }
    }

    function escapeHtml(str) {
      return (str || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    let lastLogSignature = "";
    function renderLogs(logs) {
      if (!logs) return;
      const lastItem = logs.length > 0 ? logs[logs.length - 1] : null;
      const signature = `${logs.length}_${lastItem ? lastItem.time + '_' + lastItem.msg : ''}`;
      if (signature === lastLogSignature) return;
      lastLogSignature = signature;

      const body = document.getElementById('terminalBody');
      const autoScroll = document.getElementById('autoScrollLog').checked;

      if (logs.length === 0) {
        body.innerHTML = '<div style="color: #8b949e;">[Sẵn sàng] Chờ lệnh chuyển đổi...</div>';
        return;
      }

      body.innerHTML = logs.map(l => {
        let badgeClass = 'log-info';
        if (l.level === 'DEBUG') badgeClass = 'log-debug';
        else if (l.level === 'WARN') badgeClass = 'log-warn';
        else if (l.level === 'ERROR') badgeClass = 'log-error';
        return `<div class="log-line"><span class="log-time">${l.time}</span> <span class="${badgeClass}">[${l.level}]</span> <span>${escapeHtml(l.msg)}</span></div>`;
      }).join('');

      if (autoScroll) {
        body.scrollTop = body.scrollHeight;
      }
    }

    function copyLogs() {
      const logs = (window.lastState && window.lastState.logs) ? window.lastState.logs : [];
      if (logs.length === 0) {
        alert("Chưa có log để sao chép!");
        return;
      }
      const text = logs.map(l => `${l.time} [${l.level}] ${l.msg}`).join(String.fromCharCode(10));
      navigator.clipboard.writeText(text).then(() => alert("Đã sao chép toàn bộ nhật ký vào clipboard!"));
    }

    function clearLogs() {
      document.getElementById('terminalBody').innerHTML = '<div style="color: #8b949e;">[Đã xóa log màn hình]</div>';
      lastLogSignature = "";
    }

    async function shutdownServer() {
      if (confirm("Bạn có chắc chắn muốn tắt hoàn toàn ứng dụng vid2 và giải phóng RAM & CPU?")) {
        try {
          await fetch('/api/shutdown', { method: 'POST' });
          document.body.innerHTML = `
            <div style="max-width: 520px; margin: 120px auto; text-align: center; color: #f8fafc; background: #1e293b; padding: 40px; border-radius: 16px; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
              <div style="font-size: 3.5rem; margin-bottom: 12px; color: #10b981;">✔</div>
              <h2 style="color: #10b981; margin-bottom: 14px; font-size: 1.5rem;">Đã tắt ứng dụng thành công</h2>
              <p style="color: #94a3b8; font-size: 1rem; line-height: 1.6;">
                Tiến trình Web Server và FFmpeg đã dừng lại.<br>
                <strong style="color: #f8fafc;">100% RAM và CPU đã được giải phóng cho hệ thống.</strong>
              </p>
              <p style="margin-top: 24px; color: #64748b; font-size: 0.85rem;">Bây giờ bạn có thể an tâm đóng tab trình duyệt này.</p>
            </div>
          `;
        } catch (err) {
          alert("Lỗi khi tắt server: " + err);
        }
      }
    }

    function initSSE() {
      let evtSource = null;
      function connect() {
        evtSource = new EventSource('/api/events');
        evtSource.onmessage = function(e) {
          try {
            const state = JSON.parse(e.data);
            updateUIWithState(state);
          } catch {}
        };
        evtSource.onerror = function() {
          if (evtSource) {
            evtSource.close();
            evtSource = null;
          }
          setTimeout(connect, 2000);
        };
      }
      connect();

      // Fallback polling mỗi 2 giây đảm bảo thanh tiến trình luôn chạy mượt mà ngay cả khi trình duyệt hạn chế SSE
      setInterval(async () => {
        try {
          const res = await fetch('/api/status');
          if (res.ok) {
            const state = await res.json();
            updateUIWithState(state);
          }
        } catch {}
      }, 2000);
    }

    // Hủy bỏ hẹn giờ tắt server nếu người dùng chỉ vừa F5 tải lại trang
    fetch('/api/cancel-shutdown', { method: 'POST' }).catch(() => {});

    // Khi người dùng bấm tắt tab hoặc tắt cửa sổ trình duyệt:
    // Trình duyệt sẽ hiện popup xác nhận chuẩn của hệ thống:
    // "Bạn có chắc muốn rời khỏi trang web? Các thay đổi có thể không được lưu."
    window.addEventListener('beforeunload', function (e) {
      e.preventDefault();
      e.returnValue = 'Bạn có muốn thoát app và tắt toàn bộ tiến trình vid2 không?';
      return 'Bạn có muốn thoát app và tắt toàn bộ tiến trình vid2 không?';
    });

    // Khi người dùng bấm "Rời khỏi / Leave" để xác nhận tắt tab:
    window.addEventListener('pagehide', function () {
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/tab-closed');
      } else {
        fetch('/api/tab-closed', { method: 'POST', keepalive: true }).catch(() => {});
      }
    });

    window.addEventListener('DOMContentLoaded', () => {
      initSSE();
    });
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/browse-file", methods=["POST"])
def api_browse_file():
    """Mở hộp thoại chọn file native GTK trên Ubuntu bằng Zenity và đưa lên trước."""
    zenity = shutil.which("zenity")
    if not zenity:
        return jsonify({"path": None, "error": "Zenity chưa được cài đặt trên hệ thống."})
    
    title = "Chọn file video cần chuyển đổi"
    cmd = [
        "zenity",
        "--file-selection",
        "--modal",
        f"--title={title}",
        "--file-filter=Video (*.webm *.mp4 *.mov *.mkv)|*.webm *.mp4 *.mov *.mkv",
        "--file-filter=Tất cả file (*.*)|*.*",
    ]

    # Đưa cửa sổ Zenity nổi lên trên cùng (Foreground)
    def bring_to_front():
        time.sleep(0.25)
        if shutil.which("wmctrl"):
            subprocess.run(["wmctrl", "-R", title], capture_output=True)

    threading.Thread(target=bring_to_front, daemon=True).start()

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            selected = res.stdout.strip()
            return jsonify({"path": selected if selected else None})
        elif res.returncode == 1:
            # Người dùng bấm Hủy (Cancel)
            return jsonify({"path": None})
        else:
            return jsonify({"path": None, "error": res.stderr.strip()})
    except Exception as e:
        return jsonify({"path": None, "error": str(e)})


@app.route("/api/browse-dir", methods=["POST"])
def api_browse_dir():
    """Mở hộp thoại chọn thư mục native GTK trên Ubuntu bằng Zenity và đưa lên trước."""
    zenity = shutil.which("zenity")
    if not zenity:
        return jsonify({"path": None, "error": "Zenity chưa được cài đặt trên hệ thống."})

    title = "Chọn thư mục video"
    cmd = [
        "zenity",
        "--file-selection",
        "--directory",
        "--modal",
        f"--title={title}",
    ]

    def bring_to_front():
        time.sleep(0.25)
        if shutil.which("wmctrl"):
            subprocess.run(["wmctrl", "-R", title], capture_output=True)

    threading.Thread(target=bring_to_front, daemon=True).start()

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            selected = res.stdout.strip()
            return jsonify({"path": selected if selected else None})
        elif res.returncode == 1:
            return jsonify({"path": None})
        else:
            return jsonify({"path": None, "error": res.stderr.strip()})
    except Exception as e:
        return jsonify({"path": None, "error": str(e)})


@app.route("/api/media-info", methods=["POST"])
def api_media_info():
    data = request.json or {}
    path_str = data.get("path")
    if not path_str or not Path(path_str).is_file():
        return jsonify({"success": False, "error": "File không tồn tại"})

    try:
        info = get_media_info(path_str)
        return jsonify({
            "success": True,
            "duration": round(info.duration, 2),
            "duration_formatted": format_duration(info.duration),
            "resolution": f"{info.width}x{info.height}",
            "size": format_size(info.size_bytes),
            "video_codec": info.video_codec,
            "audio_codec": info.audio_codec,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def background_worker(payload: Dict[str, Any]):
    global current_task
    with state_lock:
        current_task["is_running"] = True
        current_task["should_cancel"] = False
        current_task["status"] = "running"
        current_task["percentage"] = 0.0
    broadcast_state()

    mode = payload.get("mode", "single")
    target_format = payload.get("target_format", "mp4")
    crf = payload.get("crf", 14)
    preset = payload.get("preset", "slow")
    audio_bitrate = payload.get("audio_bitrate", "320k")
    copy_streams = payload.get("copy_streams", False)
    overwrite = payload.get("overwrite", True)
    delete_original = payload.get("delete_original", False)

    try:
        if mode == "single":
            input_path = Path(payload["input_path"]).resolve()
            files_to_convert = [input_path]
            out_dir = None
        else:
            dir_path = Path(payload["input_dir"]).resolve()
            recursive = payload.get("recursive", False)
            exts = ["webm", "mp4", "mov", "mkv"]
            files_to_convert = []
            for ext in exts:
                pat = f"**/*.{ext}" if recursive else f"*.{ext}"
                files_to_convert.extend(dir_path.glob(pat))
            files_to_convert = sorted([f for f in files_to_convert if f.is_file()])
            out_dir = Path(payload["output_dir"]).resolve() if payload.get("output_dir") else dir_path

        with state_lock:
            current_task["total_files"] = len(files_to_convert)

        for idx, file_path in enumerate(files_to_convert, start=1):
            with state_lock:
                if current_task["should_cancel"]:
                    current_task["status"] = "cancelled"
                    break
                current_task["current_file_idx"] = idx
                current_task["current_filename"] = file_path.name
                current_task["percentage"] = 0.0
            broadcast_state()

            if out_dir:
                if payload.get("recursive", False) and mode == "batch":
                    rel = file_path.relative_to(Path(payload["input_dir"]).resolve())
                    dest_file = (out_dir / rel).with_suffix(f".{target_format}")
                else:
                    dest_file = (out_dir / file_path.name).with_suffix(f".{target_format}")
            else:
                dest_file = file_path.with_suffix(f".{target_format}")

            def on_progress(p: ConversionProgress):
                with state_lock:
                    if current_task["should_cancel"]:
                        return
                    current_task["percentage"] = p.percentage
                    current_task["current_time_str"] = format_duration(p.current_time)
                    current_task["total_time_str"] = format_duration(p.total_time)
                    current_task["speed"] = p.speed
                    current_task["fps"] = p.fps
                    current_task["eta_str"] = format_duration(p.eta_seconds) if p.eta_seconds else "--:--"
                broadcast_state()

            add_log("INFO", f"Bắt đầu xử lý file [{idx}/{len(files_to_convert)}]: {file_path.name}")
            res = convert_file(
                input_path=file_path,
                output_path=dest_file,
                target_format=target_format,
                crf=crf,
                preset=preset,
                audio_bitrate=audio_bitrate,
                copy_streams=copy_streams,
                overwrite=overwrite,
                progress_callback=on_progress,
                cancel_event=cancel_event,
                log_callback=add_log,
            )

            if current_task["should_cancel"]:
                break

            if delete_original and res.success:
                try:
                    file_path.unlink()
                except OSError:
                    pass

            with state_lock:
                if not current_task["should_cancel"]:
                    current_task["history"].insert(0, {
                        "input": file_path.name,
                        "output": res.output_path.name if res.success else None,
                        "size": format_size(res.output_size_bytes) if res.success else None,
                        "elapsed": res.elapsed_time,
                        "success": res.success,
                        "error": res.error_message,
                    })
            broadcast_state()

        is_cancelled = False
        with state_lock:
            if not current_task["should_cancel"]:
                current_task["status"] = "completed"
                current_task["percentage"] = 100.0
            else:
                is_cancelled = True
                current_task["status"] = "cancelled"

        if not is_cancelled:
            add_log("INFO", "✔ Đã hoàn tất 100% tất cả các file cần chuyển đổi.")
        else:
            add_log("WARN", "⏹ Đã dừng lại và hủy tác vụ theo yêu cầu của bạn.")

    except Exception as e:
        with state_lock:
            current_task["status"] = "error"
            current_task["message"] = str(e)
        add_log("ERROR", f"Tác vụ bị lỗi: {e}")
    finally:
        with state_lock:
            current_task["is_running"] = False
        broadcast_state()


@app.route("/api/convert", methods=["POST"])
def api_convert():
    with state_lock:
        if current_task["is_running"]:
            return jsonify({"success": False, "error": "Một tác vụ chuyển đổi đang chạy!"})

    cancel_event.clear()
    payload = request.json or {}
    threading.Thread(target=background_worker, args=(payload,), daemon=True).start()
    return jsonify({"success": True})


@app.route("/api/pause", methods=["POST"])
def api_pause():
    from converter import pause_conversion
    success = pause_conversion()
    with state_lock:
        if current_task["is_running"]:
            current_task["is_paused"] = True
            current_task["status"] = "paused"
    broadcast_state()
    add_log("WARN", "■ Đã tạm dừng chuyển đổi (CPU giải phóng về 0%).")
    return jsonify({"success": success})


@app.route("/api/resume", methods=["POST"])
def api_resume():
    from converter import resume_conversion
    success = resume_conversion()
    with state_lock:
        if current_task["is_running"]:
            current_task["is_paused"] = False
            current_task["status"] = "running"
    broadcast_state()
    add_log("INFO", "▶ Đã tiếp tục chuyển đổi video.")
    return jsonify({"success": success})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """Dừng hoàn toàn quá trình chuyển đổi video."""
    from converter import stop_conversion
    cancel_event.set()
    stop_conversion()
    with state_lock:
        current_task["should_cancel"] = True
        current_task["is_paused"] = False
        current_task["is_running"] = False
        current_task["status"] = "cancelled"
    broadcast_state()
    add_log("WARN", "⏻ Đã dừng hoàn toàn việc chuyển đổi.")
    return jsonify({"success": True})


@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    return api_stop()


@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    """Tắt hoàn toàn server và giải phóng toàn bộ RAM & CPU."""
    cancel_event.set()
    with state_lock:
        current_task["should_cancel"] = True
        current_task["is_running"] = False
    broadcast_state()

    def delayed_exit():
        time.sleep(0.4)
        os._exit(0)

    threading.Thread(target=delayed_exit, daemon=True).start()
    return jsonify({"success": True, "message": "Server đã tắt và giải phóng 100% tài nguyên."})


shutdown_timer: Optional[threading.Timer] = None
shutdown_timer_lock = threading.Lock()


def perform_tab_shutdown():
    cancel_event.set()
    with state_lock:
        current_task["should_cancel"] = True
        current_task["is_running"] = False
    broadcast_state()
    time.sleep(0.3)
    os._exit(0)


@app.route("/api/tab-closed", methods=["POST"])
def api_tab_closed():
    """Nhận tín hiệu khi người dùng xác nhận đóng tab trên trình duyệt."""
    global shutdown_timer
    with shutdown_timer_lock:
        if shutdown_timer and shutdown_timer.is_alive():
            shutdown_timer.cancel()
        # Chờ 2.5s: nếu là F5 tải lại trang thì route cancel-shutdown sẽ hủy timer.
        # Nếu là đóng tab thật sự, server sẽ tắt và giải phóng 100% RAM/CPU.
        shutdown_timer = threading.Timer(2.5, perform_tab_shutdown)
        shutdown_timer.daemon = True
        shutdown_timer.start()
    return jsonify({"success": True})


@app.route("/api/cancel-shutdown", methods=["POST"])
def api_cancel_shutdown():
    """Hủy hẹn giờ tắt server nếu người dùng tải lại trang."""
    global shutdown_timer
    with shutdown_timer_lock:
        if shutdown_timer and shutdown_timer.is_alive():
            shutdown_timer.cancel()
            shutdown_timer = None
    return jsonify({"success": True})


@app.route("/api/status")
def api_status():
    """Endpoint trả về trạng thái tác vụ hiện tại cho client polling."""
    with state_lock:
        return jsonify(current_task)


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/api/events")
def api_events():
    """Server-Sent Events (SSE) để client cập nhật realtime tiến trình."""
    q = queue.Queue()
    event_listeners.append(q)

    # Gửi ngay state hiện tại
    with state_lock:
        initial_data = json.dumps(current_task)

    def event_stream():
        yield f"data: {initial_data}\n\n"
        try:
            while True:
                data = q.get()
                yield f"data: {data}\n\n"
        except GeneratorExit:
            if q in event_listeners:
                event_listeners.remove(q)

    return Response(event_stream(), mimetype="text/event-stream")


def is_port_in_use(host: str, port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def run_gui(host: str = "127.0.0.1", port: int = 5050, auto_open: bool = True):
    ready, msg = check_dependencies()
    if not ready:
        print(f"Lỗi: {msg}")
        return

    url = f"http://{host}:{port}"

    if is_port_in_use(host, port):
        import urllib.request
        try:
            req = urllib.request.urlopen(f"{url}/api/status", timeout=1)
            if req.status == 200:
                print(f"[*] vid2 GUI đã đang chạy sẵn tại: {url}")
                print(f"[*] Đang mở trình duyệt...")
                if auto_open:
                    webbrowser.open(url)
                return
        except Exception:
            pass

    print(f"[*] vid2 GUI đang khởi chạy tại: {url}")
    if auto_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"[*] Cổng {port} đang bận, tự động chuyển sang cổng {port + 1}...")
            run_gui(host=host, port=port + 1, auto_open=auto_open)
        else:
            raise


if __name__ == "__main__":
    run_gui()
