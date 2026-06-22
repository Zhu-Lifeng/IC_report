# 部署指南（VPS + GitHub Actions 自动部署）

架构：`推送 main` → GitHub Actions 通过 SSH 登录 VPS → 运行 `deploy/deploy.sh`
（git 拉取 → 装依赖 → 重启 systemd 服务）。应用由 gunicorn 跑，绑定 `0.0.0.0:8000`，
通过 `http://<VPS_IP>:8000` 访问。

---

## 一、先在本地把数据文件移出 git（只做一次，很重要）

`data/*.json` 是运行时数据，目前被 git 跟踪。若不移除，每次部署都会用仓库里的旧数据
覆盖线上真实数据。已加好 `.gitignore`，现在把它们从版本控制移除（保留本地文件）：

```bash
git rm --cached data/houseTypes.json data/properties.json data/reports.json
git add .gitignore .github deploy DEPLOY.md requirements.txt
git commit -m "部署: 移除数据文件跟踪, 新增 Actions 自动部署"
git push origin main
```

> 首次在 VPS 上运行时，应用会自动从 `seed.json` 重新生成 `data/*.json`。

---

## 二、VPS 一次性初始化（用有 sudo 权限的账号执行）

```bash
# 1) 安装依赖
sudo apt update
sudo apt install -y python3 python3-venv git

# 2) 创建专用运行账号（无登录 shell 也可，这里给 bash 方便调试）
sudo useradd -m -s /bin/bash icreport

# 3) 克隆代码到 /opt/ic_report
sudo mkdir -p /opt/ic_report
sudo chown icreport:icreport /opt/ic_report
sudo -u icreport git clone https://github.com/Zhu-Lifeng/IC_report.git /opt/ic_report

# 4) 建虚拟环境并装依赖
sudo -u icreport python3 -m venv /opt/ic_report/.venv
sudo -u icreport /opt/ic_report/.venv/bin/pip install --upgrade pip
sudo -u icreport /opt/ic_report/.venv/bin/pip install -r /opt/ic_report/requirements.txt

# 5) 安装 systemd 服务
sudo cp /opt/ic_report/deploy/ic_report.service /etc/systemd/system/ic_report.service
sudo systemctl daemon-reload
sudo systemctl enable --now ic_report
sudo systemctl status ic_report     # 应显示 active (running)

# 6) 放行端口 8000（若启用了 ufw）
sudo ufw allow 8000/tcp || true
```

此时浏览器访问 `http://<VPS_IP>:8000` 应能打开。

---

## 三、让部署脚本能免密重启服务

`deploy.sh` 里会执行 `sudo systemctl restart ic_report`。给 `icreport` 账号
只对这条命令开放免密 sudo：

```bash
echo 'icreport ALL=(ALL) NOPASSWD: /bin/systemctl restart ic_report' | \
  sudo tee /etc/sudoers.d/ic_report-deploy
sudo chmod 440 /etc/sudoers.d/ic_report-deploy
```

> 注：部分系统 systemctl 在 `/usr/bin/systemctl`。用 `which systemctl` 确认路径，
> 与上面 sudoers 里的路径保持一致。

---

## 四、为 GitHub Actions 配置 SSH 部署密钥

在 **VPS 上**为部署生成一对专用密钥（不要用你自己的私钥）：

```bash
sudo -u icreport ssh-keygen -t ed25519 -f /home/icreport/.ssh/deploy_key -N "" -C "github-actions"
# 把公钥加入授权列表，允许该密钥登录 icreport 账号
sudo -u icreport bash -c 'cat /home/icreport/.ssh/deploy_key.pub >> /home/icreport/.ssh/authorized_keys'
sudo -u icreport chmod 600 /home/icreport/.ssh/authorized_keys
# 打印私钥，复制全部内容（含 BEGIN/END 行）
sudo cat /home/icreport/.ssh/deploy_key
```

然后到 GitHub 仓库 **Settings → Secrets and variables → Actions → New repository secret**，
新建以下 4 个 secret：

| 名称          | 值                                              |
|---------------|-------------------------------------------------|
| `VPS_HOST`    | VPS 的公网 IP                                    |
| `VPS_USER`    | `icreport`                                       |
| `VPS_PORT`    | SSH 端口，通常 `22`                              |
| `VPS_SSH_KEY` | 上一步打印的**私钥全文**（`deploy_key` 的内容）   |

---

## 五、验证自动部署

1. 本地改点东西 → `git commit` → `git push origin main`
2. GitHub 仓库 **Actions** 标签页可看到 `Deploy to VPS` 工作流在跑
3. 成功后刷新 `http://<VPS_IP>:8000` 确认更新生效

也可在 Actions 页面点 `Run workflow` 手动触发（已开启 `workflow_dispatch`）。

---

## 常用排错命令（VPS 上）

```bash
sudo systemctl status ic_report          # 服务状态
sudo journalctl -u ic_report -n 50 --no-pager   # 看应用日志
sudo -u icreport bash /opt/ic_report/deploy/deploy.sh   # 手动跑一次部署
```

## 备份提醒
真实数据只存在于 VPS 的 `/opt/ic_report/data/` 和 `/opt/ic_report/uploads/`，
不在 git 里。请定期备份这两个目录（应用内也有「导出 JSON」功能，但不含图片文件）。
