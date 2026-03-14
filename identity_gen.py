import pyshark
import json
import re
import argparse
import os
import sys

def extract_to_auth_json(file_path, output_filename="identity.json"):
    print(f"[*] 正在分析二进制日志: {file_path}")
    
    if not os.path.exists(file_path):
        print(f"\n[!] 错误：找不到文件 '{file_path}'，请检查路径是否正确。")
        sys.exit(1)

    display_filter = 'btatt'
    
    auth_data = {
        "bike_name": "Unknown",
        "bike_mac": "Unknown",
        "client_id": "Unknown", 
        "uuid1": "Unknown", 
        "uuid2": "Unknown",
        "handshake_packets": []
    }

    try:
        cap = pyshark.FileCapture(file_path, display_filter=display_filter, keep_packets=False)
        
        for pkt in cap:
            try:
                src_name = getattr(pkt.bthci_acl, 'src_name', 'Unknown') if hasattr(pkt, 'bthci_acl') else 'Unknown'
                src_mac = getattr(pkt.bthci_acl, 'src_bd_addr', getattr(pkt.bluetooth, 'src', 'Unknown')) if hasattr(pkt, 'bthci_acl') else 'Unknown'
                dst_name = getattr(pkt.bthci_acl, 'dst_name', 'Unknown') if hasattr(pkt, 'bthci_acl') else 'Unknown'
                dst_mac = getattr(pkt.bthci_acl, 'dst_bd_addr', getattr(pkt.bluetooth, 'dst', 'Unknown')) if hasattr(pkt, 'bthci_acl') else 'Unknown'

                is_from_phone = False

                bike_keyword = "Keep"
                if bike_keyword in src_name:
                    auth_data["bike_name"] = src_name
                    auth_data["bike_mac"] = src_mac.upper()
                elif bike_keyword in dst_name:
                    auth_data["bike_name"] = dst_name
                    auth_data["bike_mac"] = dst_mac.upper()
                    is_from_phone = True

                value_hex = getattr(pkt.btatt, 'value', '').replace(':', '').lower()
                
                if value_hex.startswith(('a5a5a000', 'a5a5a001', 'a5a5a002', 'a5a5a003')):
                    current_prefix = value_hex[:8]
                    if not any(packet.startswith(current_prefix) for packet in auth_data["handshake_packets"]):
                        auth_data["handshake_packets"].append(value_hex)
                        auth_data["handshake_packets"].sort(key=lambda x: x[:8])
                
                if "a5a5a0" in value_hex and "2f33" in value_hex:
                    try:
                        ascii_str = bytes.fromhex(value_hex).decode('ascii', errors='ignore')
                        
                        u1 = re.search(r'[a-f0-9]{24}', ascii_str)
                        if u1 and auth_data["uuid1"] == "Unknown": 
                            auth_data["uuid1"] = u1.group(0)
                        
                        temp_str = re.sub(r'[a-f0-9]{24}', '', ascii_str)
                        u2 = re.search(r'[a-f0-9]{16}', temp_str)
                        if u2 and auth_data["uuid2"] == "Unknown": 
                            auth_data["uuid2"] = u2.group(0)
                    except:
                        pass
                
                if is_from_phone and auth_data["client_id"] == "Unknown":
                    if "a5a5a0" in value_hex and "2f31" in value_hex:
                        try:
                            match_client = re.search(r'b33[01]2f31ff([0-9a-f]{32})00', value_hex)
                            if match_client:
                                client_str = bytes.fromhex(match_client.group(1)).decode('ascii', errors='ignore')
                                auth_data["client_id"] = client_str
                        except:
                            pass

            except Exception:
                continue
                
        cap.close()

    except Exception as e:
        print("\n" + "="*60)
        print("[!] 解析失败：文件不符合规范！")
        print("[!] 请确保您提供的是未经修改的原始二进制日志（.btsnoop / .log）。")
        print("[!] 请从安卓设备中重新提取 HCI 日志文件，切勿使用 Wireshark 导出的 txt 文本。")
        print("="*60 + "\n")
        sys.exit(1)

    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(auth_data, f, indent=4, ensure_ascii=False)
    
    print(f"[√] 解析完成！鉴权配置已保存至: {output_filename}")
    
    if auth_data["handshake_packets"]:
        print(f"\n[*] 提取到 {len(auth_data['handshake_packets'])} 个握手包:")
        for i, packet in enumerate(auth_data['handshake_packets']):
            print(f"[{i+1}] {packet}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="动感单车鉴权信息提取工具")
    parser.add_argument("log", help="原始 .btsnoop 或 .pcap 日志路径")
    parser.add_argument("-o", "--output", default="identity.json", help="输出 JSON 文件名")
    args = parser.parse_args()
    
    extract_to_auth_json(args.log, args.output)
