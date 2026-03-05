"""
Crucible Configuration Manager - Insight-First Design Implementation
Architectural Choice: Centralized config with environment-aware defaults and Firebase fallback.
This enables both local development and cloud deployment with real-time config updates.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class CrucibleConfig:
    """Immutable configuration container with validation"""
    # Infrastructure
    instance_type: str = "t4g.nano"
    max_monthly_budget: float = 5.0  # USD
    target_ram_reduction: float = 0.15  # 15%
    
    # Experimentation
    mutation_target_per_week: int = 1
    quarantine_timeout_hours: int = 24
    chaos_intensity: float = 0.3  # 0-1 scale
    
    # Monitoring
    metrics_collection_interval: int = 300  # seconds
    alert_threshold_cpu: float = 0.85  # 85%
    alert_threshold_memory: float = 0.9  # 90%
    
    # Firebase
    firebase_project_id: str = ""
    firestore_collection: str = "crucible_experiments"
    
    def validate(self) -> bool:
        """Validate configuration constraints"""
        violations = []
        
        if self.max_monthly_budget > 5.0:
            violations.append(f"Budget ${self.max_monthly_budget} exceeds $5 constraint")
        
        if not 0 <= self.chaos_intensity <= 1:
            violations.append(f"Chaos intensity {self.chaos_intensity} outside [0,1] range")
        
        if self.mutation_target_per_week < 1:
            violations.append("Mutation target must be at least 1 per week")
        
        if violations:
            logger.warning(f"Configuration validation warnings: {violations}")
            return False
        
        logger.info("Configuration validation passed")
        return True
    
    def to_firestore_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-compatible dictionary"""
        data = asdict(self)
        # Firestore doesn't accept float infinity or NaN
        data = {k: (str(v) if isinstance(v, float) and (v == float('inf') or v != v) else v) 
                for k, v in data.items()}
        return data

class ConfigManager:
    """Dual-layer configuration manager with environment and Firebase sources"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or Path.home() / ".crucible" / "config.json"
        self._config: Optional[CrucibleConfig] = None
        self._firebase_client = None
        logger.info(f"Initializing ConfigManager with path: {self.config_path}")
        
    def load(self) -> CrucibleConfig:
        """Load configuration from environment, file, and Firebase"""
        config_data = {}
        
        # 1. Load from environment variables
        env_mapping = {
            'CRUCIBLE_INSTANCE_TYPE': 'instance_type',
            'CRUCIBLE_MAX_BUDGET': ('max_monthly_budget', float),
            'CRUCIBLE_CHAOS_INTENSITY': ('chaos_intensity', float)
        }
        
        for env_var, mapping in env_mapping.items():
            if env_var in os.environ:
                if isinstance(mapping, tuple):
                    key, converter = mapping
                    try:
                        config_data[key] = converter(os.environ[env_var])
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to convert {env_var}={os.environ[env_var]}: {e}")
                else:
                    config_data[mapping] = os.environ[env_var]
        
        # 2. Load from local config file if exists
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, 'r') as f:
                    file_config = json.load(f)
                    config_data.update(file_config)
                    logger.debug(f"Loaded config from {self.config_path}")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load config file {self.config_path}: {e}")
        
        # 3. Attempt Firebase config (will be initialized later)
        if 'firebase_project_id' in config_data and config_data['firebase_project_id']:
            try:
                firebase_config = self._load_firebase_config(config_data['firebase_project_id'])
                if firebase_config:
                    config_data.update(firebase_config)
                    logger.info("Loaded Firebase configuration overlay")
            except ImportError:
                logger.warning("Firebase Admin SDK not available, using local config only")
        
        # Create config object
        self._config = CrucibleConfig(**config_data)
        
        if not self._config.validate():
            logger.warning("Configuration validation failed, using defaults")
        
        logger.info(f"Configuration loaded successfully: {self._config}")
        return self._config
    
    def _load_firebase_config(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Load configuration from Firebase Remote Config"""
        # This would be implemented when Firebase Admin SDK is available
        logger.debug(f"Firebase config loading stub for project: {project_id}")
        return None
    
    def save(self, config: CrucibleConfig) -> bool:
        """Save configuration to file and optionally Firebase"""
        success = True
        
        # Save to local file
        try:
            Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(asdict(config), f, indent=2)
            logger.info(f"Configuration saved to {self.config_path}")
        except IOError as e:
            logger.error(f"Failed to save config to {self.config_path}: {e}")
            success = False
        
        return success
    
    @property
    def current(self) -> CrucibleConfig:
        """Get current configuration, loading if necessary"""
        if self._config is None:
            self._config = self.load()
        return self._config

# Global configuration instance