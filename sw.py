import streamlit as st
# Must call set_page_config() as the very first Streamlit command.
st.set_page_config(page_title="Professional Inventory Management", layout="wide")

import os
from datetime import datetime
import sqlite3
import hashlib
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import requests

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

# Users table (staff still has an 'approved' field for legacy but auto-approved here)
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

# login_requests table (not used anymore)
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

# login_log table
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

# New Tables for Additional Details
# Staff Information Table
c.execute(
    """
    CREATE TABLE IF NOT EXISTS staff_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id TEXT,
        name TEXT,
        mobile TEXT,
        email TEXT,
        additional_details TEXT
    )
    """
)
conn.commit()

# Vendor Information Table with extra field "item_vendored"
c.execute(
    """
    CREATE TABLE IF NOT EXISTS vendor_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_name TEXT,
        contact TEXT,
        address TEXT,
        item_vendored TEXT,
        additional_details TEXT
    )
    """
)
conn.commit()

# Insert default users if table is empty: 2 admins and 2 staff (auto-approved)
c.execute("SELECT COUNT(*) FROM users")
if c.fetchone()[0] == 0:
    c.execute("INSERT INTO users (name, role, pin, approved) VALUES (?, ?, ?, ?)", ("Admin1", "admin", hash_text("admin1pass"), 1))
    c.execute("INSERT INTO users (name, role, pin, approved) VALUES (?, ?, ?, ?)", ("Admin2", "admin", hash_text("admin2pass"), 1))
    c.execute("INSERT INTO users (name, role, pin, approved) VALUES (?, ?, ?, ?)", ("Staff1", "staff", hash_text("staff1pass"), 1))
    c.execute("INSERT INTO users (name, role, pin, approved) VALUES (?, ?, ?, ?)", ("Staff2", "staff", hash_text("staff2pass"), 1))
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
conn.commit()

# --------------------------------------------------------------------
# Additional Helper Functions for Logging and Additional Tables
# --------------------------------------------------------------------
def add_login_log(user_id, username):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn2 = sqlite3.connect("inventory.db", check_same_thread=False)
    c2 = conn2.cursor()
    c2.execute("INSERT INTO login_log (user_id, username, timestamp) VALUES (?, ?, ?)", (user_id, username, ts))
    conn2.commit()
    conn2.close()

def add_staff_info(staff_id, name, mobile, email, additional_details):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("INSERT INTO staff_info (staff_id, name, mobile, email, additional_details) VALUES (?, ?, ?, ?, ?)",
               (staff_id, name, mobile, email, additional_details))
    conn2.commit()
    conn2.close()

def get_staff_info():
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT * FROM staff_info")
    info = c2.fetchall()
    conn2.close()
    return info

def add_vendor_info(vendor_name, contact, address, item_vendored, additional_details):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("INSERT INTO vendor_info (vendor_name, contact, address, item_vendored, additional_details) VALUES (?, ?, ?, ?, ?)",
               (vendor_name, contact, address, item_vendored, additional_details))
    conn2.commit()
    conn2.close()

def get_vendor_info():
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT * FROM vendor_info")
    info = c2.fetchall()
    conn2.close()
    return info

# --------------------------------------------------------------------
# Real-Time News Fetching for Electricals
# --------------------------------------------------------------------
def fetch_electrical_news():
    # Use your News API key here. It is recommended to store it in Streamlit secrets.
    api_key = st.secrets["news_api_key"] if "news_api_key" in st.secrets else "YOUR_API_KEY"
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "q": "electrical goods OR electrical inventory OR electrical appliances",
        "apiKey": api_key,
        "pageSize": 5,
        "language": "en"
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get("articles", [])
    else:
        return []

# --------------------------------------------------------------------
# New: Generate Entry Log PDF
# --------------------------------------------------------------------
def generate_entry_log_pdf():
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    c2.execute("SELECT id, user_id, username, timestamp FROM login_log ORDER BY timestamp DESC")
    logs = c2.fetchall()
    conn2.close()
    if not logs:
        st.error("No login entries found.")
        return None
    df_log = pd.DataFrame(logs, columns=["Log ID", "User ID", "Username", "Timestamp"])
    filename = f"entry_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    cpdf = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    cpdf.setFont("Helvetica-Bold", 20)
    cpdf.drawString(50, height - 50, "Entry Log Report")
    cpdf.setFont("Helvetica", 12)
    y = height - 80
    headers = ["Log ID", "User ID", "Username", "Timestamp"]
    x_positions = [50, 150, 250, 450]
    for i, header in enumerate(headers):
        cpdf.drawString(x_positions[i], y, header)
    y -= 20
    cpdf.setFont("Helvetica", 10)
    for index, row in df_log.iterrows():
        if y < 50:
            cpdf.showPage()
            y = height - 50
        for i, val in enumerate(row):
            cpdf.drawString(x_positions[i], y, str(val))
        y -= 15
    cpdf.save()
    return filename

# --------------------------------------------------------------------
# Sidebar: Low Stock Alerts (Real-Time)
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

display_low_stock_alerts()

# --------------------------------------------------------------------
# STREAMLIT UI & ROLE-BASED NAVIGATION
# --------------------------------------------------------------------
# Updated sidebar titles for grammatical correctness and inclusion of "About"
if st.session_state.get("role") == "admin":
    nav = st.sidebar.radio(
        "Navigation",
        ["Home", "Manage Categories", "Add Items", "View Inventory", "User Management", "Reports", "Entry Log", "Account Settings", "About"]
    )
elif st.session_state.get("role") == "staff":
    nav = st.sidebar.radio("Navigation", ["Home", "Take Items", "View Inventory", "Account Settings", "About"])
else:
    nav = st.sidebar.radio("Navigation", ["Home", "View Inventory", "Account Settings", "About"])

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
            st.rerun()
        else:
            st.error("❌ Invalid username or PIN. Please try again.")
    st.stop()

st.sidebar.success(f"Logged in as: **{st.session_state.username}** ({st.session_state.role.capitalize()} 😊)")

# --------------------------------------------------------------------
# HOME PAGE
# --------------------------------------------------------------------
if nav == "Home":
    st.markdown("<div class='header'>🏠 Home</div>", unsafe_allow_html=True)
    st.write("Welcome to the Professional Electrical Goods Inventory Management System! 🚀")
    # Display Real-Time Electrical News
    st.markdown("<div class='subheader'>🔌 Real-Time Electrical News</div>", unsafe_allow_html=True)
    articles = fetch_electrical_news()
    if articles:
        for article in articles:
            st.markdown(f"**[{article['title']}]({article['url']})**")
            st.write(article.get('description', 'No description available.'))
            st.write("---")
    else:
        st.write("No news available at the moment.")

# --------------------------------------------------------------------
# ENTRY LOG (Admin Only) with Save & Reset Option for Monthly Log in PDF Format
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
        
        # Save & Reset Monthly Log (PDF Export)
        if st.button("Save & Reset Monthly Log (PDF)"):
            current_month = datetime.now().strftime("%Y-%m")
            df_log = pd.DataFrame(log_entries, columns=["Log ID", "User ID", "Username", "Timestamp"])
            df_month = df_log[df_log["Timestamp"].str.startswith(current_month)]
            if not df_month.empty:
                # Generate PDF for the monthly log
                filename = generate_entry_log_pdf()
                if filename and os.path.exists(filename):
                    st.download_button("Download Monthly Log PDF", open(filename, "rb"), file_name=f"monthly_log_{current_month}.pdf")
                    # Clear logs for current month
                    conn2 = get_db_connection()
                    c2 = conn2.cursor()
                    c2.execute("DELETE FROM login_log WHERE strftime('%Y-%m', timestamp)=?", (current_month,))
                    conn2.commit()
                    conn2.close()
                    st.success("Monthly log saved and reset.")
                else:
                    st.error("Failed to generate PDF.")
            else:
                st.warning("No log entries for the current month to reset.")
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
                if add_item(category, item_name, quantity, threshold):
                    st.success(f"Item '{item_name}' added to category '{category}'! 👍")
            else:
                st.error("Please provide a valid item name.")
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
        # Create a serial number starting from 1 for display purposes.
        serial_numbers = list(range(1, len(enhanced_items) + 1))
        df_items = pd.DataFrame(enhanced_items, columns=["ID", "Category", "Item Name", "Quantity", "Threshold", "Last Taken By", "Last Taken At"])
        df_items.insert(0, "S.No", serial_numbers)
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
        trans = get_transactions()
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
    current_user = get_user_by_username(st.session_state.username)
    if current_user:
        st.markdown("<div class='subheader'>Update Your Credentials 🔧:</div>", unsafe_allow_html=True)
        new_name = st.text_input("New Username", value=current_user[1])
        new_pin = st.text_input("New PIN", type="password", placeholder="Enter new PIN")
        confirm_pin = st.text_input("Confirm New PIN", type="password", placeholder="Re-enter new PIN")
        if st.button("Update Credentials"):
            if new_pin and new_pin == confirm_pin and new_name.strip() != "":
                update_user_credentials(current_user[0], new_name, new_pin)
                st.success("Credentials updated successfully! 🎉")
                st.session_state.username = new_name
            else:
                st.error("Please ensure the PINs match and the username is valid.")
    else:
        st.error("User not found.")

# --------------------------------------------------------------------
# ABOUT / DETAILS (Staff & Vendor Information)
# --------------------------------------------------------------------
elif nav == "About":
    st.markdown("<div class='header'>ℹ️ About / Details</div>", unsafe_allow_html=True)
    
    st.markdown("<div class='subheader'>Staff Information</div>", unsafe_allow_html=True)
    staff_id = st.text_input("Staff ID", placeholder="Enter your staff ID")
    staff_name = st.text_input("Name", placeholder="Enter your name")
    mobile = st.text_input("Mobile Number", placeholder="Enter your mobile number")
    email = st.text_input("Email", placeholder="Enter your email address")
    additional_details = st.text_area("Additional Details", placeholder="Enter any additional details")
    if st.button("Add Staff Info"):
        add_staff_info(staff_id, staff_name, mobile, email, additional_details)
        st.success("Staff information added.")
    staff_info = get_staff_info()
    if staff_info:
        df_staff = pd.DataFrame(staff_info, columns=["ID", "Staff ID", "Name", "Mobile", "Email", "Additional Details"])
        st.table(df_staff)
    else:
        st.write("No staff information available.")
    
    st.markdown("<div class='subheader'>Vendor Information</div>", unsafe_allow_html=True)
    vendor_name = st.text_input("Vendor Name", placeholder="Enter vendor name")
    contact = st.text_input("Contact Number", placeholder="Enter vendor contact number")
    address = st.text_input("Address", placeholder="Enter vendor address")
    item_vendored = st.text_input("Item Vendored", placeholder="Enter the item for which the vendor supplies")
    vendor_additional = st.text_area("Additional Details", placeholder="Enter additional details about the vendor")
    if st.button("Add Vendor Info"):
        add_vendor_info(vendor_name, contact, address, item_vendored, vendor_additional)
        st.success("Vendor information added.")
    vendor_info = get_vendor_info()
    if vendor_info:
        df_vendor = pd.DataFrame(vendor_info, columns=["ID", "Vendor Name", "Contact", "Address", "Item Vendored", "Additional Details"])
        st.table(df_vendor)
    else:
        st.write("No vendor information available.")

