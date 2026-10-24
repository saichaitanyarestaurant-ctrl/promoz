import httpx
import logging
from typing import Dict, Any, Optional
from ..models.task import Task, TaskStatus
from ..models.service_config import ServiceConfig
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class TaskRouter:
    def __init__(self, db: Session):
        self.db = db
        self.service_urls = {
            "browser_service": os.getenv("BROWSER_SERVICE_URL", "http://localhost:8001"),
            "document_service": os.getenv("DOCUMENT_SERVICE_URL", "http://localhost:8002"),
            "communication_service": os.getenv("COMMUNICATION_SERVICE_URL", "http://localhost:8003"),
            "media_service": os.getenv("MEDIA_SERVICE_URL", "http://localhost:8004"),
            "bot_builder_service": os.getenv("BOT_BUILDER_SERVICE_URL", "http://localhost:8005"),
        }

    async def route_task(self, task: Task) -> Dict[str, Any]:
        """
        Route a task to the appropriate service and return the response.
        """
        try:
            # Get service configuration
            service_config = self._get_service_config(task.target_service)
            if not service_config or not service_config.is_active:
                raise ValueError(f"Service {task.target_service} is not available or inactive")

            # Update task status
            task.status = TaskStatus.PROCESSING
            self.db.commit()

            # Prefer the configured service URL, falling back to environment
            # defaults. Normalize slashes to avoid requests like /service//execute.
            service_url = (service_config.base_url or self._get_service_url(task.target_service)).rstrip("/")
            endpoint = "/" + (task.service_endpoint or self._get_default_endpoint(task.target_service)).strip("/")
            if not service_url:
                raise ValueError(f"No base URL configured for service {task.target_service}")
            
            # Prepare request payload
            payload = {
                "task_id": task.id,
                "command": task.command,
                "parameters": task.parameters or {},
                "priority": task.priority.value
            }

            # Make request to service
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{service_url}/{endpoint}",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    task.result = result
                    task.status = TaskStatus.COMPLETED
                    logger.info(f"Task {task.id} completed successfully")
                    return result
                else:
                    error_msg = f"Service returned error: {response.status_code} - {response.text}"
                    task.error_message = error_msg
                    task.status = TaskStatus.FAILED
                    logger.error(f"Task {task.id} failed: {error_msg}")
                    raise Exception(error_msg)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            logger.error(f"Error routing task {task.id}: {e}")
            raise

        finally:
            self.db.commit()

    def _get_service_config(self, service_name: str) -> Optional[ServiceConfig]:
        """
        Get service configuration from database.
        """
        return self.db.query(ServiceConfig).filter(
            ServiceConfig.service_name == service_name
        ).first()

    def _get_service_url(self, service_name: str) -> str:
        """
        Get the base URL for a service.
        """
        return self.service_urls.get(service_name, "")

    def _get_default_endpoint(self, service_name: str) -> str:
        """
        Get the default endpoint for a service.
        """
        endpoints = {
            "browser_service": "execute",
            "document_service": "process",
            "communication_service": "handle",
            "media_service": "process",
            "bot_builder_service": "create"
        }
        return endpoints.get(service_name, "execute")

    async def check_service_health(self, service_name: str) -> bool:
        """
        Check if a service is healthy and responding.
        """
        try:
            service_url = self._get_service_url(service_name)
            if not service_url:
                return False

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{service_url}/health")
                return response.status_code == 200

        except Exception as e:
            logger.error(f"Health check failed for {service_name}: {e}")
            return False

    def get_available_services(self) -> Dict[str, bool]:
        """
        Get list of available services and their health status.
        """
        services = {}
        for service_name in self.service_urls.keys():
            # This would be better as an async call, but keeping it simple for now
            services[service_name] = True  # Assume healthy for now
        return services