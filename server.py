"""Simple HTTP server to serve the display page and run main.py."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import uuid
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

import markdown

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")

# Load .env so subprocess (main.py) inherits LLM_API_KEY etc.
_env_path = os.path.join(PROJECT_DIR, ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
HOTNEWS_ARTICLES = os.path.join(OUTPUT_DIR, "hotnews_articles.md")
PROFILES_CSV = os.path.join(PROJECT_DIR, "profiles.csv")
PROGRESS_FILE = os.path.join(OUTPUT_DIR, "progress.json")

CSV_FIELDS = ["id", "name", "platform", "profile"]


def _read_profiles():
    """Read all profiles from CSV file."""
    if not os.path.exists(PROFILES_CSV):
        return []
    with open(PROFILES_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _write_profiles(profiles):
    """Write all profiles to CSV file."""
    with open(PROFILES_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(profiles)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=OUTPUT_DIR, **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            return self._serve_index()
        if path == "/api/markdown":
            return self._serve_markdown()
        if path == "/api/personas":
            return self._list_personas()
        if path == "/api/profiles":
            return self._list_profiles()
        if path == "/api/export":
            return self._export_markdown()
        if path == "/api/export-recommendations":
            return self._export_recommendations()
        if path == "/api/progress":
            return self._get_progress()
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/run":
            return self._run_main()
        if self.path == "/api/profiles":
            return self._add_profile()
        self.send_error(404)

    def do_PUT(self):
        if self.path == "/api/profiles":
            return self._update_profile()
        self.send_error(404)

    def do_DELETE(self):
        if self.path == "/api/profiles":
            return self._delete_profile()
        self.send_error(404)

    def _serve_index(self):
        index_path = os.path.join(OUTPUT_DIR, "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            payload = f.read().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def _serve_markdown(self):
        # Get persona_name from query parameter
        from urllib.parse import parse_qs
        query = urlparse(self.path).query
        params = parse_qs(query)
        persona_name = params.get('persona', [''])[0]

        # Build combined markdown content
        combined_md = ""

        # If persona is specified, load their recommendations first
        if persona_name:
            recommendations_file = os.path.join(OUTPUT_DIR, f"hotnews_推荐_{persona_name}.md")
            if os.path.exists(recommendations_file):
                with open(recommendations_file, "r", encoding="utf-8") as f:
                    combined_md = f.read()
                combined_md += "\n\n"

        # Always append the articles data
        if os.path.exists(HOTNEWS_ARTICLES):
            with open(HOTNEWS_ARTICLES, "r", encoding="utf-8") as f:
                combined_md += f.read()

        if not combined_md.strip():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(b"")
            return

        html = markdown.markdown(combined_md, extensions=["tables", "fenced_code"])
        payload = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def _export_markdown(self):
        if not os.path.exists(HOTNEWS_ARTICLES):
            self.send_error(404, "暂无报告内容")
            return

        with open(HOTNEWS_ARTICLES, "r", encoding="utf-8") as f:
            md_text = f.read()

        payload = md_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", "attachment; filename=hotnews.md")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _export_recommendations(self):
        """Export only the recommendations section (LLM-generated topics)."""
        # Get persona_name from query parameter
        from urllib.parse import parse_qs
        query = urlparse(self.path).query
        params = parse_qs(query)
        persona_name = params.get('persona', [''])[0]

        if not persona_name:
            self.send_error(404, "请先选择达人画像")
            return

        recommendations_file = os.path.join(OUTPUT_DIR, f"hotnews_推荐_{persona_name}.md")
        if not os.path.exists(recommendations_file):
            self.send_error(404, "暂无推荐内容")
            return

        with open(recommendations_file, "r", encoding="utf-8") as f:
            md_text = f.read()

        payload = md_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", f"attachment; filename=recommendations_{persona_name}.md")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _run_main(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"
        data = json.loads(body)
        profile = data.get("profile", "")
        persona_name = data.get("persona_name", "")

        cmd = [sys.executable, os.path.join(PROJECT_DIR, "main.py")]
        if profile:
            cmd.append(profile)
            cmd.append(persona_name or "达人")

        try:
            result = subprocess.run(
                cmd,
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                timeout=300,
                env=os.environ.copy(),  # Explicitly pass environment variables
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

            success = result.returncode == 0
            resp = {"success": success}
            if not success:
                resp["error"] = result.stderr[-500:] if result.stderr else "exit code " + str(result.returncode)
        except subprocess.TimeoutExpired:
            resp = {"success": False, "error": "执行超时"}
        except Exception as e:
            resp = {"success": False, "error": str(e)}

        payload = json.dumps(resp, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json_response(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(body)

    def _list_profiles(self):
        profiles = _read_profiles()
        self._json_response(profiles)

    def _add_profile(self):
        data = self._read_body()
        name = data.get("name", "").strip()
        platform = data.get("platform", "").strip()
        profile = data.get("profile", "").strip()
        if not name:
            self._json_response({"success": False, "error": "达人名称不能为空"})
            return
        new_profile = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "platform": platform,
            "profile": profile,
        }
        profiles = _read_profiles()
        profiles.append(new_profile)
        _write_profiles(profiles)
        self._json_response({"success": True, "profile": new_profile})

    def _update_profile(self):
        data = self._read_body()
        pid = data.get("id", "")
        profiles = _read_profiles()
        for p in profiles:
            if p["id"] == pid:
                if "name" in data:
                    p["name"] = data["name"].strip()
                if "platform" in data:
                    p["platform"] = data["platform"].strip()
                if "profile" in data:
                    p["profile"] = data["profile"].strip()
                _write_profiles(profiles)
                self._json_response({"success": True, "profile": p})
                return
        self._json_response({"success": False, "error": "未找到该画像"})

    def _delete_profile(self):
        data = self._read_body()
        pid = data.get("id", "")
        profiles = _read_profiles()
        new_profiles = [p for p in profiles if p["id"] != pid]
        if len(new_profiles) == len(profiles):
            self._json_response({"success": False, "error": "未找到该画像"})
            return
        _write_profiles(new_profiles)
        self._json_response({"success": True})

    def _get_progress(self):
        """Return current progress of the running task."""
        if not os.path.exists(PROGRESS_FILE):
            self._json_response({"current": 0, "total": 0, "percentage": 0, "message": ""})
            return

        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                progress_data = json.load(f)
            self._json_response(progress_data)
        except Exception:
            self._json_response({"current": 0, "total": 0, "percentage": 0, "message": ""})

    def _list_personas(self):
        """List all available persona recommendation files."""
        import glob
        persona_files = glob.glob(os.path.join(OUTPUT_DIR, "hotnews_推荐_*.md"))
        personas = []
        for filepath in persona_files:
            filename = os.path.basename(filepath)
            # Extract persona name from filename: hotnews_推荐_飞哥.md -> 飞哥
            if filename.startswith("hotnews_推荐_") and filename.endswith(".md"):
                persona_name = filename[11:-3]  # Remove "hotnews_推荐_" and ".md"
                personas.append({"name": persona_name, "filename": filename})
        self._json_response(personas)


def main():
    port = 8000
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"服务已启动: http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
