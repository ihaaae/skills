开始学 T4。

[graph.py preflight T4 的输出]
✓ T4 可以讲  [🔓]  阅读：Ilya Grigorik《High Performance Browser Networking》第 2 章 "Building Blocks of TCP" 的 Three-Way Handshake 与 Slow-Start 两节：握手与 slow start 怎样决定新连接的头几个来回
  mode: reading

通往目标（学它有什么用）：
  G1「网页打开慢的时候，网络里在发生什么」：N1 → N2 → T1 → T2 → T3 → T4
    终点要能回答：一次 HTTPS 请求在真正传数据之前要等几个来回？丢包时为什么会突然卡住一下？

允许引用的概念 = 本节点 + 全部 ✅ 节点。
其中本节点的祖先：
  T1   TCP 三次握手：SYN → SYN-ACK → ACK，交换起始 sequence number
  T2   ACK 与重传：接收方用 ACK 告诉发送方收到了哪些字节；超时没收到 ACK 就重发
  T3   RTT（round-trip time）：一个来回的时间；握手要多等一个 RTT

节点列出的主张：
1. 新连接的第一个数据字节至少要等一个 RTT（握手），所以连接复用很重要。
2. slow start：新连接一开始只敢发少量数据，每收到一轮 ACK 就加倍；因此短连接常常还没"跑起来"就结束了。

—— 本节点已有内容 ——
(尚无)
