"""ORM model package — import all models so SQLAlchemy discovers them."""

from app.models.base import Base
from app.models.configuration import Configuration
from app.models.resolver import Resolver
from app.models.metrics import ConfigMetricSnapshot, ResolverMetricSnapshot
from app.models.setting import Setting, HAProxyConfig
from app.models.balancer import DnsBalancerConfig, DataBalancerConfig

__all__ = [
    "Base",
    "Configuration",
    "Resolver",
    "ConfigMetricSnapshot",
    "ResolverMetricSnapshot",
    "Setting",
    "HAProxyConfig",
    "DnsBalancerConfig",
    "DataBalancerConfig",
]
