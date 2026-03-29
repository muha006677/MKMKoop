# MKMKoop

MKMKoop 是一个真正可运行的任务管理网站，包含：
- 用户注册 / 登录
- 创建任务
- 任务内容管理
- 按日期和截止时间管理
- 倒计时显示
- 进度百分比更新
- 首页显示未完成任务
- 历史记录
- 白天 / 黑夜双主题
- 健康检查接口 `/healthz`

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate   # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

打开浏览器访问：

```text
http://127.0.0.1:5000
```

## 生产部署

### Render / Railway / 云服务器
启动命令：

```bash
gunicorn app:app
```

### Docker

```bash
docker build -t mkmkoop .
docker run -p 5000:5000 -e SECRET_KEY=your-secret mkmkoop
```

## 重要说明

这个项目已经是“真正能运行的网站代码”，不是纯前端演示页。

但“24 小时在线”这件事，必须把它部署到服务器或托管平台上。代码我已经做好，部署后就能长期在线运作。

## 建议下一步

1. 部署到 Render / Railway / VPS
2. 把 SQLite 换成 PostgreSQL
3. 增加密码找回
4. 增加提醒通知（邮件 / Telegram）
5. 增加任务编辑功能
