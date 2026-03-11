# engine/exporters 包 —— 数据输出层（策略模式）
# BaseExporter 定义了统一的导出接口（export / flush / close）；
# FileExporter 是当前阶段使用的实现，将 record 以 JSONL 格式追加写入本地文件；
# http_exporter 是未来阶段的占位，用于将数据上报至远程服务器 API。

from .base_exporter import BaseExporter
from .file_exporter import FileExporter

__all__ = ["BaseExporter", "FileExporter"]
