"""
HttpExporter —— 🔮 未来阶段占位：发送给远程服务器 API

本文件当前为空壳，留作未来阶段实现。

预期功能：
  - 继承 BaseExporter，实现 export() / flush() / close()
  - 通过 HTTP POST 请求将 SmartCollar 生成的模拟数据上报给 S端（远程服务器）
  - 目标接口示例: POST /api/data  (上报一条或一批记录)
  - 支持断网时将数据缓存到 output_data/offline_cache/ 目录
  - 网络恢复后自动补发缓存数据

与 FileExporter 的关系：
  - FileExporter 是"本地写文件"策略（当前阶段正在使用）
  - HttpExporter 是"远程发 HTTP"策略（未来替换 / 并行使用）
  - 两者都继承自 BaseExporter，调度器 (main.py) 通过统一接口调用，
    无需关心底层是写文件还是发 HTTP（策略模式）

使用方式（未来实现后）::

    exporter = HttpExporter(api_url="https://server.example.com/api/data")
    exporter.export(record)   # POST 一条记录到远程服务器
    exporter.flush()          # 确保所有缓冲数据已发送
    exporter.close()          # 关闭连接
"""
