"""核心基础设施包

- permissions：认证依赖（见 core.permissions）
- 服务工厂：定义在 ``service`` 包（见 service/__init__.py）

推荐显式导入，例如::

    from core.permissions import get_current_active_user
"""

from .permissions import get_current_active_user

__all__ = [
    "get_current_active_user",
]
