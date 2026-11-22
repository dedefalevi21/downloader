import os
import re
import secrets
import shutil
import time

from flask import Flask, request, jsonify, send_file, send_from_directory, abort

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=None)

try:
    import yt_dlp
    YTDLP_OK = True
except ImportError:
    YTDLP_OK = False

URL_RE = re.compile(r'^https?://[^\s/$.?#].[^\s]*$', re.IGNORECASE)


def valid_url(url):
    return bool(url) and bool(URL_RE.match(url)) and len(url) < 2048


# ------------------------- static frontend -------------------------

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/assets/<path:subpath>')
def assets(subpath):
    return send_from_directory(os.path.join(BASE_DIR, 'assets'), subpath)


# ------------------------- api -------------------------

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'yt_dlp': YTDLP_OK})


@app.route('/api/info', methods=['POST'])
def info():
    if not YTDLP_OK:
        return jsonify({'error': 'yt-dlp belum terinstal di server'}), 500

    url = (request.get_json(silent=True) or {}).get('url', '').strip()
    if not valid_url(url):
        return jsonify({'error': 'URL tidak valid'}), 400

    opts = {'quiet': True, 'no_warnings': True, 'noplaylist': True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)

        videos, audios = [], []
        for f in data.get('formats', []):
            if f.get('ext') in ('mhtml', 'none'):
                continue
            item = {
                'format_id': f.get('format_id'),
                'ext': f.get('ext'),
                'resolution': f.get('format_note') or f.get('resolution') or 'audio',
                'filesize': f.get('filesize') or f.get('filesize_approx'),
                'fps': f.get('fps'),
                'tbr': f.get('tbr'),
                'vcodec': f.get('vcodec'),
                'acodec': f.get('acodec'),
            }
            if f.get('vcodec') not in (None, 'none'):
                videos.append(item)
            elif f.get('acodec') not in (None, 'none'):
                audios.append(item)

        videos.sort(key=lambda v: (v.get('filesize') or 0), reverse=True)

        return jsonify({
            'title': data.get('title'),
            'duration': data.get('duration'),
            'thumbnail': data.get('thumbnail'),
            'uploader': data.get('uploader'),
            'videos': videos[:12],
            'audios': audios[:6],
        })
    except Exception as e:
        return jsonify({'error': f'Gagal mengambil info video: {e}'}), 500


@app.route('/api/download', methods=['POST'])
def download():
    if not YTDLP_OK:
        return jsonify({'error': 'yt-dlp belum terinstal di server'}), 500

    body = request.get_json(silent=True) or {}
    url = body.get('url', '').strip()
    format_id = (body.get('format_id') or 'best').strip()
    kind = body.get('kind', 'video')

    if not valid_url(url):
        return jsonify({'error': 'URL tidak valid'}), 400

    task_id = secrets.token_hex(8)
    outtmpl = os.path.join(DOWNLOAD_DIR, task_id + '.%(ext)s')

    try:
        if kind == 'audio':
            opts = {
                'format': format_id if format_id != 'best' else 'bestaudio/best',
                'outtmpl': outtmpl,
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
        else:
            # Selalu gabungkan video dengan audio terbaik agar hasil unduhan memiliki suara
            if format_id == 'best':
                fmt = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]'
            else:
                fmt = f'{format_id}+bestaudio[ext=m4a]'

            opts = {
                'format': fmt,
                'outtmpl': outtmpl,
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'merge_output_format': 'mp4',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
            }

        with yt_dlp.YoutubeDL(opts) as ydl:
            meta = ydl.extract_info(url, download=True)

        produced = [f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(task_id)]
        if not produced:
            return jsonify({'error': 'File hasil unduhan tidak ditemukan'}), 500

        filename = produced[0]
        path = os.path.join(DOWNLOAD_DIR, filename)
        return jsonify({
            'task_id': task_id,
            'filename': filename,
            'title': meta.get('title'),
            'ext': os.path.splitext(filename)[1].lstrip('.'),
            'size': os.path.getsize(path),
        })
    except Exception as e:
        return jsonify({'error': f'Gagal mengunduh: {e}'}), 500


@app.route('/api/file/<task_id>')
def file(task_id):
    if not re.fullmatch(r'[0-9a-f]{16}', task_id):
        abort(400)
    for name in os.listdir(DOWNLOAD_DIR):
        if name.startswith(task_id):
            return send_file(os.path.join(DOWNLOAD_DIR, name), as_attachment=True, download_name=name)
    abort(404)


def cleanup_old(minutes=60):
    now = time.time()
    for name in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, name)
        try:
            if now - os.path.getmtime(path) > minutes * 60:
                os.remove(path)
        except OSError:
            pass


if __name__ == '__main__':
    cleanup_old()
    app.run(host='127.0.0.1', port=8080, debug=False, threaded=True)