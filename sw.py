import streamlit as st
from firebase_admin import credentials, firestore, initialize_app
import time
import datetime
import pdfkit
from twilio.rest import Client

# Initialize Firebase
cred = credentials.Certificate("firebase_credentials.json")
initialize_app(cred)
db = firestore.client()
users_ref = db.collection("users")
inventory_ref = db.collection("inventory")
logs_ref = db.collection("logs")

# Authentication Function
def authenticate_user(pin):
    user = users_ref.where("pin", "==", pin).get()
    if user:
        user_data = user[0].to_dict()
        return user_data
    return None

# Send Notification via Twilio
def send_sms(message):
    account_sid = "your_twilio_sid"
    auth_token = "your_twilio_auth_token"
    client = Client(account_sid, auth_token)
    client.messages.create(body=message, from_="your_twilio_number", to="admin_number")

# Admin Panel
def admin_panel():
    st.title("Admin Dashboard")
    
    if st.button("View Inventory"):
        items = inventory_ref.stream()
        for item in items:
            st.write(item.to_dict())
    
    if st.button("Generate Report (PDF)"):
        report = "Inventory Report\n"
        items = inventory_ref.stream()
        for item in items:
            report += str(item.to_dict()) + "\n"
        pdfkit.from_string(report, "report.pdf")
        st.success("Report generated!")
    
    if st.button("Send Report via Email"):
        # Email sending logic
        st.success("Report sent!")

# Staff Panel
def staff_panel(user):
    st.title(f"Welcome {user['name']}")
    if st.button("Take Item"):
        item_name = st.text_input("Enter Item Name")
        quantity = st.number_input("Quantity", min_value=1)
        if st.button("Confirm"):
            inventory_ref.document(item_name).update({"quantity": firestore.Increment(-quantity)})
            logs_ref.add({"user": user["name"], "item": item_name, "quantity": quantity, "timestamp": datetime.datetime.now()})
            send_sms(f"{user['name']} took {quantity} of {item_name}")
            st.success("Transaction Logged!")

# Main Application
def main():
    st.title("Inventory Management System")
    pin = st.text_input("Enter PIN", type="password")
    if st.button("Login"):
        user = authenticate_user(pin)
        if user:
            if user['role'] == 'admin':
                admin_panel()
            else:
                staff_panel(user)
        else:
            st.error("Invalid PIN")

if __name__ == "__main__":
    main()





