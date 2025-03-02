import streamlit as st
# Must call set_page_config() as the very first Streamlit command.
st.set_page_config(page_title="Professional Inventory Management", layout="wide")

import os
from datetime import datetime
import pytz  # For IST conversion if needed in transactions
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
conn.commit()

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
conn.commit()

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

# Vendors table for vendor records
c.execute(
    """
    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
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
    # Get IST timestamp
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

# ---------------- Vendor Management Helper Functions ----------------
def add_vendor(name, contact, item_supplied, address, quantity_bought, points):
    conn2 = get_db_connection()
    c2 = conn2.cursor()
    try:
        c2.execute(
            "INSERT INTO vendors (name, contact, item_supplied, address, quantity_bought, points) VALUES (?, ?, ?, ?, ?, ?)",
            (name, contact, item_supplied, address, quantity_bought, points)
        )
        conn2.commit()
        conn2.close()
        return True
    except sqlite3.IntegrityError as e:
        st.error("Error adding vendor: " + str(e))
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
# Generate PDF Report with Serial Number Column (S.No)
# --------------------------------------------------------------------
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
    cpdf.drawString(50, height -




