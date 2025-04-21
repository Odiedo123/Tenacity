from flask import Flask, request, send_from_directory, jsonify, render_template, redirect, url_for, session, Response, make_response, send_file
import bcrypt
import os
import io
import zipfile
import requests
import concurrent.futures
import time
from concurrent.futures import ThreadPoolExecutor
from flask_compress import Compress
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from functools import wraps
from supabase import create_client, Client
from b2sdk.v2 import B2Api, InMemoryAccountInfo
from email.parser import BytesParser  # <-- Missing import added

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
Compress(app) 

csp = {
    'default-src': ["'self'"],  # Keep default security
    'script-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://demo.arcade.software", "https://www.googletagmanager.com"],  # Allow inline scripts
    'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],  # Allow inline styles
    'img-src': ["'self'", "data:", "*.backblazeb2.com", "https://api.producthunt.com"],  # Allow images from Backblaze
    'connect-src': ["'self'", "https://api.backblazeb2.com", "*.backblazeb2.com"],  # Allow API calls (uploads)
    'font-src': ["'self'", "https://fonts.gstatic.com"],
    'frame-ancestors': ["'self'", "https://demo.arcade.software"],
    'frame-src': ["https://demo.arcade.software"],
}

Talisman(app, content_security_policy=csp, force_https=True, strict_transport_security=True, frame_options='DENY')

# -------- Setting up limiter to avoid overloading--------------------------------------- #
limiter = Limiter(
    key_func=lambda: session.get("user_id", get_remote_address()),  # Use user_id if logged in, else IP
    app=app,
    default_limits=["100 per minute"]  # Global limit
)

# Initialize Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(supabase_url, supabase_key)

# Initialize Backblaze B2 client
info = InMemoryAccountInfo()
b2_api = B2Api(info)
b2_api.authorize_account("production", os.getenv('B2_KEY_ID'), os.getenv('B2_APPLICATION_KEY'))
bucket = b2_api.get_bucket_by_name(os.getenv('B2_BUCKET_NAME'))

# -------- Allow CORS policy--------------------------------------- #
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = 'https://www.tenacity.ct.ws, https://demo.arcade.software, https://www.googletagmanager.com'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cross-Origin-Resource-Policy'] = 'cross-origin' 
    return response

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        return response

# --------------Bypass free tier idling using Uptime Robot-------------------------------#
@app.route('/health')
def health_check():
    return jsonify(status="OK", time=datetime.now()), 200

# -------- Sitemap ---------------------------------------------------------- #
@app.route('/sitemap.xml')
def sitemap():
    current_directory = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(current_directory, 'sitemap.xml')

# -------- Robot.txt ---------------------------------------------------------- #
@app.route('/robots.txt')
def robots():
    current_directory = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(current_directory, 'robots.txt')

# -------- Signup ---------------------------------------------------------- #
@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute") 
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Check if email already exists
        existing_user = supabase.table('users').select('*').eq('email', email).execute()
        if existing_user.data:
            error = "This email is already registered."
            return render_template('sign-in.html', error=error)

        # Hash the password using bcrypt
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Insert the new user into Supabase
        new_user = supabase.table('users').insert({
            'email': email,
            'password': hashed_password
        }).execute()

        return redirect(url_for('login'))

    return render_template('sign-in.html')

# -------- Log In ---------------------------------------------------------- #
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute") 
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Query the user from Supabase
        user_data = supabase.table('users').select('*').eq('email', email).execute()
        if not user_data.data:
            error = "Incorrect Email or Password."
            return render_template('log-in.html', error=error)
        
        user = user_data.data[0]

        if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            session['user_id'] = user['id']  # Store user ID in session
            return redirect(url_for('home'))
        else:
            error = "Incorrect Email or Password."
            return render_template('log-in.html', error=error)

    return render_template('log-in.html')

# -------- Log Out---------------------------------------------------------- #
@app.route('/logout')
def logout():
    session.clear()  # Clear the session on logout
    return redirect(url_for('login'))

# -------- Payments Page ---------------------------------------------------------- #
@app.route('/payments', methods=['GET', 'POST'])
@login_required
def payments():
    return render_template('payments.html')

# -------- Main Place ---------------------------------------------------------- #
@app.route('/')
def index():
    if 'user_id' in session and not session.get('redirected_once'):
        # Redirect if logged in and not already redirected
        session['redirected_once'] = True
        return redirect(url_for('home'))
    return render_template('index.html')

# -------- Home ---------------------------------------------------------- #
@app.route('/home')
@login_required
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Get files associated with the logged-in user
    files_data = supabase.table('files').select('filename').eq('user_id', session['user_id']).execute()
    files = files_data.data if files_data.data else []

    return render_template('home.html', files=files)

# -------- Dashboard ---------------------------------------------------------- #
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# -------- Data Calculation ---------------------------------------------------------- #
def calculate_storage_for_user(user_id):
    total_storage = 100 * 1024 * 1024 * 1024  #100GB in bytes
    used_storage = 0
    file_counts = {
        "files": 0,
        "documents": 0,
        "images": 0,
        "others": 0
    }

    # Fetch files for the specific user from Supabase
    files_data = supabase.table('files').select('filepath').eq('user_id', user_id).execute()
    user_files = files_data.data if files_data.data else []

    for file in user_files:
        try:
            # Get file metadata from Backblaze B2
            file_info = bucket.get_file_info_by_name(file['filepath'])
            file_size = file_info.content_length

            # Convert file size to MB
            file_size_mb = file_size / (1024 * 1024)

            # Classify by file type and accumulate sizes in MB
            if file['filepath'].lower().endswith((".doc", ".docx", ".pdf", ".txt")):
                file_counts["documents"] += file_size_mb
            elif file['filepath'].lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp")):
                file_counts["images"] += file_size_mb
            else:
                file_counts["others"] += file_size_mb

            # Update total file count and used storage
            file_counts["files"] += 1
            used_storage += file_size_mb  # Sum up the used storage in MB
        except Exception as e:
            continue  # Skip files that can't be accessed

    # Convert total storage and used storage to GB
    total_storage_gb = total_storage / (1024 * 1024 * 1024)  # Convert to GB
    used_storage_gb = used_storage / 1024  # Convert MB to GB

    return total_storage_gb, used_storage_gb, file_counts  # Return both total and used in GB


@app.route('/api/storage', methods=['GET'])
@login_required
def get_storage_data():
    user_id = session.get('user_id')  # Retrieve the logged-in user's ID
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    total_storage, used_storage, file_counts = calculate_storage_for_user(user_id)

    return jsonify({
        "totalStorage": total_storage * 1024,  # Convert to MB
        "usedStorage": used_storage,  # Convert to MB
        "files": file_counts["files"],
        "documents": file_counts["documents"],
        "images": file_counts["images"],
        "others": file_counts["others"]
    })

# -------- My Files ---------------------------------------------------------- #
@app.route('/files')
@login_required
def files():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Fetch files for the logged-in user
    files_data = supabase.table('files').select('filename').eq('user_id', session['user_id']).execute()
    files = files_data.data if files_data.data else []

    return render_template('files.html', files=files)

# -------- Upload ---------------------------------------------------------- #
@app.route('/upload', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
@login_required
def upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'files' not in request.files:
            return jsonify({"error": "No files provided"}), 400

        files = request.files.getlist('files')
        upload_results = []  # List of metadata dicts for files
        errors = []
        user_id = session['user_id']

        # Function to process each file
        def process_file(file):
            if file.filename == '':
                return None  # Skip empty files
            filename = secure_filename(file.filename)
            s3_key = f"user_{user_id}/{filename}"
            try:
                # Read file contents in full (consider streaming for very large files)
                file_contents = file.read()
                # Upload to Backblaze B2
                uploaded_file = bucket.upload_bytes(file_contents, s3_key)
                file_id = uploaded_file.id_
                return {
                    'filename': filename,
                    'filepath': s3_key,
                    'file_id': file_id,
                    'user_id': user_id
                }
            except Exception as e:
                return e

        # Process all files concurrently
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(process_file, file): file for file in files}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if isinstance(result, Exception):
                    errors.append(str(result))
                elif result is not None:
                    upload_results.append(result)

        # If any error occurred, log it and return an error response
        if errors:
            app.logger.error("Upload errors: " + "; ".join(errors))
            return jsonify({"error": "One or more files failed to upload", "details": errors}), 500

        # Bulk insert file metadata into Supabase
        try:
            supabase.table('files').insert(upload_results).execute()
        except Exception as e:
            app.logger.error(f"Supabase insert error: {str(e)}")
            return jsonify({"error": "Failed to save file metadata", "details": str(e)}), 500

        # Return the list of uploaded filenames
        uploaded_filenames = [record['filename'] for record in upload_results]
        return jsonify({"message": "Files uploaded successfully", "files": uploaded_filenames}), 200

    return render_template('upload.html')

# -------- File listing ----------------------------------------------------- #
# In-memory cache for file info: key is filepath, value is a dictionary with info and timestamp.
FILE_INFO_CACHE = {}
CACHE_TTL = 90  # Cache time-to-live in seconds

def get_file_info_cached(bucket, filepath):
    now = time.time()
    # Check if cached and valid
    if filepath in FILE_INFO_CACHE:
        cached = FILE_INFO_CACHE[filepath]
        if now - cached['timestamp'] < CACHE_TTL:
            return cached['info']
    try:
        info = bucket.get_file_info_by_name(filepath)
        FILE_INFO_CACHE[filepath] = {'info': info, 'timestamp': now}
        return info
    except Exception as e:
        # Optionally log error here if needed.
        return None

@app.route('/files/list', methods=['GET'])
@login_required
def list_files():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        # 2. Fetch files from Supabase
        supabase_files = supabase.table('files').select('filename, filepath')\
            .eq('user_id', session['user_id']).execute().data

        if not supabase_files:
            return jsonify({"files": []})

        # 3. Get file info concurrently, using caching to reduce repeated API calls
        with ThreadPoolExecutor(max_workers=10) as executor:
            file_infos = list(executor.map(
                lambda f: get_file_info_cached(bucket, f['filepath']),
                supabase_files
            ))

        # 4. Format response using the cached or freshly retrieved file information
        file_list = []
        for file, info in zip(supabase_files, file_infos):
            if not info:
                continue
            file_list.append({
                "name": file['filename'],
                "size": info.content_length,
                "type": file['filename'].split('.')[-1],
                "last_modified": datetime.fromtimestamp(info.upload_timestamp / 1000)\
                    .strftime('%Y-%m-%d %H:%M:%S')
            })

        return jsonify({"files": file_list})

    except Exception as e:
        app.logger.error(f"Error in /files/list: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# -------- Delete ---------------------------------------------------------- #
@app.route('/files/delete/<filename>', methods=['DELETE'])
@login_required
def delete_file(filename):
    try:
        # 1. Get file metadata from Supabase
        file_data = supabase.table('files') \
            .select('filepath, file_id') \
            .eq('filename', secure_filename(filename)) \
            .eq('user_id', session['user_id']) \
            .execute()
        
        if not file_data.data:
            return jsonify({"error": "File not found"}), 404

        s3_key = file_data.data[0]['filepath']
        file_id = file_data.data[0]['file_id']

        # 2. Delete from Backblaze B2 using file ID
        bucket.delete_file_version(file_id, s3_key)

        # 3. Delete from Supabase
        supabase.table('files') \
            .delete() \
            .eq('filename', filename) \
            .eq('user_id', session['user_id']) \
            .execute()

        return jsonify({"message": "File deleted successfully"}), 200

    except Exception as e:
        app.logger.error(f"Delete error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# -------- Rename ---------------------------------------------------------- #
@app.route('/files/edit/<filename>', methods=['POST'])
@login_required
def edit_file(filename):
    try:
        new_filename = request.form.get('new_filename')  # Get new filename from the form
        if new_filename:
            safe_filename = secure_filename(filename)
            new_filename = secure_filename(new_filename)

            # Get the file data from Supabase
            file_data = supabase.table('files') \
                .select('filepath, file_id') \
                .eq('filename', safe_filename) \
                .eq('user_id', session['user_id']) \
                .execute()
            
            if not file_data.data:
                return jsonify({"error": "File not found"}), 404

            old_s3_key = file_data.data[0]['filepath']
            file_id = file_data.data[0]['file_id']
            new_s3_key = f"user_{session['user_id']}/{new_filename}"

            # Rename the file in Backblaze B2 (copy + delete)
            bucket.copy_file(old_s3_key, new_s3_key)
            bucket.delete_file_version(file_id, old_s3_key)

            # Update the file metadata in Supabase
            supabase.table('files').update({
                'filename': new_filename,
                'filepath': new_s3_key
            }).eq('filename', safe_filename).eq('user_id', session['user_id']).execute()

            return jsonify({"message": "File renamed successfully"}), 200
        else:
            return jsonify({"error": "No new filename provided"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------- Sort Files ----------------------------------------------------- #
@app.route('/files/sort', methods=['GET'])
@login_required
def sort_files():
    sort_by = request.args.get('by', 'name')  # Default sorting by name
    sort_order = request.args.get('order', 'asc')  # Default sorting order: ascending

    # Fetch files for the logged-in user from Supabase
    files_data = supabase.table('files').select('filename, filepath').eq('user_id', session['user_id']).execute()
    files = files_data.data if files_data.data else []

    file_list = []
    for file in files:
        try:
            # Get file metadata from Backblaze B2
            file_info = bucket.get_file_info_by_name(file['filepath'])
            file_list.append({
                "name": file['filename'],
                "size": file_info.content_length,
                "type": file['filename'].split('.')[-1],
                "last_modified": file_info.upload_timestamp
            })
        except Exception as e:
            continue  # Skip files that can't be accessed

    # Sort the files based on the 'by' and 'order' parameters
    if sort_by == 'size':
        sorted_files = sorted(file_list, key=lambda x: x['size'], reverse=(sort_order == 'desc'))
    elif sort_by == 'date':
        sorted_files = sorted(file_list, key=lambda x: x['last_modified'], reverse=(sort_order == 'desc'))
    else:
        # Default to sorting by name
        sorted_files = sorted(file_list, key=lambda x: x['name'].lower(), reverse=(sort_order == 'desc'))

    return jsonify({'files': sorted_files})

# -------- Redirect Routes ---------------------------------------------------------- #
@app.route('/redirect_to_log-in')
def redirect_to_log_in():
    return redirect(url_for('login'))

@app.route('/redirect_to_home')
def redirect_to_home():
    return redirect(url_for('home'))

@app.route('/redirect_to_dashboard')
def redirect_to_dashboard():
    return redirect(url_for('dashboard'))

# -------- Download Files ------------------------------------ #
@app.route('/files/download/<filename>', methods=['GET'])
@limiter.limit("5 per minute") 
@login_required
def download_file(filename):
    try:
        # 1. Verify file exists in database
        file_data = supabase.table('files') \
            .select('filepath, file_id') \
            .eq('filename', secure_filename(filename)) \
            .eq('user_id', session['user_id']) \
            .execute()
        
        if not file_data.data:
            return jsonify({"error": "File not found"}), 404

        filepath = file_data.data[0]['filepath']

        # 2. Fetch the actual file from Backblaze B2
        auth_token = bucket.get_download_authorization(filepath, 600)
        file_url = (
            f"https://f005.backblazeb2.com/file/tenacity-files/"
            f"{filepath}?Authorization={auth_token}"
        )

        response = requests.get(file_url)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch file"}), 500

        # 3. Create an in-memory ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(filename, response.content)
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            as_attachment=True,
            download_name=f"{filename}.zip",
            mimetype="application/zip"
        )
    
    except Exception as e:
        app.logger.error(f"Download failed: {str(e)}")
        return jsonify({"error": "Download failed", "details": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)