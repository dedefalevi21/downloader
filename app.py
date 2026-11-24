import os
import re
import secrets
import shutil
import time

from flask import Flask, request, jsonify, send_file, send_from_directory, abort

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder='assets')

try:
    import yt_dlp
    YTDLP_OK = True
except ImportError:
    YTDLP_OK = False

URL_RE = re.compile(
    r'^https?://(?:www\.)?(?:youtube\.com|youtu\.be|tiktok\.com|facebook\.com|twitter\.com|x\.com|t\.me|telegram\.me)/[^\s/$.?#].[^\s]*$',
    re.IGNORECASE
)


def valid_url(url):
    return bool(url) and bool(URL_RE.match(url)) and len(url) < 2048


def detect_site(url):
    """Deteksi tipe situs dari URL untuk menyesuaikan opsi pengunduhan"""
    if 'tiktok.com' in url or 't.me' in url:
        return 'tiktok'
    elif 'facebook.com' in url or 'fb.watch' in url:
        return 'facebook'
    elif 'twitter.com' in url or 'x.com' in url:
        return 'twitter'
    elif 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    return 'unknown'


def detect_url_from_body(url):
    """Deteksi situs dari URL ketika source tidak dikirim (untuk download endpoint)"""
    if 'tiktok.com' in url or 't.me' in url:
        return 'tiktok'
    elif 'facebook.com' in url or 'fb.watch' in url:
        return 'facebook'
    elif 'twitter.com' in url or 'x.com' in url:
        return 'twitter'
    elif 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    return 'unknown'


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

    site = detect_site(url)
    opts = {'quiet': True, 'no_warnings': True}

    # Set noplaylist berdasarkan tipe situs
    # Twitter/X dan Facebook kadang punya playlist, YouTube bisa punya playlist
    if site in ('twitter', 'facebook'):
        opts['noplaylist'] = True
    else:
        opts['noplaylist'] = True  # Default, bisa diubah jika butuh playlist

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
            'detected_site': site,
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
    source = body.get('source', 'auto').strip().lower()  # 'youtube', 'tiktok', 'facebook', 'twitter', 'telegram', 'auto'

    if not valid_url(url):
        return jsonify({'error': 'URL tidak valid'}), 400

    site = detect_url_from_body(url) if source == 'auto' else source
    opts = {'quiet': True, 'no_warnings': True, 'noplaylist': True}

    task_id = secrets.token_hex(8)
    outtmpl = os.path.join(DOWNLOAD_DIR, task_id + '.%(ext)s')

    try:
        # Konfigurasi per situs
        if site == 'tiktok':
            # TikTok biasanya video satu blok, fokus pada format video
            if kind == 'audio':
                opts['format'] = 'bestaudio/best'
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                opts['format'] = 'bestvideo+bestaudio/best'
                opts['merge_output_format'] = 'mp4'

        elif site == 'facebook':
            # Facebook video butuh perhatian pada format
            if kind == 'audio':
                opts['format'] = 'bestaudio/best'
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                # Gabungkan video + audio untuk Facebook
                if format_id == 'best' or format_id == '':
                    fmt = 'bestvideo+bestaudio/best'
                else:
                    fmt = f'{format_id}+bestaudio/best'
                opts['format'] = fmt
                opts['merge_output_format'] = 'mp4'

        elif site == 'twitter' or site == 'x':
            # Twitter/X video format
            if kind == 'audio':
                opts['format'] = 'bestaudio/best'
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                # Twitter/X butuh format spesifik untuk gabungan
                if format_id == 'best' or format_id == '':
                    fmt = 'bestvideo+bestaudio'
                else:
                    fmt = f'{format_id}+bestaudio'
                opts['format'] = fmt
                opts['merge_output_format'] = 'mp4'

        elif site == 'telegram':
            # Telegram channel/posts - biasanya butuh format khusus
            if kind == 'audio':
                opts['format'] = 'bestaudio/best'
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                # Telegram video
                if format_id == 'best' or format_id == '':
                    fmt = 'bestvideo+bestaudio/best'
                else:
                    fmt = f'{format_id}+bestaudio/best'
                opts['format'] = fmt
                opts['merge_output_format'] = 'mp4'

        else:
            # Default (YouTube dan unknown): strategi lama
            if kind == 'audio':
                opts['format'] = format_id if format_id != 'best' else 'bestaudio/best'
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            else:
                # Selalu gabungkan video dengan audio terbaik
                if format_id == 'best':
                    fmt = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]'
                else:
                    fmt = f'{format_id}+bestaudio[ext=m4a]'
                opts['format'] = fmt
                opts['merge_output_format'] = 'mp4'
                opts['postprocessors'] = [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }]

        # Semua situs: set format dan opsi dasar
        opts['outtmpl'] = outtmpl

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
            'detected_site': site,
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
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)