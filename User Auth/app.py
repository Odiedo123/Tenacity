from flask import Flask, request, send_from_directory, jsonify, render_template, redirect, url_for, session, Response
import bcrypt
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
from supabase import create_client, Client
from b2sdk.v2 import B2Api, InMemoryAccountInfo  # Backblaze B2 SDK

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

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
    response.headers['Access-Control-Allow-Origin'] = 'https://www.tenacity.ct.ws'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response


# --------------Bypass free tier idling-------------------------------#
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
    total_storage = 5000 * 1024 * 1024  # 5GB in bytes
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
@login_required
def upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'files' not in request.files:
            return jsonify({"error": "No files provided"}), 400

        files = request.files.getlist('files')
        uploaded_files = []

        for file in files:
            if file.filename == '':
                continue  # Skip empty files

            filename = secure_filename(file.filename)
            s3_key = f"user_{session['user_id']}/{filename}"  # Store files in user-specific folders

            try:
                # Debugging: Print file details
                print(f"Uploading file: {filename}, size: {len(file.read())} bytes")
                file.seek(0)  # Reset file pointer after reading

                # Upload file to Backblaze B2
                bucket.upload_bytes(file.read(), s3_key)
                uploaded_files.append(filename)

                # Save file metadata to Supabase
                supabase.table('files').insert({
                    'filename': filename,
                    'filepath': s3_key,
                    'user_id': session['user_id']
                }).execute()

            except Exception as e:
                # Debugging: Print the exception
                print(f"Error uploading file: {e}")
                return jsonify({"error": str(e)}), 500

        return jsonify({"message": "Files uploaded successfully", "files": uploaded_files}), 200

    return render_template('upload.html')

# -------- File serving ----------------------------------------------------- #
@app.route('/files/<filename>')
@login_required
def serve_file(filename):
    try:
        # Verify file ownership
        file_data = supabase.table('files') \
            .select('filepath') \
            .eq('filename', secure_filename(filename)) \
            .eq('user_id', session['user_id']) \
            .execute()
        
        if not file_data.data:
            return jsonify({"error": "File not found"}), 404

        s3_key = file_data.data[0]['filepath']
        
        # Download file from Backblaze as a stream
        file_info = bucket.get_file_info_by_name(s3_key)
        file_response = bucket.download_file_by_name(s3_key)
        
        # Stream the file through Flask with proper headers
        return Response(
            file_response.content,
            headers={
                "Content-Type": file_info.content_type,
                "Content-Disposition": f"attachment; filename={secure_filename(filename)}",
                "Content-Length": str(file_info.content_length),
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
        
    except Exception as e:
        app.logger.error(f"File serve error: {str(e)}")
        return jsonify({"error": "Failed to serve file"}), 500

# -------- File listing ----------------------------------------------------- #
@app.route('/files/list', methods=['GET'])
@login_required
def list_files():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    files_data = supabase.table('files').select('filename, filepath').eq('user_id', session['user_id']).execute()
    files = files_data.data if files_data.data else []

    file_list = []
    for file in files:
        try:
            # Get file metadata from Backblaze B2
            file_info = bucket.get_file_info_by_name(file['filepath'])
            last_modified_timestamp = file_info.upload_timestamp / 1000  # Convert to seconds
            last_modified_readable = datetime.fromtimestamp(last_modified_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            file_list.append({
                "name": file['filename'],
                "size": file_info.content_length,
                "type": file['filename'].split('.')[-1],
                "last_modified": last_modified_readable
            })
        except Exception as e:
            continue  # Skip files that can't be accessed

    return jsonify({"files": file_list})

# -------- Delete ---------------------------------------------------------- #
@app.route('/files/delete/<filename>', methods=['DELETE'])
@login_required
def delete_file(filename):
    try:
        # 1. Get file metadata from Supabase
        file_data = supabase.table('files') \
            .select('filepath') \
            .eq('filename', secure_filename(filename)) \
            .eq('user_id', session['user_id']) \
            .execute()
        
        if not file_data.data:
            return jsonify({"error": "File not found"}), 404

        s3_key = file_data.data[0]['filepath']

        # 2. Get file version info from Backblaze
        file_info = bucket.get_file_info_by_name(s3_key)
        
        # 3. Delete from Backblaze (using both ID and name)
        bucket.delete_file_version(file_info.id_, file_info.file_name)

        # 4. Delete from Supabase
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

            # Get the S3 key for the file from Supabase
            file_data = supabase.table('files').select('filepath').eq('filename', safe_filename).eq('user_id', session['user_id']).execute()
            if not file_data.data:
                return jsonify({"error": "File not found"}), 404

            s3_key = file_data.data[0]['filepath']
            new_s3_key = f"user_{session['user_id']}/{new_filename}"

            # Rename the file in Backblaze B2
            bucket.copy_file(s3_key, new_s3_key)
            bucket.delete_file_version(s3_key)

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

# -------- Download ---------------------------------------------------------- #
@app.route('/files/<filename>', methods=['GET'])
@login_required
def download_file(filename):
    try:
        # Get the S3 key for the file from Supabase
        file_data = supabase.table('files').select('filepath').eq('filename', filename).eq('user_id', session['user_id']).execute()
        if not file_data.data:
            return jsonify({"error": "File not found"}), 404

        s3_key = file_data.data[0]['filepath']

        # Generate a download URL for the file
        download_url = bucket.get_download_url(s3_key)
        return redirect(download_url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)