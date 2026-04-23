# img2api

将上游 `/v1/responses` 图片生成能力封装为标准 OpenAI 兼容接口，支持多上游轮询、API Key 池化管理。

## 功能

- 多上游 `base_url + api_key` 轮询，自动故障转移
- 对外提供 `/v1/images/generations` 和 `/v1/chat/completions` 兼容接口
- Web 管理面板：上游管理、在线画图、历史图片浏览
- 生成图片自动落盘，通过 URL 直接访问，支持 TTL 自动过期清理
- auth-key 热重载，修改 config.json 后无需重启

## 支持模型

| 模型 | 尺寸 |
|---|---|
| `gpt-draw-1024x1024` | 方形 |
| `gpt-draw-1024x1536` | 竖版 |
| `gpt-draw-1536x1024` | 横版 |

## 快速开始

### 1. 部署

**Docker 部署（推荐）：**

```bash
git clone https://github.com/a-cold-bird/codex_img2api.git
cd codex_img2api
docker compose up --build -d
```

**本地运行：**

```bash
uv sync
uv run python main.py
```

> 本地运行如需 Web 面板，先构建前端：
> ```bash
> cd web && npm install && npm run build && cd ..
> cp -r web/out web_dist
> ```

默认端口 **9099**，访问 `http://your-server:9099`。

### 2. 首次使用

1. 浏览器打开 `http://your-server:9099`，用默认密钥 `img2api` 登录
2. 进入「上游管理」页面，点击「新增上游」
3. 每行一个上游，格式：`base_url api_key`，例如：
   ```
   http://1.2.3.4:8317 sk-xxx
   https://api.example.com sk-yyy
   ```
4. 添加完成后即可使用「画图」页面生成图片

### 3. 自定义配置（可选）

创建 `config.json` 覆盖默认配置：

```bash
cp config.example.json config.json
```

```json
{
  "auth-key": "your-auth-key",
  "public-base-url": "",
  "image-ttl-hours": 360,
  "request-timeout": 300
}
```

修改 `auth-key` 后无需重启，服务会自动加载最新值。

Docker 用户需取消 `docker-compose.yml` 中的挂载注释：

```yaml
volumes:
  - ./config.json:/app/config.json:ro
```

**配置说明：**

| 字段 | 必填 | 说明 |
|---|---|---|
| `auth-key` | 否 | 鉴权密钥，默认 `img2api` |
| `public-base-url` | 否 | 图片公开访问 URL 前缀，留空自动检测。反代场景需设为 `https://your-domain.com` |
| `image-ttl-hours` | 否 | 图片保留时长，默认 360 小时（15 天）|
| `request-timeout` | 否 | 上游请求超时秒数，默认 300 |

也可通过环境变量配置（优先级高于 config.json）：

| 环境变量 | 对应配置 |
|---|---|
| `AUTH_KEY` | `auth-key` |
| `PUBLIC_BASE_URL` | `public-base-url` |
| `REQUEST_TIMEOUT` | `request-timeout` |
| `IMAGE_TTL_HOURS` | `image-ttl-hours` |

## Web 管理面板

- **画图** — 输入提示词在线生成图片，支持选择模型和尺寸，多张并发生成
- **历史图片** — 浏览服务端已生成并落盘的图片，含过期时间
- **上游管理** — 查看、添加、删除上游 API，监控各上游成功/失败次数

## API 接口

所有接口需要请求头：

```
Authorization: Bearer <auth-key>
```

### 图片生成

```
POST /v1/images/generations
```

```json
{
  "prompt": "a cyberpunk cat walking in rainy Tokyo street",
  "model": "gpt-draw-1024x1536",
  "n": 1,
  "response_format": "b64_json"
}
```

响应中每张图片包含 `b64_json`、服务端托管的 `url`（有效期由 `image-ttl-hours` 控制）、`image_id`。

### Chat 兼容接口

```
POST /v1/chat/completions
```

```json
{
  "model": "gpt-draw-1024x1536",
  "messages": [{"role": "user", "content": "画一只猫"}]
}
```

### 模型列表

```
GET /v1/models
```

### 上游管理

```
GET    /api/accounts              # 获取上游列表
POST   /api/accounts              # 添加上游
DELETE /api/accounts              # 删除上游
```

### 图片历史与访问

```
GET /api/images/history            # 图片历史列表
GET /files/images/{image_id}       # 直接访问图片文件
```

## 项目结构

```
img2api/
├── main.py                  # 入口
├── config.json              # 配置文件（git ignored）
├── config.example.json      # 配置示例
├── services/
│   ├── api.py               # FastAPI 路由
│   ├── config.py            # 配置解析
│   ├── account_service.py   # 上游池管理
│   ├── backend_service.py   # 池化调用编排
│   ├── image_service.py     # 上游 /v1/responses 调用
│   ├── image_store.py       # 图片落盘与过期清理
│   └── version.py           # 版本号读取
├── web/                     # Next.js 前端源码
├── Dockerfile               # 多阶段构建（含前端）
└── docker-compose.yml
```

## 致谢

Web UI 参考了 [basketikun/chatgpt2api](https://github.com/basketikun/chatgpt2api)。

## License

MIT
