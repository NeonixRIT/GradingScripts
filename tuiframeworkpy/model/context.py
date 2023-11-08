from dataclasses import dataclass
from typing import Any

from ..jsonconfigmanagerpy import ConfigManager
from ..dependencymanagerpy import DependencyManager


@dataclass
class Context:
    config_manager: ConfigManager
    dependency_manager: DependencyManager
    main: Any
