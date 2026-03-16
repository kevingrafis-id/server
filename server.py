from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import urllib.parse
import os

app = Flask(__name__)
CORS(app)

@app.route("/download", methods=["POST"])
def download():
    data = request.json
    video_url = data.get("url")

    if not video_url:
        return jsonify({"error": "URL kosong"}), 400

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    title = info.get("title", "Video")
    thumbnail = info.get("thumbnail", "")
    formats = info.get("formats", [])
    extractor = info.get("extractor", "").lower()

    links = []
    used_qualities = set()
    
    server_base_url = request.host_url.rstrip('/')

    for f in formats:
        url = f.get("url")
        vcodec = str(f.get("vcodec", "")).lower()
        acodec = str(f.get("acodec", "")).lower()
        ext = str(f.get("ext", "")).lower()
        height = f.get("height")
        format_id = str(f.get("format_id", "")).lower()
        format_note = str(f.get("format_note", "")).lower()

        if not url or ".m3u8" in url:
            continue

        quality = ""

        # --- DETEKSI AUDIO (MP3/DIRECT) ---
        if vcodec == "none" and acodec != "none":
            abr = f.get("abr")
            audio_bitrate = int(abr) if abr else 128
            quality = f"{audio_bitrate}kbps Audio"
            
            if quality not in used_qualities:
                used_qualities.add(quality)
                # Kirim Link Mentah agar HP user yang download langsung
                links.append({"quality": quality, "url": url})
            continue 

        # --- 1. FACEBOOK (DIRECT LINK) ---
        if "facebook" in extractor:
            if format_id in ["sd", "hd"]:
                quality = format_id.upper()
                if quality not in used_qualities:
                    used_qualities.add(quality)
                    # Kirim link mentah (hemat bandwidth PC)
                    links.append({"quality": quality, "url": url})

        # --- 2. YOUTUBE (HYBRID) ---
        elif "youtube" in extractor:
            if ext == "mp4":
                # Jika Video + Audio sudah jadi satu (Direct)
                if vcodec != "none" and acodec != "none":
                    quality = f"{height}p Direct" if height else "SD Direct"
                    if quality not in used_qualities:
                        used_qualities.add(quality)
                        links.append({"quality": quality, "url": url})
                # Jika Video Bisu (Harus dijahit di PC)
                elif vcodec != "none" and acodec == "none":
                    if height and height >= 720:
                        quality = f"{height}p HD"
                        if quality not in used_qualities:
                            used_qualities.add(quality)
                            encoded_yt_url = urllib.parse.quote(video_url)
                            custom_url = f"{server_base_url}/process_video?url={encoded_yt_url}&vid_id={format_id}"
                            links.append({"quality": quality, "url": custom_url})

        # --- 3. TIKTOK (DIRECT LINK) ---
        elif "tiktok" in extractor:
            if vcodec != "none":
                quality = "No Watermark" if ("watermark" in format_note and "no" not in format_note) else "Watermark"
                
                if quality not in used_qualities:
                    used_qualities.add(quality)
                    # TikTok kirim link mentah langsung ke HP
                    links.append({"quality": quality, "url": url})

        # --- 4. INSTAGRAM & LAINNYA (DIRECT LINK) ---
        else:
            if vcodec != "none" and acodec != "none":
                quality = f"{height}p Direct" if height else "Original Direct"
                if quality not in used_qualities:
                    used_qualities.add(quality)
                    # Instagram kirim link mentah langsung ke HP
                    links.append({"quality": quality, "url": url})

    if not links:
        best_url = info.get("url")
        if best_url:
            links.append({"quality": "Terbaik", "url": best_url})

    def sort_key(x):
        q = x["quality"]
        num = ''.join(filter(str.isdigit, q))
        if num: return int(num)
        if q in ["HD", "No Watermark", "Original", "Terbaik"]: return 1000
        if q in ["SD", "Watermark"]: return 500
        return 0

    links.sort(key=sort_key, reverse=True)

    return jsonify({
        "title": title,
        "thumbnail": thumbnail,
        "links": links
    })

@app.route("/process_video", methods=["GET"])
def process_video():
    video_url = request.args.get("url")
    vid_id = request.args.get("vid_id")
    if not video_url or not vid_id:
        return "Parameter tidak lengkap", 400
    output_filename = f"temp_yt_{vid_id}.mp4"
    ydl_opts = {
        'format': f'{vid_id}+bestaudio[ext=m4a]/bestaudio/best',
        'merge_output_format': 'mp4',
        'outtmpl': output_filename,
        'quiet': False
    }
    try:
        # Hapus file lama jika ada agar tidak bentrok
        if os.path.exists(output_filename):
            os.remove(output_filename)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return send_file(output_filename, as_attachment=True)
    except Exception as e:
        return f"Terjadi kesalahan di server: {str(e)}", 500

@app.route("/proxy_download", methods=["GET"])
def proxy_download():
    video_url = request.args.get("url")
    format_id = request.args.get("format_id")
    if not video_url or not format_id:
        return "Parameter tidak lengkap", 400
    fid = format_id if format_id != "best" else "best"
    output_filename = f"temp_dl_{fid}.mp4"
    ydl_opts = {
        'format': fid,
        'outtmpl': output_filename,
        'quiet': False
    }
    try:
        if os.path.exists(output_filename):
            os.remove(output_filename)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return send_file(output_filename, as_attachment=True)
    except Exception as e:
        return f"Terjadi kesalahan di server proxy: {str(e)}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)