# 教培教务平台 · 精简版

一个适合单校区、小规模使用的教务管理 Web 应用。使用 Python、Flask 和 SQLite，可独立运行，不依赖完整版服务。

**作者：[泪见雪.](http://154.36.185.225/)** · 微信：`NekoByte_Zzl` · QQ：`2578783496`

## 功能

| 模块 | 精简版能力 |
| --- | --- |
| 账号与人员 | 超管、校长、教师、学生四种角色；创建账户时填写姓名、年级、教师科目、手机号及归属；修改账号资料、密码；管理备注仅管理人员可见 |
| 排课 | 按具体日期创建排课；周课表；点击课程进入详情；科目与教师双向筛选；支持多人课程；检查教师、学生、教室时间冲突 |
| 手动考勤 | 管理员和任课教师登记到课情况及实际授课分钟数；半小时向上折算；重复保存更新原记录 |
| 教室状态 | 自定义教室；空闲、占用、维修中；管理人员维护详细备注；师生查看状态 |
| 试听 CRM | 年级、多节试听的科目、教师和时间；跟进备注；标记流失、恢复跟进、删除误录记录；转为正式学生并保留线索历史 |
| 公告 | 管理人员发布，全体登录人员查看 |
| 技术支持 | 作者署名、可点击博客链接、微信 / QQ 和微信二维码 |

此版本**不包含**财务算薪、预存月结、智能排课、OCR、小程序、动态扫码和私信。教室状态由管理人员手动维护，不自动随课程变更。年级手动维护，不包含年度自动升级。采用单校区结构，未提供多校区隔离、手机号别名、多次循环排课或校外占用管理。手动考勤记录时长，不执行消课扣费。

## 参考截图

以下是精简版的实际界面截图，所有人员、号码、课表和备注均为虚构演示数据。

### 工作台

![工作台](docs/screenshots/dashboard.jpg)

### 周课表

![周课表](docs/screenshots/schedule.jpg)

### 试听 / 意向学员 CRM

![试听 CRM](docs/screenshots/crm.jpg)

### 多节试听录入

![多节试听录入](docs/screenshots/crm-form.jpg)

### 技术支持与作者署名

![技术支持](docs/screenshots/support.jpg)

### 登录页

![登录页](docs/screenshots/login.jpg)

## 本地运行

需要 Python **3.11 或更新版本**。建议先使用空数据库本地试运行。仓库不提供生产数据、服务器配置或默认账号密码。

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux / macOS：

```bash
source .venv/bin/activate
```

安装依赖，并复制配置模板：

```bash
pip install -r requirements.txt
python -c "from pathlib import Path; import secrets; p=Path('.env'); p.exists() and exit('.env already exists; edit it manually.'); p.write_text('SECRET_KEY=' + secrets.token_hex(32) + '\nCOOKIE_SECURE=0\n', encoding='utf-8')"
```

上述命令适用于首次创建 `.env`，已有文件会拒绝覆盖。也可复制 `.env.example`，手动填写随机 `SECRET_KEY`。

初始化管理员（交互输入用户名和密码，密码至少 12 位）：

```bash
flask --app run:app init-db
python run.py
```

浏览器打开 **http://127.0.0.1:5003**。初始化命令不删除旧表、不覆盖已有管理员。依次创建教师、学生和教室，即可排课。本人未首次登录不影响管理人员排课。

## 部署说明

- 使用独立目录、独立密钥、独立数据库；不要连接完整版的数据库。两版数据库结构不兼容。
- `python run.py` 是本地开发入口。正式部署使用 WSGI 服务并配置 HTTPS 反向代理。
- Linux 示例：`pip install gunicorn`，然后 `gunicorn --workers 1 --threads 1 --bind 127.0.0.1:5003 run:app`。SQLite 精简版推荐单进程、单请求线程，小规模使用。
- HTTPS 下设置 `.env` 中的 `COOKIE_SECURE=1`。不要将开发端口直接暴露到公网。
- 上线前通过反向代理配置登录请求限流。应用自身也按直接连接 IP 限流，反向代理部署时该 IP 可能是代理地址，应在代理端补充按客户端 IP 限流。
- 数据保存在 `instance/lite.db`。定期备份，并保护备份权限。数据库、日志、`.env` 和上传目录均被 `.gitignore` 排除。
- 授课时间按中国标准时间显示。Windows 时区数据依赖 `tzdata`，已列入安装依赖。
- 当前没有数据迁移框架、大规模部署或高可用支持；升级数据库结构前需备份并自行规划迁移。

## 测试

```bash
python -m unittest discover -s tests -v
```

20 项测试覆盖权限边界、备注隐私、科目匹配、时间冲突、手动考勤折算、重复号码提示、试听流失 / 恢复 / 删除 / 转化、表单 CSRF、HTML 转义、密码修改后的会话失效和数据库初始化保护。GitHub Actions 配置了 Python 3.11 / 3.12 / 3.13 测试矩阵。

## 技术支持与署名

作者 **[泪见雪.](http://154.36.185.225/)**。页面侧栏、全局页脚和技术支持页均包含署名，点击姓名可跳转个人博客。

- 微信：`NekoByte_Zzl`
- QQ：`2578783496`
- 博客：[http://154.36.185.225/](http://154.36.185.225/)
- 联系时请注明「教务平台技术支持」。

<img src="lite/static/support-wechat.jpg" width="280" alt="泪见雪. 微信技术支持二维码">

Copyright © 2026 泪见雪. 本仓库公开展示精简版源码；未指定开源许可证，其他使用授权请联系作者。
