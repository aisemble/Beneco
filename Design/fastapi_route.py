"""
QA System Integration Router for Manufacturing Middleware
--------------------------------------------------------
Author: Information Technology Analyst
Created: March 8, 2024
Last Modified: April 21, 2024

This module provides FastAPI routes for integrating with the QA system.
It handles data synchronization, status updates, and test results retrieval.
"""

import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, Path, BackgroundTasks, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator

from app.database import get_db, SessionLocal
from app.models import QATest, Job, User
from app.schemas import QATestCreate, QATestUpdate, QATestResponse, QATestDetailResponse
from app.services.qa_client import QAClient, QAClientException
from app.services.auth import get_current_user, check_permissions
from app.utils.datetime_utils import convert_to_utc, format_iso_datetime
from app.config import settings
from app.background_tasks import sync_qa_test_to_erp

# Configure router
router = APIRouter(
    prefix="/qa",
    tags=["qa"],
    responses={
        404: {"description": "Resource not found"},
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        500: {"description": "Internal server error"}
    }
)

# Configure logging
logger = logging.getLogger(__name__)

# Initialize QA client
qa_client = QAClient(
    base_url=settings.QA_SYSTEM_URL,
    username=settings.QA_SYSTEM_USERNAME,
    password=settings.QA_SYSTEM_PASSWORD,
    timeout=settings.QA_SYSTEM_TIMEOUT
)

# Status mapping between systems
QA_TO_ERP_STATUS_MAP = {
    "NEW": "created",
    "IN_PROGRESS": "in_progress",
    "PAUSED": "on_hold",
    "DONE": "completed",
    "CANCELLED": "cancelled",
    "FAILED": "completed"  # Special case - ERP doesn't have "failed" status
}

ERP_TO_QA_STATUS_MAP = {
    "created": "NEW",
    "in_progress": "IN_PROGRESS",
    "on_hold": "PAUSED",
    "completed": "DONE",
    "cancelled": "CANCELLED"
}


class QATestStatus(str, Enum):
    """Enum for QA test status values"""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class QATestStatusUpdate(BaseModel):
    """Schema for QA test status update requests"""
    status: QATestStatus
    comments: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    @validator('timestamp', pre=True, always=True)
    def set_timestamp(cls, v):
        """Set timestamp to current UTC time if not provided"""
        return v or datetime.utcnow()


@router.get("/status", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint for QA integration"""
    try:
        # Check QA system connection
        qa_status = await qa_client.health_check()
        return {
            "status": "healthy",
            "qa_system_status": qa_status,
            "timestamp": datetime.utcnow().isoformat()
        }
    except QAClientException as e:
        logger.error(f"QA system health check failed: {str(e)}")
        return {
            "status": "degraded",
            "qa_system_status": "unavailable",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Unexpected error during health check: {str(e)}")
        return {
            "status": "error",
            "error": "Internal server error",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.get("/tests", response_model=Dict[str, Any])
async def get_qa_tests(
    status: Optional[QATestStatus] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    job_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve QA tests with optional filtering.
    
    Parameters:
    - status: Filter by test status
    - start_date: Filter by tests on or after this date
    - end_date: Filter by tests on or before this date
    - job_id: Filter by job ID
    - limit: Maximum number of tests to return
    - offset: Number of tests to skip
    """
    # Check permissions
    check_permissions(current_user, "qa:read")
    
    try:
        # Query QA tests from database
        query = db.query(QATest)
        
        # Apply filters
        if status:
            query = query.filter(QATest.status == status.value.upper())
        if start_date:
            query = query.filter(QATest.created_at >= start_date)
        if end_date:
            # Add one day to include the end date fully
            query = query.filter(QATest.created_at <= end_date + timedelta(days=1))
        if job_id:
            query = query.filter(QATest.job_id == job_id)
        
        # Count total before pagination
        total = query.count()
        
        # Apply pagination
        tests = query.order_by(QATest.created_at.desc()).offset(offset).limit(limit).all()
        
        # Transform to response format
        test_responses = [
            QATestResponse(
                id=str(test.id),
                order_number=test.order_number,
                job_id=test.job_id,
                client_code=test.client_code,
                creation_date=test.created_at,
                test_start=test.test_start,
                test_status=test.status,
                batch_size=test.batch_size,
                failure_count=test.failure_count,
                tester_initials=test.tester_initials,
                testing_area=test.testing_area
            ) for test in tests
        ]
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "tests": test_responses
        }
    
    except Exception as e:
        logger.error(f"Error retrieving QA tests: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving QA tests: {str(e)}"
        )


@router.get("/tests/{test_id}", response_model=QATestDetailResponse)
async def get_qa_test(
    test_id: uuid.UUID = Path(..., description="The UUID of the QA test"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve detailed information for a specific QA test.
    
    Parameters:
    - test_id: UUID of the QA test to retrieve
    """
    # Check permissions
    check_permissions(current_user, "qa:read")
    
    try:
        # Query the test from database
        test = db.query(QATest).filter(QATest.id == test_id).first()
        
        if not test:
            raise HTTPException(
                status_code=404,
                detail=f"QA test with ID {test_id} not found"
            )
        
        # Get associated job information
        job = None
        if test.job_id:
            job = db.query(Job).filter(Job.id == test.job_id).first()
        
        # Transform to detailed response
        test_detail = QATestDetailResponse(
            id=str(test.id),
            order_number=test.order_number,
            job_id=test.job_id,
            client_code=test.client_code,
            creation_date=test.created_at,
            planned_inspection=test.planned_inspection,
            test_start=test.test_start,
            completed_dt=test.completed_dt,
            test_status=test.status,
            priority=test.priority,
            batch_size=test.batch_size,
            failure_count=test.failure_count,
            tester_initials=test.tester_initials,
            product_desc=test.product_desc,
            testing_area=test.testing_area,
            comments=test.comments,
            job=job.to_dict() if job else None,
            measurements=test.measurements,
            last_modified=test.modified_at,
            sync_status=test.sync_status
        )
        
        return test_detail
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving QA test {test_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving QA test: {str(e)}"
        )


@router.post("/tests", response_model=QATestResponse, status_code=status.HTTP_201_CREATED)
async def create_qa_test(
    test: QATestCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new QA test in the system and synchronize with QA system.
    
    Parameters:
    - test: QA test creation data
    """
    # Check permissions
    check_permissions(current_user, "qa:write")
    
    try:
        # Start database transaction
        db_test = QATest(
            id=uuid.uuid4(),
            order_number=test.order_number,
            job_id=test.job_id,
            client_code=test.client_code,
            created_at=datetime.utcnow(),
            planned_inspection=test.planned_inspection,
            test_start=test.test_start,
            status=test.test_status.upper(),
            priority=test.priority,
            batch_size=test.batch_size,
            tester_initials=test.tester_initials,
            product_desc=test.product_desc,
            testing_area=test.testing_area,
            comments=test.comments,
            measurements=test.measurements or {},
            created_by=current_user.id,
            sync_status="pending"
        )
        
        db.add(db_test)
        db.commit()
        db.refresh(db_test)
        
        # Schedule background task to sync with QA system
        background_tasks.add_task(
            sync_qa_test_to_qa_system,
            db_test.id,
            "create"
        )
        
        # Transform to response
        return QATestResponse(
            id=str(db_test.id),
            order_number=db_test.order_number,
            job_id=db_test.job_id,
            client_code=db_test.client_code,
            creation_date=db_test.created_at,
            test_start=db_test.test_start,
            test_status=db_test.status,
            batch_size=db_test.batch_size,
            failure_count=db_test.failure_count,
            tester_initials=db_test.tester_initials,
            testing_area=db_test.testing_area
        )
    
    except Exception as e:
        logger.error(f"Error creating QA test: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating QA test: {str(e)}"
        )


@router.put("/tests/{test_id}", response_model=QATestResponse)
async def update_qa_test(
    test_id: uuid.UUID,
    test_update: QATestUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing QA test.
    
    Parameters:
    - test_id: UUID of the QA test to update
    - test_update: QA test update data
    """
    # Check permissions
    check_permissions(current_user, "qa:write")
    
    try:
        # Find the test to update
        db_test = db.query(QATest).filter(QATest.id == test_id).first()
        
        if not db_test:
            raise HTTPException(
                status_code=404,
                detail=f"QA test with ID {test_id} not found"
            )
        
        # Update fields if provided
        update_data = test_update.dict(exclude_unset=True)
        
        # Handle status update specially to apply uppercase conversion
        if "test_status" in update_data:
            db_test.status = update_data["test_status"].upper()
            del update_data["test_status"]
        
        # Update the rest of the fields
        for key, value in update_data.items():
            setattr(db_test, key, value)
        
        # Update modification metadata
        db_test.modified_at = datetime.utcnow()
        db_test.modified_by = current_user.id
        db_test.sync_status = "pending"
        
        db.commit()
        db.refresh(db_test)
        
        # Schedule background task to sync with QA system
        background_tasks.add_task(
            sync_qa_test_to_qa_system,
            db_test.id,
            "update"
        )
        
        # Transform to response
        return QATestResponse(
            id=str(db_test.id),
            order_number=db_test.order_number,
            job_id=db_test.job_id,
            client_code=db_test.client_code,
            creation_date=db_test.created_at,
            test_start=db_test.test_start,
            test_status=db_test.status,
            batch_size=db_test.batch_size,
            failure_count=db_test.failure_count,
            tester_initials=db_test.tester_initials,
            testing_area=db_test.testing_area
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating QA test {test_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error updating QA test: {str(e)}"
        )


@router.put("/tests/{test_id}/status", response_model=QATestResponse)
async def update_qa_test_status(
    test_id: uuid.UUID,
    status_update: QATestStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the status of an existing QA test.
    
    Parameters:
    - test_id: UUID of the QA test to update
    - status_update: Status update data
    """
    # Check permissions
    check_permissions(current_user, "qa:write")
    
    try:
        # Find the test to update
        db_test = db.query(QATest).filter(QATest.id == test_id).first()
        
        if not db_test:
            raise HTTPException(
                status_code=404,
                detail=f"QA test with ID {test_id} not found"
            )
        
        # Check for valid status transition
        old_status = db_test.status
        new_status = status_update.status.value.upper()
        
        # Update test status
        db_test.status = new_status
        
        # Update completion date if status is terminal
        if new_status in ["DONE", "CANCELLED", "FAILED"]:
            db_test.completed_dt = status_update.timestamp
        
        # Update comments if provided
        if status_update.comments:
            # Prepend timestamp and new status to comments
            status_comment = f"[{status_update.timestamp.isoformat()}] Status changed from {old_status} to {new_status}: {status_update.comments}"
            
            if db_test.comments:
                db_test.comments = f"{status_comment}\n\n{db_test.comments}"
            else:
                db_test.comments = status_comment
        
        # Update modification metadata
        db_test.modified_at = datetime.utcnow()
        db_test.modified_by = current_user.id
        db_test.sync_status = "pending"
        
        db.commit()
        db.refresh(db_test)
        
        # Schedule background task to sync with QA system
        background_tasks.add_task(
            sync_qa_test_to_qa_system,
            db_test.id,
            "status"
        )
        
        # If linked to a job, schedule ERP sync
        if db_test.job_id:
            background_tasks.add_task(
                sync_qa_test_to_erp,
                db_test.id
            )
        
        # Transform to response
        return QATestResponse(
            id=str(db_test.id),
            order_number=db_test.order_number,
            job_id=db_test.job_id,
            client_code=db_test.client_code,
            creation_date=db_test.created_at,
            test_start=db_test.test_start,
            test_status=db_test.status,
            batch_size=db_test.batch_size,
            failure_count=db_test.failure_count,
            tester_initials=db_test.tester_initials,
            testing_area=db_test.testing_area
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating QA test status {test_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error updating QA test status: {str(e)}"
        )


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_qa_sync(
    background_tasks: BackgroundTasks,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    force: bool = False,
    current_user: User = Depends(get_current_user)
):
    """
    Trigger a synchronization between middleware and QA system.
    
    Parameters:
    - start_date: Start date for sync (defaults to yesterday)
    - end_date: End date for sync (defaults to today)
    - force: Force sync even for already synced records
    """
    # Check permissions
    check_permissions(current_user, "qa:admin")
    
    # Set default date range if not provided
    if not start_date:
        start_date = date.today() - timedelta(days=1)
    
    if not end_date:
        end_date = date.today()
    
    # Schedule the background task
    background_tasks.add_task(
        sync_qa_system_to_middleware,
        start_date,
        end_date,
        force
    )
    
    return {
        "message": "QA synchronization started",
        "parameters": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "force": force
        }
    }


# Background task functions
async def sync_qa_test_to_qa_system(test_id: uuid.UUID, operation: str):
    """
    Synchronize a QA test from middleware to QA system.
    
    Parameters:
    - test_id: UUID of the test to sync
    - operation: Type of operation (create, update, status)
    """
    db = SessionLocal()
    try:
        # Retrieve the test
        test = db.query(QATest).filter(QATest.id == test_id).first()
        
        if not test:
            logger.error(f"QA test with ID {test_id} not found for sync")
            return
        
        # Map the test data to QA system format
        qa_data = {
            "order_number": test.order_number,
            "client_code": test.client_code,
            "creation_date": format_iso_datetime(test.created_at),
            "planned_inspection": format_iso_datetime(test.planned_inspection) if test.planned_inspection else None,
            "test_start": format_iso_datetime(test.test_start) if test.test_start else None,
            "completed_dt": format_iso_datetime(test.completed_dt) if test.completed_dt else None,
            "test_status": test.status,
            "priority": test.priority,
            "batch_size": test.batch_size,
            "failure_count": test.failure_count,
            "tester_initials": test.tester_initials,
            "product_desc": test.product_desc,
            "testing_area": test.testing_area,
            "comments": test.comments,
            "measurements": test.measurements
        }
        
        # Perform the sync operation
        if operation == "create":
            qa_id = await qa_client.create_test(qa_data)
            test.qa_system_id = qa_id
        elif operation == "update":
            await qa_client.update_test(test.qa_system_id, qa_data)
        elif operation == "status":
            await qa_client.update_test_status(
                test.qa_system_id,
                test.status,
                test.comments
            )
        
        # Update sync status and timestamp
        test.sync_status = "synced"
        test.last_synced = datetime.utcnow()
        db.commit()
        
        logger.info(f"Successfully synced QA test {test_id} to QA system, operation: {operation}")
    
    except QAClientException as e:
        logger.error(f"Error syncing QA test {test_id} to QA system: {str(e)}")
        # Update sync status to failed
        test.sync_status = "failed"
        test.sync_error = str(e)
        db.commit()
    except Exception as e:
        logger.error(f"Unexpected error during QA test sync: {str(e)}")
        # Update sync status to failed
        test.sync_status = "failed"
        test.sync_error = str(e)
        db.commit()
    finally:
        db.close()


async def sync_qa_system_to_middleware(start_date: date, end_date: date, force: bool = False):
    """
    Synchronize QA tests from QA system to middleware.
    
    Parameters:
    - start_date: Start date for sync
    - end_date: End date for sync
    - force: Force sync even for already synced records
    """
    db = SessionLocal()
    try:
        logger.info(f"Starting QA system to middleware sync for date range: {start_date} to {end_date}")
        
        # Fetch QA tests from QA system
        qa_tests = await qa_client.get_tests(
            start_date=start_date,
            end_date=end_date
        )
        
        logger.info(f"Retrieved {len(qa_tests)} tests from QA system")
        
        # Process each test
        for qa_test in qa_tests:
            try:
                # Check if test already exists
                existing_test = db.query(QATest).filter(
                    QATest.qa_system_id == qa_test["id"]
                ).first()
                
                if existing_test and not force:
                    # Skip if already synced and not forcing
                    if existing_test.sync_status == "synced" and existing_test.last_synced:
                        qa_last_modified = datetime.fromisoformat(qa_test["last_modified"])
                        if existing_test.last_synced > qa_last_modified:
                            logger.debug(f"Skipping already synced test: {qa_test['id']}")
                            continue
                
                # Map QA system data to middleware format
                test_data = {
                    "order_number": qa_test["order_number"],
                    "client_code": qa_test["client_code"],
                    "created_at": convert_to_utc(qa_test["creation_date"]),
                    "planned_inspection": convert_to_utc(qa_test["planned_inspection"]) if qa_test.get("planned_inspection") else None,
                    "test_start": convert_to_utc(qa_test["test_start"]) if qa_test.get("test_start") else None,
                    "completed_dt": convert_to_utc(qa_test["completed_dt"]) if qa_test.get("completed_dt") else None,
                    "status": qa_test["test_status"],
                    "priority": qa_test["priority"],
                    "batch_size": qa_test["batch_size"],
                    "failure_count": qa_test.get("failure_count", 0),
                    "tester_initials": qa_test["tester_initials"],
                    "product_desc": qa_test["product_desc"],
                    "testing_area": qa_test["testing_area"],
                    "comments": qa_test.get("comments"),
                    "measurements": qa_test.get("measurements", {}),
                    "qa_system_id": qa_test["id"],
                    "sync_status": "synced",
                    "last_synced": datetime.utcnow()
                }
                
                if existing_test:
                    # Update existing test
                    for key, value in test_data.items():
                        setattr(existing_test, key, value)
                else:
                    # Create new test
                    new_test = QATest(
                        id=uuid.uuid4(),
                        **test_data
                    )
                    db.add(new_test)
                
                # Link to job if order number matches
                order_number = qa_test["order_number"]
                if order_number.startswith("JOB-"):
                    try:
                        job_id = int(order_number.replace("JOB-", ""))
                        job = db.query(Job).filter(Job.id == job_id).first()
                        
                        if job:
                            if existing_test:
                                existing_test.job_id = job.id
                            else:
                                new_test.job_id = job.id
                    except ValueError:
                        logger.warning(f"Could not parse job ID from order number: {order_number}")
                
                # Commit the transaction
                db.commit()
                logger.debug(f"Successfully synced QA test: {qa_test['id']}")
            
            except Exception as e:
                db.rollback()
                logger.error(f"Error processing QA test {qa_test.get('id')}: {str(e)}")
        
        logger.info("QA system to middleware sync completed")
    
    except QAClientException as e:
        logger.error(f"Error retrieving tests from QA system: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error during QA system sync: {str(e)}")
    finally:
        db.close()
