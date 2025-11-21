import os
import json
import io
import zipfile
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import base64
import re
import time
import urllib.request


ROOT_DIR = os.path.abspath(os.getcwd())
ASSETS_PATH = os.path.join(ROOT_DIR, 'assets', 'menu.json')
CATEGORIES_ASSETS_PATH = os.path.join(ROOT_DIR, 'assets', 'categories.json')
GOVS_ASSETS_PATH = os.path.join(ROOT_DIR, 'assets', 'governorates.json')
REVIEWS_PATH = os.path.join(ROOT_DIR, 'assets', 'reviews.json')
SETTINGS_PATH = os.path.join(ROOT_DIR, 'assets', 'settings.json')
ANNOUNCEMENTS_PATH = os.path.join(ROOT_DIR, 'assets', 'announcements.json')
HERO_PATH = os.path.join(ROOT_DIR, 'assets', 'hero.json')
SAVE_ENDPOINT = '/api/save-menu'
SAVE_CATS_ENDPOINT = '/api/save-categories'
SAVE_GOVS_ENDPOINT = '/api/save-governorates'
UPLOAD_ENDPOINT = '/api/upload-image'
SAVE_REVIEW_ENDPOINT = '/api/save-review'
SAVE_SETTINGS_ENDPOINT = '/api/save-settings'
SAVE_ANNOUNCEMENTS_ENDPOINT = '/api/save-announcements'
SAVE_HERO_ENDPOINT = '/api/save-hero'


class Handler(SimpleHTTPRequestHandler):
    # تأكد من تقديم الملفات من مجلد المشروع
    def __init__(self, *args, **kwargs):
        kwargs['directory'] = ROOT_DIR
        super().__init__(*args, **kwargs)

    # أضف ترويسات CORS لكل الردود
    def end_headers(self):
        try:
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        except Exception:
            pass
        return super().end_headers()

    # دعم طلبات preflight
    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        if self.path == SAVE_REVIEW_ENDPOINT:
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            try:
                rec = json.loads(body.decode('utf-8')) or {}
                # حقول تقييم الخدمة الإلزامية
                customer_name = str(rec.get('customerName') or '').strip()
                customer_phone = str(rec.get('customerPhone') or '').strip()
                comment = str(rec.get('comment') or '').strip()
                service_rating = int(rec.get('serviceRating') or 0)
                timestamp = rec.get('timestamp') or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

                # حوّل الأرقام العربية/الفارسية إلى إنكليزية قبل التحقق
                def to_ascii_digits(s):
                    trans = str.maketrans({
                        '٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9',
                        '۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9'
                    })
                    return str(s or '').translate(trans)

                # تحقق من الهاتف (أرقام فقط مع إمكانية +، طول 7-15)
                phone_norm = re.sub(r'[\s\-()]+', '', to_ascii_digits(customer_phone))
                if not customer_name or not customer_phone or not comment or service_rating < 1 or service_rating > 5:
                    raise ValueError('Missing name/phone/comment or invalid serviceRating')
                if not re.match(r'^\+?\d{7,15}$', phone_norm):
                    raise ValueError('Invalid phone format')

                # فرع التقييم (اختياري)
                branch = str(rec.get('branch') or '').strip()
                # حقول اختيارية للأصناف إن وُجدت
                item_id = str(rec.get('itemId') or '').strip()
                item_name = str(rec.get('itemName') or '').strip()
                category = str(rec.get('category') or '').strip()
                rating = int(rec.get('rating') or 0)

                # read existing
                os.makedirs(os.path.join(ROOT_DIR, 'assets'), exist_ok=True)
                try:
                    if os.path.exists(REVIEWS_PATH):
                        with open(REVIEWS_PATH, 'r', encoding='utf-8') as f:
                            entries = json.load(f)
                            if not isinstance(entries, list):
                                entries = []
                    else:
                        entries = []
                except Exception:
                    entries = []

                submission_id = str(rec.get('submissionId') or '').strip()
                entry = {
                    'type': 'service',
                    'serviceRating': service_rating,
                    'comment': comment,
                    'customerName': customer_name,
                    'customerPhone': customer_phone,
                    'timestamp': timestamp,
                    'submissionId': submission_id
                }
                if branch:
                    entry['branch'] = branch
                # أضف معلومات الصنف (اختيارية)
                if item_name or item_id:
                    entry.update({
                        'itemId': item_id,
                        'itemName': item_name,
                        'category': category,
                        'rating': rating
                    })
                # منع التكرار بناءً على submissionId
                duplicate = False
                if submission_id:
                    for e in entries:
                        if str(e.get('submissionId') or '').strip() == submission_id:
                            duplicate = True
                            break
                if not duplicate:
                    entries.append(entry)
                    with open(REVIEWS_PATH, 'w', encoding='utf-8') as f:
                        json.dump(entries, f, ensure_ascii=False, indent=2)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'path': 'assets/reviews.json', 'duplicate': duplicate}).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
            return
        if self.path == '/api/save-menu':
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode('utf-8'))
                if not isinstance(data, list):
                    raise ValueError('Payload must be a JSON array')
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
                return

            # اكتب إلى ملف الأصول
            try:
                os.makedirs(os.path.dirname(ASSETS_PATH), exist_ok=True)
                with open(ASSETS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'path': 'assets/menu.json'}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
        elif self.path == '/api/save-categories':
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode('utf-8'))
                if not isinstance(data, list):
                    raise ValueError('Payload must be a JSON array')
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
                return

            try:
                os.makedirs(os.path.dirname(CATEGORIES_ASSETS_PATH), exist_ok=True)
                with open(CATEGORIES_ASSETS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'path': 'assets/categories.json'}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
        elif self.path == '/api/upload-image':
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode('utf-8'))
                data_url_or_b64 = payload.get('data')
                filename = payload.get('filename')
                if not data_url_or_b64:
                    raise ValueError('Missing image data')

                m = re.match(r'^data:(image/[\w.+-]+);base64,(.*)$', data_url_or_b64)
                if m:
                    mime = m.group(1)
                    b64data = m.group(2)
                else:
                    mime = None
                    b64data = data_url_or_b64

                ext_map = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/svg+xml': '.svg'}
                ext = ext_map.get(mime, '')
                if not filename:
                    filename = f"img_{int(time.time()*1000)}{ext or '.bin'}"

                # sanitize filename
                safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', filename)
                img_dir = os.path.join(ROOT_DIR, 'assets', 'images')
                os.makedirs(img_dir, exist_ok=True)
                abs_path = os.path.join(img_dir, safe_name)

                with open(abs_path, 'wb') as f:
                    f.write(base64.b64decode(b64data))

                rel_path = os.path.join('assets', 'images', safe_name).replace('\\', '/')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'path': rel_path}).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
        elif self.path == '/api/save-governorates':
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode('utf-8'))
                if not isinstance(data, list):
                    raise ValueError('Payload must be a JSON array')
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
                return

            try:
                os.makedirs(os.path.dirname(GOVS_ASSETS_PATH), exist_ok=True)
                with open(GOVS_ASSETS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'path': 'assets/governorates.json'}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
        elif self.path == '/api/log-customer':
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            try:
                rec = json.loads(body.decode('utf-8')) or {}
                name = (rec.get('name') or '').strip()
                phone = (rec.get('phone') or '').strip()
                branch = (rec.get('branch') or '').strip()
                ts = rec.get('timestamp') or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                order_number = rec.get('orderNumber')
                if not name or not phone:
                    raise ValueError('Missing name or phone')

                log_path = os.path.join(ROOT_DIR, 'assets', 'customer_logs.json')
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                try:
                    if os.path.exists(log_path):
                        with open(log_path, 'r', encoding='utf-8') as f:
                            entries = json.load(f)
                            if not isinstance(entries, list):
                                entries = []
                    else:
                        entries = []
                except Exception:
                    entries = []

                entry = {
                    'name': name,
                    'phone': phone,
                    'branch': branch,
                    'orderNumber': order_number,
                    'timestamp': ts
                }
                # لا تخزّن نقاط الولاء أو وقت محدد هنا
                entries.append(entry)
                with open(log_path, 'w', encoding='utf-8') as f:
                    json.dump(entries, f, ensure_ascii=False, indent=2)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True}).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
        elif self.path == '/api/forward-webhook':
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body.decode('utf-8')) or {}
                url = (payload.get('url') or '').strip()
                data = payload.get('data')
                if not url:
                    raise ValueError('Missing url')
                if data is None:
                    raise ValueError('Missing data')
                # تحقّق منع التكرار عبر submissionId عند التوجيه
                submission_id = str((data or {}).get('submissionId') or '').strip()
                forwarded_duplicate = False
                # حاول قراءة المراجعات لتعليم «مُوجّه»
                entries = []
                try:
                    if os.path.exists(REVIEWS_PATH):
                        with open(REVIEWS_PATH, 'r', encoding='utf-8') as f:
                            entries = json.load(f)
                            if not isinstance(entries, list):
                                entries = []
                except Exception:
                    entries = []

                idx_to_update = None
                if submission_id and entries:
                    for i, e in enumerate(entries):
                        if str(e.get('submissionId') or '').strip() == submission_id:
                            idx_to_update = i
                            if e.get('forwarded'):
                                forwarded_duplicate = True
                            break

                if forwarded_duplicate:
                    # تم التوجيه سابقًا؛ لا تُكرر الطلب
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(json.dumps({'ok': True, 'status': 200, 'duplicate': True, 'alreadyForwarded': True}).encode('utf-8'))
                    return

                # نفّذ الطلب الخارجي
                req = urllib.request.Request(url=url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = resp.getcode()

                # علّم التقديم كموجّه عند النجاح
                if status == 200 and idx_to_update is not None:
                    try:
                        entries[idx_to_update]['forwarded'] = True
                        entries[idx_to_update]['forwardedAt'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        entries[idx_to_update]['forwardStatus'] = status
                        with open(REVIEWS_PATH, 'w', encoding='utf-8') as f:
                            json.dump(entries, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

                self.send_response(200 if status == 200 else status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'status': status, 'duplicate': False}).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
        elif self.path == SAVE_SETTINGS_ENDPOINT:
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode('utf-8'))
                if not isinstance(data, dict):
                    raise ValueError('Payload must be a JSON object')
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
                return

            try:
                os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
                with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'path': 'assets/settings.json'}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))

        elif self.path == SAVE_ANNOUNCEMENTS_ENDPOINT:
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode('utf-8'))
                if not isinstance(data, dict):
                    raise ValueError('Payload must be a JSON object')
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
                return

            try:
                os.makedirs(os.path.dirname(ANNOUNCEMENTS_PATH), exist_ok=True)
                with open(ANNOUNCEMENTS_PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'path': 'assets/announcements.json'}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))

        elif self.path == SAVE_HERO_ENDPOINT:
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode('utf-8'))
                if not isinstance(data, dict):
                    raise ValueError('Payload must be a JSON object')
                # طبّع بعض الحقول
                iv = int(data.get('intervalMs') or 0)
                if iv > 0 and iv < 50:
                    data['intervalMs'] = iv * 1000
                imgs = data.get('images')
                if imgs is None:
                    data['images'] = []
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
                return

            try:
                os.makedirs(os.path.dirname(HERO_PATH), exist_ok=True)
                with open(HERO_PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True, 'path': 'assets/hero.json'}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))

        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({'ok': False, 'error': 'Not Found'}).encode('utf-8'))

    def do_GET(self):
        # تنزيل مجلد الأصول كملف ZIP عبر المسار /download/assets
        if self.path.startswith('/download/assets'):
            assets_dir = os.path.join(ROOT_DIR, 'assets')
            if not os.path.isdir(assets_dir):
                self.send_response(404)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': 'assets directory not found', 'path': 'assets/'}).encode('utf-8'))
                return

            try:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                    for root, _, files in os.walk(assets_dir):
                        for f in files:
                            abs_path = os.path.join(root, f)
                            rel = os.path.relpath(abs_path, ROOT_DIR)
                            arc = rel.replace('\\', '/')  # استخدم / داخل الأرشيف
                            zf.write(abs_path, arc)
                data = buf.getvalue()
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Disposition', 'attachment; filename="assets.zip"')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
            return

        # لباقي المسارات، استخدم تقديم الملفات العادي
        return super().do_GET()


def main():
    port = int(os.environ.get('PORT', '8090'))
    httpd = ThreadingHTTPServer(('', port), Handler)
    print(f"Serving at http://localhost:{port}/ (root: {ROOT_DIR})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
