# 工具目录

按用途分组，文件名保持原名，便于从历史命令和测试记录对应回去。

## 分组

| 目录 | 内容 |
| --- | --- |
| `build_image/` | BK7258 配置准备、CRC16 镜像生成、镜像校验和构建审计 |
| `system/` | 启动顺序、PSRAM、heartbeat、NSH 栈和时间相关检查 |
| `network/` | CP/AP、Wi-Fi profile/reconnect、IPv4、HTTP/HTTPS、TLS、RNG 和 NetApp 检查 |
| `audio/` | 音频寄存器、PCM、WAV、语音和音频诊断检查 |
| `rtsa/` | RTSA ABI、同步、网络、线程、生命周期探针和版本记录 |
| `convoai/` | 对话式 AI 本地控制服务、Token 测试和 HTTP 服务测试 |

## 常用入口

从作品仓根目录执行：

```sh
python3 tools/build_image/make_bk7258_linear_crc_image.py --help
python3 tools/build_image/verify_bk7258_linear_crc_image.py --help
python3 tools/network/test_wifi_profile.py <openvela-root>
python3 tools/audio/test_audio_diag.py nuttx/arch/arm/src/bk7258
python3 tools/rtsa/test_rtsa_sync.py nuttx/arch/arm/src/bk7258
```

音频测试中的公共网络测试辅助代码由 `audio/test_audio_registers.py` 通过相对路径加载；不需要设置本机绝对路径。

这些工具用于构建审计、主机测试或诊断验证。工具输出不能自动替代真机 XTS 证据，真机结果仍需保存到 `evidence/`。
