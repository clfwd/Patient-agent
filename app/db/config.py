"""数据库配置相关工具。"""

import os


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_SQLITE_PATH = os.path.join(PROJECT_ROOT, "patient_agent.db")
DEFAULT_SQLITE_URL = "sqlite:///{0}".format(DEFAULT_SQLITE_PATH.replace("\\", "/"))


def get_database_url():
    """返回数据库连接地址。

    默认使用项目根目录下的 SQLite 文件，避免因工作目录不同而落到多个数据库。
    """

    return os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)
