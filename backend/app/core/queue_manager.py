import asyncio
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from ..models.task import Task, TaskStatus, TaskPriority
from .task_router import TaskRouter
from datetime import datetime
import heapq

logger = logging.getLogger(__name__)

class QueueManager:
    def __init__(self, db: Session):
        self.db = db
        self.task_router = TaskRouter(db)
        self.processing_queue = asyncio.Queue()
        self.priority_queue = []
        self.max_concurrent_tasks = 5
        self.active_tasks = 0
        self.task_workers = []

    async def add_task(self, task: Task) -> bool:
        """
        Add a task to the processing queue.
        """
        try:
            # Set initial status
            task.status = TaskStatus.PENDING
            task.created_at = datetime.utcnow()
            self.db.add(task)
            self.db.commit()
            
            # Add to priority queue
            priority_score = self._calculate_priority_score(task)
            heapq.heappush(self.priority_queue, (-priority_score, task.id, task))
            
            logger.info(f"Task {task.id} added to queue with priority score {priority_score}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding task to queue: {e}")
            self.db.rollback()
            return False

    def _calculate_priority_score(self, task: Task) -> float:
        """
        Calculate priority score for task ordering.
        Higher score = higher priority.
        """
        base_score = {
            TaskPriority.LOW: 1.0,
            TaskPriority.MEDIUM: 2.0,
            TaskPriority.HIGH: 3.0,
            TaskPriority.URGENT: 4.0
        }.get(task.priority, 2.0)
        
        # Add time-based boost (older tasks get higher priority)
        time_boost = 0.1  # Small boost per minute
        return base_score

    async def get_next_task(self) -> Optional[Task]:
        """
        Get the next task from the queue based on priority.
        """
        try:
            # Discard stale/cancelled queue entries without recursive calls.
            while self.priority_queue:
                _, task_id, _queued_task = heapq.heappop(self.priority_queue)
                current_task = self.db.query(Task).filter(Task.id == task_id).first()
                if current_task and current_task.status == TaskStatus.PENDING:
                    return current_task
            return None

        except Exception as e:
            logger.error(f"Error getting next task: {e}")
            return None

    async def start_processing(self):
        """
        Start the task processing loop.
        """
        logger.info("Starting task processing queue")
        while True:
            try:
                # Check if we can process more tasks
                if self.active_tasks >= self.max_concurrent_tasks:
                    await asyncio.sleep(1)
                    continue
                
                # Get next task
                task = await self.get_next_task()
                if not task:
                    await asyncio.sleep(1)
                    continue
                
                # Start processing task
                self.active_tasks += 1
                asyncio.create_task(self._process_task(task))
                
            except Exception as e:
                logger.error(f"Error in task processing loop: {e}")
                await asyncio.sleep(1)

    async def _process_task(self, task: Task):
        """
        Process a single task.
        """
        try:
            logger.info(f"Processing task {task.id}: {task.title}")

            task.status = TaskStatus.PROCESSING
            task.started_at = datetime.utcnow()
            self.db.commit()

            # Execute the task through its configured service. Do not mark a
            # task complete merely because a simulated delay has elapsed.
            result = await self.task_router.route_task(task)
            if task.result is None and result is not None:
                task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            self.db.commit()

            logger.info(f"Task {task.id} completed successfully")

        except Exception as e:
            logger.exception("Error processing task %s", task.id)
            self.db.rollback()
            task = self.db.query(Task).filter(Task.id == task.id).first()
            if task is not None:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                self.db.commit()

        finally:
            self.active_tasks = max(0, self.active_tasks - 1)

    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current queue status and statistics.
        """
        try:
            total_pending = self.db.query(Task).filter(Task.status == TaskStatus.PENDING).count()
            total_processing = self.db.query(Task).filter(Task.status == TaskStatus.PROCESSING).count()
            total_completed = self.db.query(Task).filter(Task.status == TaskStatus.COMPLETED).count()
            total_failed = self.db.query(Task).filter(Task.status == TaskStatus.FAILED).count()
            
            return {
                "queue_size": len(self.priority_queue),
                "active_tasks": self.active_tasks,
                "max_concurrent_tasks": self.max_concurrent_tasks,
                "total_pending": total_pending,
                "total_processing": total_processing,
                "total_completed": total_completed,
                "total_failed": total_failed
            }
            
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {}

    def get_pending_tasks(self, limit: int = 10) -> List[Task]:
        """
        Get list of pending tasks ordered by priority.
        """
        try:
            return self.db.query(Task).filter(
                Task.status == TaskStatus.PENDING
            ).order_by(
                desc(Task.priority),
                asc(Task.created_at)
            ).limit(limit).all()
            
        except Exception as e:
            logger.error(f"Error getting pending tasks: {e}")
            return []

    async def cancel_task(self, task_id: int) -> bool:
        """
        Cancel a pending task.
        """
        try:
            task = self.db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return False
                
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                self.db.commit()
                logger.info(f"Task {task_id} cancelled")
                return True
            else:
                logger.warning(f"Cannot cancel task {task_id} - not in pending status")
                return False
                
        except Exception as e:
            logger.error(f"Error cancelling task {task_id}: {e}")
            return False