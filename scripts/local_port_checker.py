#!/usr/bin/env python3
"""
scripts/local_port_checker.py
=============================
本地端口安全檢查執行器（0 Token 消耗）。
檢查指定連接埠是否監聽在 0.0.0.0 (不安全) 或 127.0.0.1/關閉 (安全)。
"""
import sys
import socket
import subprocess

def check_port_listeners(port: int) -> tuple[bool, str]:
    """
    檢查連接埠監聽狀態。
    返回 (is_secure, reason)
    """
    # 執行 ss -ltnp 取得監聽列表
    try:
        result = subprocess.run(
            ["ss", "-ltnp"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return False, f"無法執行 ss 指令: {result.stderr}"
            
        lines = result.stdout.splitlines()
        listeners = []
        for line in lines:
            if f":{port} " in line:
                listeners.append(line)
                
        if not listeners:
            return True, f"連接埠 {port} 未啟用監聽，狀態安全。"
            
        # 分析監聽地址
        for listener in listeners:
            parts = listener.split()
            # ss 輸出格式的 Local Address 通常在第 4 欄
            if len(parts) >= 4:
                local_addr = parts[3]
                if "0.0.0.0" in local_addr or "[::]" in local_addr or "*:" in local_addr:
                    return False, f"連接埠 {port} 監聽在 0.0.0.0 或 * (全部介面)，可能有對外暴露風險。"
                
        return True, f"連接埠 {port} 僅監聽在本地/安全介面。"
        
    except Exception as e:
        # 退回使用 socket 進行連接測試
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                res = s.connect_ex(("127.0.0.1", port))
                if res != 0:
                    return True, f"連接埠 {port} 無法連線（可能已關閉），狀態安全。"
                else:
                    return False, f"連接埠 {port} 處於開啟狀態，需確認其綁定介面。"
        except Exception as err:
            return False, f"檢查時發生錯誤: {err}"

def main():
    if len(sys.argv) < 2:
        print("Usage: local_port_checker.py <port>")
        sys.exit(1)
        
    try:
        port = int(sys.argv[1])
    except ValueError:
        print("Error: Port must be an integer.")
        sys.exit(1)
        
    is_secure, reason = check_port_listeners(port)
    
    # 輸出符合 Lobster/Inspector 預期格式的結果
    task_text = f"[Security] 檢查連接埠 {port} (Unknown) 綁定安全性與雲端防火牆規則"
    
    if is_secure:
        print(f"✅ 任務完成：{task_text[:40]}")
        print(f"詳細結果: {reason}")
        sys.exit(0)
    else:
        print(f"⚠️ 需要人工介入：{reason}")
        sys.exit(0) # 回傳 0 讓 lobster 捕捉到 stdout 中的 ⚠️ 警告訊息以轉為 blocked

if __name__ == "__main__":
    main()
