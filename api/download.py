from http.server import BaseHTTPRequestHandler
import json
import re

URL_RE = re.compile(r'^https?://[^\s/$.?#].[^\s]*$', re.IGNORECASE)


class handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        try:
            import yt_dlp
        except ImportError:
            return self._send(500, {'error': 'yt-dlp belum terinstal'})

        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length).decode('utf-8') if length else '{}'
        try:
            body = json.loads(raw)
        except ValueError:
            return self._send(400, {'error': 'Body bukan JSON valid'})

        url = (body.get('url') or '').strip()
        if not URL_RE.match(url) or len(url) >= 2048:
            return self._send(400, {'error': 'URL tidak valid'})

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
                    }
                    if f.get('vcodec') not in (None, 'none'):
                        videos.append(item)
                    elif f.get('acodec') not in (None, 'none'):
                        audios.append(item)

                videos.sort(key=lambda v: (v.get('filesize') or 0), reverse=True)

                title = data.get('title') or 'Video'
                # Hide video ID that yt-dlp may return as title for restricted videos
                if title and title != 'Video':
                    first_part = title.split()[0].split('·')[0].split('-')[0]
                    if len(first_part) <= 20 and all(c in '0123456789abcdef.' for c in first_part):
                        title = 'Video'

                return self._send(200, {
                    'title': title,
                    'duration': data.get('duration'),
                    'thumbnail': data.get('thumbnail'),
                    'uploader': data.get('uploader'),
                    'videos': videos[:12],
                    'audios': audios[:6],
                })
        except Exception as e:
            return self._send(500, {'error': f'Gagal mengambil info: {e}'})