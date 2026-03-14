# Bike FTMS Bridge 🚴

> 让你的动感单车连接更多骑行App！

这是一个小工具，可以把你的动感单车"变身"成标准蓝牙健身设备，从而支持更多骑行应用（如 Zwift、TrainerRoad、MyWhoosh 等）。

## 🎯 这个项目能做什么？

简单来说：
- 你的动感单车只能用官方App？❌
- 想用 Zwift、TrainerRoad、MyWhoosh 等第三方App？✅
- 这个项目就是"翻译器"，让单车和这些App能互相"听懂"

**实际效果：**
- 📱 打开 Zwift 等骑行App
- 📡 搜索蓝牙设备，找到 "Bike_FTMS"
- 🚴 开始骑行，数据实时同步！

---

## 🛒 你需要准备什么？

| 设备 | 说明 |
|------|------|
| K某牌动感单车 | 支持手机App蓝牙控制的智能动感单车 |
| Linux设备 | 树莓派、Linux电脑等（需要蓝牙功能） |
| 安卓手机 | 用于获取鉴权信息（一次性操作） |

**推荐配置：** 树莓派 Zero2W 或其他水果派开发板（自带蓝牙和WiFi）

---

## 📖 安装教程

### 第一步：下载项目

在树莓派上打开终端，输入：

```bash
git clone https://github.com/happyderekl/Bike-FTMS-Bridge.git
cd Bike-FTMS-Bridge
```

> 💡 **小白提示：** 如果没有 git，先运行 `sudo apt install git` 安装

---

### 第二步：获取鉴权文件（关键步骤！）

> ⚠️ **重要：** 这个步骤必须做，否则无法连接单车！

动感单车使用私有蓝牙协议，需要"钥匙"才能连接。我们需要从官方App的通信中提取这个"钥匙"。

#### 2.1 在安卓手机上开启蓝牙日志

1. 打开手机 **设置** → **关于手机**
2. 找到 **版本号**（或"软件版本号"）
3. **连续点击 7 次**，直到提示"已进入开发者模式"
4. 返回设置，找到 **开发者选项**（通常在"系统"里面）
5. 打开 **"启用蓝牙 HCI 监听日志"** 开关
6. **开始蓝牙日志监听**（不同品牌手机开始方式不同，需自行搜索）

#### 2.2 生成鉴权数据

1. **重启手机蓝牙**（关闭再打开）
2. **打开K某牌动感单车官方App**，连接你的单车
3. **骑行 1-2 分钟**（让App和单车充分通信）
4. **结束运动，关闭App**
5. **结束日志监听**

#### 2.3 导出日志文件

日志文件通常在以下位置（不同手机可能不同）：
- `/data/misc/bluetooth/logs/btsnoop_hci.log`
- 或通过 `adb bugreport` 导出

> 💡 **简单方法：** 大多数手机可以直接在文件管理器搜索 `btsnoop` 找到

把这个日志文件发送到树莓派上（可以用U盘、网络传输等方式）。

#### 2.4 生成鉴权配置

在树莓派上，进入项目目录，运行：

```bash
# 安装依赖
sudo apt install tshark -y
pip install pyshark

# 生成鉴权文件（把下面的日志文件名换成你的）
python identity_gen.py btsnoop_hci.log
```

成功后会生成 `identity.json` 文件，这就是你的"钥匙"！

---

### 第三步：安装运行

#### 方法一：一键安装（推荐）

```bash
chmod +x install.sh
sudo ./install.sh
```

安装完成后，服务会自动启动，开机也会自动运行。

#### 方法二：手动测试

如果只是想试试，不想安装服务：

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 运行程序
python ftms_server.py
```

---

### 第四步：连接使用

1. 程序运行后，会自动搜索并连接动感单车
2. 打开你的骑行App（如 Zwift）
3. 在蓝牙设备列表中找到 **"Bike_FTMS"**
4. 点击连接，开始骑行！

---

## 🔧 常用命令

| 命令 | 说明 |
|------|------|
| `sudo systemctl start bike-ftms` | 启动服务 |
| `sudo systemctl stop bike-ftms` | 停止服务 |
| `sudo systemctl status bike-ftms` | 查看状态 |
| `journalctl -u bike-ftms -f` | 查看实时日志 |

---

## ⚙️ 配置参数（可选）

编辑 `config.json` 可以调整以下参数：

| 参数 | 默认值 | 通俗说明 |
|------|--------|----------|
| max_resistance_level | 24 | 你的单车有几档阻力？ |
| base_resistance_level | 6.0 | 平路骑行时的基础档位 |
| log_level | INFO | 日志详细程度（DEBUG最详细） |
| bluetooth_device_name | Bike_FTMS | 蓝牙设备名称 |

> 💡 **大多数情况下，默认配置就够用了！**

---

## ❓ 常见问题

### Q: 找不到单车设备？
**A:** 
1. 确保单车已开机
2. 确保单车没有被手机App连接（先断开手机蓝牙）
3. 检查 `identity.json` 是否正确生成

### Q: 连接后没有数据？
**A:** 
1. 确保单车屏幕显示"已连接"
2. 按单车上的"开始"按钮，单车需要在运动状态下才会发送数据
3. 查看日志：`journalctl -u bike-ftms -f`

### Q: 支持 Windows/Mac 吗？
**A:** 目前只支持 Linux。推荐使用树莓派，便宜又省电。

### Q: 支持哪些骑行App？
**A:** 所有支持 FTMS 协议的 App 都可以，包括：
- Zwift
- GTBikeV
- MyWhoosh
- TrainerRoad
- Kinomap
- Rouvy
- GoldenCheetah
- 等等...

---

## 📁 项目文件说明

```
Bike-FTMS-Bridge/
├── ftms_server.py      # 主程序
├── bike_client.py      # 单车通信模块
├── identity_gen.py     # 鉴权生成工具
├── config.json         # 配置文件
├── identity.json       # 你的鉴权文件（需自行生成）
└── install.sh          # 安装脚本
```

---

## 🙏 致谢

本项目的鉴权提取方法和单车数据包解析参考了 [shinkisan/BikeCon](https://github.com/shinkisan/BikeCon/) 项目，感谢原作者的开源贡献！

---

## ⚠️ 免责声明

**本项目仅供学习和研究目的。**

1. 本项目与任何商业公司或品牌无关
2. 使用风险自负，作者不承担任何责任
3. 请遵守当地法律法规
4. 本项目采用 GNU GPL v3 许可证

使用本软件即表示您已阅读并同意以上条款。

---

## 📜 许可证

GNU General Public License v3.0 - 详见 [LICENSE](LICENSE) 文件
