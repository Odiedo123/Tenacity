from flask import Flask, request, send_from_directory, jsonify, render_template, redirect, url_for, session
import bcrypt
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
import psycopg2  # For PostgreSQL
from psycopg2.extras import RealDictCursor
from b2sdk.v2 import B2Api, InMemoryAccountInfo  # Backblaze B2 SDK

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Initialize Backblaze B2 client
info = InMemoryAccountInfo()
b2_api = B2Api(info)
b2_api.authorize_account("production", os.getenv('B2_KEY_ID'), os.getenv('B2_APPLICATION_KEY'))
bucket = b2_api.get_bucket_by_name(os.getenv('B2_BUCKET_NAME'))

# Function to connect to PostgreSQL
def get_db_connection():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    return conn

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

        # Check if email already exists in the database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            error = "This email is already registered."
            return render_template('sign-in.html', error=error)

        # Hash the password using bcrypt
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # Decode the hashed password to a UTF-8 string
        hashed_password_str = hashed_password.decode('utf-8')

        # Insert the new user into the database
        cursor.execute("INSERT INTO users (email, password) VALUES (%s, %s)", (email, hashed_password_str))
        conn.commit()
        cursor.close()
        conn.close()

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

        # Query the database for the user with the entered email
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, password FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and bcrypt.checkpw(password.encode('utf-8'), user[2].encode('utf-8')):
            session['user_id'] = user[0]  # Store user ID in session
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM files WHERE user_id = %s", (session['user_id'],))
    files = cursor.fetchall()
    cursor.close()
    conn.close()

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

    # Fetch files for the specific user from the database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filepath FROM files WHERE user_id = %s", (user_id,))
    user_files = cursor.fetchall()
    cursor.close()
    conn.close()

    for (s3_key,) in user_files:
        try:
            # Get file metadata from Backblaze B2
            file_info = bucket.get_file_info_by_name(s3_key)
            file_size = file_info.content_length

            # Convert file size to MB
            file_size_mb = file_size / (1024 * 1024)

            # Classify by file type and accumulate sizes in MB
            if s3_key.lower().endswith((".doc", ".docx", ".pdf", ".txt")):
                file_counts["documents"] += file_size_mb
            elif s3_key.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp")):
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM files WHERE user_id = %s", (session['user_id'],))
    files = cursor.fetchall()
    cursor.close()
    conn.close()

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

                # Save file metadata to the database
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO files (filename, filepath, user_id) VALUES (%s, %s, %s)",
                    (filename, s3_key, session['user_id'])
                )
                conn.commit()
                cursor.close()
                conn.close()

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
        # Get the S3 key for the file
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT filepath FROM files WHERE filename = %s AND user_id = %s", (filename, session['user_id']))
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            return jsonify({"error": "File not found"}), 404

        s3_key = result[0]

        # Generate a download URL for the file
        download_url = bucket.get_download_url(s3_key)
        return redirect(download_url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------- File listing ----------------------------------------------------- #
@app.route('/files/list', methods=['GET'])
@login_required
def list_files():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename, filepath FROM files WHERE user_id = %s", (session['user_id'],))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    files = []
    for row in rows:
        filename = row[0]
        s3_key = row[1]

        # Get file metadata from Backblaze B2
        try:
            file_info = bucket.get_file_info_by_name(s3_key)
            last_modified_timestamp = file_info.upload_timestamp / 1000  # Convert to seconds
            last_modified_readable = datetime.fromtimestamp(last_modified_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            files.append({
                "name": filename,
                "size": file_info.content_length,
                "type": filename.split('.')[-1],
                "last_modified": last_modified_readable
            })
        except Exception as e:
            continue  # Skip files that can't be accessed

    return jsonify({"files": files})

# -------- Delete ---------------------------------------------------------- #
@app.route('/files/delete/<filename>', methods=['DELETE'])
@login_required
def delete_file(filename):
    try:
        # Get the S3 key for the file
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT filepath FROM files WHERE filename = %s AND user_id = %s", (filename, session['user_id']))
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            return jsonify({"error": "File not found"}), 404

        s3_key = result[0]

        # Delete file from Backblaze B2
        bucket.delete_file_version(s3_key)

        # Delete file metadata from the database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM files WHERE filename = %s AND user_id = %s", (filename, session['user_id']))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "File deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------- Rename ---------------------------------------------------------- #
@app.route('/files/edit/<filename>', methods=['POST'])
def edit_file(filename):
    try:
        new_filename = request.form.get('new_filename')  # Get new filename from the form
        if new_filename:
            safe_filename = secure_filename(filename)
            new_filename = secure_filename(new_filename)

            # Get the S3 key for the file
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT filepath FROM files WHERE filename = %s AND user_id = %s", (safe_filename, session['user_id']))
            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if not result:
                return jsonify({"error": "File not found"}), 404

            s3_key = result[0]
            new_s3_key = f"user_{session['user_id']}/{new_filename}"

            # Rename the file in Backblaze B2
            bucket.copy_file(s3_key, new_s3_key)
            bucket.delete_file_version(s3_key)

            # Update the file metadata in the database
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE files SET filename = %s, filepath = %s WHERE filename = %s AND user_id = %s",
                (new_filename, new_s3_key, safe_filename, session['user_id'])
            )
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({"message": "File renamed successfully"}), 200
        else:
            return jsonify({"error": "No new filename provided"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------- Sort Files ----------------------------------------------------- #
@app.route('/files/sort', methods=['GET'])
def sort_files():
    sort_by = request.args.get('by', 'name')  # Default sorting by name
    sort_order = request.args.get('order', 'asc')  # Default sorting order: ascending

    # Fetch files for the logged-in user
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename, filepath FROM files WHERE user_id = %s", (session['user_id'],))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    files = []
    for row in rows:
        filename = row[0]
        s3_key = row[1]

        # Get file metadata from Backblaze B2
        try:
            file_info = bucket.get_file_info_by_name(s3_key)
            files.append({
                "name": filename,
                "size": file_info.content_length,
                "type": filename.split('.')[-1],
                "last_modified": file_info.upload_timestamp
            })
        except Exception as e:
            continue  # Skip files that can't be accessed

    # Sort the files based on the 'by' and 'order' parameters
    if sort_by == 'size':
        sorted_files = sorted(files, key=lambda x: x['size'], reverse=(sort_order == 'desc'))
    elif sort_by == 'date':
        sorted_files = sorted(files, key=lambda x: x['last_modified'], reverse=(sort_order == 'desc'))
    else:
        # Default to sorting by name
        sorted_files = sorted(files, key=lambda x: x['name'].lower(), reverse=(sort_order == 'desc'))

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
def download_file(filename):
    try:
        # Get the S3 key for the file
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT filepath FROM files WHERE filename = %s AND user_id = %s", (filename, session['user_id']))
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            return jsonify({"error": "File not found"}), 404

        s3_key = result[0]

        # Generate a download URL for the file
        download_url = bucket.get_download_url(s3_key)
        return redirect(download_url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)