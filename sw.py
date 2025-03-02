import streamlit as st
import os
from datetime import datetime
import sqlite3
import hashlib
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# -----------------------------
# Set Page Configuration
# -----------------------------
st.set_page_config(page_title="Inventory Management System", layout="wide")

# -----------------------------
# Display Official Logo in Sidebar
# -----------------------------
logo_url = "https://i.imgur.com/e6E6TJt.jpeg"
st.sidebar.image(logo_url, width=150)

# -----------------------------
# Custom CSS for Professional Look
# -----------------------------
st.markdown(
    """
    <style>
    body { background-color: #f9f9f9; }
    .header { font-size: 36px; color: #2C3E50; font-weight: bold; margin-bottom: 20px; }
    .subheader { font-size: 28px; color: #34495E; margin-bottom: 15px; }
    .low-stock { color: #D32F2F; font-weight: bold; font-size: 20px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Database Connection
# -----------------------------
def get_db_connection():
    return sqlite3.connect("inventory.db", check_same_thread=False)

# -----------------------------
# Hash Function for Security
# -----------------------------
def hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()

# -----------------------------
# Database Setup
# -----------------------------
conn = get_db_connection()
c = conn.cursor()

# Users Table
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

# Items Table
c.execute(
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

# Transactions Table
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

# Vendor Table
c.execute(
    """
    CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_name TEXT NOT NULL,
        contact TEXT NOT NULL,
        address TEXT NOT NULL,
        item_supplied TEXT NOT NULL
    )
    """
)
conn.commit()

# Insert Default Users
c.execute("SELECT COUNT(*) FROM users")
if c.fetchone()[0] == 0:
    c.execute("INSERT INTO users (name, role, pin) VALUES (?, ?, ?)", ("Admin1", "admin", hash_text("admin1pass")))
    c.execute("INSERT INTO users (name, role, pin) VALUES (?, ?, ?)", ("Staff1", "staff", hash_text("staff1pass")))
    conn.commit()

# -----------------------------
# Helper Functions
# -----------------------------
def get_items():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, category, name, quantity, threshold FROM items")
    items = c.fetchall()
    conn.close()
    return items

def add_item(category, name, quantity, threshold):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO items (category, name, quantity, threshold) VALUES (?, ?, ?, ?)", 
              (category, name, quantity, threshold))
    conn.commit()
    conn.close()

def update_item_quantity(item_id, quantity):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE items SET quantity=? WHERE id=?", (quantity, item_id))
    conn.commit()
    conn.close()

def display_low_stock_alerts():
    items = get_items()
    low_stock = [item for item in items if item[3] < item[4]]
    if low_stock:
        st.sidebar.markdown("<div class='low-stock'><b>⚠️ Low Stock Alerts:</b></div>", unsafe_allow_html=True)
        for item in low_stock:
            st.sidebar.write(f"{item[2]} (Qty: {item[3]}, Threshold: {item[4]})")
    else:
        st.sidebar.write("✅ All stock levels are sufficient.")

# -----------------------------
# Streamlit UI & Navigation
# -----------------------------
display_low_stock_alerts()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = ""

if not st.session_state.logged_in:
    st.markdown("<div class='header'>🔐 Login</div>", unsafe_allow_html=True)
    username = st.text_input("Username", placeholder="Enter your username")
    pin = st.text_input("PIN", type="password", placeholder="Enter your PIN")
    if st.button("Login"):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, role FROM users WHERE name=? AND pin=?", (username, hash_text(pin)))
        user = c.fetchone()
        conn.close()
        if user:
            st.session_state.logged_in = True
            st.session_state.role = user[1]
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Invalid username or PIN")
    st.stop()

st.sidebar.success(f"Logged in as: **{st.session_state.username}** ({st.session_state.role.capitalize()} 😊)")

# Navigation Menu
nav = st.sidebar.radio("Menu", ["Home", "Add Items", "View Inventory", "Reports", "Vendors"])

# -----------------------------
# Home Page
# -----------------------------
if nav == "Home":
    st.markdown("<div class='header'>🏠 Home</div>", unsafe_allow_html=True)
    st.write("Welcome to the Inventory Management System! 🚀")

# -----------------------------
# Add Items Page
# -----------------------------
elif nav == "Add Items":
    st.markdown("<div class='header'>📦 Add New Item</div>", unsafe_allow_html=True)
    category = st.text_input("Category", placeholder="Enter item category")
    name = st.text_input("Item Name", placeholder="Enter item name")
    quantity = st.number_input("Quantity", min_value=1, step=1)
    threshold = st.number_input("Low Stock Threshold", min_value=1, step=1)
    if st.button("Add Item"):
        add_item(category, name, quantity, threshold)
        st.success("Item added successfully!")

# -----------------------------
# View Inventory Page
# -----------------------------
elif nav == "View Inventory":
    st.markdown("<div class='header'>📋 Inventory Items</div>", unsafe_allow_html=True)
    items = get_items()
    df = pd.DataFrame(items, columns=["ID", "Category", "Name", "Quantity", "Threshold"])
    st.table(df)

# -----------------------------
# Reports Page
# -----------------------------
elif nav == "Reports":
    st.markdown("<div class='header'>📄 Reports</div>", unsafe_allow_html=True)
    report_type = st.selectbox("Select Report Type", ["Daily", "Weekly", "Monthly"])
    st.write(f"Generating {report_type} report...")

# -----------------------------
# Vendor Management
# -----------------------------
elif nav == "Vendors":
    st.markdown("<div class='header'>🏭 Vendor Management</div>", unsafe_allow_html=True)
    vendor_name = st.text_input("Vendor Name", placeholder="Enter vendor name")
    contact = st.text_input("Contact", placeholder="Enter vendor contact number")
    address = st.text_input("Address", placeholder="Enter vendor address")
    item_supplied = st.text_input("Item Supplied", placeholder="Enter the item they supply")
    if st.button("Add Vendor"):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO vendors (vendor_name, contact, address, item_supplied) VALUES (?, ?, ?, ?)",
                  (vendor_name, contact, address, item_supplied))
        conn.commit()
        conn.close()
        st.success("Vendor added successfully!")




