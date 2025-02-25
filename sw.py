import os
import streamlit as st

# Set PYZBAR_LIBRARY for Windows (update the path if necessary)
if os.name == 'nt':
    os.environ["PYZBAR_LIBRARY"] = r"C:\Program Files (x86)\ZBar\bin\libzbar-64.dll"

try:
    from pyzbar.pyzbar import decode
    barcode_scanner_enabled = True
except Exception as e:
    barcode_scanner_enabled = False

import sqlite3
import hashlib
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image
from datetime import datetime

# MUST call set_page_config as the very first Streamlit command.
st.set_page_config(page_title="Professional Inventory Management", layout="wide")

# --------------------------------------------------------------------
# Custom CSS for a Vibrant, Engaging Look
# --------------------------------------------------------------------
st.markdown(
    """
    <style>
        body { background-color: #f0f8ff; }
        .header { font-size: 36px; color: #4B0082; font-weight: bold; margin-bottom: 20px; }
        .subheader { font-size: 28px; color: #800080; margin-bottom: 15px; }
        .big-font { font-size: 20px !important; color: #2F4F4F; }
        .low-stock { color: #D32F2F; font-weight: bold; }
    </style>
    """,
    unsafe_allow_html=True,
)

if not barcode_scanner_enabled:
    st.warning("Barcode scanning is disabled because the ZBar DLL could not be loaded. You can still enter barcodes manually.")

# --------------------------------------------------------------------
# Helper Function to Hash Text
# --------------------------------------------------------------------
def hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()

# --------------------------------------------------------------------
# DATABASE SETUP
# --------------------------------------------------------------------
conn = sqlite3.connect("inventory.db", check_same_thread=False)
c = conn.cursor()

# Create Users table (with approved flag)
c.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        pin TEXT NOT NULL,
        approved INTEGER NOT NULL DEFAULT 0
    )
    """
)
conn.commit()

# Create login_requests table for staff login requests
c.execute(
    """
    CREATE TABLE IF NOT EXISTS login_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'pending',
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """
)
conn.commit()

# Create login_log table to record every successful login
c.execute(
    """
    CREATE TABLE IF NOT EXISTS login_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """
)
conn.commit()

# Insert default users if table is empty: 2 admins (approved) and 2 staff (login approval required each time)
c.execute("SELECT COUNT(*) FROM users")
if c.fetchone()[0] == 0:
    c.execute("INSERT INTO users (name, role, pin, approved) VALUES (?, ?, ?, ?)", ("Admin1", "admin", hash_text("admin1pass"), 1))
    c.execute("INSERT INTO users (name, role, pin, approved) VALUES (?, ?, ?, ?)", ("Admin2", "admin", hash_text("admin2pass"), 1))
    c.execute("INSERT INTO users (name, role, pin, approved) VALUES (?, ?, ?, ?)", ("Staff1", "staff", hash_text("staff1pass"), 0))
    c.execute("INSERT INTO users (name, role, pin, approved) VALUES (?, ?, ?, ?)", ("Staff2", "staff", hash_text("staff2pass"), 0))
    conn.commit()

# Create Categories table
c.execute(
    """
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    """
)

# Create Items table (with threshold for low stock)
c.execute(
    """
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        barcode TEXT UNIQUE NOT NULL,
        quantity INTEGER NOT NULL,
        threshold INTEGER NOT NULL,
        FOREIGN KEY (category) REFERENCES categories(name)
    )
    """
)

# Create Transactions table to log item take events
c.execute(
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity_taken INTEGER NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """
)
conn.commit()

# --------------------------------------------------------------------
# Additional Helper Functions for Login Requests & Login Log
# --------------------------------------------------------------------
def add_login_request(user_id):
    conn2 = sqlite3.connect("inventory.db", check_same_thread=False)
    c2 = conn2.cursor()
    # Always add a new login request on each staff login attempt.
    c2.execute("INSERT INTO login_requests (user_id) VALUES (?)", (user_id,))
    conn2.commit()
    conn2.close()

def get_pending_login_requests():
    conn2 = sqlite3.connect("inventory.db", check_same_thread=False)
    c2 = conn2.cursor()
    c2.execute(
        """
        SELECT lr.id, u.name, lr.timestamp 
        FROM login_requests lr 
        JOIN users u ON lr.user_id = u.id 
        WHERE lr.status='pending'
        ORDER BY lr.timestamp ASC
        """
    )
    reqs = c2.fetchall()
    conn2.close()
    return reqs

def approve_user_request(user_id, request_id):
    conn2 = sqlite3.connect("inventory.db", check_same_thread=False)
    c2 = conn2.cursor()
    c2.execute("UPDATE login_requests SET status='approved' WHERE id=?", (request_id,))
    conn2.commit()
    conn2.close()
    # Note: We do NOT permanently change the user's 'approved' flag.
    # Approval is granted only for that login attempt.

def deny_user_request(request_id):
    conn2 = sqlite3.connect("inventory.db", check_same_thread=False)
    c2 = conn2.cursor()
    c2.execute("UPDATE login_requests SET status='denied' WHERE id=?", (request_id,))
    conn2.commit()
    conn2.close()

def add_login_log(user_id, username):
    conn2 = sqlite3.connect("inventory.db", check_same_thread=False)
    c2 = conn2.cursor()
    c2.execute("INSERT INTO login_log (user_id, username) VALUES (?, ?)", (user_id, username))
    conn2.commit()
    conn2.close()

# --------------------------------------------------------------------
# Other Database Helper Functions (Categories, Items, Users, Transactions)
# --------------------------------------------------------------------
def get_db_connection():
    return sqlite3.connect("inventory.db", check_same_thread=False)

def authenticate(username, pin):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    hashed = hash_text(pin)
    c2.execute("SELECT id, role FROM users WHERE name=? AND pin=?", (username, hashed))
    row = c2.fetchone()
    conn2.close()
    if row:
        user_id, role = row
        if role == "staff":
            # For every login attempt, require admin approval.
            add_login_request(user_id)
            # Check if there's an approved request (i.e. admin just approved)
            conn3 = get_db_connection()
            c3 = conn3.cursor()
            c3.execute("SELECT id FROM login_requests WHERE user_id=? AND status='approved'", (user_id,))
            approved_req = c3.fetchone()
            conn3.close()
            if approved_req:
                # Consume the approved request and allow login.
                approved_id = approved_req[0]
                conn3 = get_db_connection()
                c3 = conn3.cursor()
                c3.execute("DELETE FROM login_requests WHERE id=?", (approved_id,))
                conn3.commit()
                conn3.close()
                return role
            else:
                return "pending"
        return role
    return None

def add_category(name):
    if not name.strip():
        st.error("Please enter a valid category name.")
        return False
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    try:
        c2.execute("INSERT INTO categories (name) VALUES (?)", (name.strip(),))
        conn2.commit()
        conn2.close()
        return True
    except sqlite3.IntegrityError:
        st.error("Category already exists.")
        conn2.close()
        return False

def get_categories():
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT name FROM categories")
    cats = [row[0] for row in c2.fetchall()]
    conn2.close()
    return cats

def add_item(category, name, barcode, quantity, threshold):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    try:
        c2.execute("INSERT INTO items (category, name, barcode, quantity, threshold) VALUES (?, ?, ?, ?, ?)",
                   (category, name, barcode, quantity, threshold))
        conn2.commit()
        conn2.close()
        return True
    except sqlite3.IntegrityError:
        st.error("Item with this barcode already exists.")
        conn2.close()
        return False

def get_items():
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT * FROM items")
    items = c2.fetchall()
    conn2.close()
    return items

def get_items_by_category(category):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT id, name, barcode, quantity, threshold FROM items WHERE category=?", (category,))
    items = c2.fetchall()
    conn2.close()
    return items

def update_item_quantity(barcode, quantity):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("UPDATE items SET quantity=? WHERE barcode=?", (quantity, barcode))
    conn2.commit()
    conn2.close()

def delete_item(barcode):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("DELETE FROM items WHERE barcode=?", (barcode,))
    conn2.commit()
    conn2.close()

def add_user(name, role, pin):
    approved = 1 if role == "admin" else 0
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    try:
        c2.execute("INSERT INTO users (name, role, pin, approved) VALUES (?, ?, ?, ?)", (name, role, hash_text(pin), approved))
        conn2.commit()
        conn2.close()
        return True
    except sqlite3.IntegrityError:
        st.error("User already exists or username is taken.")
        conn2.close()
        return False

def get_users():
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT id, name, role, approved FROM users")
    users = c2.fetchall()
    conn2.close()
    return users

def delete_user(user_id):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn2.commit()
    conn2.close()

def get_user_by_username(username):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT id, name, role, approved FROM users WHERE LOWER(name)=LOWER(?)", (username,))
    user = c2.fetchone()
    conn2.close()
    return user

def update_user_credentials(user_id, new_name, new_pin):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("UPDATE users SET name=?, pin=? WHERE id=?", (new_name, hash_text(new_pin), user_id))
    conn2.commit()
    conn2.close()

def add_transaction(user_id, item_id, quantity_taken):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("INSERT INTO transactions (user_id, item_id, quantity_taken) VALUES (?, ?, ?)", (user_id, item_id, quantity_taken))
    conn2.commit()
    conn2.close()

def get_transactions():
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("""
        SELECT t.id, u.name, i.name, i.barcode, t.quantity_taken, t.timestamp 
        FROM transactions t 
        JOIN users u ON t.user_id = u.id 
        JOIN items i ON t.item_id = i.id 
        ORDER BY t.timestamp DESC
    """)
    trans = c2.fetchall()
    conn2.close()
    return trans

def generate_pdf():
    items = get_items()
    if not items:
        st.error("No items found to generate report.")
        return
    df_items = pd.DataFrame(items, columns=["ID", "Category", "Item Name", "Barcode", "Quantity", "Threshold"])
    filename = "inventory_report.pdf"
    cpdf = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    cpdf.setFont("Helvetica-Bold", 20)
    cpdf.drawString(50, height - 50, "Inventory Report")
    cpdf.setFont("Helvetica", 12)
    y = height - 80
    headers = ["ID", "Category", "Item Name", "Barcode", "Quantity", "Threshold"]
    x_positions = [50, 100, 200, 350, 500, 570]
    for i, header in enumerate(headers):
        cpdf.drawString(x_positions[i], y, header)
    y -= 20
    cpdf.setFont("Helvetica", 10)
    for index, row in df_items.iterrows():
        if y < 50:
            cpdf.showPage()
            y = height - 50
        for i, val in enumerate(row):
            cpdf.drawString(x_positions[i], y, str(val))
        y -= 15
    cpdf.save()

# --------------------------------------------------------------------
# Sidebar: Low Stock Alerts (Real-Time)
# --------------------------------------------------------------------
def display_low_stock_alerts():
    items = get_items()
    low_stock = [item for item in items if item[4] < item[5]]
    if low_stock:
        st.sidebar.markdown("<div class='low-stock'><b>Low Stock Alerts:</b></div>", unsafe_allow_html=True)
        for item in low_stock:
            st.sidebar.write(f"{item[2]} (Qty: {item[4]}, Threshold: {item[5]})")
    else:
        st.sidebar.write("All stock levels are sufficient.")

display_low_stock_alerts()

# --------------------------------------------------------------------
# STREAMLIT UI & ROLE-BASED NAVIGATION
# --------------------------------------------------------------------
if st.session_state.get("role") == "admin":
    nav = st.sidebar.radio(
        "Navigation",
        ["Home", "Manage Categories", "Add Items", "View Inventory", "User Management", "Reports", "Entry Log", "Account Settings"]
    )
elif st.session_state.get("role") == "staff":
    nav = st.sidebar.radio("Navigation", ["Home", "Take Items", "View Inventory", "Account Settings"])
else:
    nav = st.sidebar.radio("Navigation", ["Home", "View Inventory", "Account Settings"])

# --------------------------------------------------------------------
# LOGIN SECTION
# --------------------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = ""

if not st.session_state.logged_in:
    st.markdown("<div class='header'>🔐 Login</div>", unsafe_allow_html=True)
    username = st.text_input("Username", placeholder="Enter your username")
    pin = st.text_input("PIN", type="password", placeholder="Enter your PIN")
    if st.button("Login"):
        role = authenticate(username, pin)
        if role == "pending":
            st.error("Your account is pending admin approval. Please contact an administrator.")
        elif role:
            # Log successful login event
            user_info = get_user_by_username(username)
            if user_info:
                add_login_log(user_info[0], username)
            st.session_state.logged_in = True
            st.session_state.role = role
            st.session_state.username = username
            st.rerun()
        else:
            st.error("❌ Invalid username or PIN. Please try again.")
    st.stop()

st.sidebar.success(f"Logged in as: **{st.session_state.username}** ({st.session_state.role.capitalize()})")

# --------------------------------------------------------------------
# HOME PAGE
# --------------------------------------------------------------------
if nav == "Home":
    st.markdown("<div class='header'>🏠 Home</div>", unsafe_allow_html=True)
    st.write("Welcome to the Professional Inventory Management System.")

# --------------------------------------------------------------------
# ENTRY LOG (Admin Only)
# --------------------------------------------------------------------
elif nav == "Entry Log":
    if st.session_state.role == "admin":
        st.markdown("<div class='header'>📜 Entry Log</div>", unsafe_allow_html=True)
        def get_login_log():
            conn2 = get_db_connection()
            c2 = conn2.cursor()
            c2.execute("SELECT id, user_id, username, timestamp FROM login_log ORDER BY timestamp DESC")
            log_entries = c2.fetchall()
            conn2.close()
            return log_entries
        log_entries = get_login_log()
        if log_entries:
            df_log = pd.DataFrame(log_entries, columns=["Log ID", "User ID", "Username", "Timestamp"])
            st.table(df_log)
        else:
            st.write("No login entries recorded yet.")
    else:
        st.error("Access denied. Admins only.")

# --------------------------------------------------------------------
# MANAGE CATEGORIES (Admin)
# --------------------------------------------------------------------
elif nav == "Manage Categories":
    st.markdown("<div class='header'>📂 Manage Categories</div>", unsafe_allow_html=True)
    new_category = st.text_input("New Category Name", placeholder="Enter category name")
    if st.button("Add Category"):
        if add_category(new_category):
            st.success(f"Category '{new_category}' added successfully!")
    st.markdown("<div class='subheader'>Existing Categories:</div>", unsafe_allow_html=True)
    cats = get_categories()
    if cats:
        st.table(pd.DataFrame(cats, columns=["Category Name"]))
    else:
        st.write("No categories available.")

# --------------------------------------------------------------------
# ADD ITEMS (Admin)
# --------------------------------------------------------------------
elif nav == "Add Items":
    st.markdown("<div class='header'>📦 Add New Item</div>", unsafe_allow_html=True)
    cats = get_categories()
    if cats:
        category = st.selectbox("Select Category", cats)
        item_name = st.text_input("Item Name", placeholder="Enter item name")
        barcode = st.text_input("Barcode", placeholder="Scan or enter barcode")
        if barcode_scanner_enabled:
            st.markdown("### OR Upload Barcode Image")
            uploaded_file = st.file_uploader("Upload an image of the barcode", type=["png", "jpg", "jpeg"])
            if uploaded_file is not None:
                try:
                    image = Image.open(uploaded_file)
                    decoded = decode(image)
                    if decoded:
                        decoded_barcode = decoded[0].data.decode("utf-8")
                        st.success(f"Decoded Barcode: {decoded_barcode}")
                        barcode = decoded_barcode
                    else:
                        st.error("No barcode detected. Try another image.")
                except Exception as e:
                    st.error("Error processing image: " + str(e))
        else:
            st.info("Barcode scanner is disabled. Please enter barcode manually.")
        quantity = st.number_input("Quantity", min_value=1, step=1)
        threshold = st.number_input("Low Stock Threshold", min_value=1, step=1)
        if st.button("Add Item"):
            if item_name and barcode:
                if add_item(category, item_name, barcode, quantity, threshold):
                    st.success(f"Item '{item_name}' added to category '{category}'.")
            else:
                st.error("Please provide valid item name and barcode.")
    else:
        st.warning("No categories available. Please add a category first.")

# --------------------------------------------------------------------
# TAKE ITEMS (Staff)
# --------------------------------------------------------------------
elif nav == "Take Items" and st.session_state.role == "staff":
    st.markdown("<div class='header'>📦 Take Items</div>", unsafe_allow_html=True)
    cats = get_categories()
    if cats:
        selected_category = st.selectbox("Select Category", cats)
        def get_items_by_category(category):
            conn2 = get_db_connection()
            c2 = conn2.cursor()
            c2.execute("SELECT id, name, barcode, quantity, threshold FROM items WHERE category=?", (category,))
            items = c2.fetchall()
            conn2.close()
            return items
        items_in_cat = get_items_by_category(selected_category)
        if items_in_cat:
            item_options = {f"{item[1]} (Qty: {item[3]})": item for item in items_in_cat}
            selected_item_str = st.selectbox("Select Item", list(item_options.keys()))
            selected_item = item_options[selected_item_str]
            st.write(f"Selected: {selected_item[1]}, Current Qty: {selected_item[3]}, Threshold: {selected_item[4]}")
            take_qty = st.number_input("Quantity to take", min_value=1, max_value=selected_item[3], step=1)
            if st.button("Take Item"):
                new_qty = selected_item[3] - take_qty
                if new_qty < 0:
                    st.error("Not enough stock available.")
                else:
                    update_item_quantity(selected_item[2], new_qty)
                    current_user = get_user_by_username(st.session_state.username)
                    if current_user:
                        def add_transaction(user_id, item_id, quantity_taken):
                            conn2 = get_db_connection()
                            c2 = conn2.cursor()
                            c2.execute("INSERT INTO transactions (user_id, item_id, quantity_taken) VALUES (?, ?, ?)",
                                       (user_id, selected_item[0], quantity_taken))
                            conn2.commit()
                            conn2.close()
                        add_transaction(current_user[0], selected_item[0], take_qty)
                    st.success(f"Took {take_qty} of {selected_item[1]}. New quantity: {new_qty}.")
        else:
            st.write("No items found in this category.")
    else:
        st.write("No categories available.")

# --------------------------------------------------------------------
# VIEW INVENTORY (All)
# --------------------------------------------------------------------
elif nav == "View Inventory":
    st.markdown("<div class='header'>📋 Inventory Items</div>", unsafe_allow_html=True)
    items = get_items()
    if items:
        df_items = pd.DataFrame(items, columns=["ID", "Category", "Item Name", "Barcode", "Quantity", "Threshold"])
        st.table(df_items)
        st.markdown("<div class='subheader'>Update / Delete Items:</div>", unsafe_allow_html=True)
        barcode_update = st.text_input("Enter Barcode for Update/Delete", placeholder="Enter barcode")
        new_qty = st.number_input("New Quantity", min_value=0, step=1)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Update Quantity"):
                if barcode_update:
                    update_item_quantity(barcode_update, new_qty)
                    st.success("Quantity updated successfully.")
                else:
                    st.error("Please enter a barcode.")
        with col2:
            if st.button("Delete Item"):
                if barcode_update:
                    delete_item(barcode_update)
                    st.warning("Item deleted.")
                else:
                    st.error("Please enter a barcode.")
    else:
        st.write("No items found.")

# --------------------------------------------------------------------
# USER MANAGEMENT (Admin Only)
# --------------------------------------------------------------------
elif nav == "User Management":
    if st.session_state.role == "admin":
        st.markdown("<div class='header'>👥 User Management</div>", unsafe_allow_html=True)
        st.markdown("<div class='subheader'>Add New User:</div>", unsafe_allow_html=True)
        new_username = st.text_input("Username", placeholder="Enter new user's name")
        new_role = st.selectbox("Role", ["admin", "staff"])
        new_user_pin = st.text_input("PIN", type="password", placeholder="Enter PIN for new user")
        if st.button("Add User"):
            if new_username and new_user_pin:
                if add_user(new_username, new_role, new_user_pin):
                    st.success(f"User '{new_username}' added successfully!")
            else:
                st.error("Please enter valid user details.")
        st.markdown("<div class='subheader'>Pending Staff Login Requests:</div>", unsafe_allow_html=True)
        def get_pending_login_requests():
            conn2 = get_db_connection()
            c2 = conn2.cursor()
            c2.execute(
                """
                SELECT lr.id, u.name, lr.timestamp 
                FROM login_requests lr 
                JOIN users u ON lr.user_id = u.id 
                WHERE lr.status = 'pending'
                ORDER BY lr.timestamp ASC
                """
            )
            reqs = c2.fetchall()
            conn2.close()
            return reqs
        pending_requests = get_pending_login_requests()
        if pending_requests:
            df_requests = pd.DataFrame(pending_requests, columns=["Request ID", "Username", "Timestamp"])
            st.table(df_requests)
            for req in pending_requests:
                req_id, uname, ts = req
                colA, colB = st.columns([2, 1])
                with colA:
                    st.write(f"Request {req_id}: {uname} at {ts}")
                with colB:
                    if st.button(f"Approve {uname}'s Request", key=f"approve_{req_id}"):
                        user_info = get_user_by_username(uname)
                        if user_info:
                            approve_user_request(user_info[0], req_id)
                            st.success(f"Approved {uname}'s request.")
                            st.rerun()
                    if st.button(f"Deny {uname}'s Request", key=f"deny_{req_id}"):
                        deny_user_request(req_id)
                        st.warning(f"Denied {uname}'s request.")
                        st.rerun()
        else:
            st.write("No pending login requests.")
        st.markdown("<div class='subheader'>Existing Users:</div>", unsafe_allow_html=True)
        users = get_users()
        if users:
            df_users = pd.DataFrame(users, columns=["User ID", "Username", "Role", "Approved"])
            st.table(df_users)
            for user in users:
                if st.button(f"Delete User {user[0]}", key=f"user_{user[0]}"):
                    delete_user(user[0])
                    st.success("User deleted!")
        else:
            st.write("No users found.")
    else:
        st.error("Access denied. Admins only.")

# --------------------------------------------------------------------
# REPORTS (Admin Only)
# --------------------------------------------------------------------
elif nav == "Reports":
    if st.session_state.role == "admin":
        st.markdown("<div class='header'>📄 Reports</div>", unsafe_allow_html=True)
        if st.button("Generate PDF Report"):
            generate_pdf()
            st.success("PDF Report generated: inventory_report.pdf")
            if os.path.exists("inventory_report.pdf"):
                with open("inventory_report.pdf", "rb") as f:
                    st.download_button("Download Report", f, file_name="inventory_report.pdf")
            else:
                st.error("Report generation failed.")
        st.markdown("<div class='subheader'>Transaction Log:</div>", unsafe_allow_html=True)
        def get_transactions():
            conn2 = get_db_connection()
            c2 = conn2.cursor()
            c2.execute(
                """
                SELECT t.id, u.name, i.name, i.barcode, t.quantity_taken, t.timestamp 
                FROM transactions t 
                JOIN users u ON t.user_id = u.id 
                JOIN items i ON t.item_id = i.id 
                ORDER BY t.timestamp DESC
                """
            )
            trans = c2.fetchall()
            conn2.close()
            return trans
        trans = get_transactions()
        if trans:
            df_trans = pd.DataFrame(trans, columns=["Trans ID", "User", "Item", "Barcode", "Quantity Taken", "Timestamp"])
            st.table(df_trans)
        else:
            st.write("No transactions recorded yet.")
    else:
        st.error("Access denied. Admins only.")

# --------------------------------------------------------------------
# ACCOUNT SETTINGS
# --------------------------------------------------------------------
elif nav == "Account Settings":
    st.markdown("<div class='header'>⚙️ Account Settings</div>", unsafe_allow_html=True)
    def get_user_by_username(username):
        conn2 = get_db_connection()
        c2 = conn2.cursor()
        c2.execute("SELECT id, name, role, approved FROM users WHERE LOWER(name)=LOWER(?)", (username,))
        user = c2.fetchone()
        conn2.close()
        return user
    def update_user_credentials(user_id, new_name, new_pin):
        conn2 = get_db_connection()
        c2 = conn2.cursor()
        c2.execute("UPDATE users SET name=?, pin=? WHERE id=?", (new_name, hash_text(new_pin), user_id))
        conn2.commit()
        conn2.close()
    current_user = get_user_by_username(st.session_state.username)
    if current_user:
        st.markdown("<div class='subheader'>Update Your Credentials:</div>", unsafe_allow_html=True)
        new_name = st.text_input("New Username", value=current_user[1])
        new_pin = st.text_input("New PIN", type="password", placeholder="Enter new PIN")
        confirm_pin = st.text_input("Confirm New PIN", type="password", placeholder="Re-enter new PIN")
        if st.button("Update Credentials"):
            if new_pin and new_pin == confirm_pin and new_name.strip() != "":
                update_user_credentials(current_user[0], new_name, new_pin)
                st.success("Credentials updated successfully!")
                st.session_state.username = new_name
            else:
                st.error("Please ensure the PINs match and the username is valid.")
    else:
        st.error("User not found.")
