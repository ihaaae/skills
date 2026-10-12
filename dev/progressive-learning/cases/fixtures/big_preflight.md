开始学 T9。

[graph.py preflight T9 的输出]
✓ T9 可以讲  [🔓]  TCP 拥塞控制：slow start、congestion avoidance、fast retransmit、fast recovery，以及 Reno、CUBIC、BBR 三种算法怎样决定发送速率

通往目标（学它有什么用）：
  G1「网页打开慢的时候，网络里在发生什么」：N1 → N2 → T1 → T2 → T3 → T9
    终点要能回答：一次 HTTPS 请求在真正传数据之前要等几个来回？丢包时为什么会突然卡住一下？

允许引用的概念 = 本节点 + 全部 ✅ 节点；其余一律不可用于讲解、例子、题目答案路径。
其中本节点的祖先（讲解最可能依赖）：
  N1   IP 只负责尽力把 packet 送到对方机器：可能丢、可能乱序、可能重复，发送方不会被告知
  N2   port：同一台机器上用 port 号区分不同程序；一条连接由双方的 IP + port 确定
  T1   TCP 三次握手：SYN → SYN-ACK → ACK，交换起始 sequence number
  T2   ACK 与重传：接收方用 ACK 告诉发送方收到了哪些字节；超时没收到 ACK 就重发
  T3   RTT（round-trip time）：一个来回的时间；握手要多等一个 RTT

—— 本节点已有内容 ——
(尚无)
