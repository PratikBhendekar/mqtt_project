import re
import threading
import time
import socket
import webbrowser
import json
from copy import deepcopy
from datetime import datetime, timedelta
import math
import random

import pandas as pd
import paho.mqtt.client as mqtt
from dash import Dash, dcc, html, dash_table, callback_context
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import base64
from io import BytesIO
import os
import psycopg2
from psycopg2 import sql
from dash import Dash
import dash_bootstrap_components as dbc



# ================== DATABASE CONFIG ==================
db_user = "postgres"
db_password = "Pratik@123"
db_host = "localhost"
db_port = "5432"
db_name = "postgres"
main_table_name = "JJJ_Site"
new_entries_table_name = "JJM_New_Entries"
user_login_table = "login_access"
admin_login_table = "admin_access"

LOGO_PATH = r"C:\Users\12797\Music\Data Link MONTh\Screenshot 2025-09-10 170918.png"

# ================== MQTT CONFIG ==================
BROKER = "14.99.99.166"
PORT = 1889
USERNAME = "MQTT"
PASSWORD = "Mqtt@123"

# ================== LOGIN CONFIG ==================
# User activity tracking
user_activity_log = []

# Columns
COL_FLOW = "Topic For Flow Meter"
COL_CL = "Topic For CL"
COL_TYPE_CL = "Type of Cl"
COL_PRESSURE = "Topic For Pressure"
COL_SCHEME = "Schme ID  Name"
COL_VILLAGE = "Village"
COL_BLOCK = "Block"
COL_RESERVOIR = "Reservoir"
COL_CIRCLE = "Circle"
COL_DIVISION = "Division"
COL_SUBDIVISION = "Sub Division"
COL_SR_NO = "Sr.No"
COL_POPULATION = "Population"  # New Population column
# Columns - Status columns
COL_FLOW_STATUS = "Flow"
COL_CL_STATUS = "Chlorin"
COL_PRESSURE_STATUS = "Pressure"
COL_STUDY = "Study"  # New Study column

# UI refresh interval
UI_REFRESH_MS = 3000

# Pressure sensor settings
PRESSURE_UPDATE_HOURS = 12

# ================== DATABASE FUNCTIONS ==================
def get_db_connection():
    """Create and return a database connection"""
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def create_new_entries_table():
    """Create the new entries table if it doesn't exist"""
    conn = get_db_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()

        create_table_query = f'''
        CREATE TABLE IF NOT EXISTS "{new_entries_table_name}" (
            "{COL_SR_NO}" TEXT,
            "Region" TEXT,
            "{COL_CIRCLE}" TEXT,
            "{COL_DIVISION}" TEXT,
            "{COL_SUBDIVISION}" TEXT,
            "{COL_BLOCK}" TEXT,
            "{COL_SCHEME}" TEXT,
            "{COL_VILLAGE}" TEXT,
            "{COL_RESERVOIR}" TEXT,
            "Message Type" TEXT,
            "{COL_FLOW}" TEXT,
            "{COL_CL}" TEXT,
            "{COL_TYPE_CL}" TEXT,
            "{COL_PRESSURE}" TEXT,
            "{COL_FLOW_STATUS}" TEXT,
            "{COL_CL_STATUS}" TEXT,
            "{COL_PRESSURE_STATUS}" TEXT,
            "{COL_STUDY}" TEXT,
            "Status" TEXT,
            "Remarks" TEXT,
            "Added Date" TEXT
        )
        '''

        cursor.execute(create_table_query)
        conn.commit()
        print(f"Table {new_entries_table_name} created or already exists")
        return True

    except Exception as e:
        print(f"Error creating table {new_entries_table_name}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def load_data_from_db(table_name):
    """Load data from PostgreSQL table into DataFrame"""
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()

    try:
        # For new entries table, ensure it exists first
        if table_name == new_entries_table_name:
            create_new_entries_table()

        # Convert SQL object to string for pandas
        query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(table_name))
        query_str = query.as_string(conn)

        df = pd.read_sql_query(query_str, conn)
        return df
    except Exception as e:
        print(f"Error loading data from {table_name}: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def save_new_entry_to_db(entry_data):
    """Save new entry to the new entries table"""
    conn = get_db_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()

        # Ensure table exists
        create_new_entries_table()

        # Get the next SR No
        cursor.execute(f'SELECT MAX("{COL_SR_NO}") FROM "{new_entries_table_name}"')
        max_sr_no_result = cursor.fetchone()[0]

        # Handle None or non-digit values
        if max_sr_no_result is None or not str(max_sr_no_result).isdigit():
            next_sr_no = 1
        else:
            next_sr_no = int(max_sr_no_result) + 1

        # Prepare columns and values
        columns = [COL_SR_NO] + list(entry_data.keys())
        values = [str(next_sr_no)] + list(entry_data.values())

        # Build INSERT query
        columns_str = ', '.join([f'"{col}"' for col in columns])
        placeholders = ', '.join(['%s'] * len(columns))

        insert_query = f'INSERT INTO "{new_entries_table_name}" ({columns_str}) VALUES ({placeholders})'

        cursor.execute(insert_query, values)
        conn.commit()
        print(f"New entry saved with SR No: {next_sr_no}")
        return True

    except Exception as e:
        print(f"Error saving new entry to database: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def update_entry_in_db(entry_data):
    """Update existing entry in the new entries table"""
    conn = get_db_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()

        # Build UPDATE query
        set_clause = []
        values = []
        sr_no = None

        for key, value in entry_data.items():
            if key == COL_SR_NO:
                sr_no = value
            else:
                set_clause.append(f'"{key}" = %s')
                values.append(value)

        if not sr_no:
            return False

        values.append(sr_no)

        update_query = f'UPDATE "{new_entries_table_name}" SET {", ".join(set_clause)} WHERE "{COL_SR_NO}" = %s'

        cursor.execute(update_query, values)
        conn.commit()
        return True

    except Exception as e:
        print(f"Error updating entry in database: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_entry_from_db(sr_no):
    """Delete entry from the new entries table"""
    conn = get_db_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        delete_query = f'DELETE FROM "{new_entries_table_name}" WHERE "{COL_SR_NO}" = %s'

        cursor.execute(delete_query, (sr_no,))
        conn.commit()
        return True

    except Exception as e:
        print(f"Error deleting entry from database: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def authenticate_user(username, password, user_type):
    """Authenticate user from database"""
    conn = get_db_connection()
    if conn is None:
        return None

    try:
        cursor = conn.cursor()

        if user_type == "admin":
            table = admin_login_table
        else:
            table = user_login_table

        query = f'SELECT * FROM "{table}" WHERE "name" = %s AND "pass" = %s'
        cursor.execute(query, (username, password))
        user = cursor.fetchone()

        if user:
            # Convert to dictionary with column names
            columns = [desc[0] for desc in cursor.description]
            user_dict = dict(zip(columns, user))
            user_dict['role'] = user_type
            return user_dict
        return None

    except Exception as e:
        print(f"Error authenticating user: {e}")
        return None
    finally:
        conn.close()

def get_all_users():
    """Get all users for reference"""
    conn = get_db_connection()
    if conn is None:
        return []

    try:
        cursor = conn.cursor()

        # Get regular users
        cursor.execute(f'SELECT "name", "mail", "region" FROM "{user_login_table}"')
        users = cursor.fetchall()

        # Get admins
        cursor.execute(f'SELECT "name", "mail", "region" FROM "{admin_login_table}"')
        admins = cursor.fetchall()

        user_list = []

        # Add regular users
        for user in users:
            user_list.append({
                "username": user[0],
                "email": user[1],
                "region": user[2],
                "role": "user"
            })

        # Add admins
        for admin in admins:
            user_list.append({
                "username": admin[0],
                "email": admin[1],
                "region": admin[2],
                "role": "admin"
            })

        return user_list

    except Exception as e:
        print(f"Error getting users: {e}")
        return []
    finally:
        conn.close()

# ================== HELPER FUNCTIONS ==================
def normalize_topic(val):
    """Normalize topic string or numeric values for consistency"""
    if val is None:
        return None
    s = str(val).strip()
    try:
        # scientific notation -> plain
        if re.fullmatch(r'[+-]?\d+(?:\.\d+)?[eE][+-]?\d+', s):
            f = float(s)
            if f.is_integer():
                s = str(int(f))
            else:
                from decimal import Decimal
                s = format(Decimal(s), 'f').rstrip('0').rstrip('.') or '0'
    except Exception:
        pass
    if re.fullmatch(r'\d+\.0', s):
        return s[:-2]
    return s

def parse_payload_and_get_remarks(payload, cl_type=None, sensor_type=None):
    """
    Parse JSON payload and generate remarks based on Flow_Error and Cl_Error.
    """
    try:
        data = json.loads(payload)

        # Handle different sensor types
        if sensor_type == "pressure":
            if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                has_valid_data = any(float(item.get("value", 0)) > 0 for item in data["data"] if isinstance(item, dict))
                latest_timestamp = None
                for item in data["data"]:
                    if isinstance(item, dict) and "time" in item:
                        try:
                            ts = int(item["time"])
                            if latest_timestamp is None or ts > latest_timestamp:
                                latest_timestamp = ts
                        except (ValueError, TypeError):
                            pass

                if latest_timestamp:
                    dt = datetime.fromtimestamp(latest_timestamp)
                    now = datetime.now()
                    # Consider data from last 12 hours as valid for pressure sensors
                    time_diff = now - dt
                    if time_diff.total_seconds() <= 43200:  # 12 hours in seconds
                        return "YES ✅"
                    else:
                        return f"YES (Data from {dt.strftime('%Y-%m-%d %H:%M')})"
                elif has_valid_data:
                    return "YES ✅ "
                else:
                    return "NO "
            else:
                return "NO "
        else:
            # Handle flow and chlorine sensors - consider data from last 10 minutes as valid
            flow_error = str(data.get("Flow_Error", data.get("Flow_error", ""))).strip()
            cl_error = str(data.get("Cl_Error", data.get("Cl_error", ""))).strip()

            if flow_error == "":
                flow_error = None
            if cl_error == "":
                cl_error = None

            remarks = []

            # Special handling for 4-20 mA chlorine type
            if cl_type == "4-20 mA" and flow_error == "1" and cl_error == "1":
                remarks.append("YES✅")
            elif flow_error is not None and cl_error is not None:
                if flow_error == "1" and cl_error == "1":
                    remarks.append("NO")
                elif flow_error == "1" and cl_error == "0":
                    remarks.append("YES ✅")
                elif flow_error == "0" and cl_error == "1":
                    remarks.append("YES ✅")
                elif flow_error == "0" and cl_error == "0":
                    remarks.append("NO")
                else:
                    remarks.append(f"Flow_Error={flow_error}, Cl_Error={cl_error}")
            else:
                remarks.append("NO")

            # Check for communication/signal issues via CSQ
            csq = data.get("CSQ", "")
            try:
                csq_int = int(str(csq).strip()) if csq != "" else None
                if csq_int is not None and csq_int < 10:
                    remarks.append(f"Weak Signal (CSQ: {csq_int})")
            except Exception:
                pass

            return ", ".join(remarks) if remarks else "NO "
    except (json.JSONDecodeError, TypeError):
        return "NO "
    except Exception:
        return "NO "

def extract_value_from_payload(payload, key):
    """Extract specific value from JSON payload safely"""
    try:
        data = json.loads(payload)

        # Special handling for pressure sensor data array
        if key == "Pressure" and "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
            latest_value = None
            latest_timestamp = 0

            for item in data["data"]:
                if isinstance(item, dict) and "value" in item and "time" in item:
                    try:
                        ts = int(item["time"])
                        if ts > latest_timestamp:
                            latest_timestamp = ts
                            latest_value = item["value"]
                    except (ValueError, TypeError):
                        continue

            return latest_value if latest_value is not None else ""

        # For other sensors
        if key == "Flow":
            v = data.get("Flow", data.get("Volume_Flow", ""))
        elif key == "Total":
            v = data.get("Total", data.get("Positive_Totalizer", ""))
        elif key == "Cl":
            v = data.get("Cl", "")
        elif key == "CSQ":
            v = data.get("CSQ", "")
        elif key == "Pressure":
            v = data.get("Pressure", "")
        else:
            v = data.get(key, "")

        return "" if v is None else str(v)
    except (json.JSONDecodeError, TypeError):
        return ""
    except Exception:
        return "Error"

def count_pressure_packages(payload):
    """Count the number of pressure data packages in the payload"""
    try:
        data = json.loads(payload)
        if "data" in data and isinstance(data["data"], list):
            return len(data["data"])
        return 0
    except (json.JSONDecodeError, TypeError):
        return 0
    except Exception:
        return 0

def log_user_activity(username, action, details=""):
    """Log user activity for tracking"""
    activity = {
        "user": username,
        "action": action,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "details": details
    }
    user_activity_log.append(activity)
    # Keep only last 100 activities to prevent memory issues
    if len(user_activity_log) > 100:
        user_activity_log.pop(0)

def subscribe_to_new_topic(topic):
    """Dynamically subscribe to a new topic"""
    global mqtt_client, all_topics

    if not topic or not mqtt_client or not mqtt_client.is_connected():
        return False

    try:
        normalized_topic = normalize_topic(topic)
        if normalized_topic and normalized_topic not in all_topics:
            mqtt_client.subscribe(normalized_topic)
            if normalized_topic not in all_topics:
                all_topics.append(normalized_topic)
            print(f"✅ Successfully subscribed to new topic: {normalized_topic}")
            return True
    except Exception as e:
        print(f"❌ Error subscribing to new topic {topic}: {e}")

    return False

class LatestStore:
    """Thread-safe storage for latest MQTT payloads"""
    def __init__(self):
        self.lock = threading.Lock()
        self.latest = {}
        self.connection_time = datetime.now()
        # Store historical data for graphs
        self.pressure_history = {}  # {topic: [(timestamp, value), ...]}
        self.chlorine_history = {}  # {topic: [(timestamp, value), ...]}
        self.flow_history = {}      # {topic: [(timestamp, value), ...]}

    def update(self, topic, payload, when=None):
        if when is None:
            when = datetime.now()
        with self.lock:
            self.latest[topic] = {"payload": payload, "datetime": when}
           
            # Store historical data for graphs
            try:
                data = json.loads(payload)
               
                # Handle pressure data with array structure
                if "data" in data and isinstance(data["data"], list):
                    if topic not in self.pressure_history:
                        self.pressure_history[topic] = []
                   
                    for item in data["data"]:
                        if isinstance(item, dict) and "value" in item and "time" in item:
                            try:
                                timestamp = datetime.fromtimestamp(int(item["time"]))
                                value = float(item["value"])
                                # Add to history if not duplicate
                                if not any(abs((ts - timestamp).total_seconds()) < 60 for ts, _ in self.pressure_history[topic]):
                                    self.pressure_history[topic].append((timestamp, value))
                            except (ValueError, TypeError):
                                continue
                   
                    # Keep only last 24 hours of data
                    cutoff_time = when - timedelta(hours=24)
                    self.pressure_history[topic] = [(ts, val) for ts, val in self.pressure_history[topic] if ts > cutoff_time]
                    # Sort by timestamp
                    self.pressure_history[topic].sort(key=lambda x: x[0])
               
                # Handle chlorine data
                elif "Cl" in data:
                    if topic not in self.chlorine_history:
                        self.chlorine_history[topic] = []
                   
                    try:
                        cl_value = float(data.get("Cl", 0))
                        # Add to history if not duplicate (within 1 minute)
                        if not any(abs((ts - when).total_seconds()) < 60 for ts, _ in self.chlorine_history[topic]):
                            self.chlorine_history[topic].append((when, cl_value))
                       
                        # Keep only last 24 hours of data
                        cutoff_time = when - timedelta(hours=24)
                        self.chlorine_history[topic] = [(ts, val) for ts, val in self.chlorine_history[topic] if ts > cutoff_time]
                        # Sort by timestamp
                        self.chlorine_history[topic].sort(key=lambda x: x[0])
                    except (ValueError, TypeError):
                        pass
                       
                # Handle flow data
                elif "Flow" in data or "Volume_Flow" in data:
                    if topic not in self.flow_history:
                        self.flow_history[topic] = []
                   
                    try:
                        flow_value = float(data.get("Flow", data.get("Volume_Flow", 0)))
                        # Add to history if not duplicate (within 1 minute)
                        if not any(abs((ts - when).total_seconds()) < 60 for ts, _ in self.flow_history[topic]):
                            self.flow_history[topic].append((when, flow_value))
                       
                        # Keep only last 24 hours of data
                        cutoff_time = when - timedelta(hours=24)
                        self.flow_history[topic] = [(ts, val) for ts, val in self.flow_history[topic] if ts > cutoff_time]
                        # Sort by timestamp
                        self.flow_history[topic].sort(key=lambda x: x[0])
                    except (ValueError, TypeError):
                        pass
                       
            except (json.JSONDecodeError, TypeError):
                pass

    def snapshot(self):
        with self.lock:
            return deepcopy(self.latest)

    def get(self, topic):
        with self.lock:
            return deepcopy(self.latest.get(topic))

    def get_pressure_history(self, topic, hours=24):
        """Get pressure history for a topic for the last N hours"""
        with self.lock:
            if topic not in self.pressure_history:
                return []
           
            cutoff_time = datetime.now() - timedelta(hours=hours)
            return [(ts, val) for ts, val in self.pressure_history[topic] if ts > cutoff_time]

    def get_chlorine_history(self, topic, hours=24):
        """Get chlorine history for a topic for the last N hours"""
        with self.lock:
            if topic not in self.chlorine_history:
                return []
           
            cutoff_time = datetime.now() - timedelta(hours=hours)
            return [(ts, val) for ts, val in self.chlorine_history[topic] if ts > cutoff_time]

    def get_flow_history(self, topic, hours=24):
        """Get flow history for a topic for the last N hours"""
        with self.lock:
            if topic not in self.flow_history:
                return []
           
            cutoff_time = datetime.now() - timedelta(hours=hours)
            return [(ts, val) for ts, val in self.flow_history[topic] if ts > cutoff_time]

    def get_connection_duration(self):
        """Get how long we've been connected to MQTT"""
        return datetime.now() - self.connection_time

latest_store = LatestStore()

# ================== LOAD DATA FROM DATABASE ==================
def load_combined_data():
    """Load data from main table and combine with new entries"""
    try:
        # Load main data
        main_df = load_data_from_db(main_table_name)
        if main_df.empty:
            print("Warning: main_df is empty after loading from database.")
            main_df = pd.DataFrame()

        # Load new entries
        new_entries_df = load_data_from_db(new_entries_table_name)
        if not new_entries_df.empty:
            print(f"Loaded {len(new_entries_df)} new entries from {new_entries_table_name}")
            # Combine with main data
            combined_df = pd.concat([main_df, new_entries_df], ignore_index=True)
        else:
            combined_df = main_df

        # Ensure all required columns exist
        required_columns = [COL_FLOW, COL_CL, COL_PRESSURE, COL_TYPE_CL, COL_SCHEME,
                           COL_VILLAGE, COL_BLOCK, COL_RESERVOIR, COL_CIRCLE,
                           COL_DIVISION, COL_SUBDIVISION, COL_FLOW_STATUS,
                           COL_CL_STATUS, COL_PRESSURE_STATUS, COL_STUDY, "Region", COL_POPULATION]

        for col in required_columns:
            if col not in combined_df.columns:
                combined_df[col] = None

        # Normalize topic columns
        combined_df[COL_FLOW] = combined_df[COL_FLOW].apply(normalize_topic)
        combined_df[COL_CL] = combined_df[COL_CL].apply(normalize_topic)
        combined_df[COL_PRESSURE] = combined_df[COL_PRESSURE].apply(normalize_topic)

        return combined_df

    except Exception as e:
        print(f"Error loading combined data: {e}")
        return pd.DataFrame()

print("Loading data from database...")
base_df = load_combined_data()

# Debug: Check what columns we have
if not base_df.empty:
    print("Columns in base_df:", base_df.columns.tolist())
    print("Sample data:")
    print(base_df.head(2))
else:
    print("base_df is empty - checking database connection...")
    # Test database connection
    conn = get_db_connection()
    if conn:
        print("Database connection successful")
        conn.close()
    else:
        print("Database connection failed")

# CORRECTED: Filter out rows where ALL topic columns are blank/null - EXCLUDE NULL/BLANK PROPERLY
if not base_df.empty:
    base_df = base_df[
        (base_df[COL_FLOW].notna() & (base_df[COL_FLOW] != "") & (base_df[COL_FLOW] != "nan")) |
        (base_df[COL_CL].notna() & (base_df[COL_CL] != "") & (base_df[COL_CL] != "nan")) |
        (base_df[COL_PRESSURE].notna() & (base_df[COL_PRESSURE] != "") & (base_df[COL_PRESSURE] != "nan"))
    ]

# Topics (this should now include topics from new entries) - EXCLUDE NULL/BLANK PROPERLY
flow_topics = sorted({t for t in base_df[COL_FLOW].astype(str).unique()
                     if t and t != 'nan' and t != '' and t != 'None'}) if not base_df.empty else []
cl_topics = sorted({t for t in base_df[COL_CL].astype(str).unique()
                   if t and t != 'nan' and t != '' and t != 'None'}) if not base_df.empty else []
pressure_topics = sorted({t for t in base_df[COL_PRESSURE].astype(str).unique()
                        if t and t != 'nan' and t != '' and t != 'None'}) if not base_df.empty else []
all_topics = sorted(set(flow_topics + cl_topics + pressure_topics))

print(f"Flow topics: {len(flow_topics)}")
print(f"CL topics: {len(cl_topics)}")
print(f"Pressure topics: {len(pressure_topics)}")

# ================== MQTT ==================
mqtt_client = None
mqtt_thread = None
mqtt_stop_flag = threading.Event()

def on_connect(client, userdata, flags, rc):
    print("MQTT connected with result code", rc)
    # Update connection time
    latest_store.connection_time = datetime.now()

    for t in all_topics:
        try:
            client.subscribe(t)
            print("Subscribed to", t)
        except Exception as e:
            print("Subscribe error:", t, e)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8", errors="ignore")
    except Exception:
        payload = str(msg.payload)
    topic = normalize_topic(msg.topic)

    # Print received message for debugging
    print(f"Received message on {topic}: {payload[:100]}{'...' if len(payload) > 100 else ''}")

    latest_store.update(topic, payload)

def mqtt_worker():
    global mqtt_client
    mqtt_client = mqtt.Client(protocol=mqtt.MQTTv311)
    mqtt_client.username_pw_set(USERNAME, PASSWORD)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    while not mqtt_stop_flag.is_set():
        try:
            mqtt_client.connect(BROKER, PORT, keepalive=60)
            mqtt_client.loop_forever()
        except Exception as e:
            print("MQTT connection error:", e)
            time.sleep(5)

if all_topics:
    mqtt_thread = threading.Thread(target=mqtt_worker, daemon=True)
    mqtt_thread.start()
    print("MQTT thread started")
else:
    print("No topics to subscribe to. MQTT thread not started.")

# ================== DASH APP ==================
app = Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])

# Enhanced CSS styles with clean design
app.index_string = '''


<!DOCTYPE html>
<html lang="en">
    <head>
        {%metas%}
        <title>🌊 SWSM IoT Dashboard</title>
        {%favicon%}
        {%css%}
        <style>
            /* === Root Variables for Color System === */
            :root {
                --primary: #6366f1;
                --secondary: #8b5cf6;
                --accent: #00c6ff;
                --bg-main: #f8fafc;
                --bg-card: rgba(255, 255, 255, 0.85);
                --text-dark: #1e293b;
                --text-light: #f8f9fa;
                --border-light: rgba(0, 0, 0, 0.05);
                --radius: 14px;
                --shadow-soft: 0 10px 30px rgba(0,0,0,0.06);
                --shadow-hover: 0 12px 40px rgba(0,0,0,0.1);
            }

            /* === Global Layout === */
            body {
                font-family: 'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #f0f4ff 0%, #f8fafc 100%);
                color: var(--text-dark);
                margin: 0;
                padding: 0;
                overflow-x: hidden;
            }

            /* === Sidebar === */
            .sidebar {
                background: rgba(255, 255, 255, 0.85);
                backdrop-filter: blur(20px);
                border-right: 1px solid var(--border-light);
                box-shadow: var(--shadow-soft);
                transition: all 0.3s ease;
            }

            .sidebar:hover {
                box-shadow: var(--shadow-hover);
            }

            /* === Card Components === */
            .enhanced-card {
                background: var(--bg-card);
                border: 1px solid rgba(255, 255, 255, 0.4);
                border-radius: var(--radius);
                box-shadow: var(--shadow-soft);
                backdrop-filter: blur(20px);
                padding: 20px;
                transition: transform 0.25s ease, box-shadow 0.25s ease;
            }

            .enhanced-card:hover {
                transform: translateY(-4px);
                box-shadow: var(--shadow-hover);
            }

            /* === Buttons (Elegant Gradient) === */
            .enhanced-btn {
                display: inline-block;
                background: linear-gradient(90deg, var(--primary), var(--secondary));
                color: white;
                font-weight: 600;
                border: none;
                border-radius: var(--radius);
                padding: 12px 22px;
                cursor: pointer;
                box-shadow: 0 6px 18px rgba(99,102,241,0.2);
                transition: all 0.3s ease;
            }

            .enhanced-btn:hover {
                box-shadow: 0 8px 24px rgba(99,102,241,0.3);
                transform: translateY(-2px);
            }

            /* === Inputs and Dropdowns === */
            .enhanced-input,
            .Select-control {
                background: rgba(255,255,255,0.9) !important;
                border: 1.5px solid rgba(0,0,0,0.08) !important;
                border-radius: var(--radius) !important;
                padding: 10px 14px;
                transition: all 0.3s ease !important;
                font-size: 0.95rem;
                color: var(--text-dark);
            }

            .enhanced-input:focus,
            .Select-control:hover {
                border-color: var(--primary) !important;
                box-shadow: 0 0 10px rgba(99,102,241,0.15) !important;
                outline: none;
            }

            /* === Table Styling (Minimal + Elevated) === */
            .enhanced-table {
                border-radius: var(--radius);
                border-collapse: collapse;
                box-shadow: var(--shadow-soft);
                background: var(--bg-card);
                backdrop-filter: blur(10px);
                overflow: hidden;
            }

            .enhanced-table th,
            .enhanced-table td {
                padding: 12px 16px;
                border-bottom: 1px solid rgba(0,0,0,0.05);
            }

            .enhanced-table th {
                background: rgba(99,102,241,0.08);
                color: var(--primary);
                font-weight: 600;
                text-align: left;
            }

            /* === Navigation Links === */
            .enhanced-navlink {
                display: block;
                color: var(--text-dark) !important;
                font-weight: 500;
                padding: 10px 16px;
                border-radius: var(--radius);
                transition: all 0.3s ease;
            }

            .enhanced-navlink:hover {
                background: rgba(99,102,241,0.1);
                color: var(--primary) !important;
                transform: translateX(4px);
            }

            /* === Badges === */
            .enhanced-badge {
                display: inline-block;
                background: linear-gradient(90deg, var(--primary), var(--secondary));
                color: white;
                font-size: 0.85rem;
                font-weight: 600;
                border-radius: 999px;
                padding: 6px 14px;
                box-shadow: 0 4px 12px rgba(99,102,241,0.25);
            }

            /* === Spinner === */
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }

            .loading-spinner {
                width: 40px;
                height: 40px;
                border: 4px solid rgba(0,0,0,0.05);
                border-top: 4px solid var(--primary);
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 30px auto;
            }

            /* === Card Header === */
            .enhanced-card-header {
                background: linear-gradient(90deg, var(--primary), var(--secondary));
                color: var(--text-light);
                font-weight: 700;
                font-size: 1.05rem;
                border-radius: var(--radius) var(--radius) 0 0 !important;
                padding: 18px;
                text-align: center;
                letter-spacing: 0.5px;
                box-shadow: inset 0 -1px 6px rgba(255,255,255,0.2);
            }

            /* === Scrollbar (Soft & Minimal) === */
            ::-webkit-scrollbar {
                width: 8px;
            }

            ::-webkit-scrollbar-track {
                background: rgba(0,0,0,0.05);
                border-radius: 8px;
            }

            ::-webkit-scrollbar-thumb {
                background: linear-gradient(45deg, var(--primary), var(--secondary));
                border-radius: 8px;
            }

            ::-webkit-scrollbar-thumb:hover {
                background: linear-gradient(45deg, var(--secondary), var(--primary));
            }

            /* === Light Motion Accent (subtle background animation) === */
            body::after {
                content: "";
                position: fixed;
                inset: 0;
                background: radial-gradient(circle at 20% 20%, rgba(99,102,241,0.06), transparent 70%);
                animation: floatlight 15s ease-in-out infinite alternate;
                z-index: -1;
            }

            @keyframes floatlight {
                from { transform: translate(0,0); }
                to { transform: translate(20px, -30px); }
            }

            /* === Full Screen Modal === */
            .fullscreen-modal {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: rgba(0, 0, 0, 0.9);
                z-index: 9999;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }

            .fullscreen-content {
                background: white;
                border-radius: 15px;
                padding: 20px;
                width: 95%;
                height: 95%;
                position: relative;
                box-shadow: 0 0 50px rgba(0,0,0,0.5);
            }

            .close-fullscreen {
                position: absolute;
                top: 15px;
                right: 15px;
                background: #ff416c;
                color: white;
                border: none;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                font-size: 20px;
                cursor: pointer;
                z-index: 10000;
                display: flex;
                justify-content: center;
                align-items: center;
                box-shadow: 0 4px 15px rgba(255,65,108,0.3);
            }

            .close-fullscreen:hover {
                background: #ff1e53;
                transform: scale(1.1);
            }

            .graph-container {
                position: relative;
                cursor: pointer;
                transition: all 0.3s ease;
            }

            .graph-container:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 35px rgba(0,0,0,0.15);
            }

            .expand-icon {
                position: absolute;
                top: 10px;
                right: 10px;
                background: rgba(255,255,255,0.9);
                border-radius: 5px;
                padding: 5px;
                font-size: 16px;
                color: #667eea;
                z-index: 100;
                opacity: 0;
                transition: opacity 0.3s ease;
            }

            .graph-container:hover .expand-icon {
                opacity: 1;
            }
        </style>
    </head>

    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''



# Load and encode logo
def load_logo(logo_path):
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            encoded_image = base64.b64encode(f.read()).decode('ascii')
        return f"data:image/avif;base64,{encoded_image}"
    return None

logo_data = load_logo(LOGO_PATH)

def make_columns(cols):
    return [{"name": c, "id": c} for c in cols]

# ================== CLEAN SIDEBAR ==================
sidebar = html.Div([
    html.Div([
        html.Div([
            html.H3("", style={"textAlign": "center", "color": "white", "marginBottom": "10px", "fontWeight": "bold", "fontSize": "28px"}),
            html.Img(src=logo_data, style={"width": "100%", "maxWidth": "180px", "margin": "0 auto 20px", "display": "block", "backgroundColor": "white", "padding": "15px", "borderRadius": "15px", "boxShadow": "0 6px 20px rgba(0,0,0,0.2)"}) if logo_data else None,
            html.P("IoT Monitoring Dashboard", style={"textAlign": "center", "color": "#ecf0f1", "fontSize": "14px", "marginBottom": "30px", "fontWeight": "500"})
        ]),

        html.Hr(style={"borderColor": "rgba(255,255,255,0.3)", "margin": "20px 0"}),

        html.H5("", style={"color": "white", "marginBottom": "20px", "fontWeight": "bold", "textAlign": "center", "fontSize": "18px"}),

        dbc.Nav([
            dbc.NavLink("📊 Dashboard", href="/", active="exact", className="enhanced-navlink", style={"color": "white", "padding": "15px", "borderRadius": "10px", "marginBottom": "10px", "fontWeight": "bold", "background": "rgba(255,255,255,0.1)", "transition": "all 0.3s ease", "fontSize": "15px"}),
            dbc.NavLink("📈 Analysis", href="/analysis", active="exact", className="enhanced-navlink", style={"color": "white", "padding": "15px", "borderRadius": "10px", "marginBottom": "10px", "fontWeight": "bold", "background": "rgba(255,255,255,0.1)", "transition": "all 0.3s ease", "fontSize": "15px"}),
            dbc.NavLink("➕ Add New Entry", href="/add-entry", active="exact", className="enhanced-navlink", style={"color": "white", "padding": "15px", "borderRadius": "10px", "marginBottom": "10px", "fontWeight": "bold", "background": "rgba(255,255,255,0.1)", "transition": "all 0.3s ease", "fontSize": "15px"}),
            dbc.NavLink("📊 Reservoir Analytics", href="/reservoir-analytics", active="exact", className="enhanced-navlink", style={"color": "white", "padding": "15px", "borderRadius": "10px", "marginBottom": "10px", "fontWeight": "bold", "background": "rgba(255,255,255,0.1)", "transition": "all 0.3s ease", "fontSize": "15px"}),
        ], vertical=True, pills=True),

        html.Hr(style={"borderColor": "rgba(255,255,255,0.3)", "margin": "20px 0"}),

        html.H5("", style={"color": "white", "marginBottom": "20px", "fontWeight": "bold", "textAlign": "center", "fontSize": "18px"}),

        dbc.Label("🌍 Region", style={"color": "white", "fontWeight": "bold", "marginBottom": "8px", "fontSize": "14px"}),
        dcc.Dropdown(
            id="region-dropdown",
            options=[{"label": s, "value": s} for s in sorted(base_df["Region"].unique())] if not base_df.empty else [],
            placeholder="Select Region",
            multi=False,
            className="enhanced-dropdown",
            style={"marginBottom": "20px", "borderRadius": "10px"}
        ),

        dbc.Label("🏗️ Scheme", style={"color": "white", "fontWeight": "bold", "marginBottom": "8px", "fontSize": "14px"}),
        dcc.Dropdown(
            id="scheme-dropdown",
            placeholder="Select Scheme",
            multi=False,
            className="enhanced-dropdown",
            style={"marginBottom": "20px", "borderRadius": "10px"}
        ),

        dbc.Label("🏘️ Village", style={"color": "white", "fontWeight": "bold", "marginBottom": "8px", "fontSize": "14px"}),
        dcc.Dropdown(
            id="village-dropdown",
            placeholder="Select Village",
            multi=False,
            className="enhanced-dropdown",
            style={"marginBottom": "20px", "borderRadius": "10px"}
        ),

        dbc.Label("💧 Reservoir", style={"color": "white", "fontWeight": "bold", "marginBottom": "8px", "fontSize": "14px"}),
        dcc.Dropdown(
            id="reservoir-dropdown",
            placeholder="Select Reservoir",
            multi=False,
            className="enhanced-dropdown",
            style={"marginBottom": "20px", "borderRadius": "10px"}
        ),

        html.Hr(style={"borderColor": "rgba(255,255,255,0.3)", "margin": "25px 0"}),

        html.H6("📡 Connection Status", style={"color": "white", "marginBottom": "8px", "fontWeight": "bold", "fontSize": "16px"}),
        dbc.Badge("MQTT Connected", color="success", id="mqtt-status", className="pulse enhanced-badge", style={"marginBottom": "20px", "fontSize": "14px", "padding": "10px", "borderRadius": "20px", "width": "100%", "textAlign": "center"}),

        html.H6("⏱️ Connection Duration", style={"color": "white", "marginBottom": "8px", "fontWeight": "bold", "fontSize": "16px"}),
        html.P(id="connection-duration", style={"color": "white", "fontSize": "14px", "backgroundColor": "rgba(255,255,255,0.1)", "padding": "10px", "borderRadius": "10px", "textAlign": "center", "marginBottom": "20px"}),

        html.H6("🕒 Last Update", style={"color": "white", "marginBottom": "8px", "fontWeight": "bold", "fontSize": "16px"}),
        html.P(id="last-update", style={"color": "white", "fontSize": "14px", "backgroundColor": "rgba(255,255,255,0.1)", "padding": "10px", "borderRadius": "10px", "textAlign": "center", "marginBottom": "20px"}),

        html.Hr(style={"borderColor": "rgba(255,255,255,0.3)", "margin": "25px 0"}),

        html.H6("📊 Pressure Sensor Info", style={"color": "white", "marginBottom": "15px", "fontWeight": "bold", "fontSize": "16px"}),
        html.P("", style={"color": "white", "fontSize": "14px", "marginBottom": "8px", "textAlign": "center"}),
        html.P(id="pressure-next-update", style={"color": "white", "fontSize": "14px", "backgroundColor": "rgba(255,255,255,0.1)", "padding": "10px", "borderRadius": "10px", "textAlign": "center", "marginBottom": "20px"}),

        html.Hr(style={"borderColor": "rgba(255,255,255,0.3)", "margin": "25px 0"}),

        html.H6("📥 Export Data", style={"color": "white", "marginBottom": "15px", "fontWeight": "bold", "fontSize": "16px"}),
        dbc.Button("📥 Download Excel", id="btn-download-excel", color="primary", className="enhanced-btn", style={"width": "100%", "marginBottom": "15px", "fontWeight": "bold", "padding": "12px", "fontSize": "14px"}),
        dcc.Download(id="download-excel"),

        html.Hr(style={"margin": "25px 0", "borderColor": "rgba(255,255,255,0.3)"}),

        html.H6("👤 User Info", style={"color": "white", "marginBottom": "8px", "fontWeight": "bold", "fontSize": "16px"}),
        html.P(id="user-info", style={"color": "white", "fontSize": "14px", "marginBottom": "15px", "backgroundColor": "rgba(255,255,255,0.1)", "padding": "10px", "borderRadius": "10px", "textAlign": "center"}),

        html.Div([
            dbc.Button("🚪 Logout", id="btn-logout", color="warning", className="enhanced-btn",
                      style={"width": "100%", "fontWeight": "bold", "padding": "12px", "fontSize": "14px"}),
        ], style={"marginTop": "10px", "marginBottom": "20px"}),
    ], style={"padding": "25px"})
], className="sidebar", style={
    "width": "320px",
    "position": "fixed",
    "height": "100vh",
    "overflowY": "auto",
    "background": "linear-gradient(180deg, rgba(44, 62, 80, 0.95) 0%, rgba(52, 73, 94, 0.95) 50%, rgba(44, 62, 80, 0.95) 100%)",
    "backdropFilter": "blur(10px)",
    "boxShadow": "4px 0 20px rgba(0,0,0,0.3)",
    "borderRight": "1px solid rgba(255,255,255,0.1)",
    "zIndex": "1000"
})

# ================== FULL SCREEN MODAL COMPONENT ==================
fullscreen_modal = html.Div([
    html.Div([
        html.Button("✕", id="close-fullscreen", className="close-fullscreen"),
        html.Div(id="fullscreen-graph-content", style={"width": "100%", "height": "100%"})
    ], className="fullscreen-content")
], id="fullscreen-modal", className="fullscreen-modal", style={"display": "none"})

# ================== CLEAN LOGIN PAGE ==================
login_page = html.Div([
    html.Div([
        html.H2("🔐 Login Required", style={
            "color": "white",
            "margin": 0,
            "padding": "25px",
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "borderRadius": "15px",
            "fontWeight": "bold",
            "textAlign": "center",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.2)",
            "marginBottom": "30px"
        }),
    ]),

    dbc.Card([
        dbc.CardHeader("🚀 Welcome to SWSM IoT Dashboard", style={
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "color": "white",
            "fontWeight": "bold",
            "fontSize": "20px",
            "textAlign": "center",
            "padding": "25px",
            "borderRadius": "15px 15px 0 0"
        }),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("👤 Username *", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dbc.Input(
                        id="login-username",
                        type="text",
                        placeholder="Enter your username",
                        className="enhanced-input",
                        style={"marginBottom": "25px", "borderRadius": "12px", "padding": "12px", "border": "2px solid #e9ecef", "transition": "all 0.3s ease", "fontSize": "16px"}
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("🔒 Password *", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dbc.Input(
                        id="login-password",
                        type="password",
                        placeholder="Enter your password",
                        className="enhanced-input",
                        style={"marginBottom": "25px", "borderRadius": "12px", "padding": "12px", "border": "2px solid #e9ecef", "transition": "all 0.3s ease", "fontSize": "16px"}
                    )
                ], md=6),
            ]),

            html.Div([
                html.H6("📝 Login Instructions:", style={"fontWeight": "bold", "marginBottom": "15px", "color": "#2c3e50", "fontSize": "18px", "textAlign": "center"}),
                dbc.Row([
                    dbc.Col([
                        html.P("👤 Enter your username manually", style={"fontSize": "14px", "marginBottom": "8px", "color": "#666", "textAlign": "center"}),
                        html.P("🔒 Enter your password", style={"fontSize": "14px", "color": "#666", "textAlign": "center"})
                    ], md=6),
                    dbc.Col([
                        html.P("Admins have access to additional features", style={"fontSize": "14px", "marginBottom": "8px", "color": "#666", "textAlign": "center"}),
                        html.P("Regular users can only add entries for their assigned region", style={"fontSize": "14px", "color": "#666", "textAlign": "center"})
                    ], md=6),
                ])
            ], style={
                "background": "linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)",
                "padding": "20px",
                "borderRadius": "12px",
                "marginBottom": "25px",
                "border": "1px solid rgba(0,0,0,0.1)",
                "boxShadow": "0 4px 15px rgba(0,0,0,0.1)"
            }),

            html.Hr(style={"margin": "25px 0", "borderColor": "rgba(0,0,0,0.1)"}),

            dbc.Button("Login to Dashboard", id="btn-login", color="success", className="enhanced-btn", style={"marginBottom": "20px", "width": "100%", "fontWeight": "bold", "padding": "15px", "borderRadius": "12px", "fontSize": "16px"}),
            html.Div(id="login-status", style={"marginTop": "20px"})
        ], style={"padding": "35px"})
    ], className="enhanced-card shadow-lg", style={
        "borderRadius": "20px",
        "border": "none",
        "transition": "transform 0.3s ease",
        "maxWidth": "700px",
        "margin": "0 auto",
        "boxShadow": "0 15px 35px rgba(0,0,0,0.1)"
    })
], className="main-content", style={"marginLeft": "320px", "padding": "50px", "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)", "minHeight": "100vh", "display": "flex", "flexDirection": "column", "justifyContent": "center", "alignItems": "center"})

# ================== CLEAN ANALYSIS PAGE ==================
analysis_page = html.Div([
    html.Div([
        html.H2("📈 Sensor Data Analytics Dashboard", style={
            "color": "white",
            "margin": 0,
            "padding": "25px",
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "borderRadius": "20px",
            "fontWeight": "bold",
            "textAlign": "center",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.2)",
            "marginBottom": "30px"
        }),
    ]),

    # Clean Filters Section
    dbc.Card([
        dbc.CardHeader("🔧 Advanced Analytics Filters", style={
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "color": "white",
            "fontWeight": "bold",
            "fontSize": "20px",
            "textAlign": "center",
            "padding": "20px",
            "borderRadius": "15px 15px 0 0"
        }),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("🌍 Region", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="analysis-region",
                        options=[{"label": "All Regions", "value": "All"}] + [{"label": s, "value": s} for s in sorted(base_df["Region"].unique())] if not base_df.empty else [],
                        value="All",
                        placeholder="Select Region",
                        multi=False,
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("📡 Sensor Type", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="analysis-sensor-type",
                        options=[
                            {"label": "All Sensors", "value": "all"},
                            {"label": "🌊 Flow Meter", "value": "flow"},
                            {"label": "🧪 Chlorine Sensor", "value": "cl"},
                            {"label": "📊 Pressure Sensor", "value": "pressure"}
                        ],
                        value="all",
                        placeholder="Select Sensor Type",
                        multi=False,
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=6),
            ]),
        ], style={"padding": "25px"})
    ], className="enhanced-card shadow", style={
        "borderRadius": "20px",
        "border": "none",
        "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
        "marginBottom": "30px"
    }),

    # Clean KPI Cards Section - FIRST ROW
    dbc.Row([
        # 1️⃣ Total Request Received
        dbc.Col(dbc.Card([
            dbc.CardHeader("📊 Total Requests", style={
                "background": "linear-gradient(45deg, #667eea, #764ba2)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.H2(id="analysis-total-count", className="pulse", style={"color": "#2c3e50", "fontWeight": "bold", "textAlign": "center", "marginBottom": "10px", "fontSize": "2.5rem"}),
                html.P("All sensor requests processed", style={"color": "#666", "textAlign": "center", "marginBottom": "0", "fontSize": "14px", "fontWeight": "500"})
            ], style={"padding": "20px"})
        ], className="enhanced-card analysis-card", id="analysis-total-card", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
            "cursor": "pointer"
        }), md=2),

        # 2️⃣ Integrated
        dbc.Col(dbc.Card([
            dbc.CardHeader("✅ Integrated", style={
                "background": "linear-gradient(45deg, #56ab2f, #a8e6cf)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.H2(id="analysis-integrated-count", className="pulse", style={"color": "#2c3e50", "fontWeight": "bold", "textAlign": "center", "marginBottom": "10px", "fontSize": "2.5rem"}),
                html.P("Successfully integrated systems", style={"color": "#666", "textAlign": "center", "marginBottom": "0", "fontSize": "14px", "fontWeight": "500"})
            ], style={"padding": "20px"})
        ], className="enhanced-card analysis-card", id="analysis-integrated-card", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
            "cursor": "pointer"
        }), md=2),

        # 3️⃣ Communicating
        dbc.Col(dbc.Card([
            dbc.CardHeader("📡 Communicating", style={
                "background": "linear-gradient(45deg, #4facfe, #00f2fe)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.H2(id="analysis-communicating-count", className="pulse", style={"color": "#2c3e50", "fontWeight": "bold", "textAlign": "center", "marginBottom": "10px", "fontSize": "2.5rem"}),
                html.P("Active communication channels", style={"color": "#666", "textAlign": "center", "marginBottom": "0", "fontSize": "14px", "fontWeight": "500"})
            ], style={"padding": "20px"})
        ], className="enhanced-card analysis-card", id="analysis-communicating-card", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
            "cursor": "pointer"
        }), md=2),

        # 4️⃣ Not Communicating
        dbc.Col(dbc.Card([
            dbc.CardHeader("❌ Not Communicating", style={
                "background": "linear-gradient(45deg, #ff416c, #ff4b2b)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.H2(id="analysis-not-communicating-count", className="pulse", style={"color": "#2c3e50", "fontWeight": "bold", "textAlign": "center", "marginBottom": "10px", "fontSize": "2.5rem"}),
                html.P("Communication issues detected", style={"color": "#666", "textAlign": "center", "marginBottom": "0", "fontSize": "14px", "fontWeight": "500"})
            ], style={"padding": "20px"})
        ], className="enhanced-card analysis-card", id="analysis-not-communicating-card", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
            "cursor": "pointer"
        }), md=2),

        # 5️⃣ Returned to SI
        dbc.Col(dbc.Card([
            dbc.CardHeader("🔄 Returned to SI", style={
                "background": "linear-gradient(45deg, #f7971e, #ffd200)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.H2(id="analysis-returned-count", className="pulse", style={"color": "#2c3e50", "fontWeight": "bold", "textAlign": "center", "marginBottom": "10px", "fontSize": "2.5rem"}),
                html.P("Returned with comments", style={"color": "#666", "textAlign": "center", "marginBottom": "0", "fontSize": "14px", "fontWeight": "500"})
            ], style={"padding": "20px"})
        ], className="enhanced-card analysis-card", id="analysis-returned-card", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
            "cursor": "pointer"
        }), md=2),

        # 6️⃣ In Progress
        dbc.Col(dbc.Card([
            dbc.CardHeader("⏳ In Progress", style={
                "background": "linear-gradient(45deg, #9c27b0, #e91e63)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.H2(id="analysis-inprogress-count", className="pulse", style={"color": "#2c3e50", "fontWeight": "bold", "textAlign": "center", "marginBottom": "10px", "fontSize": "2.5rem"}),
                html.P("Work in progress", style={"color": "#666", "textAlign": "center", "marginBottom": "0", "fontSize": "14px", "fontWeight": "500"})
            ], style={"padding": "20px"})
        ], className="enhanced-card analysis-card", id="analysis-inprogress-card", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
            "cursor": "pointer"
        }), md=2),
    ], className="mb-4"),

    # SECOND ROW FOR ADDITIONAL CARDS
    dbc.Row([
        # 7️⃣ Integrated but Not Communicating - NEW CARD
        dbc.Col(dbc.Card([
            dbc.CardHeader("⚠️ Integrated but Not Communicating", style={
                "background": "linear-gradient(45deg, #ff6f00, #ffa040)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.H2(id="analysis-integrated-not-comm-count", className="pulse", style={"color": "#2c3e50", "fontWeight": "bold", "textAlign": "center", "marginBottom": "10px", "fontSize": "2.5rem"}),
                html.P("Integrated but offline systems", style={"color": "#666", "textAlign": "center", "marginBottom": "0", "fontSize": "14px", "fontWeight": "500"})
            ], style={"padding": "20px"})
        ], className="enhanced-card analysis-card", id="analysis-integrated-not-comm-card", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
            "cursor": "pointer"
        }), md=3),

        # You can add more cards here in the future
        dbc.Col(width=9),  # Empty column for spacing
    ], className="mb-4"),

    # Clean Data Table Section
    dbc.Card([
        dbc.CardHeader("📋 Detailed Analytics Data", style={
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "color": "white",
            "fontWeight": "bold",
            "fontSize": "20px",
            "textAlign": "center",
            "padding": "20px",
            "borderRadius": "15px 15px 0 0"
        }),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("🔎 Search Analytics:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dbc.Input(
                        id="analysis-search",
                        type="text",
                        placeholder="Search across all columns...",
                        className="enhanced-input",
                        style={"marginBottom": "20px", "borderRadius": "12px", "padding": "12px", "border": "2px solid #e9ecef", "fontSize": "16px"}
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("📄 Rows per page:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="analysis-page-size",
                        options=[
                            {"label": "10", "value": 10},
                            {"label": "25", "value": 25},
                            {"label": "50", "value": 50},
                            {"label": "100", "value": 100}
                        ],
                        value=25,
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=3),
                dbc.Col([
                    dbc.Label("🎯 Active Filter:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    html.Div(id="analysis-active-filter", style={
                        "background": "linear-gradient(135deg, #667eea, #764ba2)",
                        "padding": "15px",
                        "borderRadius": "12px",
                        "fontWeight": "bold",
                        "color": "white",
                        "textAlign": "center",
                        "boxShadow": "0 4px 15px rgba(0,0,0,0.1)",
                        "fontSize": "14px"
                    })
                ], md=3),
            ]),
            dash_table.DataTable(
                id="analysis-table",
                page_action="native",
                page_current=0,
                page_size=25,
                style_table={
                    "overflowX": "auto",
                    "borderRadius": "12px",
                    "overflow": "hidden",
                    "boxShadow": "0 6px 20px rgba(0,0,0,0.1)",
                    "border": "1px solid rgba(255,255,255,0.2)",
                    "marginTop": "20px"
                },
                style_cell={
                    'textAlign': 'center',
                    'fontSize': 14,
                    'font-family': 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
                    'padding': '12px',
                    'border': '1px solid rgba(0,0,0,0.1)',
                    'minWidth': '120px',
                    'width': '160px',
                    'maxWidth': '200px',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                    'backgroundColor': 'rgba(255,255,255,0.95)'
                },
                style_header={
                    'backgroundColor': '#667eea',
                    'color': 'white',
                    'fontWeight': 'bold',
                    'border': '1px solid #667eea',
                    'textAlign': 'center',
                    'fontSize': '15px',
                    'padding': '15px'
                },
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgba(248,249,250,0.9)'},
                    {'if': {'row_index': 'even'}, 'backgroundColor': 'rgba(255,255,255,0.95)'},
                    {'if': {'state': 'active'}, 'backgroundColor': 'rgba(102, 126, 234, 0.3)', 'border': '1px solid rgb(102, 126, 234)'},
                    # Status-based coloring
                    {
                        'if': {
                            'filter_query': '{Communication Status} contains "YES"',
                        },
                        'backgroundColor': 'rgba(86, 171, 47, 0.25)',
                        'color': '#155724',
                        'fontWeight': 'bold'
                    },
                    {
                        'if': {
                            'filter_query': '{Communication Status} contains "NO"',
                        },
                        'backgroundColor': 'rgba(255, 65, 108, 0.25)',
                        'color': '#721c24',
                        'fontWeight': 'bold'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "In Progress"',
                        },
                        'backgroundColor': 'rgba(255, 193, 7, 0.25)',
                        'color': '#856404',
                        'fontWeight': 'bold'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "Returned to SI with comments"',
                        },
                        'backgroundColor': 'rgba(108, 117, 125, 0.25)',
                        'color': '#383d41',
                        'fontWeight': 'bold'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "Integrated"',
                        },
                        'backgroundColor': 'rgba(23, 162, 184, 0.25)',
                        'color': '#0c5460',
                        'fontWeight': 'bold'
                    }
                ],
                filter_action="native",
                sort_action="native",
                sort_mode="multi",
                export_format="xlsx"
            )
        ], style={"padding": "30px"})
    ], className="enhanced-card shadow", style={
        "borderRadius": "20px",
        "border": "none",
        "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
    }),

    # Store for filtered data and active filter
    dcc.Store(id="analysis-filter-store", data={"active_filter": "All"}),
], className="main-content", style={"marginLeft": "320px", "padding": "35px", "background": "linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)", "minHeight": "100vh"})

# ================== CLEAN ADD ENTRY PAGE ==================
add_entry_page = html.Div([
    html.Div([
        html.H2("➕ Add New Sensor Entry", style={
            "color": "white",
            "margin": 0,
            "padding": "25px",
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "borderRadius": "20px",
            "fontWeight": "bold",
            "textAlign": "center",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.2)"
        }),
        html.Div(id="user-welcome", style={
            "color": "white",
            "textAlign": "right",
            "marginTop": "-40px",
            "marginRight": "30px",
            "fontSize": "16px",
            "fontWeight": "bold"
        }),
    ], style={"marginBottom": "30px", "position": "relative"}),

    # Clean Entry Form Card
    dbc.Card([
        dbc.CardHeader("📋 New Sensor Entry Details", style={
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "color": "white",
            "fontWeight": "bold",
            "fontSize": "20px",
            "textAlign": "center",
            "padding": "20px",
            "borderRadius": "15px 15px 0 0"
        }),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("🌍 Region *", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="new-region",
                        options=[],
                        placeholder="Select Region",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"},
                        disabled=False
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("🔵 Circle *", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="new-circle",
                        options=[],
                        placeholder="Select Circle",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=6),
            ]),

            dbc.Row([
                dbc.Col([
                    dbc.Label("🏢 Division *", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="new-division",
                        options=[],
                        placeholder="Select Division",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("🏛️ Sub Division *", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="new-subdivision",
                        options=[],
                        placeholder="Select Sub Division",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=6),
            ]),

            dbc.Row([
                dbc.Col([
                    dbc.Label("📦 Block *", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="new-block",
                        options=[],
                        placeholder="Select Block",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("🏗️ Scheme *", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="new-scheme",
                        options=[],
                        placeholder="Select Scheme",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=6),
            ]),

            dbc.Row([
                dbc.Col([
                    dbc.Label("🏘️ Village *", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="new-village",
                        options=[],
                        placeholder="Select Village",
                        className="enhanced-dropdown",
                        style={"marginBottom": "12px", "borderRadius": "12px"}
                    ),
                    dbc.Input(
                        id="new-village-input",
                        type="text",
                        placeholder="Or enter new village name",
                        className="enhanced-input",
                        style={"marginBottom": "20px", "display": "none", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("💧 Reservoir *", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="new-reservoir",
                        options=[],
                        placeholder="Select Reservoir",
                        className="enhanced-dropdown",
                        style={"marginBottom": "12px", "borderRadius": "12px"}
                    ),
                    dbc.Input(
                        id="new-reservoir-input",
                        type="text",
                        placeholder="Or enter new reservoir name",
                        className="enhanced-input",
                        style={"marginBottom": "20px", "display": "none", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                    )
                ], md=6),
            ]),

            html.Hr(style={"margin": "25px 0", "borderColor": "rgba(0,0,0,0.1)"}),

            # Clean Sensor Selection Section
            dbc.Row([
                dbc.Col([
                    dbc.Label("📡 Sensor Selection *", style={"fontWeight": "bold", "fontSize": "18px", "marginBottom": "15px", "color": "#2c3e50", "textAlign": "center"}),
                    dcc.Dropdown(
                        id="sensor-selection",
                        options=[
                            {"label": "🌊 Flow Meter", "value": "flow"},
                            {"label": "🧪 Chlorine Sensor", "value": "cl"},
                            {"label": "📊 Pressure Sensor", "value": "pressure"}
                        ],
                        placeholder="Select Sensor Type",
                        multi=True,
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=12),
            ]),

            # Clean Sensor Input Fields
            html.Div(id="sensor-input-fields", children=[
                dbc.Row([
                    dbc.Col([
                        dbc.Label("🌊 Flow Meter Topic", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dbc.Input(
                            id="new-flow-topic",
                            type="text",
                            placeholder="Enter Flow Meter Topic",
                            className="enhanced-input",
                            style={"marginBottom": "20px", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                        ),
                        html.Div(id="flow-topic-status", style={"fontSize": "14px", "marginBottom": "20px", "padding": "12px", "borderRadius": "10px", "fontWeight": "bold", "textAlign": "center"})
                    ], md=4, id="flow-topic-col", style={"display": "none"}),
                    dbc.Col([
                        dbc.Label("🧪 Chlorine Topic", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dbc.Input(
                            id="new-cl-topic",
                            type="text",
                            placeholder="Enter Chlorine Topic",
                            className="enhanced-input",
                            style={"marginBottom": "20px", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                        ),
                        html.Div(id="cl-topic-status", style={"fontSize": "14px", "marginBottom": "20px", "padding": "12px", "borderRadius": "10px", "fontWeight": "bold", "textAlign": "center"})
                    ], md=4, id="cl-topic-col", style={"display": "none"}),
                    dbc.Col([
                        dbc.Label("🔬 Chlorine Type", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dcc.Dropdown(
                            id="new-cl-type",
                            options=[
                                {"label": "🧪 DPD", "value": "DPD"},
                                {"label": "📊 4-20 mA", "value": "4-20 mA"}
                            ],
                            placeholder="Select Chlorine Type",
                            className="enhanced-dropdown",
                            style={"marginBottom": "20px", "borderRadius": "12px"}
                        )
                    ], md=4, id="cl-type-col", style={"display": "none"}),
                ]),

                dbc.Row([
                    dbc.Col([
                        dbc.Label("📊 Pressure Topic", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dbc.Input(
                            id="new-pressure-topic",
                            type="text",
                            placeholder="Enter Pressure Topic",
                            className="enhanced-input",
                            style={"marginBottom": "20px", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                        ),
                        html.Div(id="pressure-topic-status", style={"fontSize": "14px", "marginBottom": "20px", "padding": "12px", "borderRadius": "10px", "fontWeight": "bold", "textAlign": "center"})
                    ], md=6, id="pressure-topic-col", style={"display": "none"}),
                    dbc.Col([
                        dbc.Label("📨 Message Type", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dbc.Input(
                            id="new-message-type",
                            type="text",
                            placeholder="Enter Message Type (e.g., MQTT)",
                            value="MQTT",
                            className="enhanced-input",
                            style={"marginBottom": "20px", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                        )
                    ], md=6),
                ]),
            ]),

            html.Hr(style={"margin": "25px 0", "borderColor": "rgba(0,0,0,0.1)"}),

            dbc.Row([
                dbc.Col([
                    dbc.Label("📝 Status", style={"fontWeight": "bold", "fontSize": "18px", "color": "#2c3e50", "marginBottom": "12px"}),
                    dcc.Dropdown(
                        id="new-status",
                        options=[
                            {"label": "📤 Submitted", "value": "submitted"},
                            {"label": "✅ Integrated", "value": "Integrated"},
                            {"label": "🔄 Returned to SI with comments", "value": "Returned to SI with comments"}
                        ],
                        value="submitted",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("💬 Remarks", style={"fontWeight": "bold", "fontSize": "18px", "color": "#2c3e50", "marginBottom": "12px"}),
                    dbc.Textarea(
                        id="new-remarks",
                        placeholder="Enter remarks...",
                        className="enhanced-input",
                        style={"marginBottom": "20px", "height": "100px", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                    )
                ], md=6),
            ]),

            # Clean Study Field - Only visible to admin
            html.Div(id="study-field-container", children=[
                html.Hr(style={"margin": "25px 0", "borderColor": "rgba(0,0,0,0.1)"}),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("", style={"fontWeight": "bold", "fontSize": "18px", "color": "#2c3e50", "marginBottom": "12px", "textAlign": "center"}),
                        dbc.Input(
                            id="new-study",
                            type="text",
                            placeholder="Enter Study details...",
                            className="enhanced-input",
                            style={"marginBottom": "20px", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                        )
                    ], md=12),
                ]),
            ], style={"display": "none"}),

            html.Hr(style={"margin": "25px 0", "borderColor": "rgba(0,0,0,0.1)"}),

            dbc.Row([
                dbc.Col([
                    dbc.Button("🔍 Check Topics", id="btn-check-topics", color="info", className="enhanced-btn", style={"marginRight": "15px", "marginBottom": "15px", "fontWeight": "bold", "borderRadius": "12px", "padding": "15px", "fontSize": "15px"}),
                    dbc.Button("✅ Submit Entry", id="btn-submit-entry", color="success", className="enhanced-btn", style={"marginBottom": "15px", "fontWeight": "bold", "borderRadius": "12px", "padding": "15px", "fontSize": "15px"}, disabled=True),
                ], md=12, style={"textAlign": "center"}),
            ]),
            html.Div(id="submit-status", style={"marginTop": "20px"})
        ], style={"padding": "35px"})
    ], className="enhanced-card shadow", style={
        "borderRadius": "20px",
        "border": "none",
        "transition": "transform 0.3s ease",
        "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
        "marginBottom": "30px"
    }),

    # Clean Admin Controls Section
    html.Div(id="admin-controls-section", children=[
        dbc.Card([
            dbc.CardHeader("🛠️ Admin Controls - Recent Entries", style={
                "background": "linear-gradient(45deg, #56ab2f, #a8e6cf)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "20px",
                "textAlign": "center",
                "padding": "20px",
                "borderRadius": "15px 15px 0 0"
            }),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("🔍 Filter by Status:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dcc.Dropdown(
                            id="status-filter",
                            options=[
                                {"label": "📋 All", "value": "All"},
                                {"label": "📤 Submitted", "value": "submitted"},
                                {"label": "✅ Integrated", "value": "Integrated"},
                                {"label": "🔄 Returned to SI with comments", "value": "Returned to SI with comments"}
                            ],
                            value="All",
                            className="enhanced-dropdown",
                            style={"marginBottom": "20px", "borderRadius": "12px"}
                        )
                    ], md=3),
                    dbc.Col([
                        dbc.Label("🔎 Search:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dbc.Input(
                            id="search-new-entries",
                            type="text",
                            placeholder="Search by village, scheme, topic...",
                            className="enhanced-input",
                            style={"marginBottom": "20px", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                        )
                    ], md=6),
                    dbc.Col([
                        dbc.Label("📄 Items per page:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dcc.Dropdown(
                            id="page-size-new-entries",
                            options=[
                                {"label": "5", "value": 5},
                                {"label": "10", "value": 10},
                                {"label": "20", "value": 20},
                                {"label": "50", "value": 50}
                            ],
                            value=10,
                            className="enhanced-dropdown",
                            style={"marginBottom": "20px", "borderRadius": "12px"}
                        )
                    ], md=3),
                ]),

                # Clean Save Changes Button
                dbc.Row([
                    dbc.Col([
                        dbc.Button("💾 Save All Changes", id="btn-save-changes", color="primary", className="enhanced-btn",
                                  style={"marginBottom": "20px", "width": "200px", "fontWeight": "bold", "borderRadius": "12px", "padding": "15px", "fontSize": "15px"}),
                        html.Div(id="save-status", style={"marginTop": "15px"})
                    ], md=12, style={"textAlign": "center"}),
                ]),

                dash_table.DataTable(
                    id="new-entries-table",
                    page_action="native",
                    page_current=0,
                    style_table={
                        "overflowX": "auto",
                        "borderRadius": "12px",
                        "overflow": "hidden",
                        "boxShadow": "0 6px 20px rgba(0,0,0,0.1)",
                        "border": "1px solid rgba(255,255,255,0.2)",
                        "marginTop": "15px"
                    },
                    style_cell={
                        'textAlign': 'center',
                        'fontSize': 13,
                        'font-family': 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
                        'padding': '12px',
                        'border': '1px solid rgba(0,0,0,0.1)',
                        'minWidth': '120px',
                        'width': '160px',
                        'maxWidth': '200px',
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                        'whiteSpace': 'normal',
                        'height': 'auto',
                        'backgroundColor': 'rgba(255,255,255,0.95)'
                    },
                    style_header={
                        'backgroundColor': '#56ab2f',
                        'color': 'white',
                        'fontWeight': 'bold',
                        'border': '1px solid #56ab2f',
                        'textAlign': 'center',
                        'fontSize': '15px',
                        'padding': '15px'
                    },
                    style_data_conditional=[
                        {'if': {'state': 'active'}, 'backgroundColor': 'rgba(86, 171, 47, 0.3)', 'border': '1px solid rgb(86, 171, 47)'},

                        # Enhanced Status-based row coloring
                        {
                            'if': {
                                'filter_query': '{Status} = "In Progress"'
                            },
                            'backgroundColor': 'rgba(255, 193, 7, 0.25)',
                            'color': '#856404',
                            'fontWeight': 'bold'
                        },
                        {
                            'if': {
                                'filter_query': '{Status} = "Returned to SI with comments"'
                            },
                            'backgroundColor': 'rgba(255, 65, 108, 0.25)',
                            'color': '#721c24',
                            'fontWeight': 'bold'
                        },
                        {
                            'if': {
                                'filter_query': '{Status} = "Integrated"'
                            },
                            'backgroundColor': 'rgba(86, 171, 47, 0.25)',
                            'color': '#155724',
                            'fontWeight': 'bold'
                        },
                        {
                            'if': {
                                'filter_query': '{Status} = "submitted"'
                            },
                            'backgroundColor': 'rgba(102, 126, 234, 0.25)',
                            'color': "#2c3e50",
                            'fontWeight': "bold"
                        }
                    ],
                    export_headers='display',
                    merge_duplicate_headers=True,
                    editable=True,
                    row_deletable=True,
                    filter_action="native",
                    sort_action="native",
                    sort_mode="multi",
                    export_format="xlsx",
                    include_headers_on_copy_paste=True,
                    style_data={
                        'whiteSpace': 'normal',
                        'height': 'auto',
                        'lineHeight': '18px'
                    },
                    css=[{
                        'selector': '.dash-cell div.dash-cell-value',
                        'rule': 'display: inline; white-space: inherit; overflow: inherit; text-overflow: inherit;'
                    }]
                ),
            ], style={"padding": "30px"})
        ], className="enhanced-card shadow", style={
            "borderRadius": "20px",
            "border": "none",
            "transition": "transform 0.3s ease",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
        })
    ], style={"display": "none"}),

    # Clean User's Recent Entries Section
    html.Div(id="user-recent-entries-section", children=[
        dbc.Card([
            dbc.CardHeader("📋 Your Recent Entries", style={
                "background": "linear-gradient(45deg, #4facfe, #00f2fe)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "20px",
                "textAlign": "center",
                "padding": "20px",
                "borderRadius": "15px 15px 0 0"
            }),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("🔍 Filter by Status:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dcc.Dropdown(
                            id="user-status-filter",
                            options=[
                                {"label": "📋 All", "value": "All"},
                                {"label": "📤 Submitted", "value": "submitted"},
                                {"label": "✅ Integrated", "value": "Integrated"},
                                {"label": "🔄 Returned to SI with comments", "value": "Returned to SI with comments"}
                            ],
                            value="All",
                            className="enhanced-dropdown",
                            style={"marginBottom": "20px", "borderRadius": "12px"}
                        )
                    ], md=4),
                    dbc.Col([
                        dbc.Label("🔎 Search:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dbc.Input(
                            id="user-search-entries",
                            type="text",
                            placeholder="Search your entries...",
                            className="enhanced-input",
                            style={"marginBottom": "20px", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                        )
                    ], md=5),
                    dbc.Col([
                        dbc.Label("📄 Items per page:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                        dcc.Dropdown(
                            id="user-page-size",
                            options=[
                                {"label": "5", "value": 5},
                                {"label": "10", "value": 10},
                                {"label": "20", "value": 20}
                            ],
                            value=10,
                            className="enhanced-dropdown",
                            style={"marginBottom": "20px", "borderRadius": "12px"}
                        )
                    ], md=3),
                ]),

                dash_table.DataTable(
                    id="user-recent-entries-table",
                    page_action="native",
                    page_current=0,
                    style_table={
                        "overflowX": "auto",
                        "borderRadius": "12px",
                        "overflow": "hidden",
                        "boxShadow": "0 6px 20px rgba(0,0,0,0.1)",
                        "border": "1px solid rgba(255,255,255,0.2)",
                        "marginTop": "15px"
                    },
                    style_cell={
                        'textAlign': 'center',
                        'fontSize': 13,
                        'font-family': 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
                        'padding': '12px',
                        'border': '1px solid rgba(0,0,0,0.1)',
                        'minWidth': '120px',
                        'width': '160px',
                        'maxWidth': '200px',
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                        'whiteSpace': 'normal',
                        'height': 'auto',
                        'backgroundColor': 'rgba(255,255,255,0.95)'
                    },
                    style_header={
                        'backgroundColor': '#4facfe',
                        'color': 'white',
                        'fontWeight': 'bold',
                        'border': '1px solid #4facfe',
                        'textAlign': "center",
                        'fontSize': '15px',
                        'padding': '15px'
                    },
                    style_data_conditional=[
                        {'if': {'state': 'active'}, 'backgroundColor': 'rgba(79, 172, 254, 0.3)', 'border': '1px solid rgb(79, 172, 254)'},

                        # Enhanced Status-based row coloring
                        {
                            'if': {
                                'filter_query': '{Status} = "In Progress"'
                            },
                            'backgroundColor': 'rgba(255, 193, 7, 0.25)',
                            'color': '#856404',
                            'fontWeight': 'bold'
                        },
                        {
                            'if': {
                                'filter_query': '{Status} = "Returned to SI with comments"'
                            },
                            'backgroundColor': 'rgba(255, 65, 108, 0.25)',
                            'color': '#721c24',
                            'fontWeight': 'bold'
                        },
                        {
                            'if': {
                                'filter_query': '{Status} = "Integrated"'
                            },
                            'backgroundColor': 'rgba(86, 171, 47, 0.25)',
                            'color': '#155724',
                            'fontWeight': 'bold'
                        },
                        {
                            'if': {
                                'filter_query': '{Status} = "submitted"'
                            },
                            'backgroundColor': 'rgba(102, 126, 234, 0.25)',
                            'color': "#2c3e50",
                            'fontWeight': "bold"
                        },
                    ],
                    export_headers='display',
                    merge_duplicate_headers=True,
                    editable=False,
                    row_deletable=False,
                    filter_action="native",
                    sort_action="native",
                    sort_mode="multi",
                    style_data={
                        'whiteSpace': 'normal',
                        'height': 'auto',
                        'lineHeight': '18px'
                    },
                    css=[{
                        'selector': '.dash-cell div.dash-cell-value',
                        'rule': 'display: inline; white-space: inherit; overflow: inherit; text-overflow: inherit;'
                    }]
                ),
            ], style={"padding": "30px"})
        ], className="enhanced-card shadow", style={
            "borderRadius": "20px",
            "border": "none",
            "transition": "transform 0.3s ease",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
        })
    ], style={"display": "none"}),

], className="main-content", style={"marginLeft": "320px", "padding": "35px", "background": "linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)", "minHeight": "100vh"})

# ================== RESERVOIR ANALYTICS PAGE ==================
reservoir_analytics_page = html.Div([
    html.Div([
        html.H2("📊 Reservoir Analytics Dashboard", style={
            "color": "white",
            "margin": 0,
            "padding": "25px",
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "borderRadius": "20px",
            "fontWeight": "bold",
            "textAlign": "center",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.2)",
            "marginBottom": "30px"
        }),
    ]),

    # Reservoir Information Card
    dbc.Card([
        dbc.CardHeader("🏗️ Reservoir Information", style={
            "background": "linear-gradient(45deg, #56ab2f, #a8e6cf)",
            "color": "white",
            "fontWeight": "bold",
            "fontSize": "20px",
            "textAlign": "center",
            "padding": "20px",
            "borderRadius": "15px 15px 0 0"
        }),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.H4(id="reservoir-name", style={"color": "#2c3e50", "fontWeight": "bold", "marginBottom": "15px", "textAlign": "center"}),
                    dbc.Row([
                        dbc.Col([
                            html.P("🏗️ Scheme ID - Name:", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            html.P(id="reservoir-scheme", style={"color": "#666"}),
                            html.P("🏘️ Village Name:", style={"fontWeight": "bold", "marginBottom": "5px", "marginTop": "15px"}),
                            html.P(id="reservoir-village", style={"color": "#666"}),
                            html.P("💧 Reservoir:", style={"fontWeight": "bold", "marginBottom": "5px", "marginTop": "15px"}),
                            html.P(id="reservoir-name-display", style={"color": "#666"}),
                        ], md=6),
                        dbc.Col([
                            html.P("👥 Population:", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            html.P(id="reservoir-population", style={"color": "#666"}),
                            html.P("🌍 Region:", style={"fontWeight": "bold", "marginBottom": "5px", "marginTop": "15px"}),
                            html.P(id="reservoir-region-display", style={"color": "#666"}),
                            html.P("🏛️ Sub Division:", style={"fontWeight": "bold", "marginBottom": "5px", "marginTop": "15px"}),
                            html.P(id="reservoir-subdivision", style={"color": "#666"}),
                        ], md=6),
                    ]),
                    html.Hr(style={"margin": "20px 0"}),
                    dbc.Row([
                        dbc.Col([
                            html.P("🔵 Circle:", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            html.P(id="reservoir-circle", style={"color": "#666"}),
                            html.P("📦 Block:", style={"fontWeight": "bold", "marginBottom": "5px", "marginTop": "15px"}),
                            html.P(id="reservoir-block", style={"color": "#666"}),
                        ], md=6),
                        dbc.Col([
                            html.P("💧 Reservoir Type:", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            html.P("ESR", style={"color": "#666"}),
                          #  html.P("📊 Reservoir Capacity:", style={"fontWeight": "bold", "marginBottom": "5px", "marginTop": "15px"}),
                           # html.P("1.34 LL", style={"color": "#666"}),
                        ], md=6),
                    ]),
                ], md=12),
            ]),
        ], style={"padding": "30px"})
    ], className="enhanced-card shadow", style={
        "borderRadius": "20px",
        "border": "none",
        "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
        "marginBottom": "30px"
    }),

    # Analytics Charts Row 1
    dbc.Row([
        # Totalizer Graph
        dbc.Col(html.Div([
            html.Div("🔍", className="expand-icon", id="expand-totalizer"),
            dbc.Card([
                dbc.CardHeader("📈 Totalizer Value Over Time", style={
                    "background": "linear-gradient(45deg, #667eea, #764ba2)",
                    "color": "white",
                    "fontWeight": "bold",
                    "fontSize": "16px",
                    "textAlign": "center",
                    "padding": "15px"
                }),
                dbc.CardBody([
                    dcc.Graph(id="totalizer-graph", style={"height": "300px"})
                ], style={"padding": "20px"})
            ], className="enhanced-card shadow", style={
                "borderRadius": "15px",
                "border": "none",
                "transition": "all 0.3s ease",
                "height": "100%",
                "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
            })
        ], className="graph-container", id="totalizer-container"), md=6),

        # Water Consumption Graph
        dbc.Col(html.Div([
            html.Div("🔍", className="expand-icon", id="expand-consumption"),
            dbc.Card([
                dbc.CardHeader("💧 Daily Water Consumption", style={
                    "background": "linear-gradient(45deg, #4facfe, #00f2fe)",
                    "color": "white",
                    "fontWeight": "bold",
                    "fontSize": "16px",
                    "textAlign": "center",
                    "padding": "15px"
                }),
                dbc.CardBody([
                    dcc.Graph(id="consumption-graph", style={"height": "300px"})
                ], style={"padding": "20px"})
            ], className="enhanced-card shadow", style={
                "borderRadius": "15px",
                "border": "none",
                "transition": "all 0.3s ease",
                "height": "100%",
                "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
            })
        ], className="graph-container", id="consumption-container"), md=6),
    ], className="mb-4"),

    # Analytics Charts Row 2
    dbc.Row([
        # LPCD Graph
        dbc.Col(html.Div([
            html.Div("🔍", className="expand-icon", id="expand-lpcd"),
            dbc.Card([
                dbc.CardHeader("👥 LPCD (Liters Per Capita Per Day)", style={
                    "background": "linear-gradient(45deg, #56ab2f, #a8e6cf)",
                    "color": "white",
                    "fontWeight": "bold",
                    "fontSize": "16px",
                    "textAlign": "center",
                    "padding": "15px"
                }),
                dbc.CardBody([
                    dcc.Graph(id="lpcd-graph", style={"height": "300px"})
                ], style={"padding": "20px"})
            ], className="enhanced-card shadow", style={
                "borderRadius": "15px",
                "border": "none",
                "transition": "all 0.3s ease",
                "height": "100%",
                "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
            })
        ], className="graph-container", id="lpcd-container"), md=4),

        # Flow Rate Gauge
        dbc.Col(html.Div([
            html.Div("🔍", className="expand-icon", id="expand-flow"),
            dbc.Card([
                dbc.CardHeader("🌊 Current Flow Rate", style={
                    "background": "linear-gradient(45deg, #ff416c, #ff4b2b)",
                    "color": "white",
                    "fontWeight": "bold",
                    "fontSize": "16px",
                    "textAlign": "center",
                    "padding": "15px"
                }),
                dbc.CardBody([
                    dcc.Graph(id="flow-gauge", style={"height": "300px"})
                ], style={"padding": "20px"})
            ], className="enhanced-card shadow", style={
                "borderRadius": "15px",
                "border": "none",
                "transition": "all 0.3s ease",
                "height": "100%",
                "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
            })
        ], className="graph-container", id="flow-container"), md=4),

        # Chlorine Level Graph
        dbc.Col(html.Div([
            html.Div("🔍", className="expand-icon", id="expand-chlorine"),
            dbc.Card([
                dbc.CardHeader("🧪 Chlorine Levels", style={
                    "background": "linear-gradient(45deg, #f7971e, #ffd200)",
                    "color": "white",
                    "fontWeight": "bold",
                    "fontSize": "16px",
                    "textAlign": "center",
                    "padding": "15px"
                }),
                dbc.CardBody([
                    dcc.Graph(id="chlorine-graph", style={"height": "300px"})
                ], style={"padding": "20px"})
            ], className="enhanced-card shadow", style={
                "borderRadius": "15px",
                "border": "none",
                "transition": "all 0.3s ease",
                "height": "100%",
                "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
            })
        ], className="graph-container", id="chlorine-container"), md=4),
    ], className="mb-4"),

    # Pressure Graph
    dbc.Row([
        dbc.Col(html.Div([
            html.Div("🔍", className="expand-icon", id="expand-pressure"),
            dbc.Card([
                dbc.CardHeader("📊 Pressure Monitoring", style={
                    "background": "linear-gradient(45deg, #9c27b0, #e91e63)",
                    "color": "white",
                    "fontWeight": "bold",
                    "fontSize": "16px",
                    "textAlign": "center",
                    "padding": "15px"
                }),
                dbc.CardBody([
                    dcc.Graph(id="pressure-graph", style={"height": "300px"})
                ], style={"padding": "20px"})
            ], className="enhanced-card shadow", style={
                "borderRadius": "15px",
                "border": "none",
                "transition": "all 0.3s ease",
                "height": "100%",
                "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
            })
        ], className="graph-container", id="pressure-container"), md=12),
    ]),

    # Store for historical data
    dcc.Store(id="reservoir-historical-data"),
    dcc.Store(id="current-fullscreen-graph", data=""),

], className="main-content", style={"marginLeft": "320px", "padding": "35px", "background": "linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)", "minHeight": "100vh"})

# ================== CLEAN MAIN PAGE ==================
main_page = html.Div([
    html.Div([
        html.H2("SWSM IOT Real-Time Monitoring Dashboard", style={
            "color": "white",
            "margin": 0,
            "padding": "25px",
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "borderRadius": "20px",
            "fontWeight": "bold",
            "textAlign": "center",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.2)",
            "marginBottom": "30px"
        }),
    ]),

    # Clean Communication Status Cards
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("🌊 Flow Meter Communication", style={
                "background": "linear-gradient(45deg, #667eea, #764ba2)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.H4(id="flow-total-count", className="pulse", style={"color": "#2c3e50", "fontWeight": "bold", "marginBottom": "12px", "textAlign": "center", "fontSize": "1.8rem"}),
                html.H4(id="flow-communicating-count", className="pulse", style={"color": "#56ab2f", "fontWeight": "bold", "marginBottom": "12px", "textAlign": "center", "fontSize": "1.8rem"}),
                html.H4(id="flow-nodata-count", className="pulse", style={"color": "#ff416c", "fontWeight": "bold", "marginBottom": "20px", "textAlign": "center", "fontSize": "1.8rem"}),
                dcc.Graph(id="flow-pie-chart", style={"height": "200px"})
            ], style={"padding": "20px"})
        ], className="enhanced-card shadow", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
        }), md=4),

        dbc.Col(dbc.Card([
            dbc.CardHeader("🧪 Chlorine Communication", style={
                "background": "linear-gradient(45deg, #56ab2f, #a8e6cf)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.H4(id="cl-total-count", className="pulse", style={"color": "#2c3e50", "fontWeight": "bold", "marginBottom": "12px", "textAlign": "center", "fontSize": "1.8rem"}),
                html.H4(id="cl-communicating-count", className="pulse", style={"color": "#56ab2f", "fontWeight": "bold", "marginBottom": "12px", "textAlign": "center", "fontSize": "1.8rem"}),
                html.H4(id="cl-nodata-count", className="pulse", style={"color": "#ff416c", "fontWeight": "bold", "marginBottom": "20px", "textAlign": "center", "fontSize": "1.8rem"}),
                dcc.Graph(id="cl-pie-chart", style={"height": "200px"})
            ], style={"padding": "20px"})
        ], className="enhanced-card shadow", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
        }), md=4),

        dbc.Col(dbc.Card([
            dbc.CardHeader("📊 Pressure Communication", style={
                "background": "linear-gradient(45deg, #ff416c, #ff4b2b)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.H4(id="pressure-total-count", className="pulse", style={"color": "#2c3e50", "fontWeight": "bold", "marginBottom": "12px", "textAlign": "center", "fontSize": "1.8rem"}),
                html.H4(id="pressure-communicating-count", className="pulse", style={"color": "#56ab2f", "fontWeight": "bold", "marginBottom": "12px", "textAlign": "center", "fontSize": "1.8rem"}),
                html.H4(id="pressure-nodata-count", className="pulse", style={"color": "#ff416c", "fontWeight": "bold", "marginBottom": "20px", "textAlign": "center", "fontSize": "1.8rem"}),
                dcc.Graph(id="pressure-pie-chart", style={"height": "200px"})
            ], style={"padding": "20px"})
        ], className="enhanced-card shadow", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
        }), md=4),
    ], className="mb-4"),

    # Clean Topic selection
    dbc.Card([
        dbc.CardHeader("📡 Real-Time Topic Selection", style={
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "color": "white",
            "fontWeight": "bold",
            "fontSize": "20px",
            "textAlign": "center",
            "padding": "20px",
            "borderRadius": "15px 15px 0 0"
        }),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("🌊 Flow Topic", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="flow-topic-dropdown",
                        options=[{"label": t, "value": t} for t in flow_topics],
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=4),
                dbc.Col([
                    dbc.Label("🧪 CL Topic", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="cl-topic-dropdown",
                        options=[{"label": t, "value": t} for t in cl_topics],
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=4),
                dbc.Col([
                    dbc.Label("📊 Pressure Topic", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="pressure-topic-dropdown",
                        options=[{"label": t, "value": t} for t in pressure_topics],
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=4)
            ], className="mb-4"),
        ], style={"padding": "25px"})
    ], className="enhanced-card shadow", style={
        "borderRadius": "20px",
        "border": "none",
        "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
        "marginBottom": "30px"
    }),

    # Clean KPI Cards
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("🌊 Flow Meter Analytics", style={
                "background": "linear-gradient(45deg, #667eea, #764ba2)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.P("📡 Selected Topic:", style={"fontWeight": "bold", "marginBottom": "8px", "color": "#2c3e50", "fontSize": "15px"}),
                html.P(id="selected-flow-topic", style={"marginBottom": "20px", "fontSize": "14px", "background": "linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)", "padding": "12px", "borderRadius": "10px", "fontWeight": "bold", "textAlign": "center"}),
                html.Hr(style={"margin": "15px 0", "borderColor": "rgba(0,0,0,0.1)"}),
                html.P("📊 Latest Data:", style={"fontWeight": "bold", "marginBottom": "12px", "color": "#2c3e50", "fontSize": "16px", "textAlign": "center"}),
                html.P("🕒 Recent Communication:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="flow-datetime", style={"marginBottom": "15px", "fontSize": "14px", "background": "rgba(79, 172, 254, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.P("🌊 Flow Rate:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="flow-value", style={"marginBottom": "12px", "fontSize": "14px", "background": "rgba(86, 171, 47, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.P("📈 Totalizer Value:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="flow-total", style={"marginBottom": "12px", "fontSize": "14px", "background": "rgba(255, 193, 7, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.P("📶 Communication Status:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="flow-remarks", style={"fontSize": "14px", "wordBreak": "break-all", "color": "#e53935", "background": "rgba(255, 65, 108, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.Hr(style={"margin": "15px 0", "borderColor": "rgba(0,0,0,0.1)"}),
                html.P("📋 Raw JSON:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.Pre(id="flow-json", style={"fontSize": "11px", "background": "rgba(248,249,250,0.9)", "padding": "12px", "overflow": "auto", "maxHeight": "120px", "borderRadius": "10px", "border": "1px solid rgba(0,0,0,0.1)"})
            ], style={"padding": "25px"})
        ], className="enhanced-card shadow", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
        }), md=4),

        dbc.Col(dbc.Card([
            dbc.CardHeader("🧪 Chlorine Analytics", style={
                "background": "linear-gradient(45deg, #56ab2f, #a8e6cf)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.P("📡 Selected Topic:", style={"fontWeight": "bold", "marginBottom": "8px", "color": "#2c3e50", "fontSize": "15px"}),
                html.P(id="selected-cl-topic", style={"marginBottom": "20px", "fontSize": "14px", "background": "linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)", "padding": "12px", "borderRadius": "10px", "fontWeight": "bold", "textAlign": "center"}),
                html.Hr(style={"margin": "15px 0", "borderColor": "rgba(0,0,0,0.1)"}),
                html.P("📊 Latest Data:", style={"fontWeight": "bold", "marginBottom": "12px", "color": "#2c3e50", "fontSize": "16px", "textAlign": "center"}),
                html.P("🕒 Recent Communication:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="cl-datetime", style={"marginBottom": "15px", "fontSize": "14px", "background": "rgba(79, 172, 254, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.P("🧪 Chlorine:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="cl-value", style={"marginBottom": "12px", "fontSize": "14px", "background": "rgba(86, 171, 47, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.P("📶 Signal:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="cl-csq", style={"marginBottom": "12px", "fontSize": "14px", "background": "rgba(255, 193, 7, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.P("📶 Communication Status:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="cl-remarks", style={"fontSize": "14px", "wordBreak": "break-all", "color": "#e53935", "background": "rgba(255, 65, 108, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.Hr(style={"margin": "15px 0", "borderColor": "rgba(0,0,0,0.1)"}),
                html.P("📋 Raw JSON:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.Pre(id="cl-json", style={"fontSize": "11px", "background": "rgba(248,249,250,0.9)", "padding": "12px", "overflow": "auto", "maxHeight": "120px", "borderRadius": "10px", "border": "1px solid rgba(0,0,0,0.1)"})
            ], style={"padding": "25px"})
        ], className="enhanced-card shadow", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
        }), md=4),

        dbc.Col(dbc.Card([
            dbc.CardHeader("📊 Pressure Analytics", style={
                "background": "linear-gradient(45deg, #ff416c, #ff4b2b)",
                "color": "white",
                "fontWeight": "bold",
                "fontSize": "16px",
                "textAlign": "center",
                "padding": "15px"
            }),
            dbc.CardBody([
                html.P("📡 Selected Topic:", style={"fontWeight": "bold", "marginBottom": "8px", "color": "#2c3e50", "fontSize": "15px"}),
                html.P(id="selected-pressure-topic", style={"marginBottom": "20px", "fontSize": "14px", "background": "linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)", "padding": "12px", "borderRadius": "10px", "fontWeight": "bold", "textAlign": "center"}),
                html.Hr(style={"margin": "15px 0", "borderColor": "rgba(0,0,0,0.1)"}),
                html.P("📊 Latest Data:", style={"fontWeight": "bold", "marginBottom": "12px", "color": "#2c3e50", "fontSize": "16px", "textAlign": "center"}),
                html.P("🕒 Recent Communication:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="pressure-datetime", style={"marginBottom": "15px", "fontSize": "14px", "background": "rgba(79, 172, 254, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.P("📊 Pressure:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="pressure-value", style={"marginBottom": "12px", "fontSize": "14px", "background": "rgba(86, 171, 47, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.P("📶 Signal:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="pressure-csq", style={"marginBottom": "12px", "fontSize": "14px", "background": "rgba(255, 193, 7, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.P("📦 Packages:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="pressure-packages", style={"marginBottom": "12px", "fontSize": "14px", "background": "rgba(156, 39, 176, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.P("📶 Communication Status:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.P(id="pressure-remarks", style={"fontSize": "14px", "wordBreak": "break-all", "color": "#e53935", "background": "rgba(255, 65, 108, 0.15)", "padding": "10px", "borderRadius": "8px", "fontWeight": "bold", "textAlign": "center"}),
                html.Hr(style={"margin": "15px 0", "borderColor": "rgba(0,0,0,0.1)"}),
                html.P("📋 Raw JSON:", style={"fontWeight": "bold", "marginBottom": "6px", "fontSize": "14px", "color": "#666"}),
                html.Pre(id="pressure-json", style={"fontSize": "11px", "background": "rgba(248,249,250,0.9)", "padding": "12px", "overflow": "auto", "maxHeight": "120px", "borderRadius": "10px", "border": "1px solid rgba(0,0,0,0.1)"})
            ], style={"padding": "25px"})
        ], className="enhanced-card shadow", style={
            "borderRadius": "15px",
            "border": "none",
            "transition": "all 0.3s ease",
            "height": "100%",
            "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
        }), md=4),
    ], className="mb-4"),

    # Clean Advanced Filtering for Tables
    dbc.Card([
        dbc.CardHeader("🔧 Advanced Data Filtering", style={
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "color": "white",
            "fontWeight": "bold",
            "fontSize": "20px",
            "textAlign": "center",
            "padding": "20px",
            "borderRadius": "15px 15px 0 0"
        }),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("🌊 FM Status Filter:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="fm-status-filter",
                        options=[
                            {"label": "📋 All", "value": "All"},
                            {"label": "✅ Integrated", "value": "Integrated"},
                            {"label": "🔄 Returned to SI with comments", "value": "Returned to SI with comments"},
                            {"label": "⏳ In Progress", "value": "In Progress"}
                        ],
                        value="All",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=3),
                dbc.Col([
                    dbc.Label("🧪 CL Status Filter:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="cl-status-filter",
                        options=[
                            {"label": "📋 All", "value": "All"},
                            {"label": "✅ Integrated", "value": "Integrated"},
                            {"label": "🔄 Returned to SI with comments", "value": "Returned to SI with comments"},
                            {"label": "⏳ In Progress", "value": "In Progress"}
                        ],
                        value="All",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=3),
                dbc.Col([
                    dbc.Label("📊 PT Status Filter:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="pt-status-filter",
                        options=[
                            {"label": "📋 All", "value": "All"},
                            {"label": "✅ Integrated", "value": "Integrated"},
                            {"label": "🔄 Returned to SI with comments", "value": "Returned to SI with comments"},
                            {"label": "⏳ In Progress", "value": "In Progress"}
                        ],
                        value="All",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=3),
                dbc.Col([
                    dbc.Label("📶 Communication Status:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="comm-status-filter",
                        options=[
                            {"label": "📋 All", "value": "All"},
                            {"label": "✅ Communicating", "value": "YES"},
                            {"label": "❌ Not Communicating", "value": "NO"}
                        ],
                        value="All",
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=3),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("🔎 Search Data:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dbc.Input(
                        id="table-search",
                        type="text",
                        placeholder="Search across all columns...",
                        className="enhanced-input",
                        style={"marginBottom": "20px", "borderRadius": "12px", "padding": "12px", "fontSize": "16px"}
                    )
                ], md=6),
                dbc.Col([
                    dbc.Label("📄 Rows per page:", style={"fontWeight": "bold", "color": "#2c3e50", "fontSize": "16px", "marginBottom": "10px"}),
                    dcc.Dropdown(
                        id="table-page-size",
                        options=[
                            {"label": "10", "value": 10},
                            {"label": "25", "value": 25},
                            {"label": "50", "value": 50},
                            {"label": "100", "value": 100}
                        ],
                        value=25,
                        className="enhanced-dropdown",
                        style={"marginBottom": "20px", "borderRadius": "12px"}
                    )
                ], md=3),
            ])
        ], style={"padding": "25px"})
    ], className="enhanced-card shadow", style={
        "borderRadius": "20px",
        "border": "none",
        "boxShadow": "0 8px 25px rgba(0,0,0,0.1)",
        "marginBottom": "30px"
    }),

    # Clean Tables with Tabs
    dbc.Card([
        dbc.CardHeader("📊 Real-Time Data Tables", style={
            "background": "linear-gradient(45deg, #667eea, #764ba2)",
            "color": "white",
            "fontWeight": "bold",
            "fontSize": "20px",
            "textAlign": "center",
            "padding": "20px",
            "borderRadius": "15px 15px 0 0"
        }),
        dbc.CardBody([
            dbc.Tabs([
                dbc.Tab(
                    label="🌊 Flow Meter Data",
                    tab_id="flow_tab",
                    children=[
                        dash_table.DataTable(
                            id="flow-table",
                            page_action="native",
                            page_current=0,
                            page_size=25,
                            style_table={
                                "overflowX": "auto",
                                "borderRadius": "12px",
                                "overflow": "hidden",
                                "boxShadow": "0 6px 20px rgba(0,0,0,0.1)",
                                "border": "1px solid rgba(255,255,255,0.2)",
                                "marginTop": "15px"
                            },
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': 14,
                                'font-family': 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
                                'padding': '12px',
                                'border': '1px solid rgba(0,0,0,0.1)',
                                'minWidth': '120px',
                                'width': '160px',
                                'maxWidth': '200px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'backgroundColor': 'rgba(255,255,255,0.95)'
                            },
                            style_header={
                                'backgroundColor': '#667eea',
                                'color': 'white',
                                'fontWeight': 'bold',
                                'border': '1px solid #667eea',
                                'textAlign': 'center',
                                'fontSize': '15px',
                                'padding': '15px'
                            },
                            style_data_conditional=[
                                {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgba(248,249,250,0.9)'},
                                {'if': {'row_index': 'even'}, 'backgroundColor': 'rgba(255,255,255,0.95)'},
                                {'if': {'state': 'active'}, 'backgroundColor': 'rgba(102, 126, 234, 0.3)', 'border': '1px solid rgb(102, 126, 234)'},
                                {
                                    'if': {
                                        'filter_query': '{Topic For Flow Meter} != "" && {Topic For Flow Meter} != "nan" && {Flow} = "Integrated" && {Communication Status} contains "YES"',
                                    },
                                    'backgroundColor': 'rgba(86, 171, 47, 0.25)',
                                    'color': '#155724',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Topic For Flow Meter} != "" && {Topic For Flow Meter} != "nan" && {Flow} = "Integrated" && {Communication Status} contains "NO"',
                                    },
                                    'backgroundColor': 'rgba(86, 171, 47, 0.25)',
                                    'color': '#155724',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Topic For Flow Meter} != "" && {Topic For Flow Meter} != "nan" && {Flow} = "In Progress" && {Communication Status} contains "NO"',
                                    },
                                    'backgroundColor': 'rgba(255, 193, 7, 0.25)',
                                    'color': '#856404',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Topic For Flow Meter} != "" && {Topic For Flow Meter} != "nan" && {Flow} = "In Progress" && {Communication Status} contains "YES"',
                                    },
                                    'backgroundColor': 'rgba(255, 193, 7, 0.25)',
                                    'color': '#856404',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Topic For Flow Meter} != "" && {Topic For Flow Meter} != "nan" && {Flow} = "Returned to SI with comments" && {Communication Status} contains "NO"',
                                    },
                                    'backgroundColor': 'rgba(255, 65, 108, 0.25)',
                                    'color': '#721c24',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Topic For Flow Meter} != "" && {Topic For Flow Meter} != "nan" && {Flow} = "Returned to SI with comments" && {Communication Status} contains "YES"',
                                    },
                                    'backgroundColor': 'rgba(255, 65, 108, 0.25)',
                                    'color': '#721c24',
                                    'fontWeight': 'bold'
                                }
                            ],
                            filter_action="native",
                            sort_action="native",
                            sort_mode="multi",
                            editable=True,
                            export_format="xlsx"
                        )
                    ]
                ),

                dbc.Tab(
                    label="🧪 Chlorine Data",
                    tab_id="cl_tab",
                    children=[
                        dash_table.DataTable(
                            id="cl-table",
                            page_action="native",
                            page_current=0,
                            page_size=25,
                            style_table={
                                "overflowX": "auto",
                                "borderRadius": "12px",
                                "overflow": "hidden",
                                "boxShadow": "0 6px 20px rgba(0,0,0,0.1)",
                                "border": "1px solid rgba(255,255,255,0.2)",
                                "marginTop": "15px"
                            },
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': 14,
                                'font-family': 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
                                'padding': '12px',
                                'border': '1px solid rgba(0,0,0,0.1)',
                                'minWidth': '120px',
                                'width': '160px',
                                'maxWidth': '200px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'backgroundColor': 'rgba(255,255,255,0.95)'
                            },
                            style_header={
                                'backgroundColor': '#56ab2f',
                                'color': 'white',
                                'fontWeight': 'bold',
                                'border': '1px solid #56ab2f',
                                'textAlign': 'center',
                                'fontSize': '15px',
                                'padding': '15px'
                            },
                            style_data_conditional=[
                                {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgba(248,249,250,0.9)'},
                                {'if': {'row_index': 'even'}, 'backgroundColor': 'rgba(255,255,255,0.95)'},
                                {'if': {'state': 'active'}, 'backgroundColor': 'rgba(86, 171, 47, 0.3)', 'border': '1px solid rgb(86, 171, 47)'},
                                {
                                    'if': {
                                        'filter_query': '{Topic For CL} != "" && {Topic For CL} != "nan" && {Chlorin} = "Integrated" && {Communication Status} contains "YES"',
                                    },
                                    'backgroundColor': 'rgba(86, 171, 47, 0.25)',
                                    'color': '#155724',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Topic For CL} != "" && {Topic For CL} != "nan" && {Chlorin} = "Integrated" && {Communication Status} contains "NO"',
                                    },
                                    'backgroundColor': 'rgba(255, 193, 7, 0.25)',
                                    'color': '#856404',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Topic For CL} != "" && {Topic For CL} != "nan" && {Chlorin} = "Returned to SI with comments" && {Communication Status} contains "NO"',
                                    },
                                    'backgroundColor': 'rgba(255, 65, 108, 0.25)',
                                    'color': '#721c24',
                                    'fontWeight': 'bold'
                                }
                            ],
                            filter_action="native",
                            sort_action="native",
                            sort_mode="multi",
                            editable=True,
                            export_format="xlsx"
                        )
                    ]
                ),

                dbc.Tab(
                    label="📊 Pressure Data",
                    tab_id="pressure_tab",
                    children=[
                        dash_table.DataTable(
                            id="pressure-table",
                            page_action="native",
                            page_current=0,
                            page_size=25,
                            style_table={
                                "overflowX": "auto",
                                "borderRadius": "12px",
                                "overflow": "hidden",
                                "boxShadow": "0 6px 20px rgba(0,0,0,0.1)",
                                "border": "1px solid rgba(255,255,255,0.2)",
                                "marginTop": "15px"
                            },
                            style_cell={
                                'textAlign': 'center',
                                'fontSize': 14,
                                'font-family': 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
                                'padding': '12px',
                                'border': '1px solid rgba(0,0,0,0.1)',
                                'minWidth': '120px',
                                'width': '160px',
                                'maxWidth': '200px',
                                'overflow': 'hidden',
                                'textOverflow': 'ellipsis',
                                'backgroundColor': 'rgba(255,255,255,0.95)'
                            },
                            style_header={
                                'backgroundColor': "#ff416c",
                                'color': 'white',
                                'fontWeight': 'bold',
                                'border': '1px solid #ff416c',
                                'textAlign': 'center',
                                'fontSize': '15px',
                                'padding': '15px'
                            },
                            style_data_conditional=[
                                {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgba(248,249,250,0.9)'},
                                {'if': {'row_index': 'even'}, 'backgroundColor': 'rgba(255,255,255,0.95)'},
                                {'if': {'state': 'active'}, 'backgroundColor': 'rgba(255, 65, 108, 0.3)', 'border': '1px solid rgb(255, 65, 108)'},
                                {
                                    'if': {
                                        'filter_query': '{Topic For Pressure} != "" && {Topic For Pressure} != "nan" && {Pressure} = "Integrated" && {Communication Status} contains "YES"',
                                    },
                                    'backgroundColor': 'rgba(86, 171, 47, 0.25)',
                                    'color': '#155724',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Topic For Pressure} != "" && {Topic For Pressure} != "nan" && {Pressure} = "Integrated" && {Communication Status} contains "NO"',
                                    },
                                    'backgroundColor': 'rgba(255, 193, 7, 0.25)',
                                    'color': '#856404',
                                    'fontWeight': 'bold'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Topic For Pressure} != "" && {Topic For Pressure} != "nan" && {Pressure} = "Returned to SI with comments" && {Communication Status} contains "NO"',
                                    },
                                    'backgroundColor': 'rgba(255, 65, 108, 0.25)',
                                    'color': '#721c24',
                                    'fontWeight': 'bold'
                                }
                            ],
                            filter_action="native",
                            sort_action="native",
                            sort_mode="multi",
                            editable=True,
                            export_format="xlsx"
                        )
                    ]
                )
            ], id="main-tabs", active_tab="flow_tab"),
        ], style={"padding": "25px"})
    ], className="enhanced-card shadow", style={
        "borderRadius": "20px",
        "border": "none",
        "boxShadow": "0 8px 25px rgba(0,0,0,0.1)"
    }),
], className="main-content", style={"marginLeft": "320px", "padding": "35px", "background": "linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)", "minHeight": "100vh"})

# ================== MAIN LAYOUT ==================
app.layout = html.Div([
    sidebar,
    html.Div([
        dcc.Location(id='url', refresh=False),
        html.Div(id='page-content')
    ]),
    fullscreen_modal,
    dcc.Store(id='user-session', data={'logged_in': False, 'username': '', 'role': '', 'region': ''}),
    dcc.Interval(id="refresh-interval", interval=UI_REFRESH_MS, n_intervals=0),
    dcc.Store(id="base-df-json", data=base_df.to_dict(orient="records") if not base_df.empty else []),
    dcc.Store(id="uploaded-data", data=None)
])

# ================== CALLBACKS ==================
@app.callback(
    Output("page-content", "children"),
    Output("user-info", "children"),
    Output("btn-logout", "style"),
    Input("url", "pathname"),
    Input("user-session", "data")
)
def display_page(pathname, session_data):
    logged_in = session_data.get('logged_in', False)
    username = session_data.get('username', '')
    role = session_data.get('role', '')

    # Update sidebar user info
    if logged_in:
        user_info = f"👤 Logged in as: {username} ({role})"
        logout_style = {"width": "100%", "marginBottom": "10px", "fontWeight": "bold", "borderRadius": "10px", "padding": "10px"}
    else:
        user_info = "👤 Not logged in"
        logout_style = {"width": "100%", "marginBottom": "10px", "display": "none"}

    if pathname == "/add-entry":
        if logged_in:
            return add_entry_page, user_info, logout_style
        else:
            return login_page, user_info, logout_style
    elif pathname == "/analysis":
        return analysis_page, user_info, logout_style
    elif pathname == "/reservoir-analytics":
        return reservoir_analytics_page, user_info, logout_style
    else:
        return main_page, user_info, logout_style

@app.callback(
    Output("user-session", "data"),
    Input("btn-login", "n_clicks"),
    Input("btn-logout", "n_clicks"),
    State("login-username", "value"),
    State("login-password", "value"),
    State("user-session", "data"),
    prevent_initial_call=True
)
def handle_login_logout(login_clicks, logout_clicks, username, password, current_session):
    ctx = callback_context
    if not ctx.triggered:
        return current_session

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id == "btn-login" and login_clicks:
        # Login attempt
        if username and password:
            # Try both user and admin authentication
            user = authenticate_user(username, password, "user")
            if not user:
                user = authenticate_user(username, password, "admin")

            if user:
                # Log login activity
                log_user_activity(username, "Login", "User logged in successfully")
                return {
                    'logged_in': True,
                    'username': username,
                    'role': user.get('role', 'user'),
                    'name': user.get('name', username),
                    'region': user.get('region', ''),
                    'mail': user.get('mail', '')
                }
            else:
                return current_session  # Keep current session on failed login
        else:
            return current_session  # Keep current session if fields are empty

    elif trigger_id == "btn-logout" and logout_clicks:
        # Log logout activity
        if current_session.get('logged_in'):
            log_user_activity(current_session.get('username'), "Logout", "User logged out")
        # Logout
        return {
            'logged_in': False,
            'username': '',
            'role': '',
            'name': ''
        }

    return current_session

@app.callback(
    Output("login-status", "children"),
    Input("btn-login", "n_clicks"),
    State("login-username", "value"),
    State("login-password", "value"),
    prevent_initial_call=True
)
def show_login_status(login_clicks, username, password):
    if login_clicks is None:
        return ""

    if not username or not password:
        return dbc.Alert("❌ Please enter both username and password.", color="warning", style={"borderRadius": "10px", "fontSize": "14px"})

    # Authenticate from database
    user = authenticate_user(username, password, "user")
    if not user:
        user = authenticate_user(username, password, "admin")

    if user:
        return dbc.Alert(f"✅ Login successful! Welcome {username} ({user.get('role', 'user')}).", color="success", style={"borderRadius": "10px", "fontSize": "14px"})
    else:
        return dbc.Alert("❌ Invalid username or password. Please try again.", color="danger", style={"borderRadius": "10px", "fontSize": "14px"})

@app.callback(
    Output("user-welcome", "children"),
    Input("user-session", "data")
)
def update_user_welcome(session_data):
    if session_data.get('logged_in', False):
        username = session_data.get('username', '')
        role = session_data.get('role', '')
        region = session_data.get('region', '')
        mail = session_data.get('mail', '')

        welcome_text = f" Welcome, {username} ({role})"
        if region:
            welcome_text += f" | Region: {region}"
        if mail:
            welcome_text += f" | 📧 {mail}"

        return welcome_text
    return ""

@app.callback(
    Output("study-field-container", "style"),
    Output("admin-controls-section", "style"),
    Output("user-recent-entries-section", "style"),
    Input("user-session", "data")
)
def toggle_admin_features(session_data):
    if session_data.get('logged_in', False) and session_data.get('role') == 'admin':
        return {"display": "block"}, {"display": "block"}, {"display": "none"}
    elif session_data.get('logged_in', False) and session_data.get('role') == 'user':
        return {"display": "none"}, {"display": "none"}, {"display": "block"}
    return {"display": "none"}, {"display": "none"}, {"display": "none"}

@app.callback(
    Output("new-region", "options"),
    Output("new-region", "value"),
    Output("new-region", "disabled"),
    Input("user-session", "data")
)
def set_user_region(session_data):
    """Set region options based on user role"""
    if not session_data.get('logged_in', False):
        return [], None, False

    user_role = session_data.get('role', '')
    user_region = session_data.get('region', '')

    if user_role == 'admin':
        # Admin can see all regions
        regions = sorted(base_df["Region"].unique()) if not base_df.empty else []
        options = [{"label": region, "value": region} for region in regions]
        return options, None, False
    elif user_role == 'user' and user_region:
        # User can only see their assigned region
        options = [{"label": user_region, "value": user_region}]
        return options, user_region, True  # Disabled for users
    else:
        return [], None, False

@app.callback(
    Output("scheme-dropdown", "options"),
    Output("scheme-dropdown", "value"),
    Input("region-dropdown", "value")
)
def update_schemes(region):
    df = base_df[base_df["Region"] == region] if region and not base_df.empty else base_df
    schemes = sorted(df[COL_SCHEME].dropna().unique()) if not df.empty else []

    options = []
    for s in schemes:
        display_text = s
        if len(s) > 30:
            display_text = s[:27] + "..."

        options.append({
            "label": html.Div(display_text, title=s, style={"overflow": "hidden", "textOverflow": "ellipsis"}),
            "value": s
        })

    return options, None

@app.callback(
    Output("village-dropdown", "options"),
    Output("village-dropdown", "value"),
    Input("region-dropdown", "value"),
    Input("scheme-dropdown", "value")
)
def update_villages(region, scheme):
    df = base_df if not base_df.empty else pd.DataFrame()
    if region:
        df = df[df["Region"] == region]
    if scheme:
        df = df[df[COL_SCHEME] == scheme]
    villages = sorted(df[COL_VILLAGE].dropna().unique()) if not df.empty else []

    options = []
    for v in villages:
        display_text = v
        if len(v) > 30:
            display_text = v[:27] + "..."

        options.append({
            "label": html.Div(display_text, title=v, style={"overflow": "hidden", "textOverflow": "ellipsis"}),
            "value": v
        })

    return options, None

@app.callback(
    Output("reservoir-dropdown", "options"),
    Output("reservoir-dropdown", "value"),
    Input("region-dropdown", "value"),
    Input("scheme-dropdown", "value"),
    Input("village-dropdown", "value")
)
def update_reservoirs(region, scheme, village):
    df = base_df if not base_df.empty else pd.DataFrame()
    if region:
        df = df[df["Region"] == region]
    if scheme:
        df = df[df[COL_SCHEME] == scheme]
    if village:
        df = df[df[COL_VILLAGE] == village]
    reservoirs = sorted(df[COL_RESERVOIR].dropna().unique()) if not df.empty else []

    options = []
    for r in reservoirs:
        display_text = r
        if len(r) > 30:
            display_text = r[:27] + "..."

        options.append({
            "label": html.Div(display_text, title=r, style={"overflow": "hidden", "textOverflow": "ellipsis"}),
            "value": r
        })

    return options, None

# Add Entry Page Callbacks
@app.callback(
    Output("new-circle", "options"),
    Output("new-division", "options"),
    Output("new-subdivision", "options"),
    Output("new-block", "options"),
    Output("new-scheme", "options"),
    Input("new-region", "value"),
    Input("user-session", "data")
)
def update_region_dropdowns(region, session_data):
    if not region or base_df.empty:
        return [], [], [], [], []

    # For users, ensure they can only use their region
    if session_data.get('role') == 'user':
        user_region = session_data.get('region', '')
        if user_region and region != user_region:
            return [], [], [], [], []

    df = base_df[base_df["Region"] == region]

    circles = sorted(df[COL_CIRCLE].dropna().unique())
    divisions = sorted(df[COL_DIVISION].dropna().unique())
    subdivisions = sorted(df[COL_SUBDIVISION].dropna().unique())
    blocks = sorted(df[COL_BLOCK].dropna().unique())
    schemes = sorted(df[COL_SCHEME].dropna().unique())

    return (
        [{"label": c, "value": c} for c in circles],
        [{"label": d, "value": d} for d in divisions],
        [{"label": s, "value": s} for s in subdivisions],
        [{"label": b, "value": b} for b in blocks],
        [{"label": s, "value": s} for s in schemes]
    )

@app.callback(
    Output("new-village", "options"),
    Output("new-reservoir", "options"),
    Input("new-region", "value"),
    Input("new-scheme", "value"),
    Input("user-session", "data")
)
def update_village_reservoir_dropdowns(region, scheme, session_data):
    if not region or base_df.empty:
        return [], []

    # For users, ensure they can only use their region
    if session_data.get('role') == 'user':
        user_region = session_data.get('region', '')
        if user_region and region != user_region:
            return [], []

    df = base_df[base_df["Region"] == region]

    if scheme:
        df = df[df[COL_SCHEME] == scheme]

    villages = sorted(df[COL_VILLAGE].dropna().unique())
    reservoirs = sorted(df[COL_RESERVOIR].dropna().unique())

    village_options = [{"label": v, "value": v} for v in villages]
    village_options.append({"label": "✏️ Edit (Enter New)", "value": "EDIT"})

    reservoir_options = [{"label": r, "value": r} for r in reservoirs]
    reservoir_options.append({"label": "✏️ Edit (Enter New)", "value": "EDIT"})

    return village_options, reservoir_options

@app.callback(
    Output("new-village-input", "style"),
    Output("new-reservoir-input", "style"),
    Input("new-village", "value"),
    Input("new-reservoir", "value")
)
def toggle_input_fields(village, reservoir):
    village_style = {"marginBottom": "12px", "display": "block" if village == "EDIT" else "none"}
    reservoir_style = {"marginBottom": "12px", "display": "block" if reservoir == "EDIT" else "none"}
    return village_style, reservoir_style

@app.callback(
    Output("flow-topic-col", "style"),
    Output("cl-topic-col", "style"),
    Output("cl-type-col", "style"),
    Output("pressure-topic-col", "style"),
    Input("sensor-selection", "value")
)
def toggle_sensor_fields(selected_sensors):
    flow_style = {"display": "none"}
    cl_style = {"display": "none"}
    cl_type_style = {"display": "none"}
    pressure_style = {"display": "none"}

    if selected_sensors and "flow" in selected_sensors:
        flow_style = {"display": "block"}
    if selected_sensors and "cl" in selected_sensors:
        cl_style = {"display": "block"}
        cl_type_style = {"display": "block"}
    if selected_sensors and "pressure" in selected_sensors:
        pressure_style = {"display": "block"}

    return flow_style, cl_style, cl_type_style, pressure_style

def check_duplicate_topics(flow_topic, cl_topic, pressure_topic):
    """Check if topics already exist in the main data"""
    duplicates = []

    if flow_topic and flow_topic.strip():
        if flow_topic in flow_topics:
            duplicates.append(f"Flow topic: {flow_topic}")

    if cl_topic and cl_topic.strip():
        if cl_topic in cl_topics:
            duplicates.append(f"Chlorine topic: {cl_topic}")

    if pressure_topic and pressure_topic.strip():
        if pressure_topic in pressure_topics:
            duplicates.append(f"Pressure topic: {pressure_topic}")

    return duplicates

@app.callback(
    Output("btn-submit-entry", "disabled"),
    Output("new-remarks", "value"),
    Input("new-region", "value"),
    Input("new-circle", "value"),
    Input("new-division", "value"),
    Input("new-subdivision", "value"),
    Input("new-block", "value"),
    Input("new-scheme", "value"),
    Input("new-village", "value"),
    Input("new-village-input", "value"),
    Input("new-reservoir", "value"),
    Input("new-reservoir-input", "value"),
    Input("new-flow-topic", "value"),
    Input("new-cl-topic", "value"),
    Input("new-cl-type", "value"),
    Input("new-pressure-topic", "value"),
    Input("sensor-selection", "value"),
    Input("flow-topic-status", "children"),
    Input("cl-topic-status", "children"),
    Input("pressure-topic-status", "children"),
    Input("user-session", "data"),
    Input("new-study", "value")
)
def update_submit_button(region, circle, division, subdivision, block, scheme,
                        village, village_input, reservoir, reservoir_input,
                        flow_topic, cl_topic, cl_type, pressure_topic, sensor_selection,
                        flow_status, cl_status, pressure_status, session_data, study_value):

    # Check if user is admin and study field is required
    is_admin = session_data.get('role') == 'admin' if session_data else False

    if not all([region, circle, division, subdivision, block, scheme, sensor_selection]):
        return True, "❌ Please fill all required fields (*)"

    if not village or (village == "EDIT" and not village_input):
        return True, "❌ Please select or enter a village"

    if not reservoir or (reservoir == "EDIT" and not reservoir_input):
        return True, "❌ Please select or enter a reservoir"

    if "flow" in sensor_selection and not flow_topic:
        return True, "❌ Please provide Flow Meter topic"
    if "cl" in sensor_selection and not cl_topic:
        return True, "❌ Please provide Chlorine topic"
    if "pressure" in sensor_selection and not pressure_topic:
        return True, "❌ Please provide Pressure topic"
    if "cl" in sensor_selection and not cl_type:
        return True, "❌ Please select Chlorine type"

    # Check study field for admin
    if is_admin and (not study_value or study_value.strip() == ""):
        return True, "❌ Please fill Study field (required for admin)"

    duplicate_topics = check_duplicate_topics(flow_topic, cl_topic, pressure_topic)
    if duplicate_topics:
        return True, f"❌ Duplicate topics found in main file: {', '.join(duplicate_topics)}"

    status_messages = []
    if "flow" in sensor_selection and "✅" not in str(flow_status):
        status_messages.append("❌ Flow topic not communicating")
    if "cl" in sensor_selection and "✅" not in str(cl_status):
        status_messages.append("❌ Chlorine topic not communicating")
    if "pressure" in sensor_selection and "✅" not in str(pressure_status):
        status_messages.append("❌ Pressure topic not communicating")

    if status_messages:
        return True, "; ".join(status_messages)

    final_village = village_input if village == "EDIT" else village
    final_reservoir = reservoir_input if reservoir == "EDIT" else reservoir

    remarks_parts = []
    if "flow" in sensor_selection and "✅" in str(flow_status):
        remarks_parts.append("🌊 Flow: Communicating ✅")
    if "cl" in sensor_selection and "✅" in str(cl_status):
        remarks_parts.append("🧪 Chlorine: Communicating ✅")
    if "pressure" in sensor_selection and "✅" in str(pressure_status):
        remarks_parts.append("📊 Pressure: Communicating ✅")

    remarks = " | ".join(remarks_parts) if remarks_parts else "❌ No communication data"

    return False, remarks

def attach_latest(df_in, topic_col):
    """Add DateTime, Payload, and Remarks columns based on latest MQTT data"""
    df_local = df_in.copy()
    dt_vals, payload_vals, remark_vals, flow_vals, total_vals, cl_vals, csq_vals, package_vals = [], [], [], [], [], [], [], []

    for idx, row in df_local.iterrows():
        t = str(row[topic_col]).strip() if pd.notna(row[topic_col]) else ""
        if not t or t.lower() == 'nan' or t == 'None':
            dt_vals.append("")
            payload_vals.append("")
            cl_type = row.get(COL_TYPE_CL, "") if topic_col == COL_CL else None
            sensor_type = "pressure" if topic_col == COL_PRESSURE else None
            remark_vals.append("❌ NO")
            flow_vals.append("")
            total_vals.append("")
            cl_vals.append("")
            csq_vals.append("")
            package_vals.append("")
        else:
            rec = latest_store.get(t)
            if rec:
                dt_vals.append(rec["datetime"].strftime("%Y-%m-%d %H:%M:%S"))
                payload_vals.append(rec["payload"])
                cl_type = row.get(COL_TYPE_CL, "") if topic_col == COL_CL else None
                sensor_type = "pressure" if topic_col == COL_PRESSURE else None
                remark_vals.append(parse_payload_and_get_remarks(rec["payload"], cl_type, sensor_type))

                flow_vals.append(extract_value_from_payload(rec["payload"], "Flow"))
                total_vals.append(extract_value_from_payload(rec["payload"], "Total"))
                cl_vals.append(extract_value_from_payload(rec["payload"], "Cl"))
                csq_vals.append(extract_value_from_payload(rec["payload"], "CSQ"))

                if topic_col == COL_PRESSURE:
                    package_vals.append(count_pressure_packages(rec["payload"]))
                else:
                    package_vals.append("")
            else:
                dt_vals.append("")
                payload_vals.append("")
                cl_type = row.get(COL_TYPE_CL, "") if topic_col == COL_CL else None
                sensor_type = "pressure" if topic_col == COL_PRESSURE else None
                remark_vals.append("❌ NO")
                flow_vals.append("")
                total_vals.append("")
                cl_vals.append("")
                csq_vals.append("")
                package_vals.append("")

    df_local["Recent Communication"] = dt_vals
    df_local["Payload"] = payload_vals
    df_local["Communication Status"] = remark_vals
    df_local["Flow Rate"] = flow_vals
    df_local["Totalizer Value"] = total_vals
    df_local["CL Value"] = cl_vals
    df_local["CSQ"] = csq_vals

    if topic_col == COL_PRESSURE:
        df_local["Package Count"] = package_vals

    return df_local

def map_status_to_sensor_columns(row_data):
    """
    Map the Status value to the three sensor status columns based on which sensors are present.
    This function determines which sensors are present and applies the Status value accordingly.
    """
    status_value = row_data.get("Status", "")

    flow_status = ""
    cl_status = ""
    pressure_status = ""

    # Check which sensors are present (non-empty topics)
    has_flow = row_data.get(COL_FLOW) and str(row_data.get(COL_FLOW)).strip() not in ["", "nan", "None"]
    has_cl = row_data.get(COL_CL) and str(row_data.get(COL_CL)).strip() not in ["", "nan", "None"]
    has_pressure = row_data.get(COL_PRESSURE) and str(row_data.get(COL_PRESSURE)).strip() not in ["", "nan", "None"]

    # Apply status only to sensors that are present
    if has_flow:
        flow_status = status_value
    if has_cl:
        cl_status = status_value
    if has_pressure:
        pressure_status = status_value

    return {
        COL_FLOW_STATUS: flow_status,
        COL_CL_STATUS: cl_status,
        COL_PRESSURE_STATUS: pressure_status
    }

# Main refresh callback
@app.callback(
    Output("flow-table", "data"),
    Output("flow-table", "columns"),
    Output("cl-table", "data"),
    Output("cl-table", "columns"),
    Output("pressure-table", "data"),
    Output("pressure-table", "columns"),
    Output("last-update", "children"),
    Output("connection-duration", "children"),
    Output("pressure-next-update", "children"),
    Output("mqtt-status", "children"),
    Output("mqtt-status", "color"),
    Output("flow-total-count", "children"),
    Output("flow-communicating-count", "children"),
    Output("flow-nodata-count", "children"),
    Output("cl-total-count", "children"),
    Output("cl-communicating-count", "children"),
    Output("cl-nodata-count", "children"),
    Output("pressure-total-count", "children"),
    Output("pressure-communicating-count", "children"),
    Output("pressure-nodata-count", "children"),
    Output("flow-pie-chart", "figure"),
    Output("cl-pie-chart", "figure"),
    Output("pressure-pie-chart", "figure"),
    Input("refresh-interval", "n_intervals"),
    Input("fm-status-filter", "value"),
    Input("cl-status-filter", "value"),
    Input("pt-status-filter", "value"),
    Input("comm-status-filter", "value"),
    Input("table-search", "value"),
    Input("table-page-size", "value"),
    State("region-dropdown", "value"),
    State("scheme-dropdown", "value"),
    State("village-dropdown", "value"),
    State("reservoir-dropdown", "value"),
    State("user-session", "data")
)
def refresh_all(n, fm_status_filter, cl_status_filter, pt_status_filter, comm_filter, search_text, page_size, region, scheme, village, reservoir, session_data):
    global base_df

    latest = latest_store.snapshot()

    try:
        mqtt_connected = mqtt_client is not None and getattr(mqtt_client, "is_connected", lambda: True)()
    except Exception:
        mqtt_connected = False
    mqtt_status = "✅ MQTT Connected" if mqtt_connected else "❌ MQTT Disconnected"
    mqtt_color = "success" if mqtt_connected else "danger"

    connection_duration = latest_store.get_connection_duration()
    hours_connected = connection_duration.total_seconds() / 72000

    next_pressure_update = max(0, PRESSURE_UPDATE_HOURS - hours_connected)
    next_update_text = f"⏰ Next pressure data in: {next_pressure_update:.1f} hours"
    if next_pressure_update <= 0:
        next_update_text = "✅ Pressure data should be available now"

    df = base_df.copy() if not base_df.empty else pd.DataFrame()

    # For users, filter by their region
    if session_data.get('logged_in') and session_data.get('role') == 'user':
        user_region = session_data.get('region', '')
        if user_region:
            df = df[df["Region"] == user_region]

    if region:
        df = df[df["Region"] == region]
    if scheme:
        df = df[df[COL_SCHEME] == scheme]
    if village:
        df = df[df[COL_VILLAGE] == village]
    if reservoir:
        df = df[df[COL_RESERVOIR] == reservoir]

    # CORRECTED: Filter out rows with blank/null topics for each sensor type - EXCLUDE NULL/BLANK PROPERLY
    flow_df = df[df[COL_FLOW].notna() & (df[COL_FLOW] != "") & (df[COL_FLOW] != "nan") & (df[COL_FLOW] != "None")] if not df.empty else pd.DataFrame()
    cl_df = df[df[COL_CL].notna() & (df[COL_CL] != "") & (df[COL_CL] != "nan") & (df[COL_CL] != "None")] if not df.empty else pd.DataFrame()
    pressure_df = df[df[COL_PRESSURE].notna() & (df[COL_PRESSURE] != "") & (df[COL_PRESSURE] != "nan") & (df[COL_PRESSURE] != "None")] if not df.empty else pd.DataFrame()

    # Apply FM status filter
    if fm_status_filter and fm_status_filter != "All":
        if fm_status_filter == "Integrated":
            flow_df = flow_df[flow_df[COL_FLOW_STATUS] == "Integrated"] if not flow_df.empty else pd.DataFrame()
        elif fm_status_filter == "Returned to SI with comments":
            flow_df = flow_df[flow_df[COL_FLOW_STATUS] == "Returned to SI with comments"] if not flow_df.empty else pd.DataFrame()
        elif fm_status_filter == "In Progress":
            flow_df = flow_df[flow_df[COL_FLOW_STATUS] == "In Progress"] if not flow_df.empty else pd.DataFrame()

    # Apply CL status filter
    if cl_status_filter and cl_status_filter != "All":
        if cl_status_filter == "Integrated":
            cl_df = cl_df[cl_df[COL_CL_STATUS] == "Integrated"] if not cl_df.empty else pd.DataFrame()
        elif cl_status_filter == "Returned to SI with comments":
            cl_df = cl_df[cl_df[COL_CL_STATUS] == "Returned to SI with comments"] if not cl_df.empty else pd.DataFrame()
        elif cl_status_filter == "In Progress":
            cl_df = cl_df[cl_df[COL_CL_STATUS] == "In Progress"] if not cl_df.empty else pd.DataFrame()

    # Apply PT status filter
    if pt_status_filter and pt_status_filter != "All":
        if pt_status_filter == "Integrated":
            pressure_df = pressure_df[pressure_df[COL_PRESSURE_STATUS] == "Integrated"] if not pressure_df.empty else pd.DataFrame()
        elif pt_status_filter == "Returned to SI with comments":
            pressure_df = pressure_df[pressure_df[COL_PRESSURE_STATUS] == "Returned to SI with comments"] if not pressure_df.empty else pd.DataFrame()
        elif pt_status_filter == "In Progress":
            pressure_df = pressure_df[pressure_df[COL_PRESSURE_STATUS] == "In Progress"] if not pressure_df.empty else pd.DataFrame()

    # Add latest data to the DataFrames
    flow_df = attach_latest(flow_df, COL_FLOW) if not flow_df.empty else pd.DataFrame()
    cl_df = attach_latest(cl_df, COL_CL) if not cl_df.empty else pd.DataFrame()
    pressure_df = attach_latest(pressure_df, COL_PRESSURE) if not pressure_df.empty else pd.DataFrame()

    # Apply communication status filter
    if comm_filter and comm_filter != "All":
        if comm_filter == "YES":
            flow_df = flow_df[flow_df["Communication Status"].str.contains("YES", na=False)] if not flow_df.empty else pd.DataFrame()
            cl_df = cl_df[cl_df["Communication Status"].str.contains("YES", na=False)] if not cl_df.empty else pd.DataFrame()
            pressure_df = pressure_df[pressure_df["Communication Status"].str.contains("YES", na=False)] if not pressure_df.empty else pd.DataFrame()
        else:
            flow_df = flow_df[~flow_df["Communication Status"].str.contains("YES", na=False)] if not flow_df.empty else pd.DataFrame()
            cl_df = cl_df[~cl_df["Communication Status"].str.contains("YES", na=False)] if not cl_df.empty else pd.DataFrame()
            pressure_df = pressure_df[~pressure_df["Communication Status"].str.contains("YES", na=False)] if not pressure_df.empty else pd.DataFrame()

    # Apply search filter
    if search_text:
        search_lower = search_text.lower()
        def search_filter(row):
            return any(search_lower in str(val).lower() for val in row.values)

        if not flow_df.empty:
            flow_df = flow_df[flow_df.apply(search_filter, axis=1)]
        if not cl_df.empty:
            cl_df = cl_df[cl_df.apply(search_filter, axis=1)]
        if not pressure_df.empty:
            pressure_df = pressure_df[pressure_df.apply(search_filter, axis=1)]

    # CORRECTED: Count total, communicating and no data for flow - EXCLUDE NULL/BLANK PROPERLY
    flow_total = len(flow_df) if not flow_df.empty else 0
    flow_communicating = len(flow_df[flow_df["Communication Status"].str.contains("YES", na=False)]) if not flow_df.empty else 0
    flow_nodata = flow_total - flow_communicating

    # Create enhanced flow pie chart
    flow_pie_fig = go.Figure()

    if flow_total > 0:
        flow_pie_fig.add_trace(go.Pie(
            labels=["✅ Communicating", "❌ Not Communicating"],
            values=[flow_communicating, flow_nodata],
            hole=0.6,
            marker_colors=["#43a047", "#e53935"],
            textinfo="label+percent",
            textposition="inside",
            hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>",
            textfont=dict(size=14, color="white"),
            pull=[0.05, 0],
            domain={"x": [0, 1], "y": [0, 1]}
        ))
    else:
        flow_pie_fig.add_trace(go.Pie(
            labels=["📊 No Data"],
            values=[1],
            hole=0.6,
            marker_colors=["#bdbdbd"],
            textinfo="label",
            textposition="inside",
            textfont=dict(size=14, color="white")
        ))

    flow_pie_fig.update_layout(
        title=dict(
            text="🌊 Flow Communication Status",
            x=0.5,
            xanchor="center",
            font=dict(size=16, color="#37474f", family="Arial Black")
        ),
        showlegend=False,
        margin=dict(l=20, r=20, t=50, b=20),
        annotations=[
            dict(
                text=f"<b>{flow_total}</b>",
                x=0.5,
                y=0.5,
                font_size=22,
                showarrow=False,
                font=dict(color="#37474f")
            )
        ],
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=200
    )

    # CORRECTED: Count total, communicating and no data for chlorine - EXCLUDE NULL/BLANK PROPERLY
    cl_total = len(cl_df) if not cl_df.empty else 0
    cl_communicating = len(cl_df[cl_df["Communication Status"].str.contains("YES", na=False)]) if not cl_df.empty else 0
    cl_nodata = cl_total - cl_communicating

    # Create enhanced chlorine pie chart
    cl_pie_fig = go.Figure()

    if cl_total > 0:
        cl_pie_fig.add_trace(go.Pie(
            labels=["✅ Communicating", "❌ Not Communicating"],
            values=[cl_communicating, cl_nodata],
            hole=0.6,
            marker_colors=["#43a047", "#e53935"],
            textinfo="label+percent",
            textposition="inside",
            hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>",
            textfont=dict(size=14, color="white"),
            pull=[0.05, 0],
            domain={"x": [0, 1], "y": [0, 1]}
        ))
    else:
        cl_pie_fig.add_trace(go.Pie(
            labels=["📊 No Data"],
            values=[1],
            hole=0.6,
            marker_colors=["#bdbdbd"],
            textinfo="label",
            textposition="inside",
            textfont=dict(size=14, color="white")
        ))

    cl_pie_fig.update_layout(
        title=dict(
            text="🧪 Chlorine Communication Status",
            x=0.5,
            xanchor="center",
            font=dict(size=16, color="#37474f", family="Arial Black")
        ),
        showlegend=False,
        margin=dict(l=20, r=20, t=50, b=20),
        annotations=[
            dict(
                text=f"<b>{cl_total}</b>",
                x=0.5,
                y=0.5,
                font_size=22,
                showarrow=False,
                font=dict(color="#37474f")
            )
        ],
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=200
    )

    # CORRECTED: Count total, communicating and no data for pressure - EXCLUDE NULL/BLANK PROPERLY
    pressure_total = len(pressure_df) if not pressure_df.empty else 0
    pressure_communicating = len(pressure_df[pressure_df["Communication Status"].str.contains("YES", na=False)]) if not pressure_df.empty else 0
    pressure_nodata = pressure_total - pressure_communicating

    # Create enhanced pressure pie chart
    pressure_pie_fig = go.Figure()

    if pressure_total > 0:
        pressure_pie_fig.add_trace(go.Pie(
            labels=["✅ Communicating", "❌ Not Communicating"],
            values=[pressure_communicating, pressure_nodata],
            hole=0.6,
            marker_colors=["#43a047", "#e53935"],
            textinfo="label+percent",
            textposition="inside",
            hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>",
            textfont=dict(size=14, color="white"),
            pull=[0.05, 0],
            domain={"x": [0, 1], "y": [0, 1]}
        ))
    else:
        pressure_pie_fig.add_trace(go.Pie(
            labels=["📊 No Data"],
            values=[1],
            hole=0.6,
            marker_colors=["#bdbdbd"],
            textinfo="label",
            textposition="inside",
            textfont=dict(size=14, color="white")
        ))

    pressure_pie_fig.update_layout(
        title=dict(
            text="📊 Pressure Communication Status",
            x=0.5,
            xanchor="center",
            font=dict(size=16, color="#37474f", family="Arial Black")
        ),
        showlegend=False,
        margin=dict(l=20, r=20, t=50, b=20),
        annotations=[
            dict(
                text=f"<b>{pressure_total}</b>",
                x=0.5,
                y=0.5,
                font_size=22,
                showarrow=False,
                font=dict(color="#37474f")
            )
        ],
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=200
    )

    # Define column sequences for tables (including Status column)
    flow_cols = ["Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR, COL_FLOW, COL_FLOW_STATUS,"Communication Status", "Recent Communication", "Flow Rate", "Totalizer Value", "CSQ"]
    cl_cols = ["Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR, COL_CL, COL_TYPE_CL, COL_CL_STATUS, "Communication Status", "Recent Communication", "CL Value", "CSQ"]
    pressure_cols = ["Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR,COL_PRESSURE,COL_PRESSURE_STATUS, "Communication Status", "Recent Communication", "Package Count", "CSQ"]

    flow_data = flow_df[flow_cols].to_dict(orient="records") if not flow_df.empty else []
    cl_data = cl_df[cl_cols].to_dict(orient="records") if not cl_df.empty else []
    pressure_data = pressure_df[pressure_cols].to_dict(orient="records") if not pressure_df.empty else []

    # Set page size
    if flow_data:
        for row in flow_data:
            row['_dash_pagesize'] = page_size
    if cl_data:
        for row in cl_data:
            row['_dash_pagesize'] = page_size
    if pressure_data:
        for row in pressure_data:
            row['_dash_pagesize'] = page_size

    last_update = f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    connection_duration_str = f"⏱️ {hours_connected:.1f} hours"

    return (flow_data, make_columns(flow_cols),
            cl_data, make_columns(cl_cols),
            pressure_data, make_columns(pressure_cols),
            last_update, connection_duration_str, next_update_text,
            mqtt_status, mqtt_color,
            f"📊 Total Request Received: {flow_total}",
            f"✅ Communicating: {flow_communicating}",
            f"❌ Not Communicating: {flow_nodata}",
            f"📊 Total Request Received: {cl_total}",
            f"✅ Communicating: {cl_communicating}",
            f"❌ Not Communicating: {cl_nodata}",
            f"📊 Total Request Received: {pressure_total}",
            f"✅ Communicating: {pressure_communicating}",
            f"❌ Not Communicating: {pressure_nodata}",
            flow_pie_fig,
            cl_pie_fig,
            pressure_pie_fig)

# Update KPI cards
@app.callback(
    Output("selected-flow-topic", "children"),
    Output("flow-datetime", "children"),
    Output("flow-value", "children"),
    Output("flow-total", "children"),
    Output("flow-remarks", "children"),
    Output("flow-json", "children"),
    Input("flow-topic-dropdown", "value"),
    Input("refresh-interval", "n_intervals")
)
def update_flow_topic(topic, n):
    if not topic:
        return "📡 No topic selected", "📊 No data", "📊 No data", "📊 No data", "📊 No data", "📊 No data"
    rec = latest_store.get(topic)
    if rec:
        payload = rec["payload"]
        try:
            json_pretty = json.dumps(json.loads(payload), indent=2)
        except:
            json_pretty = payload

        data_age = datetime.now() - rec["datetime"]
        hours_old = data_age.total_seconds() / 3600
        age_note = f" ({hours_old:.1f}h ago)" if hours_old > 1 else ''

        return (
            topic,
            rec["datetime"].strftime("%Y-%m-%d %H:%M:%S") + age_note,
            extract_value_from_payload(payload, "Flow"),
            extract_value_from_payload(payload, "Total"),
            parse_payload_and_get_remarks(payload),
            json_pretty
        )
    return topic, "📊 No data", "📊 No data", "📊 No data", "📊 No data", "📊 No data"

@app.callback(
    Output("selected-cl-topic", "children"),
    Output("cl-datetime", "children"),
    Output("cl-value", "children"),
    Output("cl-csq", "children"),
    Output("cl-remarks", "children"),
    Output("cl-json", "children"),
    Input("cl-topic-dropdown", "value"),
    Input("refresh-interval", "n_intervals")
)
def update_cl_topic(topic, n):
    if not topic:
        return "📡 No topic selected", "📊 No data", "📊 No data", "📊 No data", "📊 No data", "📊 No data"
    rec = latest_store.get(topic)
    if rec:
        payload = rec["payload"]
        try:
            json_pretty = json.dumps(json.loads(payload), indent=2)
        except:
            json_pretty = payload

        data_age = datetime.now() - rec["datetime"]
        hours_old = data_age.total_seconds() / 3600
        age_note = f" ({hours_old:.1f}h ago)" if hours_old > 1 else ''

        return (
            topic,
            rec["datetime"].strftime("%Y-%m-%d %H:%M:%S") + age_note,
            extract_value_from_payload(payload, "Cl"),
            extract_value_from_payload(payload, "CSQ"),
            parse_payload_and_get_remarks(payload),
            json_pretty
        )
    return topic, "📊 No data", "📊 No data", "📊 No data", "📊 No data", "📊 No data"

@app.callback(
    Output("selected-pressure-topic", "children"),
    Output("pressure-datetime", "children"),
    Output("pressure-value", "children"),
    Output("pressure-csq", "children"),
    Output("pressure-packages", "children"),
    Output("pressure-remarks", "children"),
    Output("pressure-json", "children"),
    Input("pressure-topic-dropdown", "value"),
    Input("refresh-interval", "n_intervals")
)
def update_pressure_topic(topic, n):
    if not topic:
        return "📡 No topic selected", "📊 No data", "📊 No data", "📊 No data", "📊 No data", "📊 No data", "📊 No data"
    rec = latest_store.get(topic)
    if rec:
        payload = rec["payload"]
        try:
            json_pretty = json.dumps(json.loads(payload), indent=2)
        except:
            json_pretty = payload

        data_age = datetime.now() - rec["datetime"]
        hours_old = data_age.total_seconds() / 3600
        age_note = f" ({hours_old:.1f}h ago)" if hours_old > 0.1 else ''

        return (
            topic,
            rec["datetime"].strftime("%Y-%m-%d %H:%M:%S") + age_note,
            extract_value_from_payload(payload, "Pressure"),
            extract_value_from_payload(payload, "CSQ"),
            count_pressure_packages(payload),
            parse_payload_and_get_remarks(payload, sensor_type="pressure"),
            json_pretty
        )

    connection_duration = latest_store.get_connection_duration()
    hours_connected = connection_duration.total_seconds() / 3600
    time_until_update = max(0, PRESSURE_UPDATE_HOURS - hours_connected)

    if time_until_update > 0:
        status_msg = f"⏳ Waiting for data ({time_until_update:.1f}h remaining)"
    else:
        status_msg = "✅ Data expected soon"

    return topic, status_msg, "⏳ Waiting...", "⏳ Waiting...", "0", "📊 Pressure sensor sends data every 12 hours", "📊 No data received yet"

# Excel download callback
@app.callback(
    Output("download-excel", "data"),
    Input("btn-download-excel", "n_clicks"),
    State("region-dropdown", "value"),
    State("scheme-dropdown", "value"),
    State("village-dropdown", "value"),
    State("reservoir-dropdown", "value"),
    prevent_initial_call=True
)
def download_excel(n_clicks, region, scheme, village, reservoir):
    df = base_df.copy() if not base_df.empty else pd.DataFrame()
    if region:
        df = df[df["Region"] == region]
    if scheme:
        df = df[df[COL_SCHEME] == scheme]
    if village:
        df = df[df[COL_VILLAGE] == village]
    if reservoir:
        df = df[df[COL_RESERVOIR] == reservoir]

    flow_df = df[df[COL_FLOW].notna() & (df[COL_FLOW] != "") & (df[COL_FLOW] != "nan") & (df[COL_FLOW] != "None")] if not df.empty else pd.DataFrame()
    cl_df = df[df[COL_CL].notna() & (df[COL_CL] != "") & (df[COL_CL] != "nan") & (df[COL_CL] != "None")] if not df.empty else pd.DataFrame()
    pressure_df = df[df[COL_PRESSURE].notna() & (df[COL_PRESSURE] != "") & (df[COL_PRESSURE] != "nan") & (df[COL_PRESSURE] != "None")] if not df.empty else pd.DataFrame()

    flow_df = attach_latest(flow_df, COL_FLOW) if not flow_df.empty else pd.DataFrame()
    cl_df = attach_latest(cl_df, COL_CL) if not cl_df.empty else pd.DataFrame()
    pressure_df = attach_latest(pressure_df, COL_PRESSURE) if not pressure_df.empty else pd.DataFrame()

    flow_cols = ["Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR, COL_FLOW, COL_FLOW_STATUS, "Communication Status", "Recent Communication", "Flow Rate", "Totalizer Value", "CSQ"]
    cl_cols = ["Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR, COL_CL, COL_TYPE_CL, COL_CL_STATUS, "Communication Status", "Recent Communication", "CL Value", "CSQ"]
    pressure_cols = ["Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR, COL_PRESSURE, COL_PRESSURE_STATUS, "Communication Status", "Recent Communication", "Package Count", "CSQ"]

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        if not flow_df.empty:
            flow_df[flow_cols].to_excel(writer, sheet_name='Flow Data', index=False)
        if not cl_df.empty:
            cl_df[cl_cols].to_excel(writer, sheet_name='Chlorine Data', index=False)
        if not pressure_df.empty:
            pressure_df[pressure_cols].to_excel(writer, sheet_name='Pressure Data', index=False)

    buffer.seek(0)
    return dcc.send_bytes(buffer.getvalue(), "JJM_Data.xlsx")

# Add entry page callbacks
@app.callback(
    Output("flow-topic-status", "children"),
    Output("cl-topic-status", "children"),
    Output("pressure-topic-status", "children"),
    Input("btn-check-topics", "n_clicks"),
    State("new-flow-topic", "value"),
    State("new-cl-topic", "value"),
    State("new-pressure-topic", "value"),
    State("new-cl-type", "value"),
    State("sensor-selection", "value"),
    prevent_initial_call=True
)
def check_topics(n_clicks, flow_topic, cl_topic, pressure_topic, cl_type, sensor_selection):
    if n_clicks is None:
        return "", "", ""

    flow_status = ""
    cl_status = ""
    pressure_status = ""

    if sensor_selection and "flow" in sensor_selection and flow_topic:
        # Subscribe to the topic if not already subscribed
        subscribe_to_new_topic(flow_topic)

        # Check for existing data
        rec = latest_store.get(flow_topic)
        if rec:
            # Check if data is recent (within 10 minutes)
            data_age = datetime.now() - rec["datetime"]
            if data_age.total_seconds() <= 600:  # 10 minutes
                remarks = parse_payload_and_get_remarks(rec["payload"])
                if "YES" in remarks:
                    flow_status = html.Span("✅ Communicating (Recent Data)", style={"color": "green", "fontWeight": "bold"})
                else:
                    flow_status = html.Span("❌ Not Communicating", style={"color": "red", "fontWeight": "bold"})
            else:
                # Data is older but still shows communication
                remarks = parse_payload_and_get_remarks(rec["payload"])
                if "YES" in remarks:
                    time_diff = data_age.total_seconds() / 60  # minutes
                    flow_status = html.Span(f"✅ Communicating (Data from {rec['datetime'].strftime('%H:%M')} - {time_diff:.0f} min ago)", style={"color": "orange", "fontWeight": "bold"})
                else:
                    flow_status = html.Span("❌ Not Communicating", style={"color": "red", "fontWeight": "bold"})
        else:
            flow_status = html.Span("⏳ Waiting for data... (Click Check Again)", style={"color": "orange", "fontWeight": "bold"})

    if sensor_selection and "cl" in sensor_selection and cl_topic:
        # Subscribe to the topic if not already subscribed
        subscribe_to_new_topic(cl_topic)

        rec = latest_store.get(cl_topic)
        if rec:
            # Check if data is recent (within 10 minutes)
            data_age = datetime.now() - rec["datetime"]
            if data_age.total_seconds() <= 600:  # 10 minutes
                remarks = parse_payload_and_get_remarks(rec["payload"], cl_type)
                if "YES" in remarks:
                    cl_status = html.Span("✅ Communicating (Recent Data)", style={"color": "green", "fontWeight": "bold"})
                else:
                    cl_status = html.Span("❌ Not Communicating", style={"color": "red", "fontWeight": "bold"})
            else:
                # Data is older but still shows communication
                remarks = parse_payload_and_get_remarks(rec["payload"], cl_type)
                if "YES" in remarks:
                    time_diff = data_age.total_seconds() / 60  # minutes
                    cl_status = html.Span(f"✅ Communicating (Data from {rec['datetime'].strftime('%H:%M')} - {time_diff:.0f} min ago)", style={"color": "orange", "fontWeight": "bold"})
                else:
                    cl_status = html.Span("❌ Not Communicating", style={"color": "red", "fontWeight": "bold"})
        else:
            cl_status = html.Span("⏳ Waiting for data... (Click Check Again)", style={"color": "orange", "fontWeight": "bold"})

    if sensor_selection and "pressure" in sensor_selection and pressure_topic:
        # Subscribe to the topic if not already subscribed
        subscribe_to_new_topic(pressure_topic)

        rec = latest_store.get(pressure_topic)
        if rec:
            # Check if data is recent (within 12 hours for pressure sensors)
            data_age = datetime.now() - rec["datetime"]
            if data_age.total_seconds() <= 43200:  # 12 hours in seconds
                remarks = parse_payload_and_get_remarks(rec["payload"], sensor_type="pressure")
                if "YES" in remarks:
                    pressure_status = html.Span("✅ Communicating (Recent Data)", style={"color": "green", "fontWeight": "bold"})
                else:
                    pressure_status = html.Span("❌ Not Communicating", style={"color": "red", "fontWeight": "bold"})
            else:
                # Data is older but still shows communication
                remarks = parse_payload_and_get_remarks(rec["payload"], sensor_type="pressure")
                if "YES" in remarks:
                    time_diff = data_age.total_seconds() / 3600  # hours
                    pressure_status = html.Span(f"✅ Communicating (Data from {rec['datetime'].strftime('%H:%M')} - {time_diff:.1f}h ago)", style={"color": "orange", "fontWeight": "bold"})
                else:
                    pressure_status = html.Span("❌ Not Communicating", style={"color": "red", "fontWeight": "bold"})
        else:
            pressure_status = html.Span("⏳ Waiting for data... (Click Check Again)", style={"color": "orange", "fontWeight": "bold"})

    return flow_status, cl_status, pressure_status

@app.callback(
    Output("save-status", "children"),
    Input("btn-save-changes", "n_clicks"),
    State("new-entries-table", "data"),
    State("user-session", "data"),
    prevent_initial_call=True
)
def save_changes(n_clicks, table_data, session_data):
    if n_clicks is None or not table_data:
        return ""

    try:
        username = session_data.get('username', 'Unknown')

        for row in table_data:
            sr_no = row.get(COL_SR_NO)
            if sr_no:
                # Map the Status value to sensor status columns
                sensor_status_mapping = map_status_to_sensor_columns(row)

                # Update the row with mapped status values
                row.update(sensor_status_mapping)

                # Update the entry in database
                success = update_entry_in_db(row)
                if not success:
                    return dbc.Alert(f"❌ Error updating entry with SR No: {sr_no}", color="danger")

                # Log the activity
                log_user_activity(username, "Update Entry", f"Updated entry SR No: {sr_no}")

        # Reload the base data to reflect changes
        global base_df
        base_df = load_combined_data()

        return dbc.Alert("✅ Changes saved successfully! The main tables will update automatically.", color="success")

    except Exception as e:
        return dbc.Alert(f"❌ Error saving changes: {str(e)}", color="danger")

@app.callback(
    Output("submit-status", "children"),
    Output("new-entries-table", "data"),
    Output("new-entries-table", "columns"),
    Output("user-recent-entries-table", "data"),
    Output("user-recent-entries-table", "columns"),
    Input("btn-submit-entry", "n_clicks"),
    Input("status-filter", "value"),
    Input("search-new-entries", "value"),
    Input("page-size-new-entries", "value"),
    Input("user-status-filter", "value"),
    Input("user-search-entries", "value"),
    Input("user-page-size", "value"),
    State("new-region", "value"),
    State("new-circle", "value"),
    State("new-division", "value"),
    State("new-subdivision", "value"),
    State("new-block", "value"),
    State("new-scheme", "value"),
    State("new-village", "value"),
    State("new-village-input", "value"),
    State("new-reservoir", "value"),
    State("new-reservoir-input", "value"),
    State("new-flow-topic", "value"),
    State("new-cl-topic", "value"),
    State("new-cl-type", "value"),
    State("new-pressure-topic", "value"),
    State("new-status", "value"),
    State("sensor-selection", "value"),
    State("new-message-type", "value"),
    State("new-remarks", "value"),
    State("user-session", "data"),
    State("new-study", "value"),
    prevent_initial_call=True
)
def submit_entry(n_clicks, status_filter, search_text, page_size, user_status_filter, user_search_text, user_page_size, region, circle, division, subdivision, block,
                scheme, village, village_input, reservoir, reservoir_input,
                flow_topic, cl_topic, cl_type, pressure_topic, status, sensor_selection, message_type, remarks, session_data, study_value):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # If triggered by filters/search, just update the tables
    if triggered_id in ['status-filter', 'search-new-entries', 'page-size-new-entries', 'user-status-filter', 'user-search-entries', 'user-page-size']:
        new_entries_df = load_data_from_db(new_entries_table_name)

        # Admin table
        admin_df = new_entries_df.copy()
        if not admin_df.empty:
            # Apply status filter
            if status_filter and status_filter != "All":
                admin_df = admin_df[admin_df["Status"] == status_filter]

            # Apply search filter
            if search_text:
                search_lower = search_text.lower()
                def search_filter(row):
                    return any(search_lower in str(val).lower() for val in row.values)
                admin_df = admin_df[admin_df.apply(search_filter, axis=1)]

            # Select display columns - include Status column for editing
            display_cols = [COL_SR_NO, "Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR,
                           "Status", COL_FLOW, COL_CL, COL_PRESSURE, "Added Date"]

            # Ensure all columns exist
            for col in display_cols:
                if col not in admin_df.columns:
                    admin_df[col] = ""

            admin_table_data = admin_df[display_cols].to_dict(orient="records")
            admin_table_columns = make_columns(display_cols)
        else:
            admin_table_data = []
            admin_table_columns = []

        # User table - filtered by user's region
        user_df = new_entries_df.copy()
        if session_data.get('logged_in') and session_data.get('role') == 'user':
            user_region = session_data.get('region', '')
            if user_region:
                user_df = user_df[user_df["Region"] == user_region]

        if not user_df.empty:
            # Apply status filter
            if user_status_filter and user_status_filter != "All":
                user_df = user_df[user_df["Status"] == user_status_filter]

            # Apply search filter
            if user_search_text:
                search_lower = user_search_text.lower()
                def search_filter(row):
                    return any(search_lower in str(val).lower() for val in row.values)
                user_df = user_df[user_df.apply(search_filter, axis=1)]

            # Select display columns
            user_display_cols = [COL_SR_NO, "Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR,
                               "Status", COL_FLOW, COL_CL, COL_PRESSURE, "Added Date"]

            # Ensure all columns exist
            for col in user_display_cols:
                if col not in user_df.columns:
                    user_df[col] = ""

            user_table_data = user_df[user_display_cols].to_dict(orient="records")
            user_table_columns = make_columns(user_display_cols)
        else:
            user_table_data = []
            user_table_columns = []

        return "", admin_table_data, admin_table_columns, user_table_data, user_table_columns

    # If triggered by submit button
    if n_clicks is None:
        return "", [], [], [], []

    # Get final village and reservoir values
    final_village = village_input if village == "EDIT" else village
    final_reservoir = reservoir_input if reservoir == "EDIT" else reservoir

    # Map status to sensor status columns using the helper function
    sensor_status_mapping = map_status_to_sensor_columns({
        "Status": status,
        COL_FLOW: flow_topic if sensor_selection and "flow" in sensor_selection else "",
        COL_CL: cl_topic if sensor_selection and "cl" in sensor_selection else "",
        COL_PRESSURE: pressure_topic if sensor_selection and "pressure" in sensor_selection else ""
    })

    # Create new entry
    new_entry = {
        "Region": region or "",
        COL_CIRCLE: circle or "",
        COL_DIVISION: division or "",
        COL_SUBDIVISION: subdivision or "",
        COL_BLOCK: block or "",
        COL_SCHEME: scheme or "",
        COL_VILLAGE: final_village or "",
        COL_RESERVOIR: final_reservoir or "",
        "Status": status or "submitted",
        "Message Type": message_type or "MQTT",
        COL_FLOW: flow_topic if sensor_selection and "flow" in sensor_selection else "",
        COL_CL: cl_topic if sensor_selection and "cl" in sensor_selection else "",
        COL_TYPE_CL: cl_type if sensor_selection and "cl" in sensor_selection else "",
        COL_PRESSURE: pressure_topic if sensor_selection and "pressure" in sensor_selection else "",
        "Remarks": remarks or "",
        "Added Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Add study field if user is admin
    if session_data.get('role') == 'admin':
        new_entry[COL_STUDY] = study_value or ""

    # Add the mapped sensor status values
    new_entry.update(sensor_status_mapping)

    try:
        # Save to database
        success = save_new_entry_to_db(new_entry)

        if success:
            # Log the activity
            username = session_data.get('username', 'Unknown')
            log_user_activity(username, "Add New Entry", f"Added entry for {final_village} - {final_reservoir}")

            # Reload the base data to include the new entry
            global base_df
            base_df = load_combined_data()

            # Load and display the new entries in both tables
            new_entries_df = load_data_from_db(new_entries_table_name)

            # Admin table
            admin_df = new_entries_df.copy()
            if not admin_df.empty:
                display_cols = [COL_SR_NO, "Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR,
                               "Status", COL_FLOW, COL_CL, COL_PRESSURE, "Added Date"]

                for col in display_cols:
                    if col not in admin_df.columns:
                        admin_df[col] = ""

                admin_table_data = admin_df[display_cols].to_dict(orient="records")
                admin_table_columns = make_columns(display_cols)
            else:
                admin_table_data = []
                admin_table_columns = []

            # User table - filtered by user's region
            user_df = new_entries_df.copy()
            if session_data.get('logged_in') and session_data.get('role') == 'user':
                user_region = session_data.get('region', '')
                if user_region:
                    user_df = user_df[user_df["Region"] == user_region]

            if not user_df.empty:
                user_display_cols = [COL_SR_NO, "Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR,
                                   "Status", COL_FLOW, COL_CL, COL_PRESSURE, "Added Date"]

                for col in user_display_cols:
                    if col not in user_df.columns:
                        user_df[col] = ""

                user_table_data = user_df[user_display_cols].to_dict(orient="records")
                user_table_columns = make_columns(user_display_cols)
            else:
                user_table_data = []
                user_table_columns = []

            return dbc.Alert("✅ Entry submitted successfully! The new entry will now appear in the main tables.", color="success"), admin_table_data, admin_table_columns, user_table_data, user_table_columns
        else:
            return dbc.Alert("❌ Error saving entry to database.", color="danger"), [], [], [], []
    except Exception as e:
        return dbc.Alert(f"❌ Error submitting entry: {str(e)}", color="danger"), [], [], [], []

# Manual reload callback for main data
@app.callback(
    Output("base-df-json", "data"),
    Input("btn-submit-entry", "n_clicks"),
    Input("btn-save-changes", "n_clicks"),
    prevent_initial_call=True
)
def reload_main_data(n_clicks1, n_clicks2):
    """Manually reload main data only when explicitly triggered"""
    if n_clicks1 or n_clicks2:
        global base_df, flow_topics, cl_topics, pressure_topics, all_topics
        base_df = load_combined_data()

        # Update topics lists - EXCLUDE NULL/BLANK PROPERLY
        flow_topics = sorted({t for t in base_df[COL_FLOW].astype(str).unique()
                             if t and t != 'nan' and t != '' and t != 'None'}) if not base_df.empty else []
        cl_topics = sorted({t for t in base_df[COL_CL].astype(str).unique()
                           if t and t != 'nan' and t != '' and t != 'None'}) if not base_df.empty else []
        pressure_topics = sorted({t for t in base_df[COL_PRESSURE].astype(str).unique()
                                if t and t != 'nan' and t != '' and t != 'None'}) if not base_df.empty else []
        all_topics = sorted(set(flow_topics + cl_topics + pressure_topics))

        return base_df.to_dict(orient="records") if not base_df.empty else []
    return dash.no_update


# ================== ANALYSIS PAGE CALLBACKS ==================
@app.callback(
    Output("analysis-total-count", "children"),
    Output("analysis-communicating-count", "children"),
    Output("analysis-not-communicating-count", "children"),
    Output("analysis-inprogress-count", "children"),
    Output("analysis-returned-count", "children"),
    Output("analysis-integrated-count", "children"),
    Output("analysis-integrated-not-comm-count", "children"),  # NEW OUTPUT
    Output("analysis-table", "data"),
    Output("analysis-table", "columns"),
    Output("analysis-active-filter", "children"),
    Output("analysis-filter-store", "data"),
    Input("refresh-interval", "n_intervals"),
    Input("analysis-region", "value"),
    Input("analysis-sensor-type", "value"),
    Input("analysis-search", "value"),
    Input("analysis-page-size", "value"),
    Input("analysis-total-card", "n_clicks"),
    Input("analysis-communicating-card", "n_clicks"),
    Input("analysis-not-communicating-card", "n_clicks"),
    Input("analysis-inprogress-card", "n_clicks"),
    Input("analysis-returned-card", "n_clicks"),
    Input("analysis-integrated-card", "n_clicks"),
    Input("analysis-integrated-not-comm-card", "n_clicks"),  # NEW INPUT
    State("analysis-filter-store", "data")
)
def update_analysis(n, region, sensor_type, search_text, page_size,
                   total_clicks, comm_clicks, not_comm_clicks,
                   inprogress_clicks, returned_clicks, integrated_clicks,
                   integrated_not_comm_clicks,  # NEW INPUT
                   filter_store):
    ctx = callback_context
    if not ctx.triggered:
        return "", "", "", "", "", "", "", [], [], "All Data", filter_store

    # Get the triggered component ID
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # Start with base data
    df = base_df.copy() if not base_df.empty else pd.DataFrame()

    # Apply region filter
    if region and region != "All":
        df = df[df["Region"] == region]

    # Apply sensor type filter and prepare data
    if sensor_type == "flow":
        df = df[df[COL_FLOW].notna() & (df[COL_FLOW] != "") & (df[COL_FLOW] != "nan") & (df[COL_FLOW] != "None")] if not df.empty else pd.DataFrame()
        df = attach_latest(df, COL_FLOW) if not df.empty else pd.DataFrame()
        display_cols = ["Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR, COL_FLOW,
                       COL_FLOW_STATUS, "Communication Status", "Recent Communication",
                       "Flow Rate", "Totalizer Value", "CSQ"]
        status_col = COL_FLOW_STATUS
        sensor_name = "Flow Meter"
    elif sensor_type == "cl":
        df = df[df[COL_CL].notna() & (df[COL_CL] != "") & (df[COL_CL] != "nan") & (df[COL_CL] != "None")] if not df.empty else pd.DataFrame()
        df = attach_latest(df, COL_CL) if not df.empty else pd.DataFrame()
        display_cols = ["Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR, COL_CL, COL_TYPE_CL,
                       COL_CL_STATUS, "Communication Status", "Recent Communication",
                       "CL Value", "CSQ"]
        status_col = COL_CL_STATUS
        sensor_name = "Chlorine Sensor"
    elif sensor_type == "pressure":
        df = df[df[COL_PRESSURE].notna() & (df[COL_PRESSURE] != "") & (df[COL_PRESSURE] != "nan") & (df[COL_PRESSURE] != "None")] if not df.empty else pd.DataFrame()
        df = attach_latest(df, COL_PRESSURE) if not df.empty else pd.DataFrame()
        display_cols = ["Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR, COL_PRESSURE,
                       COL_PRESSURE_STATUS, "Communication Status", "Recent Communication",
                       "Package Count", "CSQ"]
        status_col = COL_PRESSURE_STATUS
        sensor_name = "Pressure Sensor"
    else:
        # All sensors - combine data from all three types
        flow_df = df[df[COL_FLOW].notna() & (df[COL_FLOW] != "") & (df[COL_FLOW] != "nan") & (df[COL_FLOW] != "None")] if not df.empty else pd.DataFrame()
        cl_df = df[df[COL_CL].notna() & (df[COL_CL] != "") & (df[COL_CL] != "nan") & (df[COL_CL] != "None")] if not df.empty else pd.DataFrame()
        pressure_df = df[df[COL_PRESSURE].notna() & (df[COL_PRESSURE] != "") & (df[COL_PRESSURE] != "nan") & (df[COL_PRESSURE] != "None")] if not df.empty else pd.DataFrame()

        # Add latest data to each
        flow_df = attach_latest(flow_df, COL_FLOW) if not flow_df.empty else pd.DataFrame()
        cl_df = attach_latest(cl_df, COL_CL) if not cl_df.empty else pd.DataFrame()
        pressure_df = attach_latest(pressure_df, COL_PRESSURE) if not pressure_df.empty else pd.DataFrame()

        # Combine all data
        all_dfs = []
        if not flow_df.empty:
            flow_df['Sensor_Type'] = 'Flow Meter'
            all_dfs.append(flow_df)
        if not cl_df.empty:
            cl_df['Sensor_Type'] = 'Chlorine Sensor'
            all_dfs.append(cl_df)
        if not pressure_df.empty:
            pressure_df['Sensor_Type'] = 'Pressure Sensor'
            all_dfs.append(pressure_df)

        if all_dfs:
            df = pd.concat(all_dfs, ignore_index=True)
            display_cols = ["Region", COL_SCHEME, COL_VILLAGE, COL_RESERVOIR, "Sensor_Type",
                           "Communication Status", "Recent Communication"]
            status_col = "Status"
            sensor_name = "All Sensors"
        else:
            df = pd.DataFrame()
            display_cols = []
            status_col = ""
            sensor_name = "All Sensors"

    # Store the current filtered data for counting
    current_filtered_data = df.copy()

    # Handle card clicks for filtering
    active_filter = "All Data"
    if trigger_id == "analysis-communicating-card" and comm_clicks:
        df = df[df["Communication Status"].str.contains("YES", na=False)] if not df.empty else pd.DataFrame()
        active_filter = "Communicating"
    elif trigger_id == "analysis-not-communicating-card" and not_comm_clicks:
        df = df[~df["Communication Status"].str.contains("YES", na=False)] if not df.empty else pd.DataFrame()
        active_filter = "Not Communicating"
    elif trigger_id == "analysis-inprogress-card" and inprogress_clicks:
        df = df[df[status_col] == "In Progress"] if not df.empty else pd.DataFrame()
        active_filter = "In Progress"
    elif trigger_id == "analysis-returned-card" and returned_clicks:
        df = df[df[status_col] == "Returned to SI with comments"] if not df.empty else pd.DataFrame()
        active_filter = "Returned to SI"
    elif trigger_id == "analysis-integrated-card" and integrated_clicks:
        df = df[df[status_col] == "Integrated"] if not df.empty else pd.DataFrame()
        active_filter = "Integrated"
    elif trigger_id == "analysis-integrated-not-comm-card" and integrated_not_comm_clicks:  # NEW FILTER
        # Filter for sensors that are Integrated but NOT communicating
        df = df[(df[status_col] == "Integrated") & (~df["Communication Status"].str.contains("YES", na=False))] if not df.empty else pd.DataFrame()
        active_filter = "Integrated but Not Communicating"
    elif trigger_id == "analysis-total-card" and total_clicks:
        # Show all data - no additional filtering
        active_filter = "All Data"

    # Apply search filter
    if search_text:
        search_lower = search_text.lower()
        def search_filter(row):
            return any(search_lower in str(val).lower() for val in row.values)
        df = df[df.apply(search_filter, axis=1)] if not df.empty else pd.DataFrame()

    # Calculate counts from the current filtered data (before card filtering)
    total_count = len(current_filtered_data) if not current_filtered_data.empty else 0
    communicating_count = len(current_filtered_data[current_filtered_data["Communication Status"].str.contains("YES", na=False)]) if not current_filtered_data.empty else 0
    not_communicating_count = total_count - communicating_count

    # Calculate status counts
    if sensor_type == "all":
        # For all sensors, we need to check each sensor's status column
        inprogress_count = 0
        returned_count = 0
        integrated_count = 0
        integrated_not_comm_count = 0  # NEW COUNT

        if not current_filtered_data.empty:
            for _, row in current_filtered_data.iterrows():
                sensor_type_row = row.get('Sensor_Type', '')
                if sensor_type_row == 'Flow Meter':
                    status_val = row.get(COL_FLOW_STATUS, '')
                    comm_status = row.get("Communication Status", "")
                elif sensor_type_row == 'Chlorine Sensor':
                    status_val = row.get(COL_CL_STATUS, '')
                    comm_status = row.get("Communication Status", "")
                elif sensor_type_row == 'Pressure Sensor':
                    status_val = row.get(COL_PRESSURE_STATUS, '')
                    comm_status = row.get("Communication Status", "")
                else:
                    status_val = ''
                    comm_status = ''

                if status_val == "In Progress":
                    inprogress_count += 1
                elif status_val == "Returned to SI with comments":
                    returned_count += 1
                elif status_val == "Integrated":
                    integrated_count += 1
                    # Check if integrated but not communicating
                    if "YES" not in comm_status:
                        integrated_not_comm_count += 1
    else:
        # For specific sensor types
        inprogress_count = len(current_filtered_data[current_filtered_data[status_col] == "In Progress"]) if not current_filtered_data.empty else 0
        returned_count = len(current_filtered_data[current_filtered_data[status_col] == "Returned to SI with comments"]) if not current_filtered_data.empty else 0
        integrated_count = len(current_filtered_data[current_filtered_data[status_col] == "Integrated"]) if not current_filtered_data.empty else 0
        # NEW: Count integrated but not communicating
        integrated_not_comm_count = len(current_filtered_data[
            (current_filtered_data[status_col] == "Integrated") &
            (~current_filtered_data["Communication Status"].str.contains("YES", na=False))
        ]) if not current_filtered_data.empty else 0

    # Prepare table data
    if not df.empty:
        # Ensure all display columns exist
        for col in display_cols:
            if col not in df.columns:
                df[col] = ""

        table_data = df[display_cols].to_dict(orient="records")
        table_columns = make_columns(display_cols)

        # Set page size
        for row in table_data:
            row['_dash_pagesize'] = page_size
    else:
        table_data = []
        table_columns = []

    # Update active filter display
    region_display = region if region and region != "All" else "All Regions"
    sensor_display = sensor_name
    active_filter_display = f"🌍 {region_display} | 📡 {sensor_display} | 🎯 {active_filter}"

    # Update filter store with current state
    filter_store = {
        'active_filter': active_filter,
        'region': region,
        'sensor_type': sensor_type,
        'search_text': search_text,
        'page_size': page_size
    }

    return (str(total_count), str(communicating_count), str(not_communicating_count),
            str(inprogress_count), str(returned_count), str(integrated_count),
            str(integrated_not_comm_count),  # NEW RETURN VALUE
            table_data, table_columns, active_filter_display, filter_store)

# ================== RESERVOIR ANALYTICS CALLBACKS ==================
@app.callback(
    Output("reservoir-name", "children"),
    Output("reservoir-scheme", "children"),
    Output("reservoir-village", "children"),
    Output("reservoir-name-display", "children"),
    Output("reservoir-population", "children"),
    Output("reservoir-region-display", "children"),
    Output("reservoir-subdivision", "children"),
    Output("reservoir-circle", "children"),
    Output("reservoir-block", "children"),
    Input("refresh-interval", "n_intervals"),
    State("region-dropdown", "value"),
    State("scheme-dropdown", "value"),
    State("village-dropdown", "value"),
    State("reservoir-dropdown", "value")
)
def update_reservoir_info(n, region, scheme, village, reservoir):
    if not reservoir or not region or base_df.empty:
        return "Select Reservoir", "-", "-", "-", "-", "-", "-", "-", "-"

    df = base_df[(base_df["Region"] == region) & (base_df[COL_RESERVOIR] == reservoir)]
   
    if df.empty:
        return "Reservoir Not Found", "-", "-", "-", "-", "-", "-", "-", "-"

    # Get the first matching row
    row = df.iloc[0]
   
    return (
        row[COL_RESERVOIR] or "Reservoir Name",
        row[COL_SCHEME] or "-",
        row[COL_VILLAGE] or "-",
        row[COL_RESERVOIR] or "-",
        row[COL_POPULATION] or "16,860",  # Default population
        row["Region"] or "-",
        row[COL_SUBDIVISION] or "-",
        row[COL_CIRCLE] or "-",
        row[COL_BLOCK] or "-"
    )

# Full screen modal callbacks
@app.callback(
    Output("fullscreen-modal", "style"),
    Output("fullscreen-graph-content", "children"),
    Output("current-fullscreen-graph", "data"),
    Input("expand-totalizer", "n_clicks"),
    Input("expand-consumption", "n_clicks"),
    Input("expand-lpcd", "n_clicks"),
    Input("expand-flow", "n_clicks"),
    Input("expand-chlorine", "n_clicks"),
    Input("expand-pressure", "n_clicks"),
    Input("close-fullscreen", "n_clicks"),
    State("current-fullscreen-graph", "data"),
    prevent_initial_call=True
)
def toggle_fullscreen(totalizer_clicks, consumption_clicks, lpcd_clicks, flow_clicks,
                     chlorine_clicks, pressure_clicks, close_clicks, current_graph):
    ctx = callback_context
    if not ctx.triggered:
        return {"display": "none"}, "", current_graph

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id == "close-fullscreen":
        return {"display": "none"}, "", ""

    # Determine which graph to show
    graph_id = ""
    if trigger_id == "expand-totalizer":
        graph_id = "totalizer-graph"
    elif trigger_id == "expand-consumption":
        graph_id = "consumption-graph"
    elif trigger_id == "expand-lpcd":
        graph_id = "lpcd-graph"
    elif trigger_id == "expand-flow":
        graph_id = "flow-gauge"
    elif trigger_id == "expand-chlorine":
        graph_id = "chlorine-graph"
    elif trigger_id == "expand-pressure":
        graph_id = "pressure-graph"

    if graph_id:
        # Create a container for the fullscreen graph
        fullscreen_content = html.Div([
            dcc.Graph(id=f"fullscreen-{graph_id}", style={"height": "100%", "width": "100%"})
        ], style={"height": "100%", "width": "100%"})

        return {"display": "flex"}, fullscreen_content, graph_id

    return {"display": "none"}, "", current_graph

# Update fullscreen graph when data changes
@app.callback(
    Output("fullscreen-totalizer-graph", "figure"),
    Output("fullscreen-consumption-graph", "figure"),
    Output("fullscreen-lpcd-graph", "figure"),
    Output("fullscreen-flow-gauge", "figure"),
    Output("fullscreen-chlorine-graph", "figure"),
    Output("fullscreen-pressure-graph", "figure"),
    Input("refresh-interval", "n_intervals"),
    Input("current-fullscreen-graph", "data"),
    State("region-dropdown", "value"),
    State("scheme-dropdown", "value"),
    State("village-dropdown", "value"),
    State("reservoir-dropdown", "value")
)
def update_fullscreen_graphs(n, current_graph, region, scheme, village, reservoir):
    # Get all the regular graphs
    totalizer_fig, consumption_fig, lpcd_fig, gauge_fig, chlorine_fig, pressure_fig = update_reservoir_analytics_internal(region, scheme, village, reservoir)
   
    # Return all figures - the fullscreen one will be displayed based on current_graph
    return totalizer_fig, consumption_fig, lpcd_fig, gauge_fig, chlorine_fig, pressure_fig

def update_reservoir_analytics_internal(region, scheme, village, reservoir):
    # Default empty figures
    empty_fig = go.Figure()
    empty_fig.update_layout(
        title="No data available",
        xaxis_title="Time",
        yaxis_title="Value",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        height=300
    )

    if not reservoir or not region:
        return empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig

    # Get reservoir data
    df = base_df.copy()
    reservoir_data = df[(df["Region"] == region) & (df[COL_RESERVOIR] == reservoir)]

    if reservoir_data.empty:
        return empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig

    # Get topics for this reservoir
    flow_topic = reservoir_data[COL_FLOW].iloc[0] if not reservoir_data[COL_FLOW].isna().iloc[0] else None
    cl_topic = reservoir_data[COL_CL].iloc[0] if not reservoir_data[COL_CL].isna().iloc[0] else None
    pressure_topic = reservoir_data[COL_PRESSURE].iloc[0] if not reservoir_data[COL_PRESSURE].isna().iloc[0] else None

    # 1. Totalizer Graph (Line Chart) - Only show real data
    totalizer_fig = go.Figure()
    if flow_topic:
        # Get historical flow data
        flow_history = latest_store.get_flow_history(flow_topic, hours=24)
       
        if flow_history:
            times = [ts for ts, _ in flow_history]
            values = [val for _, val in flow_history]
           
            totalizer_fig.add_trace(go.Scatter(
                x=times,
                y=values,
                mode='lines+markers',
                name='Totalizer Value',
                line=dict(color='#667eea', width=3),
                marker=dict(size=4, color='#667eea'),
                fill='tozeroy',
                fillcolor='rgba(102, 126, 234, 0.1)'
            ))

            totalizer_fig.update_layout(
                title="Totalizer Value Over Time (Real Data)",
                xaxis_title="Time",
                yaxis_title="Totalizer Value",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color="#2c3e50"),
                showlegend=False,
                height=300
            )
        else:
            totalizer_fig = empty_fig
    else:
        totalizer_fig = empty_fig

    # 2. Water Consumption Graph (Bar Chart) - Only show real data
    consumption_fig = go.Figure()
    if flow_topic:
        flow_history = latest_store.get_flow_history(flow_topic, hours=24)
       
        if len(flow_history) > 1:
            times = [ts for ts, _ in flow_history]
            values = [val for _, val in flow_history]
           
            # Calculate consumption from differences
            consumption_values = []
            consumption_times = []
           
            for i in range(1, len(values)):
                consumption = values[i] - values[i-1]
                if consumption > 0:  # Only show positive consumption
                    consumption_values.append(consumption)
                    consumption_times.append(times[i])
           
            if consumption_values:
                consumption_fig.add_trace(go.Bar(
                    x=consumption_times,
                    y=consumption_values,
                    name='Water Consumption',
                    marker_color='#4facfe'
                ))

                consumption_fig.update_layout(
                    title="Water Consumption (Real Data)",
                    xaxis_title="Time",
                    yaxis_title="Consumption",
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color="#2c3e50"),
                    showlegend=False,
                    height=300
                )
            else:
                consumption_fig = empty_fig
        else:
            consumption_fig = empty_fig
    else:
        consumption_fig = empty_fig

    # 3. LPCD Graph (Bar Chart) - Only show real data
    lpcd_fig = go.Figure()
    if flow_topic and not consumption_fig.data:
        # Only show if we have consumption data
        population = reservoir_data[COL_POPULATION].iloc[0] if not reservoir_data[COL_POPULATION].isna().iloc[0] else 16860
        try:
            population = int(population)
        except:
            population = 16860

        flow_history = latest_store.get_flow_history(flow_topic, hours=24)
       
        if len(flow_history) > 1:
            times = [ts for ts, _ in flow_history]
            values = [val for _, val in flow_history]
           
            # Calculate LPCD from consumption differences
            lpcd_values = []
            lpcd_times = []
           
            for i in range(1, len(values)):
                consumption = values[i] - values[i-1]
                if consumption > 0 and population > 0:
                    lpcd = (consumption * 1000) / population
                    lpcd_values.append(lpcd)
                    lpcd_times.append(times[i])
           
            if lpcd_values:
                lpcd_fig.add_trace(go.Bar(
                    x=lpcd_times,
                    y=lpcd_values,
                    name='LPCD',
                    marker_color='#56ab2f'
                ))

                lpcd_fig.update_layout(
                    title="Liters Per Capita Per Day (LPCD) - Real Data",
                    xaxis_title="Time",
                    yaxis_title="LPCD",
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color="#2c3e50"),
                    showlegend=False,
                    height=300
                )
            else:
                lpcd_fig = empty_fig
        else:
            lpcd_fig = empty_fig
    else:
        lpcd_fig = empty_fig

    # 4. Flow Rate Gauge - Only show real data
    gauge_fig = go.Figure()
    if flow_topic:
        rec = latest_store.get(flow_topic)
        if rec:
            try:
                payload = json.loads(rec["payload"])
                current_flow = float(payload.get("Flow", payload.get("Volume_Flow", 0)))
               
                gauge_fig.add_trace(go.Indicator(
                    mode="gauge+number+delta",
                    value=current_flow,
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': "Flow Rate (L/s)"},
                    gauge={
                        'axis': {'range': [None, 100]},
                        'bar': {'color': "#ff416c"},
                        'steps': [
                            {'range': [0, 30], 'color': "lightgray"},
                            {'range': [30, 70], 'color': "gray"},
                            {'range': [70, 100], 'color': "darkgray"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 90
                        }
                    }
                ))

                gauge_fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(color="#2c3e50"),
                    height=300
                )
            except:
                gauge_fig = empty_fig
        else:
            gauge_fig = empty_fig
    else:
        gauge_fig = empty_fig

    # 5. Chlorine Graph (Line Chart) - Only show real data
    chlorine_fig = go.Figure()
    if cl_topic:
        # Get historical chlorine data
        chlorine_history = latest_store.get_chlorine_history(cl_topic, hours=24)
       
        if chlorine_history:
            times = [ts for ts, _ in chlorine_history]
            values = [val for _, val in chlorine_history]
           
            chlorine_fig.add_trace(go.Scatter(
                x=times,
                y=values,
                mode='lines+markers',
                name='Chlorine Level',
                line=dict(color='#f7971e', width=3),
                marker=dict(size=4, color='#f7971e')
            ))

            # Add recommended range
            chlorine_fig.add_hline(y=0.2, line_dash="dash", line_color="green", annotation_text="Min Recommended")
            chlorine_fig.add_hline(y=0.5, line_dash="dash", line_color="red", annotation_text="Max Recommended")

            chlorine_fig.update_layout(
                title="Chlorine Levels Over Time (Real Data)",
                xaxis_title="Time",
                yaxis_title="Chlorine (mg/L)",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color="#2c3e50"),
                showlegend=False,
                height=300
            )
        else:
            chlorine_fig = empty_fig
    else:
        chlorine_fig = empty_fig

    # 6. Pressure Graph (Line Chart) - Only show real data
    pressure_fig = go.Figure()
    if pressure_topic:
        # Get historical pressure data
        pressure_history = latest_store.get_pressure_history(pressure_topic, hours=24)
       
        if pressure_history:
            times = [ts for ts, _ in pressure_history]
            values = [val for _, val in pressure_history]
           
            pressure_fig.add_trace(go.Scatter(
                x=times,
                y=values,
                mode='lines+markers',
                name='Pressure',
                line=dict(color='#9c27b0', width=3),
                marker=dict(size=4, color='#9c27b0'),
                fill='tozeroy',
                fillcolor='rgba(156, 39, 176, 0.1)'
            ))

            pressure_fig.update_layout(
                title="Pressure Monitoring (Real Data)",
                xaxis_title="Time",
                yaxis_title="Pressure (Bar)",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color="#2c3e50"),
                showlegend=False,
                height=300
            )
        else:
            pressure_fig = empty_fig
    else:
        pressure_fig = empty_fig

    return totalizer_fig, consumption_fig, lpcd_fig, gauge_fig, chlorine_fig, pressure_fig

@app.callback(
    Output("totalizer-graph", "figure"),
    Output("consumption-graph", "figure"),
    Output("lpcd-graph", "figure"),
    Output("flow-gauge", "figure"),
    Output("chlorine-graph", "figure"),
    Output("pressure-graph", "figure"),
    Input("refresh-interval", "n_intervals"),
    State("region-dropdown", "value"),
    State("scheme-dropdown", "value"),
    State("village-dropdown", "value"),
    State("reservoir-dropdown", "value")
)
def update_reservoir_analytics(n, region, scheme, village, reservoir):
    return update_reservoir_analytics_internal(region, scheme, village, reservoir)

# ================== RUN APP ==================
server = app.server   # 👈 required for Render / Gunicorn

if __name__ == "__main__":
    # Auto-create the new entries table on startup
    create_new_entries_table()

    # Fixed port (no auto-increment)
    port = 8011

    # Try to open the app in the default web browser
    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass

    # Run the Dash app on the fixed port
    app.run(debug=False, host='0.0.0.0', port=port)
