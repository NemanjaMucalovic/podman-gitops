import os
import pytest
from pathlib import Path
from src.core.state_manager import StateManager

@pytest.fixture
def state_manager(tmp_path):
    """Create a StateManager instance with a temporary database."""
    db_path = tmp_path / "test.db"
    return StateManager(db_path)

def test_service_state_tracking(state_manager):
    """Test tracking service states."""
    # Test initial state
    assert state_manager.get_service_state("test-service") is None
    
    # Test setting state
    state_manager.set_service_state("test-service", "running")
    assert state_manager.get_service_state("test-service") == "running"
    
    # Test updating state
    state_manager.set_service_state("test-service", "stopped")
    assert state_manager.get_service_state("test-service") == "stopped"
    
    # Test removing state
    state_manager.remove_service_state("test-service")
    assert state_manager.get_service_state("test-service") is None

def test_deployment_history(state_manager):
    """Test deployment history tracking."""
    # Test initial history
    assert state_manager.get_deployment_history("test-service") == []
    
    # Test adding deployment
    state_manager.add_deployment("test-service", "v1", "success")
    history = state_manager.get_deployment_history("test-service")
    assert len(history) == 1
    assert history[0]["version"] == "v1"
    assert history[0]["status"] == "success"
    
    # Test adding multiple deployments
    state_manager.add_deployment("test-service", "v2", "failed")
    history = state_manager.get_deployment_history("test-service")
    assert len(history) == 2
    assert history[0]["version"] == "v2"
    assert history[0]["status"] == "failed"
    assert history[1]["version"] == "v1"
    assert history[1]["status"] == "success"

def test_error_tracking(state_manager):
    """Test error tracking."""
    # Test initial error state
    assert state_manager.get_last_error("test-service") is None
    
    # Test setting error
    error_msg = "Test error message"
    state_manager.set_last_error("test-service", error_msg)
    assert state_manager.get_last_error("test-service") == error_msg
    
    # Test clearing error
    state_manager.clear_last_error("test-service")
    assert state_manager.get_last_error("test-service") is None

def test_service_dependencies(state_manager):
    """Test service dependency tracking."""
    # Test initial dependencies
    assert state_manager.get_service_dependencies("test-service") == []
    
    # Test setting dependencies
    deps = ["dep1", "dep2"]
    state_manager.set_service_dependencies("test-service", deps)
    assert state_manager.get_service_dependencies("test-service") == deps
    
    # Test updating dependencies
    new_deps = ["dep3"]
    state_manager.set_service_dependencies("test-service", new_deps)
    assert state_manager.get_service_dependencies("test-service") == new_deps
    
    # Test removing dependencies
    state_manager.set_service_dependencies("test-service", [])
    assert state_manager.get_service_dependencies("test-service") == []

def test_service_configuration(state_manager):
    """Test service configuration tracking."""
    # Test initial configuration
    assert state_manager.get_service_configuration("test-service") is None
    
    # Test setting configuration
    config = {"port": 8080, "env": "prod"}
    state_manager.set_service_configuration("test-service", config)
    assert state_manager.get_service_configuration("test-service") == config
    
    # Test updating configuration
    new_config = {"port": 9090, "env": "dev"}
    state_manager.set_service_configuration("test-service", new_config)
    assert state_manager.get_service_configuration("test-service") == new_config
    
    # Test removing configuration
    state_manager.set_service_configuration("test-service", None)
    assert state_manager.get_service_configuration("test-service") is None

def test_service_health_history(state_manager):
    """Test service health history tracking."""
    # Test initial health history
    assert state_manager.get_service_health_history("test-service") == []
    
    # Test adding health check
    health_data = {"status": "healthy", "timestamp": "2024-01-01T00:00:00"}
    state_manager.add_health_check("test-service", health_data)
    history = state_manager.get_service_health_history("test-service")
    assert len(history) == 1
    assert history[0]["status"] == "healthy"
    
    # Test adding multiple health checks
    health_data2 = {"status": "unhealthy", "timestamp": "2024-01-01T00:01:00"}
    state_manager.add_health_check("test-service", health_data2)
    history = state_manager.get_service_health_history("test-service")
    assert len(history) == 2
    assert history[0]["status"] == "unhealthy"
    assert history[1]["status"] == "healthy"

def test_service_rollback_history(state_manager):
    """Test service rollback history tracking."""
    # Test initial rollback history
    assert state_manager.get_service_rollback_history("test-service") == []
    
    # Test adding rollback
    rollback_data = {"version": "v1", "reason": "deployment failed"}
    state_manager.add_rollback("test-service", rollback_data)
    history = state_manager.get_service_rollback_history("test-service")
    assert len(history) == 1
    assert history[0]["version"] == "v1"
    assert history[0]["reason"] == "deployment failed"
    
    # Test adding multiple rollbacks
    rollback_data2 = {"version": "v2", "reason": "health check failed"}
    state_manager.add_rollback("test-service", rollback_data2)
    history = state_manager.get_service_rollback_history("test-service")
    assert len(history) == 2
    assert history[0]["version"] == "v2"
    assert history[0]["reason"] == "health check failed"
    assert history[1]["version"] == "v1"
    assert history[1]["reason"] == "deployment failed" 