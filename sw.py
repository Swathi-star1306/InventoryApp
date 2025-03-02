import streamlit as st
# Must call set_page_config() as the very first Streamlit command.
st.set_page_config(page_title="Professional Inventory Management", layout="wide")

import os
from datetime import datetime
import pytz  # For IST conversion
import sqlite3
import hashlib
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Barcode functionality removed in this version.
barcode_scanner_enabled = False

# -----------------------------
# Display Official Logo in Sidebar
# -----------------------------
logo_url = "https://i.imgur.com/e6E6TJt.jpeg"
st.sidebar.image(logo_url, width=150)

# --------------------------------------------------------------------
# Custom CSS for a Vibrant, Official Look with Emojis
# --------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Pacifico&display=swap');
    body { background-color: #f0f8ff; }
    .header { font-family: 'Pacifico', cursive; font-size: 42px; color: #4B0082; font-weight: bold; margin-bottom: 20px; }
    .subheader { font-family: 'Pacifico', cursive; font-size: 32px; color: #800080; margin-bottom: 15px; }
    .big-font { font-size: 24px !important; color: #2F4F4F; }
    .low-stock { color: #D32F2F; font-weight: bold; font-size: 20px; }
    </style>
    """,
    unsafe_allow_html=True,
)

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

# Users table (staff approval removed)
c.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        pin TEXT NOT NULL
    )
    """
)
conn.commit()

# login_log table to record every successful login
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

# Insert default users if table is empty: 2 admins and 2 staff
c.execute("SELECT COUNT(*) FROM users")
if c.fetchone()[0] == 0:
    c.execute("INSERT INTO users (name, role, pin) VALUES (?, ?, ?)", ("Admin1", "admin", hash_text("admin1pass")))
    c.execute("INSERT INTO users (name, role, pin) VALUES (?, ?, ?)", ("Admin2", "admin", hash_text("admin2pass")))
    c.execute("INSERT INTO users (name, role, pin) VALUES (?, ?, ?)", ("Staff1", "staff", hash_text("staff1pass")))
    c.execute("INSERT INTO users (name, role, pin) VALUES (?, ?, ?)", ("Staff2", "staff", hash_text("staff2pass")))
    conn.commit()

# Categories table
c.execute(
    """
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
    """
)

# Items table (barcode removed)
c.execute(
    """
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        threshold INTEGER NOT NULL,
        FOREIGN KEY (category) REFERENCES categories(name)
    )
    """
)

# Transactions table to log item take events
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

# New Vendors table
c.execute(
    """
    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_name TEXT NOT NULL,
        contact TEXT,
        item_supplied TEXT,
        address TEXT,
        quantity_bought INTEGER,
        points TEXT
    )
    """
)
conn.commit()

# --------------------------------------------------------------------
# Additional Helper Functions for Logging
# --------------------------------------------------------------------
def add_login_log(user_id, username):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn2 = sqlite3.connect("inventory.db", check_same_thread=False)
    c2 = conn2.cursor()
    c2.execute("INSERT INTO login_log (user_id, username, timestamp) VALUES (?, ?, ?)", (user_id, username, ts))
    conn2.commit()
    conn2.close()

# --------------------------------------------------------------------
# Other Helper Functions (Categories, Items, Users, Transactions, Vendors)
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
        return row[1]
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

def add_item(category, name, quantity, vendor, threshold):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    try:
        c2.execute("INSERT INTO items (category, name, quantity, threshold) VALUES (?, ?, ?, ?)",
                   (category, name, quantity, threshold))
        conn2.commit()
        conn2.close()
        return True
    except sqlite3.IntegrityError:
        st.error("Item already exists.")
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
    c2.execute("SELECT id, name, quantity, threshold FROM items WHERE category=?", (category,))
    items = c2.fetchall()
    conn2.close()
    return items

def update_item_quantity(item_id, quantity):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("UPDATE items SET quantity=? WHERE id=?", (quantity, item_id))
    conn2.commit()
    conn2.close()

def delete_item(item_id):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn2.commit()
    conn2.close()

def add_user(name, role, pin):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    try:
        c2.execute("INSERT INTO users (name, role, pin) VALUES (?, ?, ?)", (name, role, hash_text(pin)))
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
    c2.execute("SELECT id, name, role FROM users")
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
    c2.execute("SELECT id, name, role FROM users WHERE LOWER(name)=LOWER(?)", (username,))
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
    # Record IST timestamp (UTC+5:30)
    ist = pytz.timezone('Asia/Kolkata')
    ts = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("INSERT INTO transactions (user_id, item_id, quantity_taken, timestamp) VALUES (?, ?, ?, ?)",
               (user_id, item_id, quantity_taken, ts))
    conn2.commit()
    conn2.close()

def get_transactions():
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute(
        """
        SELECT t.id, u.name, i.name, t.quantity_taken, t.timestamp 
        FROM transactions t 
        JOIN users u ON t.user_id = u.id 
        JOIN items i ON t.item_id = i.id 
        ORDER BY t.timestamp DESC
        """
    )
    trans = c2.fetchall()
    conn2.close()
    return trans

def get_last_transaction_for_item(item_id):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute(
        """
        SELECT u.name, t.timestamp 
        FROM transactions t 
        JOIN users u ON t.user_id = u.id 
        WHERE t.item_id = ? 
        ORDER BY t.timestamp DESC 
        LIMIT 1
        """, (item_id,)
    )
    result = c2.fetchone()
    conn2.close()
    return result

def generate_report_pdf(report_type):
    txs = get_transactions()
    filtered = []
    now = datetime.now()
    if report_type == "instant":
        filtered = txs
    else:
        for tx in txs:
            tx_time = datetime.strptime(tx[4], "%Y-%m-%d %H:%M:%S")
            if report_type == "daily" and tx_time.date() == now.date():
                filtered.append(tx)
            elif report_type == "weekly" and (now - tx_time).days < 7:
                filtered.append(tx)
            elif report_type == "monthly" and (now - tx_time).days < 30:
                filtered.append(tx)
            elif report_type == "yearly" and (now - tx_time).days < 365:
                filtered.append(tx)
    if not filtered:
        st.error("No transactions found for the selected period.")
        return None
    # Create DataFrame and add serial numbering starting from 1
    df_tx = pd.DataFrame(filtered, columns=["Trans ID", "User", "Item", "Quantity Taken", "Timestamp"])
    df_tx.insert(0, "S.No", range(1, len(df_tx) + 1))
    filename = f"inventory_report_{report_type}_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
    cpdf = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    cpdf.setFont("Helvetica-Bold", 20)
    cpdf.drawString(50, height - 50, f"Inventory Report - {report_type.capitalize()} Report 😊")
    cpdf.setFont("Helvetica", 12)
    y = height - 80
    headers = ["S.No", "Trans ID", "User", "Item", "Quantity Taken", "Timestamp"]
    x_positions = [30, 80, 140, 240, 350, 500]
    for i, header in enumerate(headers):
        cpdf.drawString(x_positions[i], y, header)
    y -= 20
    cpdf.setFont("Helvetica", 10)
    for index, row in df_tx.iterrows():
        if y < 50:
            cpdf.showPage()
            y = height - 50
        for i, val in enumerate(row):
            cpdf.drawString(x_positions[i], y, str(val))
        y -= 15
    cpdf.save()
    return filename

# ---------------- Vendor Management Functions ----------------
def add_vendor(vendor_name, contact, item_supplied, address, quantity_bought, points):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    try:
        c2.execute(
            "INSERT INTO vendors (vendor_name, contact, item_supplied, address, quantity_bought, points) VALUES (?, ?, ?, ?, ?, ?)",
            (vendor_name, contact, item_supplied, address, quantity_bought, points)
        )
        conn2.commit()
        conn2.close()
        return True
    except sqlite3.IntegrityError:
        st.error("Vendor may already exist.")
        conn2.close()
        return False

def get_vendors():
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT * FROM vendors")
    vendors = c2.fetchall()
    conn2.close()
    return vendors

def delete_vendor(vendor_id):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("DELETE FROM vendors WHERE id=?", (vendor_id,))
    conn2.commit()
    conn2.close()

# --------------------------------------------------------------------
# Save and Reset Entry Log (Admin Only)
# --------------------------------------------------------------------
def save_and_reset_log():
    # Get all login log entries
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT * FROM login_log ORDER BY timestamp DESC")
    logs = c2.fetchall()
    conn2.close()
    if not logs:
        st.error("No log entries to save.")
        return None
    filename = f"entry_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(50, height - 50, "Entry Log Report")
    pdf.setFont("Helvetica", 12)
    y = height - 80
    headers = ["Log ID", "User ID", "Username", "Timestamp"]
    x_positions = [50, 100, 200, 350]
    for i, header in enumerate(headers):
        pdf.drawString(x_positions[i], y, header)
    y -= 20
    pdf.setFont("Helvetica", 10)
    for log in logs:
        if y < 50:
            pdf.showPage()
            y = height - 50
        for i, val in enumerate(log):
            pdf.drawString(x_positions[i], y, str(val))
        y -= 15
    pdf.save()
    # Reset the log table by deleting all entries
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("DELETE FROM login_log")
    conn2.commit()
    conn2.close()
    return filename

# --------------------------------------------------------------------
# Display Low Stock Alerts
# --------------------------------------------------------------------
def display_low_stock_alerts():
    items = get_items()
    low_stock = []
    for item in items:
        try:
            qty = int(item[3])
            thresh = int(item[4])
        except ValueError:
            continue
        if qty < thresh:
            low_stock.append((item[2], qty, thresh))
    if low_stock:
        st.sidebar.markdown("<div class='low-stock'><b>Low Stock Alerts ⚠️:</b></div>", unsafe_allow_html=True)
        for name, qty, thresh in low_stock:
            st.sidebar.write(f"{name} (Qty: {qty}, Threshold: {thresh})")
    else:
        st.sidebar.write("All stock levels are sufficient.")

# Call display_low_stock_alerts after defining all functions
display_low_stock_alerts()

# --------------------------------------------------------------------
# LOGOUT BUTTON (Available in Sidebar)
# --------------------------------------------------------------------
if st.sidebar.button("Logout"):
    st.session_state.clear()
    st.experimental_rerun()

# --------------------------------------------------------------------
# STREAMLIT UI & ROLE-BASED NAVIGATION
# --------------------------------------------------------------------
if st.session_state.get("role") == "admin":
    nav = st.sidebar.radio(
        "Navigation",
        ["Home", "Manage Categories", "Add Items", "View Inventory", "Vendor Management", "User Management", "Reports", "Entry Log", "Account Settings"]
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
        if role:
            user_info = get_user_by_username(username)
            if user_info:
                add_login_log(user_info[0], username)
            st.session_state.logged_in = True
            st.session_state.role = role
            st.session_state.username = username
        else:
            st.error("❌ Invalid username or PIN. Please try again.")
    st.stop()

st.sidebar.success(f"Logged in as: **{st.session_state.username}** ({st.session_state.role.capitalize()} 😊)")

# --------------------------------------------------------------------
# HOME PAGE
# --------------------------------------------------------------------
if nav == "Home":
    st.markdown("<div class='header'>🏠 Home</div>", unsafe_allow_html=True)
    st.write("Welcome to the Professional Inventory Management System! 🚀")

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
        if st.button("Save and Reset Log"):
            pdf_filename = save_and_reset_log()
            if pdf_filename and os.path.exists(pdf_filename):
                st.success(f"Log saved as {pdf_filename} and reset successfully.")
                with open(pdf_filename, "rb") as f:
                    st.download_button("Download Log PDF", f, file_name=pdf_filename)
            else:
                st.error("Failed to save and reset log.")
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
            st.success(f"Category '{new_category}' added successfully! 🎉")
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
        quantity = st.number_input("Quantity", min_value=1, step=1)
        threshold = st.number_input("Low Stock Threshold", min_value=1, step=1)
        if st.button("Add Item"):
            if item_name:
                if add_item(category, item_name, quantity, "", threshold):
                    st.success(f"Item '{item_name}' added to category '{category}'! 👍")
            else:
                st.error("Please provide a valid item name.")
    else:
        st.warning("No categories available. Please add a category first.")

# --------------------------------------------------------------------
# VENDOR MANAGEMENT (Admin Only)
# --------------------------------------------------------------------
elif nav == "Vendor Management":
    if st.session_state.role == "admin":
        st.markdown("<div class='header'>🏢 Vendor Management</div>", unsafe_allow_html=True)
        st.markdown("<div class='subheader'>Add New Vendor:</div>", unsafe_allow_html=True)
        vendor_name = st.text_input("Vendor Name", placeholder="Enter vendor name")
        contact = st.text_input("Contact", placeholder="Enter contact details")
        item_supplied = st.text_input("Item Supplied", placeholder="Enter item supplied")
        address = st.text_area("Address", placeholder="Enter vendor address")
        quantity_bought = st.number_input("Quantity Bought", min_value=0, step=1)
        points = st.text_area("Additional Points", placeholder="Enter any additional notes")
        if st.button("Add Vendor"):
            if vendor_name:
                if add_vendor(vendor_name, contact, item_supplied, address, quantity_bought, points):
                    st.success(f"Vendor '{vendor_name}' added successfully! 🎉")
            else:
                st.error("Please provide a valid vendor name.")
        st.markdown("<div class='subheader'>Existing Vendors:</div>", unsafe_allow_html=True)
        vendors = get_vendors()
        if vendors:
            df_vendors = pd.DataFrame(vendors, columns=["ID", "Vendor Name", "Contact", "Item Supplied", "Address", "Quantity Bought", "Points"])
            st.table(df_vendors)
            for vendor in vendors:
                if st.button(f"Delete Vendor {vendor[0]}", key=f"vendor_{vendor[0]}"):
                    delete_vendor(vendor[0])
                    st.success("Vendor deleted! 🗑️")
        else:
            st.write("No vendors found.")
    else:
        st.error("Access denied. Admins only.")

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
            c2.execute("SELECT id, name, quantity, threshold FROM items WHERE category=?", (category,))
            items = c2.fetchall()
            conn2.close()
            return items
        items_in_cat = get_items_by_category(selected_category)
        if items_in_cat:
            item_options = {f"{item[1]} (Qty: {item[2]})": item for item in items_in_cat}
            selected_item_str = st.selectbox("Select Item", list(item_options.keys()))
            selected_item = item_options[selected_item_str]
            st.write(f"Selected: {selected_item[1]} (Current Qty: {selected_item[2]}, Threshold: {selected_item[3]})")
            take_qty = st.number_input("Quantity to take", min_value=1, max_value=selected_item[2], step=1)
            if st.button("Take Item"):
                new_qty = selected_item[2] - take_qty
                if new_qty < 0:
                    st.error("Not enough stock available.")
                else:
                    update_item_quantity(selected_item[0], new_qty)
                    current_user = get_user_by_username(st.session_state.username)
                    if current_user:
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
    enhanced_items = []
    # Each item row: (id, category, name, quantity, threshold)
    for item in items:
        item_fixed = item[:5]
        last_txn = get_last_transaction_for_item(item_fixed[0])
        if last_txn:
            last_by, last_at = last_txn
        else:
            last_by, last_at = "-", "-"
        enhanced_items.append(item_fixed + (last_by, last_at))
    if enhanced_items:
        df_items = pd.DataFrame(
            enhanced_items,
            columns=["ID", "Category", "Item Name", "Quantity", "Threshold", "Last Taken By", "Last Taken At"]
        )
        st.table(df_items)
        st.markdown("<div class='subheader'>Update / Delete Items:</div>", unsafe_allow_html=True)
        item_id_update = st.text_input("Enter Item ID for Update/Delete", placeholder="Enter item ID")
        new_qty = st.number_input("New Quantity", min_value=0, step=1)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Update Quantity"):
                if item_id_update:
                    update_item_quantity(int(item_id_update), new_qty)
                    st.success("Quantity updated successfully.")
                else:
                    st.error("Please enter an item ID.")
        with col2:
            if st.button("Delete Item"):
                if item_id_update:
                    delete_item(int(item_id_update))
                    st.warning("Item deleted.")
                else:
                    st.error("Please enter an item ID.")
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
                    st.success(f"User '{new_username}' added successfully! 🎉")
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
                    st.success("User deleted! 🗑️")
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
        report_type = st.radio("Select Report Type", ["Instant", "Daily", "Weekly", "Monthly", "Yearly"])
        if st.button("Generate PDF Report"):
            filename = generate_report_pdf(report_type.lower())
            if filename and os.path.exists(filename):
                st.success(f"PDF Report generated: {filename}")
                with open(filename, "rb") as f:
                    st.download_button("Download Report", f, file_name=filename)
            else:
                st.error("Report generation failed.")
        st.markdown("<div class='subheader'>Transaction Log:</div>", unsafe_allow_html=True)
        def get_transactions_display():
            conn2 = get_db_connection()
            c2 = conn2.cursor()
            c2.execute(
                """
                SELECT t.id, u.name, i.name, t.quantity_taken, t.timestamp 
                FROM transactions t 
                JOIN users u ON t.user_id = u.id 
                JOIN items i ON t.item_id = i.id 
                ORDER BY t.timestamp DESC
                """
            )
            trans = c2.fetchall()
            conn2.close()
            return trans
        trans = get_transactions_display()
        if trans:
            df_trans = pd.DataFrame(trans, columns=["Trans ID", "User", "Item", "Quantity Taken", "Timestamp"])
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
    def get_user_by_username_local(username):
        conn2 = get_db_connection()
        c2 = conn2.cursor()
        c2.execute("SELECT id, name, role FROM users WHERE LOWER(name)=LOWER(?)", (username,))
        user = c2.fetchone()
        conn2.close()
        return user
    def update_user_credentials_local(user_id, new_name, new_pin):
        conn2 = get_db_connection()
        c2 = conn2.cursor()
        c2.execute("UPDATE users SET name=?, pin=? WHERE id=?", (new_name, hash_text(new_pin), user_id))
        conn2.commit()
        conn2.close()
    current_user = get_user_by_username_local(st.session_state.username)
    if current_user:
        st.markdown("<div class='subheader'>Update Your Credentials 🔧:</div>", unsafe_allow_html=True)
        new_name = st.text_input("New Username", value=current_user[1])
        new_pin = st.text_input("New PIN", type="password", placeholder="Enter new PIN")
        confirm_pin = st.text_input("Confirm New PIN", type="password", placeholder="Re-enter new PIN")
        if st.button("Update Credentials"):
            if new_pin and new_pin == confirm_pin and new_name.strip() != "":
                update_user_credentials_local(current_user[0], new_name, new_pin)
                st.success("Credentials updated successfully! 🎉")
                st.session_state.username = new_name
            else:
                st.error("Please ensure the PINs match and the username is valid.")
    else:
        st.error("User not found.")



