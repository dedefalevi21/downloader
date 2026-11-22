document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('downloadForm');
    const urlInput = document.getElementById('videoUrl');
    const resultDiv = document.getElementById('result');
    const navLinks = document.querySelectorAll('.nav a[data-platform]');
    const platformCards = document.querySelectorAll('.platform-card');

    function isValidUrl(value) {
        try {
            const u = new URL(value);
            return u.protocol === 'http:' || u.protocol === 'https:';
        } catch (_) {
            return false;
        }
    }

    let currentMode = 'youtube';

    function setMode(mode) {
        currentMode = mode;
        navLinks.forEach(a => a.classList.toggle('active', a.dataset.platform === mode));
    }

    navLinks.forEach(a => {
        a.addEventListener('click', function (e) {
            e.preventDefault();
            setMode(this.dataset.platform);
            urlInput.focus();
        });
    });

    platformCards.forEach(card => {
        card.addEventListener('click', function (e) {
            e.preventDefault();
            setMode(this.dataset.platform);
            urlInput.focus();
        });
    });

    function showResult(type, message) {
        resultDiv.className = 'result show';
        resultDiv.innerHTML = `<p class="result-${type}">${message}</p>`;
    }

    function formatSize(bytes) {
        if (!bytes) return '0 B';
        const k = 1024, m = 1024 * 1024, g = 1024 * 1024 * 1024;
        if (bytes < 1024) return bytes + ' B';
        else if (bytes < m) return (bytes / 1024).toFixed(1) + ' KB';
        else if (bytes < g) return (bytes / m).toFixed(1) + ' MB';
        else return (bytes / g).toFixed(1) + ' GB';
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        const url = urlInput.value.trim();

        if (!url) {
            showResult('error', 'Masukkan URL video');
            return;
        }

        if (!isValidUrl(url)) {
            showResult('error', 'URL tidak valid. Pastikan dimulai dengan http:// atau https://');
            return;
        }

        resultDiv.className = 'result show';
        resultDiv.innerHTML = '<p class="result-loading">Mengambil informasi video...</p>';

        fetch('/api/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        })
        .then(r => r.json())
        .then(info => {
            if (info.error) {
                showResult('error', info.error);
                return;
            }

            const videoRows = info.videos.map(v => `
                <div class="format-row">
                    <div class="format-info">
                        <strong>${v.resolution} · ${v.ext.toUpperCase()}</strong>
                        <span>${formatSize(v.filesize)}</span>
                        <span>${v.fps ? '· ' + v.fps + 'fps' : ''}</span>
                    </div>
                    <button class="btn-download" data-format="${v.format_id}" data-kind="video">Unduh</button>
                </div>
            `).join('');

            const audioRows = info.audios.map(a => `
                <div class="format-row">
                    <div class="format-info">
                        <strong>Audio · ${a.ext.toUpperCase()}</strong>
                        <span>${formatSize(a.filesize)}</span>
                        <span>${a.tbr ? '· ' + a.tbr.toFixed(0) + ' kbps' : ''}</span>
                    </div>
                    <button class="btn-download" data-format="${a.format_id}" data-kind="audio">Unduh MP3</button>
                </div>
            `).join('');

            resultDiv.innerHTML = `
                <h3>${info.title || 'Video'}</h3>
                <p class="result-note">${info.uploader || ''}</p>
                <h4>Video</h4>
                ${videoRows || '<p class="result-note">Tidak ada format video.</p>'}
                <h4>Audio</h4>
                ${audioRows || '<p class="result-note">Tidak ada format audio.</p>'}
            `;

            resultDiv.querySelectorAll('.btn-download').forEach(btn => {
                btn.addEventListener('click', function () {
                    const formatId = this.dataset.format;
                    const kind = this.dataset.kind;
                    const originalText = this.textContent;

                    this.disabled = true;
                    this.textContent = 'Memproses...';

                    fetch('/api/download', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: url, format_id: formatId, kind: kind })
                    })
                    .then(r => r.json())
                    .then(res => {
                        if (res.error) {
                            alert(res.error);
                            this.disabled = false;
                            this.textContent = originalText;
                            return;
                        }

                        const downloadLink = document.createElement('a');
                        downloadLink.href = '/api/file/' + res.task_id;
                        downloadLink.download = res.filename;
                        downloadLink.textContent = 'Unduh ' + (kind === 'audio' ? 'Audio' : 'Video');
                        downloadLink.className = 'btn-download';

                        resultDiv.innerHTML = `
                            <p class="result-success">Unduhan siap! Klik tombol di bawah untuk mengunduh.</p>
                            ${downloadLink.outerHTML}
                        `;
                    })
                    .catch(() => {
                        alert('Gagal mengunduh. Coba lagi.');
                        this.disabled = false;
                        this.textContent = originalText;
                    });
                });
            });
        })
        .catch(() => {
            showResult('error', 'Gagal menghubungi server. Pastikan backend berjalan.');
        });
    });
});