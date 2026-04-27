from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

class MongoStorage:
    def __init__(self):
        # 这里的 localhost:27017 对应你 Docker 运行命令中的 -p 27017:27017
        self.client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
        self.db = self.client["petnode_db"]
        self.collection = self.db["dog_health_data"]
        
        # 冒烟测试：尝试连接数据库
        try:
            self.client.admin.command('ping')
            print("✅ 数据库连接成功！Docker 里的 MongoDB 响应正常。")
        except ConnectionFailure:
            print("❌ 数据库连接失败，请检查 Docker 容器是否在运行。")

    def save_data(self, data_dict):
        result = self.collection.insert_one(data_dict)
        return result.inserted_id

if __name__ == "__main__":
    # 运行此文件进行测试
    storage = MongoStorage()
    test_id = storage.save_data({"test": "hello_mongo"})
    print(f"测试数据插入成功，ID: {test_id}")