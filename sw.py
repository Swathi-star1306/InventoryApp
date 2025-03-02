import streamlit as st
import os
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

st.set_page_config(page_title="Electrical Inventory Management", layout="wide")

# -----------------------------
# Display Official Logo in Sidebar
# -----------------------------
logo_url = "https://i.imgur.com/e6E6TJt.jpeg"
st.sidebar.image(logo_url, width=150)

# -----------------------------
# Custom Fonts & UI Styling
# -----------------------------
st.markdown(
    """
    <style>
    .header { font-size: 32px; font-weight: bold; color: #4B0082; }
    .subheader { font-size: 24px; font-weight: bold; color: #800080; }
    .low-stock { color: #D32F2F; font-weight: bold; font-size: 18px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Helper Functions
# -----------------------------
def hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()

def get_db_connection():
    return sqlite3.connect("inventory.db", check_same_thread=False)

def execute_query(query, params=()):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def fetch_query(query, params=()):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(query, params)
    data = c.fetchall()
    conn.close()
    return data

# -----------------------------
# Database Setup
# -----------------------------
execute_query(
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        pin TEXT NOT NULL
    )
    """
)
execute_query(
    """
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        threshold INTEGER NOT NULL
    )
    """
)
execute_query(
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity_taken INTEGER NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
)
execute_query(
    """
    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact TEXT NOT NULL,
        address TEXT NOT NULL,
        item_vendored TEXT NOT NULL
    )
    """
)
execute_query(
    """
    CREATE TABLE IF NOT EXISTS login_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
)

def authenticate(username, pin):
    hashed_pin = hash_text(pin)
    user = fetch_query("SELECT id, role FROM users WHERE name=? AND pin=?", (username, hashed_pin))
    return user[0] if user else None

def add_transaction(user_id, item_id, quantity_taken):
    execute_query("INSERT INTO transactions (user_id, item_id, quantity_taken) VALUES (?, ?, ?)",
                 (user_id, item_id, quantity_taken))

def generate_pdf(data, filename, title, columns):
    pdf = canvas.Canvas(filename, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 750, title)
    pdf.setFont("Helvetica", 12)
    y = 720
    for i, header in enumerate(columns):
        pdf.drawString(50 + i * 120, y, header)
    y -= 20
    for row in data:
        if y < 50:
            pdf.showPage()
            y = 750
        for i, value in enumerate(row):
            pdf.drawString(50 + i * 120, y, str(value))
        y -= 20
    pdf.save()
    return filename

def generate_user_pdf():
    users = fetch_query("SELECT id, name, role FROM users")
    return generate_pdf(users, "user_report.pdf", "User Management Report", ["ID", "Name", "Role"])

def generate_inventory_pdf():
    items = fetch_query("SELECT * FROM items")
    return generate_pdf(items, "inventory_report.pdf", "Inventory Report", ["ID", "Category", "Name", "Quantity", "Threshold"])

def generate_vendor_pdf():
    vendors = fetch_query("SELECT * FROM vendors")
    return generate_pdf(vendors, "vendor_report.pdf", "Vendor Report", ["ID", "Name", "Contact", "Address", "Item"])

def generate_entry_log_pdf():
    logs = fetch_query("SELECT * FROM login_log")
    return generate_pdf(logs, "entry_log.pdf", "Entry Log Report", ["ID", "User ID", "Username", "Timestamp"])

# -----------------------------
# Streamlit UI
# -----------------------------
st.sidebar.title("Navigation")
navigation = st.sidebar.radio("Select Page", ["Home", "User Management", "Inventory", "Vendors", "Reports", "Entry Log"])

if navigation == "Home":
    st.title("🏠 Electrical Inventory Management System")
    st.write("Welcome to the inventory management system for electrical goods.")

elif navigation == "User Management":
    st.title("👥 User Management")
    if st.button("Export User Data to PDF"):
        filename = generate_user_pdf()
        st.download_button("Download User Report", open(filename, "rb"), file_name=filename)

elif navigation == "Inventory":
    st.title("📦 Inventory Management")
    if st.button("Export Inventory Data to PDF"):
        filename = generate_inventory_pdf()
        st.download_button("Download Inventory Report", open(filename, "rb"), file_name=filename)

elif navigation == "Vendors":
    st.title("🏭 Vendor Management")
    if st.button("Export Vendor Data to PDF"):
        filename = generate_vendor_pdf()
        st.download_button("Download Vendor Report", open(filename, "rb"), file_name=filename)

elif navigation == "Entry Log":
    st.title("📜 Entry Log")
    if st.button("Export Entry Log to PDF"):
        filename = generate_entry_log_pdf()
        st.download_button("Download Entry Log Report", open(filename, "rb"), file_name=filename)




