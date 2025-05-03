"""
MES to ERP Real-Time Synchronization Script
-------------------------------------------
Author: Data Integration Specialist
Created: March 12, 2024
Last Modified: April 22, 2024

This script provides real-time synchronization between the Manufacturing Execution System (MES)
and Enterprise Resource Planning (ERP) system using MQTT protocol for machine data and
REST API for job scheduling information.

Features:
- MQTT subscription for real-time machine status updates
- REST API connectors for ERP system integration
- Timestamp synchronization between systems
- Error handling with automatic retry logic
- Comprehensive logging for audit purposes
- Validation checks for data consistency

Dependencies:
- paho-mqtt
- requests
- psycopg2 (PostgreSQL connector)
- dateutil
- pyjwt (for ERP authentication)
"""

import os
import sys
import time
import json
import logging
import signal
import threading
import queue
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
import re
import hashlib
import uuid

import paho.mqtt.client as mqtt
import requests
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import jwt
from dateutil import parser
from dateutil.tz import tzlocal, tzutc

# Configure logging
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file = 'mes_sync.log'
log_handler = RotatingFileHandler(log_file, maxBytes=10485760, backupCount=10)
log_handler.setFormatter(log_formatter)

logger = logging.getLogger('mes_sync')
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# Configuration - In production, these would be in a separate config file or environment variables
CONFIG = {
    # Central Database Configuration
    'db': {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'port': int(os.environ.get('DB_PORT', 5432)),
        'database': os.environ.get('DB_NAME', 'central_db'),
        'user': os.environ.get('DB_USER', 'integration_user'),
        'password': os.environ.get('DB_PASSWORD', 'secure_password'),
        'min_connections': 1,
        'max_connections': 10
    },
    
    # MQTT Configuration for MES
    'mqtt': {
        'broker': os.environ.get('MQTT_BROKER', 'mes-broker.internal'),
        'port': int(os.environ.get('MQTT_PORT', 1883)),
        'username': os.environ.get('MQTT_USERNAME', 'mes_subscriber'),
        'password': os.environ.get('MQTT_PASSWORD', 'mqtt_password'),
        'client_id': f'mes_sync_{uuid.uuid4().hex[:8]}',
        'topics': {
            'machine_status': 'factory/machines/+/status',
            'production_data': 'factory/production/+/data',
            'quality_alerts': 'factory/quality/alerts'
        }
    },
    
    # ERP Configuration
    'erp': {
        'base_url': os.environ.get('ERP_API_URL', 'https://erp-api.internal'),
        'username': os.environ.get('ERP_USERNAME', 'api_user'),
        'password': os.environ.get('ERP_PASSWORD', 'api_password'),
        'api_key': os.environ.get('ERP_API_KEY', 'erp_api_key_12345'),
        'token_endpoint': '/api/auth/token',
        'schedule_endpoint': '/api/production/schedule',
        'job_status_endpoint': '/api/production/jobs/status'
    },
    
    # Sync Configuration
    'sync': {
        'interval_seconds': int(os.environ.get('SYNC_INTERVAL', 300)),  # 5 minutes
        'batch_size': int(os.environ.get('BATCH_SIZE', 100)),
        'max_retries': int(os.environ.get('MAX_RETRIES', 3)),
        'retry_delay_seconds': int(os.environ.get('RETRY_DELAY', 30))
    }
}

# Global variables
running = True
message_queue = queue.Queue()
db_connection_pool = None
erp_auth_token = None
erp_token_expiry = None

class DatabaseManager:
    """Handle database connections and operations"""
    
    def __init__(self, config):
        self.config = config
        self.connection_pool = None
        self.initialize_pool()
    
    def initialize_pool(self):
        """Initialize the database connection pool"""
        try:
            self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
                self.config['min_connections'],
                self.config['max_connections'],
                host=self.config['host'],
                port=self.config['port'],
                database=self.config['database'],
                user=self.config['user'],
                password=self.config['password']
            )
            logger.info("Database connection pool initialized successfully")
        except psycopg2.Error as e:
            logger.error(f"Failed to initialize database connection pool: {e}")
            raise
    
    def get_connection(self):
        """Get a connection from the pool"""
        if not self.connection_pool:
            self.initialize_pool()
        return self.connection_pool.getconn()
    
    def release_connection(self, conn):
        """Release a connection back to the pool"""
        if self.connection_pool:
            self.connection_pool.putconn(conn)
    
    def close_all(self):
        """Close all connections"""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("Closed all database connections")

    def execute_query(self, query, params=None):
        """Execute a query and return results"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                if cursor.description:  # If it's a SELECT query
                    return cursor.fetchall()
                conn.commit()
                return cursor.rowcount
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database query error: {e}")
            raise
        finally:
            if conn:
                self.release_connection(conn)
    
    def execute_batch(self, query, params_list):
        """Execute batch operations"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                for params in params_list:
                    cursor.execute(query, params)
                conn.commit()
                return len(params_list)
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database batch error: {e}")
            raise
        finally:
            if conn:
                self.release_connection(conn)

class ERPConnector:
    """Handle ERP API connections and data exchange"""
    
    def __init__(self, config):
        self.config = config
        self.token = None
        self.token_expiry = None
    
    def authenticate(self):
        """Authenticate with the ERP system and get a token"""
        try:
            auth_data = {
                'username': self.config['username'],
                'password': self.config['password'],
                'api_key': self.config['api_key']
            }
            
            response = requests.post(
                f"{self.config['base_url']}{self.config['token_endpoint']}",
                json=auth_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"ERP authentication failed: {response.status_code}, {response.text}")
                raise Exception(f"ERP authentication failed: {response.status_code}")
            
            auth_response = response.json()
            self.token = auth_response.get('token')
            
            # Parse expiry time or set default (1 hour)
            expiry = auth_response.get('expires_in', 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expiry)
            
            logger.info(f"ERP authentication successful, token expires at {self.token_expiry}")
            return self.token
        
        except requests.RequestException as e:
            logger.error(f"ERP authentication request error: {e}")
            raise
    
    def get_valid_token(self):
        """Get a valid authentication token, refreshing if necessary"""
        if not self.token or not self.token_expiry or datetime.now() >= self.token_expiry:
            return self.authenticate()
        return self.token
    
    def get_schedule(self, days=1):
        """Get production schedule for the specified number of days"""
        try:
            token = self.get_valid_token()
            
            params = {
                'days': days,
                'include_details': True
            }
            
            response = requests.get(
                f"{self.config['base_url']}{self.config['schedule_endpoint']}",
                params=params,
                headers={
                    'Authorization': f"Bearer {token}",
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get ERP schedule: {response.status_code}, {response.text}")
                raise Exception(f"Failed to get ERP schedule: {response.status_code}")
            
            return response.json()
        
        except requests.RequestException as e:
            logger.error(f"ERP schedule request error: {e}")
            raise
    
    def update_job_status(self, job_id, status, actual_start=None, actual_end=None, quantity=None, notes=None):
        """Update job status in ERP"""
        try:
            token = self.get_valid_token()
            
            update_data = {
                'job_id': job_id,
                'status': status
            }
            
            if actual_start:
                update_data['actual_start'] = actual_start.isoformat()
            
            if actual_end:
                update_data['actual_end'] = actual_end.isoformat()
            
            if quantity is not None:
                update_data['quantity_completed'] = quantity
            
            if notes:
                update_data['notes'] = notes
            
            response = requests.put(
                f"{self.config['base_url']}{self.config['job_status_endpoint']}",
                json=update_data,
                headers={
                    'Authorization': f"Bearer {token}",
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            if response.status_code not in (200, 204):
                logger.error(f"Failed to update job status in ERP: {response.status_code}, {response.text}")
                raise Exception(f"Failed to update job status in ERP: {response.status_code}")
            
            logger.info(f"Job {job_id} status updated to {status} in ERP")
            return True
        
        except requests.RequestException as e:
            logger.error(f"ERP job status update error: {e}")
            raise

class MQTTHandler:
    """Handle MQTT subscriptions and message processing"""
    
    def __init__(self, config, message_queue):
        self.config = config
        self.message_queue = message_queue
        self.client = mqtt.Client(client_id=config['client_id'])
        self.client.username_pw_set(config['username'], config['password'])
        
        # Set callbacks
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        # Enable logger in the MQTT client
        self.client.enable_logger(logger)
    
    def start(self):
        """Start the MQTT client and connect to broker"""
        try:
            self.client.connect(self.config['broker'], self.config['port'], 60)
            self.client.loop_start()
            logger.info(f"MQTT client started, connecting to {self.config['broker']}:{self.config['port']}")
        except Exception as e:
            logger.error(f"Failed to start MQTT client: {e}")
            raise
    
    def stop(self):
        """Stop the MQTT client"""
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("MQTT client stopped")
    
    def on_connect(self, client, userdata, flags, rc):
        """Callback when client connects to the broker"""
        if rc == 0:
            logger.info("Connected to MQTT broker")
            # Subscribe to all configured topics
            for topic in self.config['topics'].values():
                client.subscribe(topic)
                logger.info(f"Subscribed to topic: {topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker, return code: {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        """Callback when client disconnects from the broker"""
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker, return code: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")
    
    def on_message(self, client, userdata, msg):
        """Callback when a message is received from the broker"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            logger.debug(f"Received message on topic {topic}: {payload}")
            
            # Parse message and extract topic type
            topic_parts = topic.split('/')
            message_type = None
            
            if len(topic_parts) >= 2:
                if topic_parts[1] == 'machines' and topic_parts[3] == 'status':
                    message_type = 'machine_status'
                elif topic_parts[1] == 'production' and topic_parts[3] == 'data':
                    message_type = 'production_data'
                elif topic_parts[1] == 'quality' and topic_parts[2] == 'alerts':
                    message_type = 'quality_alert'
            
            if not message_type:
                logger.warning(f"Unknown message type for topic: {topic}")
                return
            
            # Parse JSON payload
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON payload: {e}")
                return
            
            # Add metadata and put in queue
            message = {
                'type': message_type,
                'topic': topic,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }
            
            self.message_queue.put(message)
            
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

class DataProcessor:
    """Process and synchronize data between systems"""
    
    def __init__(self, db_manager, erp_connector, config):
        self.db_manager = db_manager
        self.erp = erp_connector
        self.config = config
        self.last_sync_time = datetime.now() - timedelta(seconds=config['interval_seconds'])
    
    def process_message(self, message):
        """Process a message from the queue"""
        message_type = message.get('type')
        data = message.get('data', {})
        
        try:
            if message_type == 'machine_status':
                self.process_machine_status(data)
            elif message_type == 'production_data':
                self.process_production_data(data)
            elif message_type == 'quality_alert':
                self.process_quality_alert(data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
        except Exception as e:
            logger.error(f"Error processing {message_type} message: {e}")
            # Log the problematic data for debugging
            logger.error(f"Problematic data: {json.dumps(data)}")
    
    def process_machine_status(self, data):
        """Process machine status updates"""
        machine_id = data.get('machine_id')
        status = data.get('status')
        timestamp = parser.parse(data.get('timestamp'))
        
        if not machine_id or not status:
            logger.warning("Missing required fields in machine status update")
            return
        
        # Update machine status in database
        query = """
        UPDATE MACHINE 
        SET status = %s, last_updated = %s 
        WHERE machine_id = %s
        """
        params = (status, timestamp, machine_id)
        
        rows_updated = self.db_manager.execute_query(query, params)
        
        if rows_updated == 0:
            logger.warning(f"Machine ID {machine_id} not found in database")
        else:
            logger.info(f"Updated status for machine {machine_id} to {status}")
            
            # Check if this affects any scheduled jobs
            self.check_affected_schedules(machine_id, status, timestamp)
    
    def process_production_data(self, data):
        """Process production data updates"""
        schedule_id = data.get('schedule_id')
        machine_id = data.get('machine_id')
        start_time = parser.parse(data.get('start_time')) if data.get('start_time') else None
        end_time = parser.parse(data.get('end_time')) if data.get('end_time') else None
        quantity_completed = data.get('quantity_completed', 0)
        quantity_defective = data.get('quantity_defective', 0)
        notes = data.get('notes')
        
        if not schedule_id or not machine_id:
            logger.warning("Missing required fields in production data update")
            return
        
        # Check if production log already exists
        query = """
        SELECT log_id FROM PRODUCTION_LOG 
        WHERE schedule_id = %s AND machine_id = %s AND 
              (start_time = %s OR (start_time IS NULL AND %s IS NULL))
        """
        params = (schedule_id, machine_id, start_time, start_time)
        
        result = self.