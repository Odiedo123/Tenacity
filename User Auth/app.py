from flask import Flask, request,send_from_directory, jsonify, render_template, redirect, url_for, session
import mysql.connector
import bcrypt
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Connect to MariaDB
db = mysql.connector.connect(
    host=os.getenv('FLASK_HOST'),
    user=os.getenv('FLASK_USER'),
    password=os.getenv('FLASK_PASSWORD'),
    database=os.getenv('FLASK_DATABASE')
)

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
cursor = db.cursor()

# Helper to get user-specific folder
def get_user_folder():
    """Returns the path to the current user's subfolder within UPLOAD_FOLDER."""
    if 'user_id' in session:
        user_folder = os.path.join(app.config['UPLOAD_FOLDER'], f"user_{session['user_id']}")
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
        return user_folder
    return None

# -------- Signup ---------------------------------------------------------- #
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Check if email already exists in the database
        cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            error="This email is already registered."
            return render_template('sign-in.html', error=error)
        
        # Hash the password using bcrypt
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # Insert the new user into the database
        cursor.execute("INSERT INTO users (email, password) VALUES (%s, %s)", (email, hashed_password))
        db.commit()

        return redirect(url_for('login'))

    return render_template('sign-in.html')


# -------- Log In ---------------------------------------------------------- #

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))  # Redirect to login if not logged in
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Query the database for the user with the entered email
        cursor.execute("SELECT id, email, password FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user and bcrypt.checkpw(password.encode('utf-8'), user[2].encode('utf-8')):
            session['user_id'] = user[0]  # Store user ID in session
            return redirect(url_for('home'))
        else:
            error="Incorrect Email or Password."
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
    cursor.execute("SELECT filename FROM files WHERE user_id = %s", (session['user_id'],))
    files = cursor.fetchall()
    
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
    cursor.execute("SELECT filepath, filename FROM files WHERE user_id = %s", (user_id,))
    user_files = cursor.fetchall()

    for file_path, filename in user_files:
        if os.path.isfile(file_path):
            file_size = os.path.getsize(file_path)
            
            # Convert file size to MB
            file_size_mb = file_size / (1024 * 1024)

            # Classify by file type and accumulate sizes in MB
            if filename.lower().endswith((".doc", ".docx", ".pdf", ".txt")):
                file_counts["documents"] += file_size_mb
            elif filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp")):
                file_counts["images"] += file_size_mb
            else:
                file_counts["others"] += file_size_mb

            # Update total file count and used storage
            file_counts["files"] += 1
            used_storage += file_size_mb  # Sum up the used storage in MB

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
        "usedStorage": used_storage,    # Convert to MB
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
    cursor.execute("SELECT filename FROM files WHERE user_id = %s", (session['user_id'],))
    files = cursor.fetchall()  # Ensure all results are fetched

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
        user_folder = get_user_folder()  # Get user-specific folder

        for file in files:
            filename = secure_filename(file.filename)
            file_path = os.path.join(user_folder, filename)  # Save to user folder
            file.save(file_path)
            
            cursor.execute(
                "INSERT INTO files (filename, filepath, user_id) VALUES (%s, %s, %s)",
                (filename, file_path, session['user_id'])
            )
            db.commit()

        return jsonify({"message": "Files uploaded successfully"}), 200

    return render_template('upload.html')
# -------- File serving ----------------------------------------------------- #
@app.route('/files/<filename>')
@login_required
def serve_file(filename):
    user_folder = get_user_folder()
    try:
        file_path = os.path.join(user_folder, filename)
        return send_from_directory(user_folder, filename)
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

# -------- File listing ----------------------------------------------------- #
@app.route('/files/list', methods=['GET'])
@login_required
def list_files():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    cursor.execute("SELECT filename, filepath FROM files WHERE user_id = %s", (session['user_id'],))
    rows = cursor.fetchall()

    user_folder = get_user_folder()
    files = []
    for row in rows:
        filename = row[0]
        file_path = row[1]
        if os.path.isfile(file_path):
            files.append({
                "name": filename,
                "size": os.path.getsize(file_path),
                "type": filename.split('.')[-1],
                "last_modified": datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
            })

    return jsonify({"files": files})

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
        # Secure the filename before serving
        safe_filename = secure_filename(filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)

        if os.path.exists(file_path):
            return send_from_directory(app.config['UPLOAD_FOLDER'], safe_filename, as_attachment=True)
        else:
            return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------- Delete ---------------------------------------------------------- #
@app.route('/files/delete/<filename>', methods=['DELETE'])
@login_required
def delete_file(filename):
    user_folder = get_user_folder()
    try:
        file_path = os.path.join(user_folder, secure_filename(filename))
        if os.path.exists(file_path):
            os.remove(file_path)
            cursor.execute("DELETE FROM files WHERE filename = %s AND user_id = %s", (filename, session['user_id']))
            db.commit()
            return jsonify({"message": "File deleted successfully"}), 200
        else:
            return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------- Rename ---------------------------------------------------------- 
@app.route('/files/edit/<filename>', methods=['POST'])
def edit_file(filename):
    try:
        new_filename = request.form.get('new_filename')  # Get new filename from the form
        if new_filename:
            safe_filename = secure_filename(filename)
            new_filename = secure_filename(new_filename)
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
            new_file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)

            if os.path.exists(file_path):
                os.rename(file_path, new_file_path)  # Rename the file
                return jsonify({"message": "File renamed successfully"}), 200
            else:
                return jsonify({"error": "File not found"}), 404
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
    cursor.execute("SELECT filename, filepath FROM files WHERE user_id = %s", (session['user_id'],))
    rows = cursor.fetchall()

    files = []
    for row in rows:
        filename = row[0]
        file_path = row[1]
        if os.path.isfile(file_path):
            files.append({
                "name": filename,
                "size": os.path.getsize(file_path),  # File size in bytes
                "type": filename.split('.')[-1],  # File extension/type
                "last_modified": datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')  # Last modified timestamp
            })

    # Sort the files based on the 'by' and 'order' parameters
    if sort_by == 'size':
        sorted_files = sorted(files, key=lambda x: x['size'], reverse=True)
    elif sort_by == 'date':
        sorted_files = sorted(files, key=lambda x: x['last_modified'], reverse=(sort_order == 'desc'))
    else:
        # Default to sorting by name
        sorted_files = sorted(files, key=lambda x: x['name'].lower(), reverse=(sort_order == 'desc'))

    return jsonify({'files': sorted_files})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
 