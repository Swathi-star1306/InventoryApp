import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

st.set_page_config(page_title="Inventory Management", layout="wide")

# Database Connection
conn = sqlite3.connect("inventory.db", check_same_thread=False)
c = conn.cursor()

# Create Tables
c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL,
        pin TEXT NOT NULL
    )
""")

c.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        vendor TEXT NOT NULL
    )
""")

c.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        vendor TEXT NOT NULL,
        threshold INTEGER NOT NULL
    )
""")

c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity_taken INTEGER NOT NULL,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
""")

conn.commit()

# -------------------------- Utility Functions --------------------------

def hash_text(text):
    return hashlib.sha256(text.encode()).hexdigest()

def get_db_connection():
    return sqlite3.connect("inventory.db", check_same_thread=False)

def authenticate(username, pin):
    conn = get_db_connection()
    c = conn.cursor()
    hashed = hash_text(pin)
    c.execute("SELECT id, role FROM users WHERE name=? AND pin=?", (username, hashed))
    row = c.fetchone()
    conn.close()
    if row:
        return row
    return None

def get_categories():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name, vendor FROM categories")
    categories = c.fetchall()
    conn.close()
    return categories

def get_items():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, category, name, quantity, vendor, threshold FROM items")
    items = c.fetchall()
    conn.close()
    return items

def update_item_quantity(item_id, new_quantity):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE items SET quantity=? WHERE id=?", (new_quantity, item_id))
    conn.commit()
    conn.close()

def add_transaction(user_id, item_id, quantity):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO transactions (user_id, item_id, quantity_taken, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, item_id, quantity, timestamp))
    conn.commit()
    conn.close()

def get_transactions():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT t.id, u.name, i.name, t.quantity_taken, t.timestamp, i.vendor
        FROM transactions t
        JOIN users u ON t.user_id = u.id
        JOIN items i ON t.item_id = i.id
        ORDER BY t.timestamp DESC
    """)
    transactions = c.fetchall()
    conn.close()
    return transactions

def generate_pdf_report():
    transactions = get_transactions()
    if not transactions:
        st.error("No transaction data available.")
        return None

    filename = f"inventory_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, height - 50, "Inventory Transaction Report")
    pdf.setFont("Helvetica", 10)

    y = height - 80
    headers = ["S.No", "User", "Item", "Quantity", "Timestamp", "Vendor"]
    x_positions = [30, 100, 200, 300, 400, 500]

    for i, header in enumerate(headers):
        pdf.drawString(x_positions[i], y, header)

    y -= 20
    for index, row in enumerate(transactions, start=1):
        if y < 50:
            pdf.showPage()
            y = height - 50
        pdf.drawString(x_positions[0], y, str(index))
        for i, val in enumerate(row[1:], start=1):
            pdf.drawString(x_positions[i], y, str(val))
        y -= 15

    pdf.save()
    return filename

# -------------------------- Streamlit UI --------------------------

if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🔐 Inventory Management Login")
    username = st.text_input("Username")
    pin = st.text_input("PIN", type="password")
    if st.button("Login"):
        user = authenticate(username, pin)
        if user:
            st.session_state.user = user
            st.experimental_rerun()
        else:
            st.error("Invalid username or PIN.")

else:
    user_id, role = st.session_state.user
    st.sidebar.success(f"Logged in as: {role.capitalize()}")

    menu = ["Home", "Inventory", "Transactions", "Generate Report"]
    choice = st.sidebar.radio("Menu", menu)

    if choice == "Home":
        st.header("📊 Dashboard")
        st.write("Welcome to the Inventory Management System!")

    elif choice == "Inventory":
        st.header("📦 Manage Inventory")
        items = get_items()
        if items:
            df = pd.DataFrame(items, columns=["ID", "Category", "Item", "Quantity", "Vendor", "Threshold"])
            st.table(df)
        else:
            st.write("No inventory data available.")

    elif choice == "Transactions":
        st.header("📜 Transaction Log")
        transactions = get_transactions()
        if transactions:
            df = pd.DataFrame(transactions, columns=["ID", "User", "Item", "Quantity", "Timestamp", "Vendor"])
            st.table(df)
        else:
            st.write("No transactions recorded.")

    elif choice == "Generate Report":
        st.header("📄 Generate Report")
        if st.button("Download PDF Report"):
            filename = generate_pdf_report()
            if filename:
                with open(filename, "rb") as f:
                    st.download_button("Download Report", f, file_name=filename)


