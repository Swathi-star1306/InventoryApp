import os
import streamlit as st

# Set the environment variable for pyzbar.
# Update the path below to point to your ZBar DLL if available.
os.environ["PYZBAR_LIBRARY"] = r"C:\Program Files (x86)\ZBar\bin\libzbar-64.dll"

# Try to import pyzbar. If it fails, disable barcode scanning.
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

# MUST call set_page_config as the very first Streamlit command.
st.set_page_config(page_title="Professional Inventory Management", layout="wide")

# -----------------------------
# Custom CSS for a Vibrant, Engaging Look
# -----------------------------
st.markdown("""
    <style>
        body {
            background-color: #f0f8ff;
        }
        .header {
            font-size: 36px; 
            color: #4B0082; 
            font-weight: bold;
            margin-bottom: 20px;
        }
        .subheader {
            font-size: 28px;
            color: #800080;
            margin-bottom: 15px;
        }
        .big-font {
            font-size: 20px !important;
            color: #2F4F4F;
        }
        .low-stock {
            color: #D32F2F;
            font-weight: bold;
        }
    </style>
    """, unsafe_allow_html=True)

if not barcode_scanner_enabled:
    st.warning("Barcode scanning functionality is disabled because the ZBar DLL was not found. You can still enter barcodes manually.")

# -----------------------------
# Helper Function to Hash Text
# -----------------------------
def hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()

# -----------------------------
# DATABASE SETUP (Persistent Mode)
# -----------------------------
conn = sqlite3.connect("inventory.db", check_same_thread=False)
c = conn.cursor()

# Create Users table if it doesn't exist
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        pin TEXT NOT NULL
    )
''')
# Insert default admin user if no users exist
c.execute("SELECT COUNT(*) FROM users")
if c.fetchone()[0] == 0:
    c.execute("INSERT INTO users (name, role, pin) VALUES (?, ?, ?)", ("Admin", "admin", hash_text("1234")))
    conn.commit()

# Create Categories table if it doesn't exist
c.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
''')

# Create Items table if it doesn't exist (includes threshold for low stock)
c.execute('''
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        barcode TEXT UNIQUE NOT NULL,
        quantity INTEGER NOT NULL,
        threshold INTEGER NOT NULL,
        FOREIGN KEY (category) REFERENCES categories(name)
    )
''')
conn.commit()

# -----------------------------
# DATABASE HELPER FUNCTIONS
# -----------------------------
def get_db_connection():
    return sqlite3.connect("inventory.db", check_same_thread=False)

def authenticate(username, pin):
    conn = get_db_connection()
    c = conn.cursor()
    hashed = hash_text(pin)
    c.execute("SELECT role FROM users WHERE name=? AND pin=?", (username, hashed))
    user = c.fetchone()
    conn.close()
    if user:
        return user[0]
    return None

def add_category(name):
    if not name.strip():
        st.error("Please enter a valid category name.")
        return False
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name) VALUES (?)", (name.strip(),))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        st.error("Category already exists.")
        conn.close()
        return False

def get_categories():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM categories")
    cats = [row[0] for row in c.fetchall()]
    conn.close()
    return cats

def add_item(category, name, barcode, quantity, threshold):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO items (category, name, barcode, quantity, threshold) VALUES (?, ?, ?, ?, ?)",
                  (category, name, barcode, quantity, threshold))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        st.error("Item with this barcode already exists.")
        conn.close()
        return False

def get_items():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM items")
    items = c.fetchall()
    conn.close()
    return items

def update_item_quantity(barcode, quantity):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE items SET quantity = ? WHERE barcode = ?", (quantity, barcode))
    conn.commit()
    conn.close()

def delete_item(barcode):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM items WHERE barcode = ?", (barcode,))
    conn.commit()
    conn.close()

def add_user(name, role, pin):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (name, role, pin) VALUES (?, ?, ?)", (name, role, hash_text(pin)))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        st.error("User already exists or username is taken.")
        conn.close()
        return False

def get_users():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name, role FROM users")
    users = c.fetchall()
    conn.close()
    return users

def delete_user(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_by_username(username):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, name, role FROM users WHERE LOWER(name)=LOWER(?)", (username,))
    user = c.fetchone()
    conn.close()
    return user

def update_user_credentials(user_id, new_name, new_pin):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET name=?, pin=? WHERE id=?", (new_name, hash_text(new_pin), user_id))
    conn.commit()
    conn.close()

# -----------------------------
# PDF REPORT GENERATION USING REPORTLAB
# -----------------------------
def generate_pdf():
    items = get_items()
    if not items:
        st.error("No items found to generate report.")
        return
    df_items = pd.DataFrame(items, columns=["ID", "Category", "Item Name", "Barcode", "Quantity", "Threshold"])
    filename = "inventory_report.pdf"
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, "Inventory Report")
    c.setFont("Helvetica", 12)
    y = height - 80
    headers = ["ID", "Category", "Item Name", "Barcode", "Quantity", "Threshold"]
    x_positions = [50, 100, 200, 350, 500, 570]
    for i, header in enumerate(headers):
        c.drawString(x_positions[i], y, header)
    y -= 20
    c.setFont("Helvetica", 10)
    for index, row in df_items.iterrows():
        if y < 50:
            c.showPage()
            y = height - 50
        for i, item in enumerate(row):
            c.drawString(x_positions[i], y, str(item))
        y -= 15
    c.save()

# -----------------------------
# Sidebar: Low Stock Alerts (Real-Time)
# -----------------------------
def display_low_stock_alerts():
    items = get_items()
    low_stock = [item for item in items if item[4] < item[5]]  # quantity < threshold
    if low_stock:
        st.sidebar.markdown("<div class='low-stock'><b>Low Stock Alerts:</b></div>", unsafe_allow_html=True)
        for item in low_stock:
            st.sidebar.write(f"{item[2]} (Qty: {item[4]}, Threshold: {item[5]})")
    else:
        st.sidebar.write("All stock levels are sufficient.")

display_low_stock_alerts()

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.sidebar.title("📦 Inventory Management")

# -----------------------------
# LOGIN SECTION
# -----------------------------
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
        if role:
            st.session_state.logged_in = True
            st.session_state.role = role
            st.session_state.username = username
            st.rerun()
        else:
            st.error("❌ Invalid username or PIN. Please try again.")
    st.stop()

st.sidebar.success(f"Logged in as: **{st.session_state.username}** ({st.session_state.role.capitalize()})")
nav = st.sidebar.radio("Navigation", ["Home", "Manage Categories", "Add Items", "View Inventory", "User Management", "Reports", "Account Settings"])

# -----------------------------
# HOME PAGE
# -----------------------------
if nav == "Home":
    st.markdown("<div class='header'>🏠 Home</div>", unsafe_allow_html=True)
    st.write("Welcome to the Professional Inventory Management System.")

# -----------------------------
# MANAGE CATEGORIES
# -----------------------------
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

# -----------------------------
# ADD ITEMS
# -----------------------------
elif nav == "Add Items":
    st.markdown("<div class='header'>📦 Add New Item</div>", unsafe_allow_html=True)
    cats = get_categories()
    if cats:
        category = st.selectbox("Select Category", cats)
        item_name = st.text_input("Item Name", placeholder="Enter item name")
        barcode = st.text_input("Barcode", placeholder="Scan or enter barcode")
        # --- Barcode Scanner Section ---
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
                        barcode = decoded_barcode  # Use the decoded value
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

# -----------------------------
# VIEW INVENTORY
# -----------------------------
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

# -----------------------------
# USER MANAGEMENT (Admin Only)
# -----------------------------
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
        st.markdown("<div class='subheader'>Existing Users:</div>", unsafe_allow_html=True)
        users = get_users()
        if users:
            df_users = pd.DataFrame(users, columns=["User ID", "Username", "Role"])
            st.table(df_users)
            for user in users:
                if st.button(f"Delete User {user[0]}", key=f"user_{user[0]}"):
                    delete_user(user[0])
                    st.success("User deleted!")
        else:
            st.write("No users found.")
    else:
        st.error("Access denied. Admins only.")

# -----------------------------
# REPORTS
# -----------------------------
elif nav == "Reports":
    st.markdown("<div class='header'>📄 Reports</div>", unsafe_allow_html=True)
    if st.button("Generate PDF Report"):
        generate_pdf()
        st.success("PDF Report generated: inventory_report.pdf")
        if os.path.exists("inventory_report.pdf"):
            with open("inventory_report.pdf", "rb") as f:
                st.download_button("Download Report", f, file_name="inventory_report.pdf")
        else:
            st.error("Report generation failed.")

# -----------------------------
# ACCOUNT SETTINGS (Change Username & PIN)
# -----------------------------
elif nav == "Account Settings":
    st.markdown("<div class='header'>⚙️ Account Settings</div>", unsafe_allow_html=True)
    def get_user_by_username(username):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, name, role FROM users WHERE LOWER(name)=LOWER(?)", (username,))
        user = c.fetchone()
        conn.close()
        return user
    def update_user_credentials(user_id, new_name, new_pin):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET name=?, pin=? WHERE id=?", (new_name, hash_text(new_pin), user_id))
        conn.commit()
        conn.close()
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















