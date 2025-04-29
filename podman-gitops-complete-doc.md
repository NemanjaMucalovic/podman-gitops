# Podman GitOps - Project Documentation

## Project Overview

Podman GitOps is a lightweight, self-contained GitOps tool designed specifically for managing Podman container deployments using quadlet files. The tool follows the GitOps principle of using Git as the single source of truth for declarative infrastructure and applications.

## Core Value Proposition

This tool addresses the need for a simple, resource-efficient GitOps solution for individual Podman hosts, especially in edge computing environments. While many GitOps tools focus on Kubernetes, Podman GitOps targets standalone Podman deployments on resource-constrained devices like Raspberry Pi and small VMs.

## Key Features

1. **Git-Centric Deployment Approach**
   * Git repository as source of truth for Podman quadlet files
   * Polling-based change detection with efficient Git operations
   * Optimized for resource-constrained environments

2. **Independent Node Architecture**
   * Self-contained deployment logic on each Podman host
   * No central orchestration required
   * No dependencies between nodes

3. **Robust State Management**
   * SQLite database for atomic state operations
   * Transaction-based updates to prevent state corruption
   * Deployment history tracking and querying

4. **Comprehensive Observability**
   * FastAPI endpoint exposing Prometheus metrics
   * Key metrics for deployments, Git operations, and system health
   * Ready for Grafana dashboard integration

5. **Resilient Deployment Process**
   * Automatic health checks after deployments
   * Autonomous rollback capability on failure
   * Local backup of previous working configurations

6. **Secret Management**
   * Environment variable-based secret handling using python-dotenv
   * No sensitive data stored in Git
   * Secure processing of environment files

7. **Notification System**
   * Configurable notifications for deployment events
   * Support for email and custom endpoints
   * Throttling to prevent notification storms

## Technical Specifications

### Target Environments
* **Primary**: Virtual machines on various providers
* **Secondary**: Raspberry Pi devices (ARM)
* **Minimum Requirements**: 512MB RAM, 1GB storage

### Technology Stack
* **Language**: Python 3.8+
* **State Storage**: SQLite
* **Metrics**: Prometheus via FastAPI
* **Configuration**: TOML with Pydantic validation
* **Container Runtime**: Podman with quadlet support
* **Package Management**: uv (for efficient, reliable Python package installation)
* **Code Quality**: ruff (for linting and formatting)
* **Data Modeling**: Pydantic for external interfaces, dataclasses for internal structures
* **Secret Management**: python-dotenv for environment variable handling

## Core Components

1. **Git Operations Handler**
   * Efficient Git operations (shallow clone, sparse checkout)
   * Incremental updates to minimize bandwidth
   * Secure credential handling
   * Implementation using GitPython

2. **Quadlet Processor**
   * Parsing and validation of quadlet files using Pydantic
   * Support for variable templating
   * Environment variable substitution
   * Deployment to systemd directories

3. **Environment File Processor**
   * Processing .env files with python-dotenv
   * Variable substitution from environment
   * Secure handling of processed files
   * Integration with quadlet files

4. **Systemd Manager**
   * Interaction with systemd for service management
   * Controlled service reloads and restarts
   * Service status monitoring

5. **Health Checker**
   * Container health verification (HTTP, TCP, Command)
   * Custom health check definitions
   * Multiple verification strategies
   * Automatic failure detection
   * Optional Podman Python SDK integration

6. **State Manager**
   * SQLite-based state tracking with dataclasses
   * Deployment history and status
   * Rollback point management
   * Transaction-based operations

7. **Metrics Endpoint**
   * FastAPI server for Prometheus metrics
   * Resource-efficient metrics collection
   * Configurable endpoint settings
   * Pydantic models for API responses

8. **Notification Dispatcher**
   * Event-based notification system
   * Multiple delivery methods
   * Template-based messages

## Project Structure

```
podman-gitops/
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── git_operations.py    # Git clone/pull functionality
│   │   ├── quadlet_handler.py   # Processing quadlet files
│   │   ├── env_processor.py     # Environment file processing
│   │   ├── systemd_manager.py   # Interacting with systemd
│   │   ├── health_checker.py    # Container health verification
│   │   └── config.py            # Configuration handling
│   ├── state/
│   │   ├── __init__.py
│   │   ├── models.py            # SQLite DB models
│   │   └── manager.py           # State operations
│   ├── metrics/
│   │   ├── __init__.py
│   │   ├── collector.py         # Prometheus metrics collection
│   │   └── server.py            # FastAPI server for metrics
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── dispatcher.py        # Notification logic
│   └── main.py                  # Entry point
├── tests/
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── conftest.py              # Test fixtures
├── scripts/
│   ├── install.sh               # Installation script
│   └── systemd/                 # Systemd service files
├── examples/
│   ├── config.toml              # Example configurations
│   └── quadlets/                # Example quadlet files
├── docs/
│   ├── index.md                 # Documentation home
│   ├── installation.md          # Installation guide
│   ├── configuration.md         # Configuration reference
│   └── development.md           # Development guide
├── .github/                     # GitHub specific files
│   ├── workflows/               # GitHub Actions CI/CD
│   └── ISSUE_TEMPLATE/          # Issue templates
├── pyproject.toml               # Project metadata and dependencies
├── README.md                    # Project overview
├── CONTRIBUTING.md              # Contribution guidelines
└── LICENSE                      # Open source license
```

## Development Roadmap

### Version 0.1.0 - Foundation Release
* Basic Git polling mechanism
* Simple quadlet file deployment
* Rudimentary SQLite state tracking
* Basic systemd service management
* Minimal CLI interface
* Configuration via TOML file with Pydantic validation
* Initial documentation

### Version 0.2.0 - Resilience Update
* Improved error handling
* Backup and restore functionality
* Basic health checking for deployed containers
* Automatic rollback on deployment failure
* Enhanced state tracking with deployment history (using dataclasses)
* Improved logging system
* Installation script

### Version 0.3.0 - Metrics & Monitoring
* FastAPI metrics endpoint
* Prometheus metrics collection
* Core operational metrics
  * Deployment success/failure rates
  * Git operation statistics
  * Health check results
* Basic resource usage reporting
* Simple status dashboard

### Version 0.4.0 - Secret Management & Notification System
* Python-dotenv integration for environment variables
* Secure environment file processing
* Environment variable substitution in quadlet files
* Email notifications for deployment events
* Configurable notification templates
* Notification filtering and throttling
* Better error reporting

### Version 0.5.0 - Deployment Enhancements
* Improved quadlet file validation with Pydantic
* Pre-deployment checks
* Support for quadlet templating
* Phased deployment capability
* Deployment scheduling options
* Enhanced backup management
* Efficient Git operations for limited bandwidth

### Version 0.6.0 - Health Check Improvements
* Enhanced container health verification
* Multiple health check strategies (HTTP, TCP, command)
* Optional Podman Python SDK integration
* Dependency-aware health checking
* Customizable retry and timeout settings
* Health history tracking
* Container resource health monitoring

### Version 0.7.0 - Security Improvements
* Secure credential handling
* Environment variable support for secrets
* Input validation and sanitization
* Enhanced permission management
* Secure logging practices
* Audit trail for deployments

### Version 0.8.0 - User Experience
* Improved CLI with rich output
* Status reporting commands
* Interactive configuration assistant
* Example Grafana dashboards
* Better documentation with tutorials
* Troubleshooting guides

### Version 0.9.0 - Testing & Pre-Release Preparation
* Comprehensive testing suite
* Performance optimization
* Bug fixes and stability improvements
* Documentation completion
* Package distribution setup
* Installation streamlining
* Example deployment scenarios
* Migration tools and guides
* Upgrade path testing
* Resource optimization for edge devices

### Version 1.0.0 - Complete Release
* Production-ready stability
* All planned features implemented
* Comprehensive documentation
* Example deployments and use cases
* Well-defined APIs for extension
* Verified compatibility across target environments

## Configuration Specification

The tool uses a TOML configuration file with Pydantic validation. Key configuration sections include:

1. **Git Configuration**
   * Repository URL and branch
   * Sparse checkout paths
   * Polling interval
   * Credential management

2. **Quadlet Settings**
   * System directory for quadlet files
   * Backup directory
   * Validation options

3. **Health Check Configuration**
   * Default timing parameters
   * Container-specific health checks
   * Strategy definitions (HTTP, TCP, command)

4. **Notification Settings**
   * Email configuration
   * Custom endpoints
   * Throttling parameters

5. **Secrets Management**
   * Environment file directory
   * Missing variable handling

6. **State Management**
   * Database path
   * History retention policy

7. **Metrics Configuration**
   * Endpoint settings
   * Collection parameters

8. **System Settings**
   * Logging level
   * Debug options

## SQLite Schema Design

The state database uses the following core tables:

1. **deployments**
   * Deployment identifier and metadata
   * Git reference information
   * Timestamp and status tracking
   * Description and details

2. **containers**
   * Container identifier and metadata
   * Relation to deployment
   * Quadlet file reference
   * Status and health information

3. **backups**
   * Backup identifier
   * Relation to deployment
   * File paths
   * Timestamp information

4. **events**
   * Event tracking and logging
   * Optional relation to deployments
   * Timestamp and type classification
   * Detailed message contents

## Health Check System Architecture

The health check system in Podman GitOps is designed to verify the proper functioning of containers after deployment. It uses a combination of Pydantic for configuration validation and dataclasses for internal data structures.

### Core Health Check Features

1. **Multiple Health Check Types**:
   * HTTP endpoint checks for web services
   * TCP socket connections for database and cache services
   * Custom command execution for specialized verification
   * Process status verification for basic checks
   * Optional Podman SDK integration for deeper container inspection

2. **Fallback Mechanisms**:
   When no explicit health check is defined, the system follows this precedence:
   
   ```
   Container-specific config in TOML → Health checks in quadlet file → Default check
   ```

3. **Default Health Check Behavior**:
   * Verifies container running state
   * Provides minimal assurance without application-specific checks
   * Configurable with reasonable defaults

4. **Advanced Health Check Features**:
   * Dependency awareness for proper check ordering
   * Retry mechanisms with exponential backoff
   * Detailed failure reporting
   * Failure threshold configuration

## Secret Management with python-dotenv

Podman GitOps uses python-dotenv for secure and flexible secret management without storing sensitive information in Git repositories.

### Environment File Processing Flow

The tool handles environment files (.env) as follows:

1. **Repository Structure**: 
   * .env files in the repository contain variable references but not actual secrets
   * Variables are referenced using standard `$VARIABLE` or `${VARIABLE}` syntax

2. **Secret Sources**: 
   * Host system environment variables
   * Service-specific prefixed variables (e.g., SERVICENAME_VARIABLE)

3. **Processing Steps**: 
   * Read .env files from the repository
   * Substitute variables with values from the environment
   * Store processed files securely with restricted permissions

4. **Integration with Quadlet Files**:
   * Quadlet files reference .env files
   * During deployment, these references are updated to point to processed files

5. **Security Measures**: 
   * Processed files stored with 0600 permissions
   * Directories secured with 0700 permissions
   * Missing variables clearly logged

### Benefits of This Approach

1. **Separation of Configuration and Secrets**: No sensitive values in Git
2. **Flexibility**: Works with existing environment variable patterns
3. **Minimal Dependencies**: python-dotenv is lightweight and well-maintained
4. **Security**: Secure file permissions for processed files
5. **Visibility**: Clear logging of missing variables for troubleshooting

## Prometheus Metrics

Core metrics exposed by the system:

1. **Operational Metrics**
   * Git operations tracking by type and status
   * Deployment metrics with status classification
   * Duration measurements for performance monitoring
   * Rollback operation counting
   * Health check result statistics

2. **State Metrics**
   * Running container counts
   * Failed container tracking
   * Timestamp monitoring of successful operations

3. **Resource Usage Metrics**
   * Memory consumption tracking
   * CPU utilization percentage
   * Storage usage for backups and state data

## Architecture and Flow Diagrams

### System Architecture

```
+----------------------------------------------+
|                Podman GitOps Tool            |
+---------------+---------------+---------------+
|               |               |               |
| Git Handler   | Quadlet       | Systemd      |
|               | Processor     | Manager      |
|               |               |               |
+---------------+---------------+---------------+
|               |               |               |
| EnvFile       | Health        | Notifier     |
| Processor     | Checker       |               |
|               |               |               |
+---------------+---------------+---------------+
|                                              |
|          SQLite State Manager                |
|          (Using Dataclasses)                 |
|                                              |
+---------------------------+------------------+
|                           |                  |
| Main Service              | FastAPI Metrics  |
|                           | Server           |
+---------------------------+------------------+
        |                           |
        | Reads/Writes              | Exposes
        ▼                           ▼
+---------------+          +----------------+
|               |          |                |
| Podman        |◄---------| Prometheus    |
|               | Monitors |                |
+---------------+          +----------------+
        |                           |
        | Manages                   | Scrapes
        ▼                           ▼
+---------------+          +----------------+
|               |          |                |
| Containers    |          | Grafana        |
|               |          |                |
+---------------+          +----------------+
```

### Deployment Flow

```
+------------------+
|                  |
|   Start Poll     |
|                  |
+--------+---------+
         |
         ▼
+------------------+
| Check Git for    |
|    Changes       |◄------------------+
+--------+---------+                   |
         |                             |
         ▼                             |
+------------------+                   |
| Changes Found?   |---- No -----------+
+--------+---------+
         | Yes
         ▼
+------------------+
| Process .env     |  <-- Using python-dotenv
|    Files         |      for variable substitution
+--------+---------+
         |
         ▼
+------------------+
| Process Quadlet  |  <-- Using Pydantic for validation
|     Files        |
+--------+---------+
         |
         ▼
+------------------+
| Backup Current   |
|     State        |
+--------+---------+
         |
         ▼
+------------------+
| Deploy Quadlet   |
|     Files        |
+--------+---------+
         |
         ▼
+------------------+
| Reload Systemd   |
|    Services      |
+--------+---------+
         |
         ▼
+------------------+
| Health Check     |  <-- Using dataclasses for results
|   Containers     |
+--------+---------+
         |
         ▼
+------------------+                +------------------+
| Successful?      |---- No ------->|     Rollback     |
+--------+---------+                |    Deployment    |
         | Yes                      +--------+---------+
         ▼                                   |
+------------------+                         |
| Update State     |                         |
|    Database      |                         |
+--------+---------+                         |
         |                                   |
         ▼                                   |
+------------------+                         |
|  Send Success    |                         |
|  Notification    |                         |
+--------+---------+                         |
         |                                   |
         |                                   |
         |                                   ▼
         |                          +------------------+
         |                          |   Send Failure   |
         |                          |   Notification   |
         |                          +--------+---------+
         |                                   |
         ▼                                   ▼
+--------------------------------------------------+
|                                                  |
|              Wait for Next Poll                  |
|                                                  |
+--------------------------------------------------+
```

## Implementation Details

### Data Modeling Approach

Podman GitOps uses a hybrid approach to data modeling:

1. **Pydantic Models** for external interfaces and configuration:
   * Configuration parsing and validation
   * API input/output schemas
   * Quadlet file validation

2. **Dataclasses** for internal data structures:
   * Deployment results
   * Health check results
   * State tracking

This provides strong validation at the boundaries while keeping internal code simple and efficient.

### Core Dependencies

The project uses the following key dependencies:

1. **GitPython**: For Git repository operations
2. **FastAPI**: For the metrics API
3. **Pydantic**: For data validation and configuration
4. **python-dotenv**: For environment variable handling
5. **SQLite**: For state storage (built into Python)
6. **podman-py** (optional): For advanced container health checks
7. **httpx**: For HTTP health checks and API calls
8. **uv**: For package management

### Getting Started for Contributors

1. **Setup Development Environment**
   * Clone the repository
   * Create and activate virtual environment
   * Install dependencies using uv

2. **Running Tests**
   * Unit tests for component verification
   * Integration tests for system validation

3. **Code Style**
   * Uses ruff for formatting and linting
   * Type checking with mypy

4. **Contribution Workflow**
   * Fork the repository
   * Create feature branches
   * Submit pull requests with tests
   * Follow the contribution guidelines

## License

This project is licensed under the MIT License - see the LICENSE file for details.
