import streamlit as st
import sqlite3
import pandas as pd
import datetime
import pdfkit

# Database Connection
def get_db_connection():
    conn = sqlite3.connect("inventory.db")
    return conn

# Retrieve all inventory items
def get_items():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM items")
    items = c.fetchall()
    conn.close()
    return items

# Retrieve low stock items
def display_low_stock_alerts():
    items = get_items()
    low_stock = []
    for item in items:
        try:
            qty = int(item[3])  # Column 3: Current Quantity
            thresh = int(item[4])  # Column 4: Threshold
        except ValueError:
            continue
        if qty < thresh:
            low_stock.append((item[2], qty, thresh))  # Column 2: Item Name

    if low_stock:
        st.sidebar.markdown("<b>⚠️ Low Stock Alerts:</b>", unsafe_allow_html=True)
        for name, qty, thresh in low_stock:
            st.sidebar.write(f"{name} (Qty: {qty}, Threshold: {thresh})")
    else:
        st.sidebar.write("✅ All stock levels are sufficient.")

# User Authentication
def authenticate_user(username, password):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE username=? AND password=?", (username, password))
    user = c.fetchone()
    conn.close()
    return user[0] if user else None

# Add Inventory Item
def add_item(name, category, quantity, vendor, threshold):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO items (name, category, quantity, vendor, threshold) VALUES (?, ?, ?, ?, ?)",
              (name, category, quantity, vendor, threshold))
    conn.commit()
    conn.close()
    st.success("✅ Item added successfully!")

# Update Item Quantity
def update_item(name, quantity_change):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE items SET quantity = quantity + ? WHERE name = ?", (quantity_change, name))
    conn.commit()
    conn.close()
    st.success("✅ Item quantity updated!")

# Delete an Item
def delete_item(name):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM items WHERE name=?", (name,))
    conn.commit()
    conn.close()
    st.success("🗑️ Item deleted successfully!")

# Generate PDF Report
def generate_pdf_report():
    items = get_items()
    df = pd.DataFrame(items, columns=["ID", "Category", "Item Name", "Quantity", "Vendor", "Threshold"])
    pdf_content = df.to_string(index=False)
    pdfkit.from_string(pdf_content, "inventory_report.pdf")
    st.success("📄 PDF Report Generated!")

# Main Application
def main():
    st.title("📦 Inventory Management System")
    menu = ["Login", "Register", "Inventory", "Reports"]
    choice = st.sidebar.selectbox("Menu", menu)

    # Login Section
    if choice == "Login":
        st.subheader("🔑 User Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            role = authenticate_user(username, password)
            if role:
                st.session_state["authenticated"] = True
                st.session_state["user_role"] = role
                st.success(f"✅ Logged in as {role}")
                st.experimental_rerun()
            else:
                st.error("❌ Invalid credentials")

    # Register Section
    elif choice == "Register":
        st.subheader("🆕 Register New User")
        new_user = st.text_input("New Username")
        new_pass = st.text_input("New Password", type="password")
        role = st.selectbox("Role", ["admin", "staff"])
        if st.button("Register"):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (new_user, new_pass, role))
            conn.commit()
            conn.close()
            st.success("✅ User registered successfully!")

    # Inventory Management
    elif choice == "Inventory" and "authenticated" in st.session_state:
        role = st.session_state["user_role"]
        st.subheader("📋 Manage Inventory")
        display_low_stock_alerts()

        # Add New Item (Admin Only)
        if role == "admin":
            with st.form("add_item_form"):
                name = st.text_input("Item Name")
                category = st.text_input("Category")
                quantity = st.number_input("Quantity", min_value=1)
                vendor = st.text_input("Vendor Name")
                threshold = st.number_input("Low Stock Threshold", min_value=1)
                submit = st.form_submit_button("Add Item")
                if submit:
                    add_item(name, category, quantity, vendor, threshold)

        # Update Stock (Admin & Staff)
        with st.form("update_item_form"):
            item_name = st.text_input("Item Name to Update")
            quantity_change = st.number_input("Quantity Change (+/-)", min_value=-1000, max_value=1000, step=1)
            submit = st.form_submit_button("Update Stock")
            if submit:
                update_item(item_name, quantity_change)

        # Delete Item (Admin Only)
        if role == "admin":
            with st.form("delete_item_form"):
                delete_item_name = st.text_input("Item Name to Delete")
                submit = st.form_submit_button("Delete Item")
                if submit:
                    delete_item(delete_item_name)

    # Reports Section
    elif choice == "Reports" and "authenticated" in st.session_state:
        st.subheader("📊 Generate Reports")
        if st.button("Generate PDF Report"):
            generate_pdf_report()

    else:
        st.warning("🔒 Please log in first.")

if __name__ == "__main__":
    main()





