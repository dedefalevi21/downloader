from http.server import BaseHTTPRequestHandler
import json
import yt_dlp


class handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length).decode('utf-8') if length else '{}'
            body = json.loads(raw)
        except Exception:
            return self._send(400, {'error': 'Invalid request body'})

        url = (body.get('url') or '').strip()
        format_id = (body.get('format_id') or 'best').strip()
        kind = body.get('kind', 'video')

        if not url:
            return self._send(400, {'error': 'URL diperlukan'})

        try:
            opts = {
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
            }

            if kind == 'audio':
                opts['format'] = format_id if format_id != 'best' else 'bestaudio/best'
            else:
                if format_id == 'best':
                    opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                else:
                    opts['format'] = f'{format_id}+bestaudio[ext=m4a]'

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])

                direct_url = None

                if kind == 'audio':
                    if format_id != 'best':
                        for f in formats:
                            if f.get('format_id') == format_id and f.get('acodec') not in (None, 'none'):
                                direct_url = f.get('url')
                                break
                    if not direct_url:
                        for f in formats:
                            if f.get('acodec') not in (None, 'none') and f.get('vcodec') in (None, 'none'):
                                direct_url = f.get('url')
                                break
                else:
                    if format_id != 'best':
                        for f in formats:
                            if f.get('format_id') == format_id and f.get('vcodec') not in (None, 'none'):
                                direct_url = f.get('url')
                                break
                    if not direct_url:
                        for f in formats:
                            if f.get('vcodec') not in (None, 'none') and f.get('acodec') not in (None, 'none'):
                                direct_url = f.get('url')
                                break
                    if not direct_url:
                        for f in formats:
                            if f.get('vcodec') not in (None, 'none'):
                                direct_url = f.get('url')
                                break

                if direct_url:
                    title = info.get('title') or 'Video'
                    # Hide video ID that yt-dlp may return as title for restricted videos
                    if title and title != 'Video':
                        first_part = title.split()[0].split('·')[0].split('-')[0]
                        if len(first_part) <= 20 and all(c in '0123456789abcdef.' for c in first_part):
                            title = 'Video'
                    return self._send(200, {
                        'direct_url': direct_url,
                        'title': title,
                    })
                else:
                    return self._send(500, {'error': 'Tidak dapat menemukan URL unduhan langsung'})

        except Exception as e:
            return self._send(500, {'error': str(e)})