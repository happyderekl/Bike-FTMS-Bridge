# Bike FTMS Bridge

一个将动感单车数据转换为标准FTMS（Fitness Machine Service）协议的桥接工具，让动感单车能够与FTMS应用配合使用。

## 功能特性

- ✅ 将动感单车的私有蓝牙协议转换为标准FTMS协议
- ✅ 实时数据传输：速度、踏频、功率、阻力、距离、卡路里等
- ✅ 支持FTMS应用的模拟参数控制（坡度、风速、路面阻力）
- ✅ 自动重连机制
- ✅ 数据记录到CSV文件
- ✅ Systemd服务支持（Linux）
- ✅ 可配置参数，适配不同型号单车

## 硬件要求

- 支持私有蓝牙协议的动感单车
- 支持蓝牙4.0+的Linux设备（推荐树莓派）

## 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/happyderekl/Bike-FTMS-Bridge.git
cd Bike-FTMS-Bridge
```

### 2. 获取鉴权配置

由于动感单车使用私有蓝牙协议，需要从手机蓝牙日志中提取鉴权信息：

1. 在安卓手机上启用蓝牙HCI日志
2. 使用动感单车App连接单车
3. 提取HCI日志文件（通常为`btsnoop_hci.log`格式）
4. 使用提供的工具生成鉴权配置（来源：`https://github.com/shinkisan/BikeCon/`）

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 生成鉴权配置
python identity_gen.py btsnoop_hci.log
```

这将生成`identity.json`文件。

### 3. 配置参数（可选）

编辑`config.json`文件，根据需要调整参数：

```json
{
    "csv_enabled": false,
    "max_resistance_level": 24,
    "base_resistance_level": 6.0,
    "grade_effect_uphill": 1.5,
    "grade_effect_downhill": 1.0,
    "wind_effect": 0.05,
    "crr_effect": 500,
    ...
}
```

### 4. 运行安装脚本

```bash
chmod +x install.sh
./install.sh
```

安装脚本会自动：
- 检测 `identity.json` 是否存在
- 创建虚拟环境
- 安装依赖
- 配置蓝牙权限
- 生成 `bike-ftms.service` 文件

### 5. 启用服务

```bash
sudo cp bike-ftms.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bike-ftms.service
sudo systemctl start bike-ftms.service
```

### 6. 查看状态

```bash
# 查看服务状态
sudo systemctl status bike-ftms.service

# 查看日志
journalctl -u bike-ftms.service -f
```

## 快速测试（不安装服务）

如果只想快速测试，不需要安装为系统服务：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python identity_gen.py btsnoop_hci.log
python ftms_server.py
```

## 使用方法

1. 启动FTMS服务器
2. 打开FTMS应用
3. 在蓝牙设备列表中找到"Bike_FTMS"并连接
4. 开始骑行！

## 配置说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| csv_enabled | false | 是否启用CSV数据记录 |
| max_resistance_level | 24 | 动感单车最大阻力档位 |
| base_resistance_level | 6.0 | 基础平路阻力档位 |
| grade_effect_uphill | 1.5 | 上坡坡度影响系数（每1%坡度增加的档位数） |
| grade_effect_downhill | 1.0 | 下坡坡度影响系数（每1%坡度减少的档位数） |
| wind_effect | 0.05 | 风速影响系数（每1m/s逆风增加的档位数） |
| crr_effect | 500 | 路面阻力影响系数 |
| resistance_throttle_interval | 5.0 | 阻力调节节流间隔（秒） |
| ftms_update_interval | 1.0 | FTMS数据广播间隔（秒） |
| reconnect_interval | 15 | 蓝牙重连间隔（秒） |
| heartbeat_interval | 1.0 | 心跳包发送间隔（秒） |
| log_level | INFO | 日志级别：DEBUG, INFO, WARNING, ERROR |
| bluetooth_device_name | Bike_FTMS | FTMS服务蓝牙设备名称 |
| csv_dir | data | CSV文件存储目录 |
| identity_file | identity.json | 身份验证配置文件路径 |

## 项目结构

```
.
├── ftms_server.py          # FTMS服务器主程序
├── bike_client.py          # 动感单车蓝牙客户端
├── identity_gen.py         # 鉴权配置生成工具
├── config.json             # 配置文件
├── requirements.txt        # Python依赖
├── install.sh              # 安装脚本
├── bike-ftms.service       # Systemd服务配置（自动生成）
├── data/                   # 骑行数据存储目录
└── identity.json           # 鉴权配置（需自行生成）
```

## 技术说明

- 使用`bleak`库与动感单车通信
- 使用`bless`库实现FTMS GATT服务器
- 支持阻力自动调节，根据坡度、风速等参数计算
- 可配置节流机制防止阻力频繁变化

## 免责声明

**DISCLAIMER / 免责声明**

本项目仅供学习和研究目的，旨在探索蓝牙低功耗（BLE）协议和FTMS标准。

1. **本项目与任何商业公司或品牌无关。** 本项目不隶属于、不受认可于、也不与任何健身设备制造商、软件供应商或相关公司有关联。

2. **使用风险自负。** 本软件按"原样"提供，不附带任何明示或暗示的保证。使用本软件所造成的任何直接或间接损失，包括但不限于设备损坏、数据丢失、人身伤害等，开发者不承担任何责任。

3. **遵守当地法律。** 用户有责任确保其使用本软件的行为符合所在地区的法律法规。在某些司法管辖区，逆向工程可能受到限制或禁止。

4. **尊重知识产权。** 本项目不包含任何受版权保护的专有协议文档或密钥。用户需自行获取必要的鉴权信息，并确保其获取方式合法。

5. **非商业用途。** 本项目采用GNU GPL v3许可证，禁止将本软件用于商业目的，除非完全遵守GPL v3的条款。

6. **设备兼容性。** 本软件可能不适用于所有设备型号。使用前请确认您的设备兼容性。

使用本软件即表示您已阅读、理解并同意以上条款。如果您不同意这些条款，请勿使用本软件。

---

**DISCLAIMER (English)**

This project is for educational and research purposes only, aimed at exploring Bluetooth Low Energy (BLE) protocols and FTMS standards.

1. This project is not affiliated with, endorsed by, or connected to any commercial company or brand.
2. Use at your own risk. This software is provided "as is" without any warranties.
3. Users are responsible for ensuring compliance with local laws and regulations.
4. This project does not contain any copyrighted proprietary protocol documents or keys.
5. This project is licensed under GNU GPL v3. Commercial use is prohibited unless fully complying with GPL v3 terms.
6. This software may not be compatible with all device models.

By using this software, you acknowledge that you have read, understood, and agree to these terms.

## 许可证

GNU General Public License v3.0 - 详见 [LICENSE](LICENSE) 文件
