"""
QuoteWiz API Connector for Integration with Central Database
---------------------------------------------------------
Author: Data Integration Specialist
Created: February 2, 2024
Last Modified: April 15, 2024

This module provides a Flask-based API interface for the legacy QuoteWiz system
which lacks native API endpoints. It handles authentication, data retrieval,
and synchronization with the central database.

Dependencies:
- Flask
- Requests
- SQLAlchemy
- Celery (for scheduled tasks)
- PostgreSQL (target database)
"""

import os
import logging
import json
import time
import requests
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, g, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import SQLAlchemyError
from celery import Celery
from celery.schedules import crontab

# Configure logging
logging.basicConfig(
    filename='api_connector.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object('config.ProductionConfig')

# Configure database connection
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://user:password@localhost:5432/centralized_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configure Celery
app.config['CELERY_BROKER_URL'] = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
app.config['CELERY_RESULT_BACKEND'] = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
app.config['CELERY_TIMEZONE'] = 'UTC'

celery = Celery(
    app.name,
    broker=app.config['CELERY_BROKER_URL'],
    backend=app.config['CELERY_RESULT_BACKEND']
)
celery.conf.update(app.config)

# Legacy QuoteWiz system connection parameters
QUOTEWIZ_BASE_URL = os.environ.get('QUOTEWIZ_URL', 'http://legacy-quotewiz.internal:8080')
QUOTEWIZ_USERNAME = os.environ.get('QUOTEWIZ_USERNAME', 'integration_user')
QUOTEWIZ_PASSWORD = os.environ.get('QUOTEWIZ_PASSWORD', 'securepassword')
QUOTEWIZ_AUTH_TOKEN = None
QUOTEWIZ_TOKEN_EXPIRY = None

# Database models
Base = declarative_base()

class Quote(db.Model):
    __tablename__ = 'QUOTATION'
    
    quote_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('CUSTOMER.customer_id'))
    quote_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    status = db.Column(db.String(20))
    total_amount = db.Column(db.Float)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    items = db.relationship('QuoteItem', backref='quote', lazy=True)

class QuoteItem(db.Model):
    __tablename__ = 'QUOTE_ITEM'
    
    quote_item_id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('QUOTATION.quote_id'))
    material_id = db.Column(db.Integer, db.ForeignKey('MATERIAL.material_id'))
    quantity = db.Column(db.Integer)
    unit_price = db.Column(db.Float)
    total_price = db.Column(db.Float)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

class SyncLog(db.Model):
    __tablename__ = 'SYNC_LOG'
    
    log_id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50))  # 'quote' or 'quote_item'
    entity_id = db.Column(db.Integer)
    sync_status = db.Column(db.String(20))  # 'success', 'failed', 'retry'
    error_message = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Authentication decorator for QuoteWiz API
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        global QUOTEWIZ_AUTH_TOKEN, QUOTEWIZ_TOKEN_EXPIRY
        
        # Check if token expired or missing
        current_time = datetime.utcnow()
        if not QUOTEWIZ_AUTH_TOKEN or not QUOTEWIZ_TOKEN_EXPIRY or current_time >= QUOTEWIZ_TOKEN_EXPIRY:
            try:
                # Authenticate with legacy system
                auth_response = requests.post(
                    f"{QUOTEWIZ_BASE_URL}/auth",
                    data={"username": QUOTEWIZ_USERNAME, "password": QUOTEWIZ_PASSWORD},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=10
                )
                
                if auth_response.status_code != 200:
                    logger.error(f"Authentication failed: {auth_response.text}")
                    return jsonify({"error": "Authentication failed"}), 401
                
                auth_data = auth_response.json()
                QUOTEWIZ_AUTH_TOKEN = auth_data.get('token')
                # Token expires in 2 hours
                QUOTEWIZ_TOKEN_EXPIRY = current_time + timedelta(hours=2)
                
            except requests.RequestException as e:
                logger.error(f"Authentication request failed: {str(e)}")
                return jsonify({"error": "Connection to QuoteWiz failed"}), 503
        
        return f(*args, **kwargs)
    return decorated

# API endpoints for QuoteWiz data
@app.route('/api/quotes', methods=['GET'])
@requires_auth
def get_quotes():
    """Get all quotes or filter by parameters"""
    try:
        # Parse filter parameters
        customer_id = request.args.get('customer_id')
        status = request.args.get('status')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Build filter parameters for legacy system
        params = {}
        if customer_id:
            params['customerID'] = customer_id
        if status:
            params['quoteStatus'] = status
        if start_date:
            params['fromDate'] = start_date
        if end_date:
            params['toDate'] = end_date
        
        # Query legacy system
        response = requests.get(
            f"{QUOTEWIZ_BASE_URL}/quotes",
            params=params,
            headers={"Authorization": f"Bearer {QUOTEWIZ_AUTH_TOKEN}"},
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to retrieve quotes: {response.text}")
            return jsonify({"error": "Failed to retrieve quotes"}), response.status_code
        
        quotes_data = response.json()
        
        # Transform data to match our schema
        transformed_quotes = []
        for quote in quotes_data:
            transformed_quotes.append({
                'quote_id': quote.get('QuoteID'),
                'customer_id': quote.get('CustomerID'),
                'quote_date': quote.get('QuoteDate'),
                'expiry_date': quote.get('ValidUntil'),
                'status': quote.get('Status'),
                'total_amount': quote.get('TotalAmount')
            })
        
        return jsonify(transformed_quotes)
        
    except requests.RequestException as e:
        logger.error(f"Request to QuoteWiz failed: {str(e)}")
        return jsonify({"error": "Connection to QuoteWiz failed"}), 503
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "Unexpected error occurred"}), 500

@app.route('/api/quotes/<int:quote_id>', methods=['GET'])
@requires_auth
def get_quote(quote_id):
    """Get a specific quote by ID"""
    try:
        # Query legacy system
        response = requests.get(
            f"{QUOTEWIZ_BASE_URL}/quotes/{quote_id}",
            headers={"Authorization": f"Bearer {QUOTEWIZ_AUTH_TOKEN}"},
            timeout=15
        )
        
        if response.status_code == 404:
            return jsonify({"error": "Quote not found"}), 404
        
        if response.status_code != 200:
            logger.error(f"Failed to retrieve quote {quote_id}: {response.text}")
            return jsonify({"error": "Failed to retrieve quote"}), response.status_code
        
        quote_data = response.json()
        
        # Transform data to match our schema
        transformed_quote = {
            'quote_id': quote_data.get('QuoteID'),
            'customer_id': quote_data.get('CustomerID'),
            'quote_date': quote_data.get('QuoteDate'),
            'expiry_date': quote_data.get('ValidUntil'),
            'status': quote_data.get('Status'),
            'total_amount': quote_data.get('TotalAmount'),
            'items': []
        }
        
        # Get quote items if available
        items = quote_data.get('Items', [])
        for item in items:
            transformed_quote['items'].append({
                'quote_item_id': item.get('ItemID'),
                'quote_id': quote_id,
                'material_id': item.get('MaterialID'),
                'quantity': item.get('Quantity'),
                'unit_price': item.get('UnitPrice'),
                'total_price': item.get('TotalPrice')
            })
        
        return jsonify(transformed_quote)
        
    except requests.RequestException as e:
        logger.error(f"Request to QuoteWiz failed: {str(e)}")
        return jsonify({"error": "Connection to QuoteWiz failed"}), 503
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "Unexpected error occurred"}), 500

@app.route('/api/quotes/<int:quote_id>/status', methods=['GET'])
@requires_auth
def get_quote_status(quote_id):
    """Get the status of a specific quote"""
    try:
        # Query legacy system for just the status
        response = requests.get(
            f"{QUOTEWIZ_BASE_URL}/quotes/{quote_id}/status",
            headers={"Authorization": f"Bearer {QUOTEWIZ_AUTH_TOKEN}"},
            timeout=10
        )
        
        if response.status_code == 404:
            return jsonify({"error": "Quote not found"}), 404
        
        if response.status_code != 200:
            logger.error(f"Failed to retrieve quote status for {quote_id}: {response.text}")
            return jsonify({"error": "Failed to retrieve quote status"}), response.status_code
        
        status_data = response.json()
        
        return jsonify({
            'quote_id': quote_id,
            'status': status_data.get('Status'),
            'last_updated': status_data.get('LastUpdated')
        })
        
    except requests.RequestException as e:
        logger.error(f"Request to QuoteWiz failed: {str(e)}")
        return jsonify({"error": "Connection to QuoteWiz failed"}), 503
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "Unexpected error occurred"}), 500

# Synchronization tasks
@app.route('/api/sync/quotes', methods=['POST'])
def trigger_quote_sync():
    """Manually trigger quote synchronization"""
    try:
        # Get parameters
        start_date = request.json.get('start_date', (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d'))
        end_date = request.json.get('end_date', datetime.utcnow().strftime('%Y-%m-%d'))
        
        # Trigger async task
        task = sync_quotes.delay(start_date, end_date)
        
        return jsonify({
            'message': 'Quote synchronization started',
            'task_id': task.id
        })
        
    except Exception as e:
        logger.error(f"Failed to trigger sync: {str(e)}")
        return jsonify({"error": "Failed to trigger synchronization"}), 500

@app.route('/api/sync/status/<task_id>', methods=['GET'])
def get_sync_status(task_id):
    """Get the status of a sync task"""
    task = sync_quotes.AsyncResult(task_id)
    
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'status': task.info.get('status', '')
        }
        if 'result' in task.info:
            response['result'] = task.info['result']
    else:
        response = {
            'state': task.state,
            'status': str(task.info)
        }
    
    return jsonify(response)

@celery.task(bind=True, max_retries=3, name='sync_quotes')
def sync_quotes(self, start_date=None, end_date=None):
    """Synchronize quotes from QuoteWiz to central database"""
    global QUOTEWIZ_AUTH_TOKEN, QUOTEWIZ_TOKEN_EXPIRY
    
    try:
        self.update_state(state='PROGRESS', meta={'status': 'Starting synchronization'})
        
        # Default date range is last 24 hours if not specified
        if not start_date:
            start_date = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')