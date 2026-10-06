# bitset

一小套位图集合内核：定长位块存储（下标 0 是块 0 的最低位）、并交差三种集合运算、
基数统计、按位扫描迭代、以及只保留非空连续段的稀疏块压缩与还原。只使用 Python
标准库，结果与运行次数无关，也不做任何 I/O。

## 目录

- bitset/core.py 位图集合与稀疏块实现
- tests/test_core.py 行为测试

## 运行测试

在项目根目录（本文件所在目录）执行：

    python3 -m unittest discover -s tests -v

全部用例通过时进程退出码为 0。若系统里没有 `python3`，把命令里的 `python3`
换成 `python` 即可（Windows 上常见）。
