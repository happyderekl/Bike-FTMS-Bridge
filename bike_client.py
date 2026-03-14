import sys
import logging
import os

REQUIRED_PACKAGES = ["bleak"]

def check_dependencies():
    """
    检查必要的依赖包
    """
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        logging.error("缺少以下依赖:")
        for pkg in missing:
            logging.error(f"    - {pkg}")
        logging.error(f"请运行以下命令安装: pip install {' '.join(missing)}")
        sys.exit(1)

check_dependencies()

import asyncio
import struct
import csv
import json
from datetime import datetime
from bleak import BleakClient, BleakScanner

def load_config():
    """
    加载配置文件
    """
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    default_config = {
        "log_level": "INFO",
        "csv_enabled": False,
        "csv_dir": "data",
        "reconnect_interval": 15,
        "heartbeat_interval": 1.0,
        "identity_file": "identity.json"
    }
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            for key in default_config:
                if key not in config:
                    config[key] = default_config[key]
            return config
    except FileNotFoundError:
        logging.warning("未找到 config.json，使用默认配置")
        return default_config
    except json.JSONDecodeError as e:
        logging.error(f"config.json 格式错误: {e}")
        return default_config

CONFIG = load_config()

logging.basicConfig(level=getattr(logging, CONFIG["log_level"].upper(), logging.INFO))
logger = logging.getLogger("Bike")

BIKE_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"

_identity_file = CONFIG["identity_file"]
if not os.path.isabs(_identity_file):
    _identity_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), _identity_file)

try:
    with open(_identity_file, "r", encoding="utf-8") as f:
        _identity = json.load(f)
    if "handshake_packets" not in _identity:
        raise KeyError("缺少 handshake_packets 字段")
    BIKE_INIT_CMDS = [bytes.fromhex(pkt) for pkt in _identity["handshake_packets"]]
except FileNotFoundError:
    logger.error("未找到 identity.json 文件,请使用 identity_gen.py 生成鉴权配置")
    sys.exit(1)
except KeyError as e:
    logger.error(f"identity.json 格式错误: {e}")
    sys.exit(1)
except Exception as e:
    logger.error(f"读取 identity.json 失败: {e}")
    sys.exit(1)

class BikeClient:
    def __init__(self):
        """
        初始化动感单车客户端
        """
        self.client = None
        self.seq = 0x04
        self.app_cnt = 0x1104
        self.resistance_cnt = 0x06
        self.csv_dir = CONFIG["csv_dir"]
        self.csv_enabled = CONFIG["csv_enabled"]
        self.last_valid_data = {
            "duration": 0, "distance": 0, "power": 0, "cadence": 0,
            "resistance": 1, "calories": 0.0, "status": 2, "speed": 0.0
        }
        self.prev_dist = None
        self.prev_dur = None
        self.current_csv_date = None
        self.csv_file = None
        self.csv_writer = None
        self.print_enabled = True
        self.prev_status = 2
        self.csv_error_shown = False
        self.waiting_for_input = False
        self.csv_count = 0

    def _get_csv_writer(self):
        """
        获取 CSV 写入器（按天分割文件）
        :return: CSV 写入器，如果文件被占用则返回 None
        """
        if not self.csv_enabled:
            return None
            
        today = datetime.now().strftime("%Y-%m-%d")
        if self.current_csv_date != today:
            if self.csv_file:
                self.csv_file.close()
            
            if not os.path.exists(self.csv_dir):
                os.makedirs(self.csv_dir)
            
            filename = os.path.join(self.csv_dir, f"ride_{today}.csv")
            file_exists = os.path.exists(filename)
            
            try:
                self.csv_file = open(filename, "a", newline="", encoding="utf-8")
                self.csv_writer = csv.writer(self.csv_file)
                
                if not file_exists:
                    self.csv_writer.writerow([
                        "Time", "Status", "Duration(s)", "Distance(m)", "Speed(km/h)",
                        "Power(W)", "Cadence(rpm)", "Resistance", "Calories(kcal)", "HEX"
                    ])
                
                self.current_csv_date = today
                self.csv_error_shown = False
                
            except PermissionError:
                if not self.csv_error_shown:
                    logger.error(f"CSV 文件被占用，无法写入: {filename}")
                    logger.error("请关闭 Excel 或其他程序后重启")
                    self.csv_error_shown = True
                self.csv_enabled = False
                return None
        
        return self.csv_writer

    def _crc16(self, data: bytearray) -> int:
        """
        计算 CRC16 校验和
        :param data: 要计算的数据
        :return: CRC16 校验值
        """
        crc = 0x0000
        for b in data:
            crc ^= (b << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return crc

    def _build_packet(self, payload: bytes) -> bytes:
        """
        构建蓝牙数据包
        :param payload: 数据包内容
        :return: 完整的数据包
        """
        header = bytearray([0xA5, 0xA5, 0xA0, self.seq])
        header += struct.pack("<H", len(payload))
        packet = header + payload
        packet += struct.pack("<H", self._crc16(packet))
        self.seq = (self.seq + 1) & 0xFF
        return bytes(packet)

    async def _smart_write(self, data: bytes):
        """
        智能写入数据（处理 MTU 限制）
        :param data: 要写入的数据
        """
        try:
            await self.client.write_gatt_char(BIKE_CHAR_UUID, data, response=True)
        except:
            mtu = 20
            for i in range(0, len(data), mtu):
                await self.client.write_gatt_char(BIKE_CHAR_UUID, data[i:i+mtu], response=False)
                await asyncio.sleep(0.01)

    async def set_resistance(self, level: int, max_level: int = 24):
        """
        设置阻力等级
        :param level: 阻力等级 (1-max_level)
        :param max_level: 最大阻力等级
        """
        if level < 1 or level > max_level:
            logger.warning(f"阻力范围 1-{max_level}")
            return False

        payload = (
            bytes.fromhex("3216ef235503")
            + bytes([0xb0, self.resistance_cnt % 256, (self.resistance_cnt + 9) % 256])
            + bytes.fromhex("04000002b53130362f36ff08")
            + bytes([level])
        )

        packet = self._build_packet(payload)
        
        await self._smart_write(packet)
        
        self.resistance_cnt = (self.resistance_cnt + 1) & 0xFF
        return True

    async def stop_bike(self):
        """
        停止单车运动
        """
        payload = (
            bytes.fromhex("3216ef235503")
            + bytes([0xb0, self.resistance_cnt % 256, (self.resistance_cnt + 9) % 256])
            + bytes.fromhex("04000002b53130362f34ff0801")
        )

        packet = self._build_packet(payload)
        
        logger.debug(f"发送停止: {packet.hex()}")
        
        await self._smart_write(packet)
        
        self.resistance_cnt = (self.resistance_cnt + 1) & 0xFF
        logger.info("已发送停止指令")
        return True

    async def start_bike(self):
        """
        开始单车运动
        """
        payload = (
            bytes.fromhex("3216ef235503")
            + bytes([0xb0, self.resistance_cnt % 256, (self.resistance_cnt + 9) % 256])
            + bytes.fromhex("04000002b53130362f34ff0803")
        )

        packet = self._build_packet(payload)
        
        logger.debug(f"发送开始: {packet.hex()}")
        
        await self._smart_write(packet)
        
        self.resistance_cnt = (self.resistance_cnt + 1) & 0xFF
        logger.info("已发送开始指令")
        return True

    def get_current_data(self):
        """
        供外部调用的方法，获取当前单车数据
        """
        return self.last_valid_data

    async def run_client(self):
        """
        供外部调用的非阻塞启动函数（带自动重连机制）
        """
        while True:
            try:
                logger.info("正在扫描动感单车...")
                device = await BleakScanner.find_device_by_filter(lambda d, ad: d.name and d.name.startswith("Keep"))
                if not device:
                    logger.warning(f"未找到动感单车设备，{CONFIG['reconnect_interval']}秒后重试...")
                    await asyncio.sleep(CONFIG["reconnect_interval"])
                    continue

                async with BleakClient(device) as client:
                    self.client = client
                    logger.info(f"已连接，等待鉴权: {device.address}")
                    
                    await client.start_notify(BIKE_CHAR_UUID, self.notification_handler)
                    
                    logger.info("握手鉴权中...")
                    for cmd in BIKE_INIT_CMDS:
                        await self._smart_write(cmd)
                        await asyncio.sleep(0.3)

                    logger.info("握手完成，请查看单车屏幕是否显示已连接")
                    
                    while True:
                        hb_payload = bytes.fromhex("3216ef23550193") + struct.pack("<H", self.app_cnt) + bytes.fromhex("04000001b53130362f37")
                        await self._smart_write(self._build_packet(hb_payload))
                        self.app_cnt = (self.app_cnt + 1) & 0xFFFF
                        await asyncio.sleep(CONFIG["heartbeat_interval"])
                        
            except Exception as e:
                logger.error(f"蓝牙连接异常: {e}，{CONFIG['reconnect_interval']}秒后重连...")
                await asyncio.sleep(CONFIG["reconnect_interval"])

    def _parse_varint(self, data, ptr):
        """
        解析 Protobuf varint 编码
        :param data: 数据
        :param ptr: 起始位置
        :return: (值, 新位置)
        """
        val = 0; shift = 0
        while True:
            b = data[ptr]
            val |= (b & 0x7F) << shift
            ptr += 1
            if not (b & 0x80): break
            shift += 7
        return val, ptr

    def _decode_protobuf(self, pb_data):
        """
        解码 Protobuf 数据
        :param pb_data: Protobuf 数据
        :return: 解码后的字段字典
        """
        results = {}
        ptr = 0
        while ptr < len(pb_data):
            try:
                tag = pb_data[ptr]
                field_num = tag >> 3
                wire_type = tag & 0x07
                ptr += 1
                if wire_type == 0:
                    val, ptr = self._parse_varint(pb_data, ptr)
                    results[field_num] = val
                elif wire_type == 2:
                    length, ptr = self._parse_varint(pb_data, ptr)
                    results[field_num] = pb_data[ptr:ptr+length]
                    ptr += length
                else:
                    ptr += 1
            except: break
        return results

    def notification_handler(self, sender, data):
        """
        处理蓝牙通知数据
        :param sender: 发送者
        :param data: 接收到的数据
        """
        if len(data) < 10 or data[0:2] != b'\xa5\xa5':
            return
        
        payload_len = struct.unpack("<H", data[4:6])[0]
        
        payload_end = 6 + payload_len
        
        if len(data) < payload_end:
            return
        
        payload = data[6:payload_end]
        
        if b'\xcf' in payload[:12]:
            return
        
        ff_idx = payload.find(b'\xff')
        if ff_idx == -1:
            return
        
        pb_data = payload[ff_idx + 1:]
        fields = self._decode_protobuf(pb_data)
        
        def to_int(val):
            if isinstance(val, bytearray):
                return int.from_bytes(val, 'little') if len(val) <= 4 else 0
            return int(val) if isinstance(val, (int, float)) else 0
        
        curr_dist = to_int(fields.get(2, 0))
        curr_dur = to_int(fields.get(3, 0))
        
        if curr_dur in (0, 1):
            return
        
        if self.prev_dist is not None and self.prev_dur is not None:
            delta_d = curr_dist - self.prev_dist
            delta_t = curr_dur - self.prev_dur
            
            if delta_t > 0 and delta_d >= 0:
                real_speed = (delta_d / delta_t) * 3.6
                self.last_valid_data["speed"] = round(real_speed, 1)
        
        self.prev_dist = curr_dist
        self.prev_dur = curr_dur
        
        self.last_valid_data["distance"] = curr_dist
        self.last_valid_data["duration"] = curr_dur
        
        current_cadence = 0
        current_power = 0
        
        if 5 in fields:
            self.last_valid_data["resistance"] = to_int(fields[5])
        if 4 in fields:
            self.last_valid_data["calories"] = to_int(fields[4]) / 1.0
        if 8 in fields:
            self.last_valid_data["status"] = to_int(fields[8])
        
        if 6 in fields:
            current_cadence = to_int(fields[6])
        if 7 in fields:
            current_power = to_int(fields[7])
        
        self.last_valid_data["cadence"] = current_cadence
        self.last_valid_data["power"] = current_power
        
        if self.last_valid_data["status"] in [2, 4]:
            self.last_valid_data["cadence"] = 0
            self.last_valid_data["power"] = 0
            self.last_valid_data["speed"] = 0.0

        self.prev_status = self.last_valid_data["status"]

        d = self.last_valid_data
        status_map_print = {1: "准备", 2: "待机", 3: "运动", 4: "停止"}
        status_map_csv = {1: "Ready", 2: "Idle", 3: "Running", 4: "Stopped"}
        status_text = status_map_print.get(d["status"], f"未知({d['status']})")
        status_text_csv = status_map_csv.get(d["status"], f"Unknown({d['status']})")
        
        raw_hex = data.hex()
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        if self.print_enabled:
            logger.debug(f"[{timestamp}] 状态:{status_text:2} | "
                  f"时长:{d['duration']:3d}s | 距离:{d['distance']:5d}m | 速度:{d['speed']:4.1f}km/h | "
                  f"功率:{d['power']:3d}W | 踏频:{d['cadence']:3d}rpm | 阻力:{d['resistance']:2d} | "
                  f"卡路里:{d['calories']:.1f}kcal | HEX: {raw_hex}")
        
        writer = self._get_csv_writer()
        if writer:
            try:
                writer.writerow([
                    timestamp, status_text_csv, d['duration'], d['distance'], d['speed'],
                    d['power'], d['cadence'], d['resistance'], d['calories'], raw_hex
                ])
                self.csv_count += 1
                if self.csv_count % 10 == 0:
                    self.csv_file.flush()
            except:
                pass

    async def start(self):
        """
        启动客户端，连接设备并开始监听数据
        """
        await self.run_client()

if __name__ == "__main__":
    client = BikeClient()
    try:
        asyncio.run(client.start())
    except KeyboardInterrupt:
        logger.info("已停止")
    finally:
        if client.csv_file:
            client.csv_file.close()
