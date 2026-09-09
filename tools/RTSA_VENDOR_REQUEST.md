# R1 OpenVela RTSA port: requested vendor integration materials

Target: R1 BK7258, Cortex-M33 hard-float, OpenVela/NuttX AP with existing
Beken CP. Must retain OpenVela. No project credentials are needed to answer
these SDK porting questions.

Available binaries are librtsa.a, libahpl.a and libagora-cjson.a from
BK7258 agora-iot-sdk, CHANGELOG 1.9.5.7.dbg (2025-06-18), G.722 profile.

Please provide either an OpenVela/NuttX-compatible RTSA package or the
documented portable HAL interfaces/source needed to rebuild libahpl.a:

1. Thread create/exit/identity contracts and error propagation. Current
   k_os_thread_create discards agora_create_thread failures.
2. Message/event-loop wakeup and backpressure behavior, including the
   bk_netif_trigger_loopnetif_msg fallback used after failed lwip_write.
3. Official ABI configuration: short enums, 64-bit time_t, 16-byte timespec,
   8-byte fd_set, mutex/condition storage and allocator ownership.
4. Minimum/recommended heap and stack requirements, callback threading and
   init/fini cancellation guarantees on this G.722 build.
5. R1 full-duplex aud_intf and AEC integration source/portable library with
   microphone/reference channel mapping and supported OpenVela deployment.

Our isolated port currently translates 42 imports and passes host boundary
tests plus Cortex-M33 compilation. It has NOT joined RTC or passed a board
lifecycle test. Please do not interpret this as a request to replace the
OpenVela AP with the vendor FreeRTOS example.
