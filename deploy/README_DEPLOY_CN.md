# PetNode 部署说明（中文）

## 固定部署信息
- 服务器 IP：`8.156.95.140`
- 域名：`pppetnode.com`

## 1) Docker Compose 启动（在 `C_end_Simulator` 下）
```bash
cd /path/to/PetNode/C_end_Simulator
docker compose up -d
```

## 2) Nginx 反向代理配置
仓库内配置文件：
- `/path/to/PetNode/deploy/nginx/pppetnode.com.conf`

部署到服务器时，建议放置到：
- `/etc/nginx/conf.d/pppetnode.com.conf`

校验并重载 Nginx：
```bash
nginx -t && systemctl reload nginx
```

## 3) 微信小程序 API 基地址
小程序 `wechat/WeChat_miniprogram/utils/api.js` 的 `BASE_URL` 应为：
- `https://pppetnode.com/api/v1`

## 4) 必须替换的敏感配置项
请在 `C_end_Simulator/docker-compose.yml` 中替换以下占位值：
- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`
- `JWT_SECRET`
- `API_KEY`
- `HMAC_KEY`
- `MYSQL_ROOT_PASSWORD`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DEFAULT_PASSWORD_HASH`

说明：
- `API_KEY` 与 `HMAC_KEY` 在 `flask-server`、`mq-worker`、`engine` 三处必须保持一致。
- `MYSQL_DEFAULT_PASSWORD_HASH` 需填写你希望设置的默认密码对应的 SHA-256 十六进制哈希值。

## 5) 基础连通性验证
```bash
curl https://pppetnode.com/api/health
```
说明：健康检查接口是 `/api/health`（非 `/api/v1/health`）。  
如返回健康状态（HTTP 200）即说明 Nginx -> Flask 转发链路可用。
