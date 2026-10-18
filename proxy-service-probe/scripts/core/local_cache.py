# -*- coding: utf-8 -*-
"""轻量 SQLite 本地 24 小时持久化缓存管理器。

用于缓存 IP 信誉评分、四级家宽形态等级与反欺诈元数据，避免批量测试时重复请求外部接口或被限流。
"""
import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TTL = 86400.0  # 24 小时 (秒)


class LocalReputationCache:
    """线程安全的 SQLite 本地 IP 信誉缓存器，支持优雅内存回退。"""

    def __init__(self, db_path: Optional[str] = None, ttl: float = DEFAULT_TTL):
        self.ttl = ttl
        if db_path is None:
            # 默认存放在项目根目录下的 cache/ 目录中
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            cache_dir = os.path.join(base_dir, "cache")
            self.db_path = os.path.join(cache_dir, "ip_reputation_cache.db")
        else:
            self.db_path = db_path

        self._memory_fallback: Dict[str, Dict[str, Any]] = {}
        self._use_memory_only = False
        self._init_db()

    def _init_db(self) -> None:
        """初始化 SQLite 数据库表结构，失败时降级为内存字典。"""
        if self.db_path == ":memory:":
            return
        conn = None
        try:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ip_reputation_cache (
                    ip TEXT PRIMARY KEY,
                    score INTEGER,
                    res_level TEXT,
                    data_json TEXT,
                    updated_at REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_updated_at ON ip_reputation_cache(updated_at)")
            conn.commit()
        except Exception as e:
            logger.warning("SQLite 缓存初始化失败 (%s)，降级为内存缓存", e)
            self._use_memory_only = True
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get(self, ip: str) -> Optional[Dict[str, Any]]:
        """获取未过期的缓存数据，命中返回 dict，未命中或已过期返回 None。"""
        if not ip:
            return None
        now = time.time()

        if self._use_memory_only:
            item = self._memory_fallback.get(ip)
            if item and (now - item["updated_at"]) < self.ttl:
                return item["data"]
            return None

        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=3.0)
            cur = conn.cursor()
            cur.execute(
                "SELECT score, res_level, data_json, updated_at FROM ip_reputation_cache WHERE ip = ?",
                (ip,)
            )
            row = cur.fetchone()
            if row:
                score, res_level, data_json, updated_at = row
                if (now - updated_at) < self.ttl:
                    data = json.loads(data_json) if data_json else {}
                    data["score"] = score
                    data["residential_level"] = res_level
                    data["cached"] = True
                    data["cache_age_hours"] = round((now - updated_at) / 3600.0, 1)
                    return data
                else:
                    cur.execute("DELETE FROM ip_reputation_cache WHERE ip = ?", (ip,))
                    conn.commit()
        except Exception as e:
            logger.debug("读取 SQLite 缓存异常 (%s)，回退尝试内存", e)
            item = self._memory_fallback.get(ip)
            if item and (now - item["updated_at"]) < self.ttl:
                return item["data"]
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return None

    def set(self, ip: str, score: Optional[int], res_level: str, data: Dict[str, Any]) -> None:
        """写入或更新 IP 缓存数据。"""
        if not ip:
            return
        now = time.time()
        # 始终同步一份在内存字典备用
        cache_copy = dict(data)
        cache_copy["score"] = score
        cache_copy["residential_level"] = res_level
        self._memory_fallback[ip] = {"data": cache_copy, "updated_at": now}

        if self._use_memory_only:
            return

        conn = None
        try:
            data_json = json.dumps(data, ensure_ascii=False)
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            conn.execute(
                """
                INSERT INTO ip_reputation_cache (ip, score, res_level, data_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ip) DO UPDATE SET
                    score=excluded.score,
                    res_level=excluded.res_level,
                    data_json=excluded.data_json,
                    updated_at=excluded.updated_at
                """,
                (ip, score, res_level, data_json, now)
            )
            conn.commit()
        except Exception as e:
            logger.warning("写入 SQLite 缓存异常 (%s)", e)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def clear_expired(self) -> int:
        """清理已过期的旧记录。"""
        if self._use_memory_only:
            now = time.time()
            expired = [ip for ip, it in self._memory_fallback.items() if (now - it["updated_at"]) >= self.ttl]
            for ip in expired:
                del self._memory_fallback[ip]
            return len(expired)

        conn = None
        try:
            expire_before = time.time() - self.ttl
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            cur = conn.cursor()
            cur.execute("DELETE FROM ip_reputation_cache WHERE updated_at < ?", (expire_before,))
            deleted = cur.rowcount
            conn.commit()
            return deleted
        except Exception as e:
            logger.warning("清理过期缓存异常: %s", e)
            return 0
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


# 全局默认单例
_GLOBAL_CACHE: Optional[LocalReputationCache] = None


def get_default_cache() -> LocalReputationCache:
    """获取默认的全局信誉缓存实例。"""
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is None:
        _GLOBAL_CACHE = LocalReputationCache()
    return _GLOBAL_CACHE
