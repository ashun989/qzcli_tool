"""任务存储模块 - JSON 文件存储。"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Iterable
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta

from .config import JOBS_FILE, JOBS_ARCHIVE_FILE, ensure_config_dir


PRUNABLE_STATUSES = frozenset({"job_succeeded", "job_failed", "job_stopped"})


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    """解析 ISO 时间字符串。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@dataclass
class JobRecord:
    """任务记录"""
    job_id: str
    name: str = ""
    status: str = "unknown"
    workspace_id: str = ""
    project_id: str = ""
    created_at: str = ""  # ISO 格式时间
    updated_at: str = ""  # 最后更新时间
    finished_at: str = ""
    source: str = ""  # 提交来源脚本
    command: str = ""
    url: str = ""  # 任务链接
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # API 返回的额外信息
    running_time_ms: str = ""
    priority_level: str = ""
    gpu_count: int = 0
    instance_count: int = 0
    
    # 新增：计算组和 GPU 信息
    compute_group_name: str = ""  # 如 "H200-3号机房-2"
    gpu_type: str = ""  # 如 "H200"
    project_name: str = ""  # 如 "CI-扩散音视频生成"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobRecord":
        # 只取已知字段
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any], source: str = "") -> "JobRecord":
        """从 API 响应创建记录"""
        # 解析时间戳（毫秒）
        def parse_timestamp(ts: str) -> str:
            if not ts:
                return ""
            try:
                return datetime.fromtimestamp(int(ts) / 1000).isoformat()
            except (ValueError, TypeError):
                return ""
        
        # 提取 framework_config 中的信息
        framework_config = data.get("framework_config", [{}])
        gpu_count = 0
        instance_count = 0
        gpu_type = ""
        
        if framework_config:
            fc = framework_config[0]
            gpu_count = fc.get("gpu_count", 0)
            instance_count = fc.get("instance_count", 0)
            # 从 instance_spec_price_info.gpu_info 中提取 GPU 类型
            spec_info = fc.get("instance_spec_price_info", {})
            gpu_info = spec_info.get("gpu_info", {})
            gpu_type = gpu_info.get("gpu_product_simple", "")  # 如 "H200"
        
        # 提取计算组名称和项目名称
        compute_group_name = data.get("logic_compute_group_name", "")
        project_name = data.get("project_name", "")
        
        # 构建任务 URL
        job_id = data.get("job_id", "")
        workspace_id = data.get("workspace_id", "")
        url = ""
        if job_id and workspace_id:
            url = f"https://qz.sii.edu.cn/jobs/distributedTrainingDetail/{job_id}?spaceId={workspace_id}"
        
        return cls(
            job_id=job_id,
            name=data.get("name", ""),
            status=data.get("status", "unknown"),
            workspace_id=workspace_id,
            project_id=data.get("project_id", ""),
            created_at=parse_timestamp(data.get("created_at", "")),
            updated_at=datetime.now().isoformat(),
            finished_at=parse_timestamp(data.get("finished_at", "")),
            source=source,
            command=data.get("command", ""),
            url=url,
            running_time_ms=data.get("running_time_ms", ""),
            priority_level=data.get("priority_level", ""),
            gpu_count=gpu_count,
            instance_count=instance_count,
            compute_group_name=compute_group_name,
            gpu_type=gpu_type,
            project_name=project_name,
        )


class JobStore:
    """任务存储"""
    
    def __init__(self, store_file: Optional[Path] = None, archive_file: Optional[Path] = None):
        self.store_file = store_file or JOBS_FILE
        self.archive_file = archive_file or JOBS_ARCHIVE_FILE
        self._jobs: Dict[str, JobRecord] = {}
        self._loaded = False
    
    def _ensure_loaded(self) -> None:
        """确保数据已加载"""
        if self._loaded:
            return
        
        ensure_config_dir()
        
        if self.store_file.exists():
            try:
                with open(self.store_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    jobs_data = data.get("jobs", {})
                    self._jobs = {
                        k: JobRecord.from_dict(v)
                        for k, v in jobs_data.items()
                    }
            except (json.JSONDecodeError, IOError):
                self._jobs = {}
        
        self._loaded = True
    
    def _save(self) -> None:
        """保存数据"""
        ensure_config_dir()
        
        data = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "jobs": {k: v.to_dict() for k, v in self._jobs.items()}
        }
        
        with open(self.store_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def add(self, job: JobRecord) -> None:
        """添加任务"""
        self._ensure_loaded()
        self._jobs[job.job_id] = job
        self._save()
    
    def update(self, job_id: str, **kwargs) -> Optional[JobRecord]:
        """更新任务"""
        self._ensure_loaded()
        
        if job_id not in self._jobs:
            return None
        
        job = self._jobs[job_id]
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        
        job.updated_at = datetime.now().isoformat()
        self._save()
        return job
    
    def update_from_api(self, job_id: str, api_data: Dict[str, Any]) -> Optional[JobRecord]:
        """从 API 响应更新任务"""
        self._ensure_loaded()
        
        if job_id not in self._jobs:
            # 如果不存在则创建
            job = JobRecord.from_api_response(api_data)
            self._jobs[job_id] = job
        else:
            # 更新现有记录
            job = self._jobs[job_id]
            new_job = JobRecord.from_api_response(api_data, source=job.source)
            # 保留原有的 source 和 metadata
            new_job.source = job.source
            new_job.metadata = job.metadata
            self._jobs[job_id] = new_job
        
        self._save()
        return self._jobs[job_id]
    
    def get(self, job_id: str) -> Optional[JobRecord]:
        """获取任务"""
        self._ensure_loaded()
        return self._jobs.get(job_id)
    
    def list(
        self,
        limit: Optional[int] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[JobRecord]:
        """列出任务"""
        self._ensure_loaded()
        
        jobs = list(self._jobs.values())
        
        # 过滤
        if status:
            jobs = [j for j in jobs if j.status == status]
        if source:
            jobs = [j for j in jobs if source in j.source]
        
        # 按创建时间倒序
        jobs.sort(key=lambda x: x.created_at or "", reverse=True)
        
        # 限制数量
        if limit:
            jobs = jobs[:limit]
        
        return jobs
    
    def list_job_ids(self) -> List[str]:
        """列出所有任务 ID"""
        self._ensure_loaded()
        return list(self._jobs.keys())
    
    def remove(self, job_id: str) -> bool:
        """删除任务记录"""
        self._ensure_loaded()
        
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save()
            return True
        return False
    
    def clear(self) -> None:
        """清空所有任务"""
        self._jobs = {}
        self._loaded = True
        self._save()
    
    def count(self) -> int:
        """任务总数"""
        self._ensure_loaded()
        return len(self._jobs)

    @staticmethod
    def _is_prunable_status(status: str, statuses: Optional[Iterable[str]] = None) -> bool:
        """判断状态是否允许按 TTL 清理。"""
        allowed = set(statuses) if statuses else set(PRUNABLE_STATUSES)
        return status in PRUNABLE_STATUSES and status in allowed

    @staticmethod
    def _last_activity_at(job: JobRecord) -> Optional[datetime]:
        """返回任务的最后活跃时间。"""
        for candidate in (job.finished_at, job.updated_at, job.created_at):
            parsed = _parse_iso_datetime(candidate)
            if parsed is not None:
                return parsed
        return None

    def find_prunable_jobs(
        self,
        ttl_days: int,
        statuses: Optional[Iterable[str]] = None,
        now: Optional[datetime] = None,
    ) -> List[JobRecord]:
        """找出超过 TTL 的可清理任务。"""
        self._ensure_loaded()

        current_time = now or datetime.now()
        cutoff = current_time - timedelta(days=ttl_days)
        jobs_to_prune: List[JobRecord] = []

        for job in self._jobs.values():
            if not self._is_prunable_status(job.status, statuses):
                continue

            last_activity = self._last_activity_at(job)
            if last_activity is None:
                continue

            if last_activity <= cutoff:
                jobs_to_prune.append(job)

        jobs_to_prune.sort(
            key=lambda job: self._last_activity_at(job) or datetime.min,
            reverse=True,
        )
        return jobs_to_prune

    def archive_jobs(
        self,
        jobs: List[JobRecord],
        *,
        ttl_days: int,
        reason: str = "ttl_expired",
        cleaned_at: Optional[datetime] = None,
        archive_file: Optional[Path] = None,
    ) -> Path:
        """把被清理任务追加写入归档文件。"""
        archive_path = archive_file or self.archive_file
        ensure_config_dir()

        timestamp = (cleaned_at or datetime.now()).isoformat()
        with open(archive_path, "a", encoding="utf-8") as f:
            for job in jobs:
                payload = {
                    "cleaned_at": timestamp,
                    "reason": reason,
                    "ttl_days": ttl_days,
                    "job": job.to_dict(),
                }
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        return archive_path

    def prune(
        self,
        ttl_days: int,
        *,
        statuses: Optional[Iterable[str]] = None,
        dry_run: bool = False,
        now: Optional[datetime] = None,
        archive_file: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """按 TTL 清理完成态任务。"""
        if ttl_days < 0:
            raise ValueError("ttl_days 必须大于等于 0")

        self._ensure_loaded()

        jobs_to_prune = self.find_prunable_jobs(ttl_days, statuses=statuses, now=now)
        archive_path = archive_file or self.archive_file
        result = {
            "scanned": len(self._jobs),
            "eligible": len(jobs_to_prune),
            "pruned": 0,
            "archive_file": archive_path,
            "jobs": jobs_to_prune,
        }

        if dry_run or not jobs_to_prune:
            return result

        current_time = now or datetime.now()
        self.archive_jobs(
            jobs_to_prune,
            ttl_days=ttl_days,
            cleaned_at=current_time,
            archive_file=archive_path,
        )

        for job in jobs_to_prune:
            self._jobs.pop(job.job_id, None)

        self._save()
        result["pruned"] = len(jobs_to_prune)
        return result
    
    def import_from_file(self, filepath: Path, source: str = "") -> int:
        """从文件导入任务 ID"""
        self._ensure_loaded()
        
        count = 0
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                # 支持多种格式
                # 1. 纯 job_id
                # 2. name\tstep\tjob_id (eval 格式)
                parts = line.split("\t")
                if len(parts) >= 3:
                    job_id = parts[-1]
                    name = parts[0]
                else:
                    job_id = parts[0]
                    name = ""
                
                if job_id.startswith("job-") and job_id not in self._jobs:
                    job = JobRecord(
                        job_id=job_id,
                        name=name,
                        source=source or filepath.name,
                        updated_at=datetime.now().isoformat(),
                    )
                    self._jobs[job_id] = job
                    count += 1
        
        if count > 0:
            self._save()
        
        return count


# 全局存储实例
_store_instance: Optional[JobStore] = None


def get_store() -> JobStore:
    """获取全局存储实例"""
    global _store_instance
    if _store_instance is None:
        _store_instance = JobStore()
    return _store_instance
